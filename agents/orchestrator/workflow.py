"""Orchestrator のグラフワークフロー（要件 F-02 / F-03）。

START -> router(Function Node) -> designer -> implementer -> tester

- router は Function ノード（コスト$0・決定論的分岐の土台）
- designer / implementer / tester は LlmAgent ノード
- ノード間は DesignSpec -> ImplementationResult -> TestResult と型付きで受け渡す

M1は直列1本（APIゴールデンパス）。2本目を足すときは route_task を Event(route=...) 化し、
edges を (route_task, {"api": designer, "lp": ...}) の分岐形に切り替える。
"""

from __future__ import annotations

from google.adk import Workflow

from agents.designer.agent import designer_agent
from agents.implementer.agent import implementer_agent
from agents.orchestrator.router import route_task
from agents.tester.agent import tester_agent


def build_workflow() -> Workflow:
    return Workflow(
        name="hive_orchestrator",
        description="自然言語の発注をAPIパイプライン(designer→implementer→tester)で処理する",
        edges=[
            ("START", route_task, designer_agent, implementer_agent, tester_agent),
        ],
    )


root_agent = build_workflow()
