"""shared/runcheck.py（ブラウザ実行検証・出荷基準④・v2.9）の単体テスト。

コンソールログの解析は常にテストし、実ブラウザを使うテストは
chrome-headless-shell が見つかる環境でのみ実行する（CIでは自動スキップ）。
"""

from __future__ import annotations

import pytest

from shared.runcheck import _console_errors, check_browser, find_browser

_ERROR_LINE = (
    '[0704/235214.009076:INFO:CONSOLE:2] "Uncaught ReferenceError: undefinedFunction'
    ' is not defined", source: file:///tmp/index.html (2)'
)
_INFO_LINE = '[0704/235213.222997:INFO:CONSOLE:2] "loaded", source: file:///tmp/index.html (2)'


def test_console_errors_detects_uncaught():
    assert _console_errors(_ERROR_LINE)


def test_console_errors_ignores_normal_logs():
    assert not _console_errors(_INFO_LINE)


def test_console_errors_ignores_resource_failures():
    # Google Fonts等の読み込み失敗（オフライン環境）はコードの欠陥ではないので拾わない
    line = '[0704/1:INFO:CONSOLE:0] "Failed to load resource: net::ERR_INTERNET_DISCONNECTED", source: https://fonts.googleapis.com/css2 (0)'
    assert not _console_errors(line)


_OK_HTML = (
    "<!DOCTYPE html><html lang=\"ja\"><head><meta charset=\"utf-8\"><title>ok</title></head>"
    "<body><h1>ok</h1><script>document.body.appendChild(document.createElement('p'))"
    ".textContent='dynamic';</script></body></html>"
)
_BROKEN_HTML = (
    "<!DOCTYPE html><html lang=\"ja\"><head><meta charset=\"utf-8\"><title>ng</title></head>"
    "<body><h1>ng</h1><script>undefinedFunction();</script></body></html>"
)

_needs_browser = pytest.mark.skipif(
    find_browser() is None, reason="chrome-headless-shell が無い環境ではスキップ"
)


def test_check_browser_without_browser_skips_as_pass(monkeypatch):
    monkeypatch.setattr("shared.runcheck.find_browser", lambda: None)
    result = check_browser(_BROKEN_HTML)
    assert result.passed
    assert "スキップ" in result.output


@_needs_browser
def test_check_browser_ok_page_passes():
    result = check_browser(_OK_HTML)
    assert result.passed, result.output


@_needs_browser
def test_check_browser_detects_js_error():
    result = check_browser(_BROKEN_HTML)
    assert not result.passed
    assert "JSエラー" in result.output


# --- 白画面検出（出荷基準・v2.10） ------------------------------------------

from shared.runcheck import _has_visible_content  # noqa: E402

_BLANK_HTML = (
    '<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8"><title>blank</title></head>'
    "<body><script>console.log('loaded but renders nothing');</script></body></html>"
)


def test_visible_content_detects_elements_and_text():
    assert _has_visible_content("<html><body><canvas></canvas></body></html>")
    assert _has_visible_content("<html><body><button>置く</button></body></html>")
    assert _has_visible_content("<html><body><h1>ok</h1></body></html>")


def test_visible_content_rejects_blank_and_script_only():
    assert not _has_visible_content("<html><body></body></html>")
    assert not _has_visible_content("<html><body>   \n  </body></html>")
    assert not _has_visible_content(
        "<html><body><script>const s = 'テキストに見えるがscript内';</script></body></html>"
    )


@_needs_browser
def test_check_browser_detects_blank_screen():
    result = check_browser(_BLANK_HTML)
    assert not result.passed
    assert "白画面" in result.output
