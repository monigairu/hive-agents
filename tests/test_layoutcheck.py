"""スマホ表示のvision判定（F-04・v2.10）の純粋ロジックのテスト。

LLM呼び出し（check_layout）は対象外。レポート整形と
「レポートのみ＝合否を変えない」前提の文言を固定する。
"""

from shared.layoutcheck import LayoutReport, render_report


def test_render_report_skip():
    assert render_report(None) is None


def test_render_report_ok():
    text = render_report(LayoutReport(broken=False))
    assert "崩れ検出なし" in text


def test_render_report_broken_is_report_only():
    text = render_report(
        LayoutReport(broken=True, issues=["ボタンが画面右にはみ出している"])
    )
    assert "はみ出している" in text
    assert "差し戻しはしない" in text  # レポートのみの約束を文言で明示
