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


def build_workflow(
    task_type: str = "api",
    designer_model: str | None = None,
    implementer_model: str | None = None,
    thinking: str | None = None,
) -> Workflow:
    """タスク種別に応じたパイプラインのグラフを組む（F-02 差し込み式）。

    ルーティング判断は呼び出し側が router.classify で行い（コスト$0・決定論的）、
    モデルは品質レベル（F-02：ユーザー選択＋自動判定）に応じて差し替える。
    thinking は討伐ランク連動の思考レベル（router.thinking_level）。designer /
    implementer に設定する（A2Aモードのノードはリモート側の既定が使われる）。
    - app: webapp designer → webapp implementer（既定・v2.9。ブラウザ完結の単一HTMLアプリ）
    - api: designer → implementer → tester（A2A切り替え対応）
    - lp : web designer → web implementer（M8。当面プロセス内実行のみ）
    - fullstack: designer → {implementer → tester ∥ frontend} → join
      （API班と画面班の並列・v2.11。画面の検証と差し戻しは orchestrator が後段で行う）
    """
    from shared.models import FLASH, with_thinking

    d_model = designer_model or FLASH
    i_model = implementer_model or FLASH

    def _t(agent):
        """このクエストの思考レベルをAgentに適用する（None なら素通し）。"""
        return with_thinking(agent, thinking)
    # 注意：グラフのノードは必ず「呼び出しごとに新しいAgentインスタンス」を使う。
    # Workflow はAgentにモード等の状態を持たせるため、インスタンスを複数のグラフで
    # 使い回すと2つ目以降の構築が "mode='chat'" の検証エラーで落ちる。
    if task_type == "app":
        from agents.webapp.agent import make_webapp_designer, make_webapp_implementer

        return Workflow(
            name="hive_orchestrator",
            description="自然言語の発注を単一HTMLアプリパイプライン(designer→implementer)で処理する",
            edges=[
                (
                    "START",
                    route_task,
                    _t(make_webapp_designer(d_model)),
                    _t(make_webapp_implementer(i_model)),
                ),
            ],
        )
    if task_type == "fullstack":
        # 並列ファンアウト（F-03 Phase 2・v2.11）：設計書が出た瞬間に
        # API班（implementer→tester）と画面班（frontend）が同時に働く。
        # 画面はAPIの完成を待たず、設計の endpoints（契約）だけを頼りに作る
        # ＝「前段出力＝契約」の原則がそのままグラフの形になっている。
        # JoinNode は両班の完了を待つ合流点（Workflowは終端ノードを1つしか
        # 許さないため必須。実測で確認済み）
        from google.adk.workflow import JoinNode

        from agents.app.agent import make_app_designer, make_app_implementer, make_frontend

        designer = _t(make_app_designer(d_model))
        join = JoinNode(name="join", description="API班と画面班の合流点")
        return Workflow(
            name="hive_orchestrator",
            description="自然言語の発注をフルスタック（API班∥画面班の並列）で処理する",
            edges=[
                ("START", route_task, designer, _t(make_app_implementer(i_model)), make_tester(), join),
                (designer, _t(make_frontend(i_model)), join),
            ],
        )
    if task_type == "lp":
        # 遅延import：APIパイプラインだけ使う場面で余計な依存を引かない
        from agents.web.agent import make_web_designer, make_web_implementer

        return Workflow(
            name="hive_orchestrator",
            description="自然言語の発注をWebページパイプライン(designer→implementer)で処理する",
            edges=[
                ("START", route_task, _t(make_web_designer(d_model)), _t(make_web_implementer(i_model))),
            ],
        )
    designer = _node(_t(make_designer(d_model)), "designer")
    implementer = _node(_t(make_implementer(i_model)), "implementer")
    tester = _node(make_tester(), "tester")
    return Workflow(
        name="hive_orchestrator",
        description="自然言語の発注をAPIパイプライン(designer→implementer→tester)で処理する",
        edges=[
            ("START", route_task, designer, implementer, tester),
        ],
    )


root_agent = build_workflow()
