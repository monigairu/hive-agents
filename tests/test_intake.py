"""発注ゲート（要件 F-01）の純粋ロジックのテスト。

make_intake（LLM呼び出し）は対象外。parse_order のフェイルオープン
（壊れた出力→None→原文で続行）と、render_order の依頼書組み立てを固定する。
"""

from agents.orchestrator.intake import parse_order, render_order
from agents.orchestrator.schemas import OrderSpec

_VALID = (
    '{"what": "ブラウザで遊べるオセロ", '
    '"features": ["石を置くと相手の石が裏返る", "勝敗を表示する"], '
    '"success_criteria": ["合法手のみ置ける"], '
    '"assumed": ["盤は8x8"]}'
)


def test_parse_order_valid():
    spec = parse_order(_VALID)
    assert spec is not None
    assert spec.what == "ブラウザで遊べるオセロ"
    assert spec.assumed == ["盤は8x8"]


def test_parse_order_fails_open():
    # 出力が無い・JSONでない・スキーマ違反・what空 → すべて None（原文で続行）
    assert parse_order(None) is None
    assert parse_order("") is None
    assert parse_order("JSONではないテキスト") is None
    assert parse_order('{"features": "リストでなく文字列"}') is None
    assert parse_order('{"what": "   "}') is None


def test_render_order_includes_sections():
    text = render_order(parse_order(_VALID))
    assert "[クエスト依頼書（発注の解釈）]" in text
    assert "作るもの: ブラウザで遊べるオセロ" in text
    assert "主要機能: 石を置くと相手の石が裏返る / 勝敗を表示する" in text
    assert "成功条件: 合法手のみ置ける" in text
    assert "推測で補った点: 盤は8x8" in text
    # 依頼書の直後に発注の原文が続く前提（server.py が原文を連結する）
    assert text.endswith("[発注の原文]\n")


def test_render_order_omits_empty_sections():
    text = render_order(OrderSpec(what="クイズアプリ"))
    assert "作るもの: クイズアプリ" in text
    assert "主要機能" not in text
    assert "成功条件" not in text
    assert "推測で補った点" not in text
