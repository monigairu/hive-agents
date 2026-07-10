"""ブラウザ実行検証（要件 F-04・出荷基準④「開いた瞬間にJSエラーがない」・v2.9）。

生成した単一HTMLアプリを headless ブラウザで実際に開いてJSを実行し、
Uncaught エラー等をコンソールログから機械検出する＝webcheck（構造）に続く
第2の決定論的オラクル。「見た目は揃っているが動かないアプリ」を差し戻せる。

実装方針：
- playwright 等の追加依存を入れず、Playwright配布物の chrome-headless-shell を
  subprocess で直接起動する（`--dump-dom` はJS実行後のDOMを出力し、
  `--enable-logging=stderr` はページのコンソールをstderrに流す）
- ブラウザが見つからない環境では検証をスキップして合格扱いにする
  （構造チェック webcheck は常に効いている。環境が無いだけで全タスクを
  落とすほうが害が大きい）。スキップはoutputに明記して透明性を保つ
- WSL等でChromeの共有ライブラリが不足する場合は、`HIVE_BROWSER_LIB` か
  既定の ~/.cache/hive/chrome-libs に展開したライブラリを LD_LIBRARY_PATH で渡す

結果は sandbox / webcheck と同じ VerificationResult で返し、F-04 の修正ループに乗せる。
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

from shared.sandbox import VerificationResult

# コンソール行（[pid:tid:date:INFO:CONSOLE:行番号] "メッセージ", source: ...）
_CONSOLE_RE = re.compile(r":CONSOLE[:(](?:\d+[)]?)?\]?\s*\"(?P<msg>.*?)\", source:", re.DOTALL)
# 差し戻し対象とするJSエラー（リソース読み込み失敗は除外：Google Fontsのオフライン失敗等で
# 誤検知するため。構文エラー・未定義参照・null参照などコードの欠陥だけを拾う）
_ERROR_PATTERNS = ("Uncaught", "SyntaxError", "ReferenceError", "TypeError", "RangeError")

_DEFAULT_LIB_DIR = Path.home() / ".cache" / "hive" / "chrome-libs" / "usr" / "lib" / "x86_64-linux-gnu"


def find_browser() -> Path | None:
    """chrome-headless-shell の実行ファイルを探す（HIVE_BROWSER_BIN が最優先）。"""
    env_bin = os.environ.get("HIVE_BROWSER_BIN")
    if env_bin:
        p = Path(env_bin)
        return p if p.is_file() else None
    cache = Path.home() / ".cache" / "ms-playwright"
    candidates = sorted(cache.glob("chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"))
    return candidates[-1] if candidates else None


def _browser_env() -> dict[str, str]:
    """ブラウザ起動用の環境変数（不足する共有ライブラリの解決を含む）。"""
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL")}
    lib = os.environ.get("HIVE_BROWSER_LIB") or (
        str(_DEFAULT_LIB_DIR) if _DEFAULT_LIB_DIR.is_dir() else ""
    )
    if lib:
        current = os.environ.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = f"{lib}:{current}" if current else lib
    return env


def _has_visible_content(dom: str) -> bool:
    """描画後のDOMに「見えるもの」があるか（出荷基準・白画面の検出・v2.10）。

    script/style を除いた body に、視覚要素（canvas・button等）か表示テキストが
    あれば良しとする。「JSエラーは無いのに body が空のまま」だけを落とす
    （正当な最小ページを誤って差し戻さない＝誤検知ゼロを優先）。
    """
    m = re.search(r"<body[^>]*>(.*)</body>", dom, re.S | re.I)
    content = m.group(1) if m else ""
    content = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", content, flags=re.S | re.I)
    if re.search(
        r"<(canvas|button|input|select|textarea|table|svg|img|video)\b", content, re.I
    ):
        return True
    text = re.sub(r"<[^>]+>", "", content)
    return bool(re.sub(r"\s+", "", text))


def _console_errors(stderr: str) -> list[str]:
    """stderr のコンソールログからJSエラー行を抜き出す。"""
    errors: list[str] = []
    for m in _CONSOLE_RE.finditer(stderr):
        msg = m.group("msg")
        if any(pat in msg for pat in _ERROR_PATTERNS):
            errors.append(msg[:300])
    return errors


def _run_page(html: str, timeout: int) -> tuple[subprocess.CompletedProcess | None, str]:
    """HTMLを headless ブラウザで1回実行する。

    Returns:
        (実行結果, "") か、実行できなかったときは (None, スキップ/失敗の理由)。
    """
    browser = find_browser()
    if browser is None:
        return None, "skip: chrome-headless-shell 未検出"
    with tempfile.TemporaryDirectory(prefix="hive-runcheck-") as d:
        page = Path(d) / "index.html"
        page.write_text(html, encoding="utf-8")
        cmd = [
            str(browser),
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--enable-logging=stderr",
            "--virtual-time-budget=5000",  # タイマー・初期化を仮想時間で先送りして観測する
            "--dump-dom",
            f"file://{page}",
        ]
        # 連続起動でまれにブラウザの立ち上がりが引っかかるため1回だけやり直す
        # （タイムアウトの誤判定で差し戻すと、無駄な修正ループ＝トークン浪費になる）
        proc = None
        for attempt in (1, 2):
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=timeout, env=_browser_env()
                )
                break
            except subprocess.TimeoutExpired:
                if attempt == 2:
                    return None, f"timeout: ブラウザ実行がTIMEOUT（{timeout}s×2回）"
    if proc.returncode != 0 and not proc.stdout:
        # ブラウザ自体が起動できない（ライブラリ不足等）＝生成物の欠陥ではない
        detail = proc.stderr.strip().splitlines()[-1][:200] if proc.stderr.strip() else "不明"
        return None, f"skip: 起動失敗: {detail}"
    return proc, ""


def check_browser(html: str, timeout: int = 30) -> VerificationResult:
    """HTMLを headless ブラウザで開き、JS実行エラーの有無を機械判定する。"""
    proc, reason = _run_page(html, timeout)
    if proc is None:
        if reason.startswith("timeout:"):
            return VerificationResult(
                passed=False, returncode=-1, output=reason.removeprefix("timeout: ")
            )
        return VerificationResult(
            passed=True,
            returncode=0,
            output=f"ブラウザ実行検証をスキップ（{reason.removeprefix('skip: ')}。構造チェックのみで判定）",
        )
    errors = _console_errors(proc.stderr)
    if errors:
        return VerificationResult(
            passed=False,
            returncode=1,
            output="ブラウザ実行でJSエラーを検出（開いた瞬間に壊れている）:\n"
            + "\n".join(f"- {e}" for e in errors[:10]),
        )
    if not _has_visible_content(proc.stdout):
        return VerificationResult(
            passed=False,
            returncode=1,
            output=(
                "ブラウザ実行でJSエラーは無いが、画面に何も表示されていない（白画面）。\n"
                "- body に見える要素（canvas・button・テキスト等）を描画すること"
            ),
        )
    rendered = len(re.sub(r"\s+", "", proc.stdout))
    return VerificationResult(
        passed=True,
        returncode=0,
        output=f"ブラウザ実行OK（JSエラーなし・描画DOM {rendered}文字）",
    )


def screenshot_mobile(html: str, timeout: int = 30) -> bytes | None:
    """スマホ幅（390x844）でページを実描画したスクリーンショットPNGを返す。

    出荷基準③「スマホで崩れない」の実画面判定（shared/layoutcheck.py）に使う。
    ブラウザが無い・失敗した場合は None（呼び出し側はスキップする）。
    """
    browser = find_browser()
    if browser is None:
        return None
    with tempfile.TemporaryDirectory(prefix="hive-shot-") as d:
        page = Path(d) / "index.html"
        shot = Path(d) / "shot.png"
        page.write_text(html, encoding="utf-8")
        cmd = [
            str(browser),
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--window-size=390,844",
            "--virtual-time-budget=5000",
            f"--screenshot={shot}",
            f"file://{page}",
        ]
        try:
            subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout, env=_browser_env()
            )
        except subprocess.TimeoutExpired:
            return None
        return shot.read_bytes() if shot.is_file() else None


# --- 受け入れ基準のブラウザ実行テスト（F-04・v2.10） --------------------------
# designer が書いた検証スクリプト（hiveAssert の列）をページに注入して実行し、
# 「要求どおり操作できるか」を機械判定する。書くのは設計担当・通すのは実装担当
# ＝「検証役は修正しない」原則と受け入れ基準の上流定義（v2.5）のブラウザ版。

_HARNESS = """
<script>
(function () {
  window.hiveAssert = function (name, cond) {
    console.log((cond ? "HIVE_PASS: " : "HIVE_FAIL: ") + name);
  };
  window.addEventListener("load", function () {
    setTimeout(function () {
      try {
        __HIVE_CHECK__
      } catch (e) {
        console.log("HIVE_FAIL: 検証スクリプトが中断: " + e.message);
      }
      console.log("HIVE_DONE");
    }, 300);
  });
})();
</script>
"""


def _with_harness(html: str, script: str) -> str:
    """検証ハーネス＋スクリプトを </body> の直前に注入する（無ければ末尾）。"""
    harness = _HARNESS.replace("__HIVE_CHECK__", script)
    m = re.search(r"</body>", html, re.I)
    if m:
        return html[: m.start()] + harness + html[m.start():]
    return html + harness


def check_acceptance(html: str, script: str, timeout: int = 30) -> VerificationResult:
    """受け入れ基準の検証スクリプトをブラウザで実行し、合否を機械判定する。

    - HIVE_FAIL が1件でもあれば不合格（どの基準が落ちたかを差し戻しに載せる）
    - HIVE_DONE が出ていなければスクリプトが完走していない＝不合格
    - ブラウザが使えない環境ではスキップ（check_browser と同じフェイルオープン）
    """
    proc, reason = _run_page(_with_harness(html, script), timeout)
    if proc is None:
        if reason.startswith("timeout:"):
            return VerificationResult(
                passed=False, returncode=-1, output=reason.removeprefix("timeout: ")
            )
        return VerificationResult(
            passed=True,
            returncode=0,
            output=f"受け入れ検証をスキップ（{reason.removeprefix('skip: ')}）",
        )
    messages = [m.group("msg") for m in _CONSOLE_RE.finditer(proc.stderr)]
    passes = [m.removeprefix("HIVE_PASS: ") for m in messages if m.startswith("HIVE_PASS: ")]
    fails = [m.removeprefix("HIVE_FAIL: ") for m in messages if m.startswith("HIVE_FAIL: ")]
    done = any(m.startswith("HIVE_DONE") for m in messages)
    if fails:
        return VerificationResult(
            passed=False,
            returncode=1,
            output="受け入れ検証で不合格の基準あり:\n"
            + "\n".join(f"- NG: {f}" for f in fails[:10])
            + (f"\n（合格 {len(passes)}件）" if passes else ""),
        )
    if not done:
        return VerificationResult(
            passed=False,
            returncode=1,
            output="受け入れ検証スクリプトが完走しなかった（ページのloadが完了していない可能性）",
        )
    label = "・".join(passes[:10]) if passes else "検証項目なし"
    return VerificationResult(
        passed=True, returncode=0, output=f"受け入れ検証OK（{len(passes)}件合格: {label}）"
    )
