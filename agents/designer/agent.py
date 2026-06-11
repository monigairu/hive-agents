"""designer Agent（要件 F-03）：発注内容から API 設計を起こす。

入力：ユーザーのタスク文（str）
出力：DesignSpec（概要・エンドポイント・ファイル構成）
"""

from __future__ import annotations

from google.adk import Agent

from agents.orchestrator.schemas import DesignSpec
from shared.models import FLASH
from shared.skills import skill_toolset

def make_designer() -> Agent:
    """designer を生成する。

    Workflow はAgentインスタンスにモード等の状態を持たせるため、グラフを組むたびに
    新しいインスタンスを作る（使い回すと2つ目以降のグラフ構築で検証エラーになる）。
    """
    return Agent(
        name="designer",
        model=FLASH,
        description="発注内容からAPIの設計仕様（エンドポイント・ファイル構成）を起こす設計担当",
        output_schema=DesignSpec,
        tools=[skill_toolset("api-design")],
        instruction=(
            "あなたはソフトウェア設計者です。与えられた発注内容を読み、"
            "FastAPI で実装する前提の設計仕様を作成してください。\n"
            "- overview: 何を作るかを1〜2文で\n"
            "- endpoints: 必要なHTTPエンドポイントを 'メソッド パス 説明' の形式で列挙\n"
            "- file_structure: 単一ファイル(main.py)で完結する想定で、必要ファイルを列挙\n"
            "- notes: 設計上の前提（データモデル・永続化方針など）\n"
            "CRUD系の発注なら作成/取得(一覧・単体)/更新/削除を漏れなく含めること。"
        ),
    )


designer_agent = make_designer()
