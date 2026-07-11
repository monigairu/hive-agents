"""shared/sandbox.py の VerificationResult.headline() の単体テスト。"""

from __future__ import annotations

from shared.sandbox import STARTUP_HEADING, VerificationResult, check_selfstart


def test_headline_passed():
    result = VerificationResult(passed=True, returncode=0, output="3 passed in 0.2s")
    assert result.headline() == "全テスト通過"


def test_headline_extracts_error_line():
    output = "test_main.py::test_create FAILED\nE   assert 422 == 201\n1 failed"
    result = VerificationResult(passed=False, returncode=1, output=output)
    assert "assert 422 == 201" in result.headline()


def test_headline_fallback_without_error_line():
    result = VerificationResult(passed=False, returncode=2, output="collected 0 items")
    assert "returncode=2" in result.headline()


# --- check_selfstart（ダブルクリック起動の前提チェック・F-04 v2.11）-------------

_GOOD = (
    "from fastapi import FastAPI\n"
    "app = FastAPI()\n"
    'if __name__ == "__main__":\n'
    "    import uvicorn\n"
    '    uvicorn.run(app, host="127.0.0.1", port=8001)\n'
)


def test_selfstart_accepts_runnable_main():
    assert check_selfstart(_GOOD).passed


def test_selfstart_accepts_single_quoted_guard():
    assert check_selfstart(_GOOD.replace('"__main__"', "'__main__'")).passed


def test_selfstart_rejects_missing_main_block():
    result = check_selfstart("from fastapi import FastAPI\napp = FastAPI()\n")
    assert not result.passed
    assert "__main__" in result.output


def test_selfstart_rejects_wrong_port():
    result = check_selfstart(_GOOD.replace("8001", "8000"))
    assert not result.passed
    assert "8001" in result.output


def test_selfstart_failure_is_recognizable_by_heading():
    """orchestrator が「pytestは通ったが起動チェックが落ちた」を見分けるための目印。

    この目印が無いと、差し戻し理由が pytest の失敗行探索にフォールバックして
    「テスト失敗 (returncode=1)」という誤った表示になる。
    """
    result = check_selfstart("app = 1\n")
    assert STARTUP_HEADING in result.output
    # UI に出る理由は最初の "- " 行（_page_reason と同じ抽出）
    assert result.output.splitlines()[1].startswith("- ")
