"""スマホ表示の実画面判定（要件 F-04・出荷基準③「スマホで崩れない」・v2.10）。

これまで③は viewport タグ等の構造チェックのみ＝実際の見た目は誰も見ていなかった。
スマホ幅で実描画したスクリーンショットを Gemini（画像入力・Flash・思考MINIMAL）に
渡し、**レイアウトの崩れだけ**を判定させる。

設計方針：
- LLM審判だが対象を「崩れ」に限定する（ロジックの正しさ・デザインの好みは判定させない）
- **レポートのみ＝差し戻しには使わない**。審判のブレで無駄な修正ループ
  （トークン浪費）を作らないため。実績を見て将来ゲート化を判断する
- 失敗（ブラウザ無し・認証無し・API不調）はすべて None＝黙ってスキップ（フェイルオープン）
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from shared.runcheck import screenshot_mobile

_PROMPT = (
    "これはスマホ幅(390px)で表示したWebアプリのスクリーンショットです。"
    "レイアウトの崩れだけを判定してください：\n"
    "- 画面外へのはみ出し・横スクロールが必要な要素\n"
    "- 要素同士の重なり・文字の見切れ\n"
    "- 小さすぎて押せないボタン\n"
    "機能の良し悪しやデザインの好みは判定しないこと。\n"
    "注意：検証環境に日本語フォントが無いため、文字が □（豆腐）に見えることがある。"
    "文字化け・豆腐・フォントの見た目は判定対象外とすること。崩れが無ければ broken=false。"
)


class LayoutReport(BaseModel):
    """vision審判の出力（崩れの有無と指摘一覧）。"""

    broken: bool = Field(description="明確なレイアウト崩れがあれば true")
    issues: list[str] = Field(default_factory=list, description="崩れの指摘（1件1文・最大5件）")


def render_report(report: LayoutReport | None) -> str | None:
    """判定結果を verify 出力に足す1ブロックの文にする（None はスキップ＝何も足さない）。"""
    if report is None:
        return None
    if not report.broken:
        return "スマホ表示チェックOK（390px幅の実画面で崩れ検出なし）"
    lines = "\n".join(f"- {i}" for i in report.issues[:5])
    return f"📱 スマホ表示の気になる点（参考・自動判定のため差し戻しはしない）:\n{lines}"


def check_layout(html: str) -> str | None:
    """スマホ実画面のスクリーンショットをGeminiで判定し、報告文を返す（不調なら None）。"""
    png = screenshot_mobile(html)
    if png is None:
        return None
    try:
        # google-genai は遅延import（tests/ の隔離実行を保つため）
        from google import genai
        from google.genai import types

        from shared.models import FLASH

        client = genai.Client()
        resp = client.models.generate_content(
            model=FLASH,
            contents=[types.Part.from_bytes(data=png, mime_type="image/png"), _PROMPT],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=LayoutReport,
                thinking_config=types.ThinkingConfig(thinking_level="MINIMAL"),
            ),
        )
        report = LayoutReport.model_validate_json(resp.text or "")
    except Exception:  # noqa: BLE001 - 審判の不調はスキップに倒す（本体を壊さない）
        return None
    return render_report(report)
