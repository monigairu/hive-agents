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

from agents.designer.agent import make_designer
from agents.implementer.agent import make_implementer
from agents.orchestrator.router import route_task
from agents.tester.agent import make_tester

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


def build_workflow(task_type: str = "api") -> Workflow:
    """タスク種別に応じたパイプラインのグラフを組む（F-02 差し込み式）。

    ルーティング判断は呼び出し側が router.classify で行い（コスト$0・決定論的）、
    ここでは該当する直列パイプラインを返す。
    - api: designer → implementer → tester（A2A切り替え対応）
    - lp : web designer → web implementer（M8。当面プロセス内実行のみ）
    """
    # 注意：グラフのノードは必ず「呼び出しごとに新しいAgentインスタンス」を使う。
    # Workflow はAgentにモード等の状態を持たせるため、インスタンスを複数のグラフで
    # 使い回すと2つ目以降の構築が "mode='chat'" の検証エラーで落ちる。
    if task_type == "app":
        # フルスタック：設計だけapp版に差し替え、実装・テストはAPI版を再利用。
        # frontend（画面担当）はバックエンド検証の通過後に orchestrator が起動する
        from agents.app.agent import make_app_designer, make_app_implementer

        return Workflow(
            name="hive_orchestrator",
            description="自然言語の発注をフルスタック設計→API実装→テストで処理する（画面は後段）",
            edges=[
                ("START", route_task, make_app_designer(), make_app_implementer(), make_tester()),
            ],
        )
    if task_type == "lp":
        # 遅延import：APIパイプラインだけ使う場面で余計な依存を引かない
        from agents.web.agent import make_web_designer, make_web_implementer

        return Workflow(
            name="hive_orchestrator",
            description="自然言語の発注をWebページパイプライン(designer→implementer)で処理する",
            edges=[
                ("START", route_task, make_web_designer(), make_web_implementer()),
            ],
        )
    designer = _node(make_designer(), "designer")
    implementer = _node(make_implementer(), "implementer")
    tester = _node(make_tester(), "tester")
    return Workflow(
        name="hive_orchestrator",
        description="自然言語の発注をAPIパイプライン(designer→implementer→tester)で処理する",
        edges=[
            ("START", route_task, designer, implementer, tester),
        ],
    )


root_agent = build_workflow()
