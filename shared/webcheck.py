"""Webページの決定論的検証（要件 F-02/F-04 複数タスク対応・M8）。

APIにおけるサンドボックス(pytest)に相当する、LPパイプライン用のオラクル。
「良いデザインか」は機械判定できないが、「壊れていないページか」は判定できる：
構造の妥当性・必須要素・プレースホルダ残り・リンク切れ・外部画像依存を
標準ライブラリのみで機械チェックする（コスト$0・決定論的）。

結果は sandbox と同じ VerificationResult で返し、F-04 の修正ループにそのまま乗せる。
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

from shared.sandbox import VerificationResult

# 実コンテンツを書かずに残されがちなプレースホルダ
_PLACEHOLDERS = ("lorem ipsum", "ここにテキスト", "サンプルテキスト", "placeholder")
# アプリ用：入力欄の placeholder= はHTML属性として正当（良いUX）なので文言だけを見る
_APP_PLACEHOLDERS = ("lorem ipsum", "ここにテキスト", "サンプルテキスト")
# 外部画像・プレースホルダ画像サービス（単一ファイル原則違反＝表示崩れの元）
_EXTERNAL_IMG = re.compile(r"<img[^>]+src=[\"']https?://", re.IGNORECASE)


class _PageScan(HTMLParser):
    """タグ・id・アンカー・タイトル・本文量を収集する。"""

    def __init__(self) -> None:
        super().__init__()
        self.tags: set[str] = set()
        self.h1_count = 0
        self.ids: set[str] = set()
        self.anchors: list[str] = []
        self.has_viewport = False
        self.title = ""
        self._in_title = False
        self.text_len = 0
        self._skip_text = 0  # style/script 内はテキストに数えない

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.add(tag)
        a = dict(attrs)
        if tag == "h1":
            self.h1_count += 1
        if a.get("id"):
            self.ids.add(str(a["id"]))
        if tag == "a" and (a.get("href") or "").startswith("#"):
            self.anchors.append(str(a["href"])[1:])
        if tag == "meta" and a.get("name") == "viewport":
            self.has_viewport = True
        if tag == "title":
            self._in_title = True
        if tag in ("style", "script"):
            self._skip_text += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in ("style", "script") and self._skip_text:
            self._skip_text -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data.strip()
        elif not self._skip_text:
            self.text_len += len(data.strip())


def check_web(html: str) -> VerificationResult:
    """単一ファイルHTMLを機械チェックし、合否と指摘一覧を返す。"""
    problems: list[str] = []
    stripped = (html or "").strip()
    if not stripped:
        return VerificationResult(passed=False, returncode=1, output="HTMLが空")

    scan = _PageScan()
    scan.feed(stripped)

    if not stripped.lower().startswith("<!doctype html"):
        problems.append("<!DOCTYPE html> で始まっていない")
    for required in ("html", "head", "body"):
        if required not in scan.tags:
            problems.append(f"<{required}> タグがない")
    if not scan.title:
        problems.append("<title> が空または無い")
    if not scan.has_viewport:
        problems.append('<meta name="viewport"> が無い（モバイル対応の必須要素）')
    if scan.h1_count != 1:
        problems.append(f"h1 は1つにする（現在 {scan.h1_count} 個）")
    if "style" not in scan.tags and "link" not in scan.tags:
        problems.append("CSSが無い（<style> 内蔵が原則）")
    if scan.text_len < 200:
        problems.append(f"本文テキストが少なすぎる（{scan.text_len}文字）。実コンテンツを書くこと")
    lowered = stripped.lower()
    for ph in _PLACEHOLDERS:
        if ph in lowered:
            problems.append(f"プレースホルダ「{ph}」が残っている。実物のコピーに置き換えること")
    for anchor in scan.anchors:
        if anchor and anchor not in scan.ids:
            problems.append(f'ページ内リンク "#{anchor}" の飛び先 id が存在しない（リンク切れ）')
    if _EXTERNAL_IMG.search(stripped):
        problems.append("外部画像URLに依存している。CSS/インラインSVGで表現すること")

    if problems:
        output = "ページ検証で以下の問題を検出:\n" + "\n".join(f"- {p}" for p in problems)
        return VerificationResult(passed=False, returncode=1, output=output)
    return VerificationResult(
        passed=True, returncode=0, output=f"ページ検証OK（本文{scan.text_len}文字・id {len(scan.ids)}個）"
    )


def check_app(html: str, persistence: str = "none") -> VerificationResult:
    """単一HTMLアプリの構造チェック（appパイプライン・出荷基準①②③の機械判定・v2.9）。

    LP向け check_web と違い、本文はJSが描画するため文字数・実コンテンツは要求しない。
    代わりにアプリの成立条件（scriptがある・宣言どおりlocalStorage永続化がある）を見る。
    JS実行時エラーの検出は runcheck.check_browser（出荷基準④）が担う。
    """
    problems: list[str] = []
    stripped = (html or "").strip()
    if not stripped:
        return VerificationResult(passed=False, returncode=1, output="HTMLが空")

    scan = _PageScan()
    scan.feed(stripped)

    if not stripped.lower().startswith("<!doctype html"):
        problems.append("<!DOCTYPE html> で始まっていない")
    for required in ("html", "head", "body"):
        if required not in scan.tags:
            problems.append(f"<{required}> タグがない")
    if not scan.title:
        problems.append("<title> が空または無い")
    if not scan.has_viewport:
        problems.append('<meta name="viewport"> が無い（スマホ対応＝出荷基準の必須要素）')
    if "script" not in scan.tags:
        problems.append("<script> が無い（アプリとして動作しない）")
    if "style" not in scan.tags and "link" not in scan.tags:
        problems.append("CSSが無い（<style> 内蔵が原則）")
    lowered = stripped.lower()
    for ph in _APP_PLACEHOLDERS:
        if ph in lowered:
            problems.append(f"プレースホルダ「{ph}」が残っている。実物の文言に置き換えること")
    if _EXTERNAL_IMG.search(stripped):
        problems.append("外部画像URLに依存している。CSS/インラインSVGで表現すること")
    if persistence == "localstorage" and "localstorage" not in lowered:
        problems.append(
            "設計は localStorage 永続化を宣言しているのに実装に localStorage が無い"
            "（リロードでデータが消える＝出荷基準違反）"
        )

    if problems:
        output = "アプリ構造チェックで以下の問題を検出:\n" + "\n".join(f"- {p}" for p in problems)
        return VerificationResult(passed=False, returncode=1, output=output)
    return VerificationResult(
        passed=True, returncode=0, output="アプリ構造チェックOK（構成・viewport・script・永続化）"
    )


_PATH_RE = re.compile(r"/[A-Za-z0-9_\-{}/]+")


def check_frontend(html: str, endpoints: list[str]) -> VerificationResult:
    """フルスタックの画面(index.html)を検証する（appパイプライン・M8）。

    check_web の全チェックに加えて、
    - 契約チェック：実装済みAPIのエンドポイント（契約）のパスを参照しているか
      （F-03「前段出力＝契約」。画面がAPIを呼んでいなければアプリとして成立しない）
    """
    base = check_web(html)
    problems = []
    paths = [m.group(0) for ep in endpoints for m in [_PATH_RE.search(ep)] if m]
    # "/expenses/{id}" → "/expenses" のように、パスパラメータ前の固定部分で照合する
    prefixes = [p for p in (path.split("{")[0].rstrip("/") for path in paths) if p]
    if prefixes and not any(prefix in html for prefix in prefixes):
        problems.append(
            "契約違反: 実装済みAPIのエンドポイント（"
            + ", ".join(paths[:5])
            + "）がHTML内で参照されていない。fetch で契約どおりのパスを呼ぶこと"
        )
    if not base.passed:
        return VerificationResult(
            passed=False,
            returncode=1,
            output=base.output + ("\n- " + "\n- ".join(problems) if problems else ""),
        )
    if problems:
        return VerificationResult(
            passed=False, returncode=1,
            output="画面検証で以下の問題を検出:\n" + "\n".join(f"- {p}" for p in problems),
        )
    return VerificationResult(
        passed=True, returncode=0, output=base.output + "・API契約の参照OK"
    )
