"""Orchestrator のグラフワークフロー（要件 F-02 / F-03）。

START -> router(Function Node) -> designer -> implementer -> tester

- router は Function ノード（コスト$0・決定論的分岐の土台）
- designer / implementer / tester は LlmAgent ノード
- ノード間は DesignSpec -> ImplementationResult -> TestResult と型付きで受け渡す

M1は直列1本（APIゴールデンパス）。2本目を足すときは route_task を Event(route=...) 化し、
edges を (route_task, {"api": designer, "lp": ...}) の分岐形に切り替える。
"""

from __future__ import annotations

import os

from google.adk import Workflow
from google.adk.agents.base_agent import BaseAgent

from agents.designer.agent import designer_agent
from agents.implementer.agent import implementer_agent
from agents.orchestrator.router import route_task
from agents.tester.agent import tester_agent

# A2Aモード時の各Agentサービスのポート（agents/<name>/main.py の既定と一致）
_A2A_PORTS = {"designer": 8001, "implementer": 8002, "tester": 8003}


def _card_url(name: str) -> str:
    host = os.environ.get(f"{name.upper()}_HOST", "localhost")
    port = os.environ.get(f"{name.upper()}_PORT", str(_A2A_PORTS[name]))
    return f"http://{host}:{port}/.well-known/agent-card.json"


def _node(local_agent: BaseAgent, name: str) -> BaseAgent:
    """HIVE_A2A=1 なら A2A越しの RemoteA2aAgent、それ以外はプロセス内Agentを返す。

    M1（プロセス内）と M2（A2A独立サービス）を同じグラフ定義で切り替える。
    """
    if os.environ.get("HIVE_A2A") == "1":
        # experimental扱いのため遅延import（A2A未使用時は依存を引かない）
        from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

        return RemoteA2aAgent(
            name=name,
            agent_card=_card_url(name),
            description=getattr(local_agent, "description", name),
        )
    return local_agent


def build_workflow() -> Workflow:
    designer = _node(designer_agent, "designer")
    implementer = _node(implementer_agent, "implementer")
    tester = _node(tester_agent, "tester")
    return Workflow(
        name="hive_orchestrator",
        description="自然言語の発注をAPIパイプライン(designer→implementer→tester)で処理する",
        edges=[
            ("START", route_task, designer, implementer, tester),
        ],
    )


root_agent = build_workflow()
