"""決定論ルータのゴールデン評価（google-adk非依存・隔離環境で実行可能）。

router.classify は LLM を使わないコード分岐（要件 F-02）なので、ゴールデンタスクに対し
種別・規模が安定して正しいことを CI で機械的に保証する＝最も安価な品質ゲート。
実パイプライン（生成物の品質）の採点は run_full_eval.py が担う。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.orchestrator.router import classify, difficulty_rank

_GOLDEN = json.loads((Path(__file__).parent / "golden_tasks.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _GOLDEN["tasks"], ids=lambda c: c["id"])
def test_router_classifies_golden(case):
    decision = classify(case["task"])
    assert decision["task_type"] == case["task_type"]
    assert decision["scale"] == case["scale"]


@pytest.mark.parametrize("case", _GOLDEN["tasks"], ids=lambda c: c["id"])
def test_difficulty_rank_golden(case):
    """討伐ランク（E/C/S・F-02）が発注文から安定して決まることを保証する。"""
    decision = classify(case["task"])
    assert difficulty_rank(decision["task_type"], decision["scale"]) == case["rank"]
