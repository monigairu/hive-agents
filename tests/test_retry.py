"""agents/orchestrator/retry.py（自己修正リトライの純粋ロジック）の単体テスト。"""

from __future__ import annotations

from agents.orchestrator import retry
from agents.orchestrator.retry import build_attempt_message


def test_first_attempt_is_context_plus_task():
    msg = build_attempt_message("教訓\n\n", "APIを作って", attempt=1, feedback="")
    assert msg == "教訓\n\nAPIを作って"


def test_retry_reinjects_goal_and_feedback():
    msg = build_attempt_message("", "APIを作って", attempt=2, feedback="422が出る")
    # 目標（元の発注）が再注入されている
    assert "APIを作って" in msg
    # 試行番号と失敗要因が含まれる
    assert f"2/{retry.MAX_ATTEMPTS}" in msg
    assert "422が出る" in msg


def test_context_is_preserved_on_retry():
    msg = build_attempt_message("過去の教訓\n\n", "LP", attempt=3, feedback="x")
    assert msg.startswith("過去の教訓")
