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


def _console_errors(stderr: str) -> list[str]:
    """stderr のコンソールログからJSエラー行を抜き出す。"""
    errors: list[str] = []
    for m in _CONSOLE_RE.finditer(stderr):
        msg = m.group("msg")
        if any(pat in msg for pat in _ERROR_PATTERNS):
            errors.append(msg[:300])
    return errors


def check_browser(html: str, timeout: int = 30) -> VerificationResult:
    """HTMLを headless ブラウザで開き、JS実行エラーの有無を機械判定する。"""
    browser = find_browser()
    if browser is None:
        return VerificationResult(
            passed=True,
            returncode=0,
            output="ブラウザ実行検証をスキップ（chrome-headless-shell 未検出。構造チェックのみで判定）",
        )
    with tempfile.TemporaryDirectory(prefix="hive-runcheck-") as d:
        page = Path(d) / "index.html"
        page.write_text(html, encoding="utf-8")
        cmd = [
            str(browser),
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--enable-logging=stderr",
            "--virtual-time-budget=3000",  # タイマー・初期化を仮想時間で先送りして観測する
            "--dump-dom",
            f"file://{page}",
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout, env=_browser_env()
            )
        except subprocess.TimeoutExpired:
            return VerificationResult(
                passed=False, returncode=-1, output=f"ブラウザ実行がTIMEOUT（{timeout}s）"
            )
    if proc.returncode != 0 and not proc.stdout:
        # ブラウザ自体が起動できない（ライブラリ不足等）＝生成物の欠陥ではないのでスキップ扱い
        detail = proc.stderr.strip().splitlines()[-1][:200] if proc.stderr.strip() else "不明"
        return VerificationResult(
            passed=True,
            returncode=0,
            output=f"ブラウザ実行検証をスキップ（起動失敗: {detail}）",
        )
    errors = _console_errors(proc.stderr)
    if errors:
        return VerificationResult(
            passed=False,
            returncode=1,
            output="ブラウザ実行でJSエラーを検出（開いた瞬間に壊れている）:\n"
            + "\n".join(f"- {e}" for e in errors[:10]),
        )
    rendered = len(re.sub(r"\s+", "", proc.stdout))
    return VerificationResult(
        passed=True,
        returncode=0,
        output=f"ブラウザ実行OK（JSエラーなし・描画DOM {rendered}文字）",
    )
