"""決定論ルータのゴールデン評価（google-adk非依存・隔離環境で実行可能）。

router.classify は LLM を使わないコード分岐（要件 F-02）なので、ゴールデンタスクに対し
種別・規模が安定して正しいことを CI で機械的に保証する＝最も安価な品質ゲート。
実パイプライン（生成物の品質）の採点は run_full_eval.py が担う。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.orchestrator.router import (
    classify,
    difficulty_rank,
    rank_reasons,
    thinking_level,
)

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


def test_difficulty_rank_uses_feature_count():
    """依頼書（F-01）の機能数が討伐ランクに加点される（F-02・v2.10）。"""
    assert difficulty_rank("app", "light", 5) == "E"  # 6個未満は加点なし
    assert difficulty_rank("app", "light", 6) == "C"
    assert difficulty_rank("fullstack", "heavy", 6) == "S"  # 3点以上もS
    assert rank_reasons("app", "light", 0) == []  # 受付失敗時は従来判定と同じ
    assert rank_reasons("app", "light", 7) == ["機能が多い（7個）"]


def test_thinking_level_mapping():
    """討伐ランク→思考レベル（F-02・v2.10）：むずかしいほど深く考える対応を固定する。"""
    assert thinking_level("E") == "LOW"
    assert thinking_level("C") == "MEDIUM"
    assert thinking_level("S") == "HIGH"
    assert thinking_level("?") == "MEDIUM"  # 未知ランクは中庸に倒す
