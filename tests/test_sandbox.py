"""shared/sandbox.py の VerificationResult.headline() / count_passed() の単体テスト。"""

from __future__ import annotations

from shared.sandbox import VerificationResult, count_passed


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


def test_count_passed_extracts_number():
    assert count_passed("4 passed in 0.3s") == 4
    assert count_passed("3 passed, 1 failed in 0.5s") == 3


def test_count_passed_zero_when_absent():
    assert count_passed("collection error") == 0
