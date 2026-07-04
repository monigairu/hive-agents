"""shared/webcheck.py（LPパイプラインの決定論的検証）の単体テスト。"""

from __future__ import annotations

from shared.webcheck import check_web

_BODY_COPY = "自家焙煎の豆を使ったコーヒーと、毎朝焼き上げる自家製スイーツをご用意しています。" * 5

GOOD_PAGE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>喫茶ひだまり</title>
<style>body { font-family: sans-serif; }</style>
</head>
<body>
<header><h1>喫茶ひだまり</h1><a href="#menu">メニューを見る</a></header>
<main>
<section id="menu">
<h2>こだわりのメニュー</h2>
<p>""" + _BODY_COPY + """</p>
</section>
</main>
<footer><p>東京都どこか区ひだまり町1-2-3</p></footer>
</body>
</html>"""


def test_good_page_passes():
    result = check_web(GOOD_PAGE)
    assert result.passed, result.output


def test_empty_html_fails():
    assert not check_web("").passed


def test_missing_doctype_and_viewport():
    result = check_web("<html><head><title>t</title></head><body><h1>x</h1></body></html>")
    assert not result.passed
    assert "DOCTYPE" in result.output
    assert "viewport" in result.output


def test_placeholder_text_fails():
    bad = GOOD_PAGE.replace("自家焙煎の豆", "ここにテキストが入ります 自家焙煎の豆")
    result = check_web(bad)
    assert not result.passed
    assert "プレースホルダ" in result.output


def test_broken_anchor_fails():
    bad = GOOD_PAGE.replace('href="#menu"', 'href="#access"')
    result = check_web(bad)
    assert not result.passed
    assert "#access" in result.output


def test_external_image_fails():
    bad = GOOD_PAGE.replace(
        "<header>", '<header><img src="https://placehold.co/600x400">'
    )
    result = check_web(bad)
    assert not result.passed
    assert "外部画像" in result.output


def test_multiple_h1_fails():
    bad = GOOD_PAGE.replace("<h2>こだわりのメニュー</h2>", "<h1>こだわりのメニュー</h1>")
    result = check_web(bad)
    assert not result.passed
    assert "h1" in result.output


def test_thin_content_fails():
    thin = GOOD_PAGE.split("<p>")[0] + "<p>短い</p></section></main></body></html>"
    result = check_web(thin)
    assert not result.passed
    assert "本文テキスト" in result.output


# --- check_frontend（フルスタックの契約チェック）---

from shared.webcheck import check_frontend  # noqa: E402

_ENDPOINTS = ["POST /expenses 収支の登録", "GET /expenses 一覧取得", "DELETE /expenses/{id} 削除"]


def _page_with_fetch(path: str) -> str:
    script = '<script>fetch("http://localhost:8000' + path + '")</script>'
    return GOOD_PAGE.replace("</body>", script + "</body>")


def test_frontend_with_contract_reference_passes():
    result = check_frontend(_page_with_fetch("/expenses"), _ENDPOINTS)
    assert result.passed, result.output


def test_frontend_without_contract_reference_fails():
    result = check_frontend(GOOD_PAGE, _ENDPOINTS)
    assert not result.passed
    assert "契約違反" in result.output


def test_frontend_path_param_prefix_matches():
    result = check_frontend(_page_with_fetch("/expenses/1"), _ENDPOINTS)
    assert result.passed, result.output


def test_frontend_no_endpoints_means_no_contract_check():
    result = check_frontend(GOOD_PAGE, [])
    assert result.passed


# --- check_app（単一HTMLアプリの構造チェック・出荷基準・v2.9）---

from shared.webcheck import check_app  # noqa: E402

GOOD_APP = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>かけいぼ</title>
<style>body { font-family: sans-serif; }</style>
</head>
<body>
<h1>かけいぼ</h1>
<main id="app"></main>
<script>
"use strict";
const KEY = "kakeibo.v1";
let state = [];
try { state = JSON.parse(localStorage.getItem(KEY)) || []; } catch (e) { state = []; }
document.getElementById("app").textContent = state.length + "件の記録";
</script>
</body>
</html>"""


def test_good_app_passes():
    result = check_app(GOOD_APP, "localstorage")
    assert result.passed, result.output


def test_app_without_script_fails():
    bad = GOOD_APP[: GOOD_APP.index("<script>")] + "</body></html>"
    result = check_app(bad)
    assert not result.passed
    assert "script" in result.output


def test_app_missing_declared_persistence_fails():
    bad = GOOD_APP.replace("localStorage", "sessionStorage")
    result = check_app(bad, "localstorage")
    assert not result.passed
    assert "localStorage" in result.output


def test_app_persistence_none_does_not_require_localstorage():
    game = GOOD_APP.replace("localStorage", "sessionStorage")
    result = check_app(game, "none")
    assert result.passed, result.output


def test_app_does_not_require_long_text():
    # ゲーム等は本文がJS描画のため、LPと違い静的な文字数を要求しない
    result = check_app(GOOD_APP, "none")
    assert result.passed, result.output


def test_app_without_viewport_fails():
    bad = GOOD_APP.replace('<meta name="viewport" content="width=device-width, initial-scale=1">', "")
    result = check_app(bad)
    assert not result.passed
    assert "viewport" in result.output


def test_app_input_placeholder_attribute_is_allowed():
    # 入力欄の placeholder= はHTML属性として正当（LP向けの文言チェックと混同しない）
    with_form = GOOD_APP.replace(
        '<main id="app"></main>',
        '<main id="app"><input type="text" placeholder="例: 食費 500円"></main>',
    )
    result = check_app(with_form, "localstorage")
    assert result.passed, result.output


def test_app_placeholder_text_still_fails():
    bad = GOOD_APP.replace('<main id="app"></main>', "<main>ここにテキストが入ります</main>")
    result = check_app(bad)
    assert not result.passed
    assert "プレースホルダ" in result.output
