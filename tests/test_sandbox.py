"""shared/sandbox.py の VerificationResult.headline() の単体テスト。"""

from __future__ import annotations

from shared.sandbox import VerificationResult


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
