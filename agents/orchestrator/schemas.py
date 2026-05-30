"""Hive のAgent間で受け渡す構造化スキーマ（要件 F-02 / F-03）。

ADK 2.x のグラフでは、各ノードの output_schema / input_schema にこれらを指定し、
ノード間を型付きで受け渡す。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentPlan(BaseModel):
    """router がタスクを解析した結果（要件 F-02）。"""

    agents: list[str] = Field(description="動員するAgent名の一覧")
    reason: str = Field(description="その編成にした理由")
    execution_order: list[str] = Field(description="実行順")
    phase: str = Field(description="Discover / Implement / Verify など")
    scale: str = Field(description='"light" | "heavy"（動員規模）')


class DesignSpec(BaseModel):
    """designer の成果物：設計仕様。"""

    overview: str = Field(description="作るものの概要")
    endpoints: list[str] = Field(
        default_factory=list,
        description="APIエンドポイントの一覧（例: 'POST /tasks タスク作成'）",
    )
    file_structure: list[str] = Field(
        default_factory=list, description="想定するファイル構成"
    )
    notes: str = Field(default="", description="設計上の補足・前提")


class ImplementationResult(BaseModel):
    """implementer の成果物：コード本体（要件 F-03）。"""

    code: str = Field(description="生成したコード本体（単一ファイル想定・M1）")
    file_structure: list[str] = Field(
        default_factory=list, description="生成物のファイル構成"
    )
    how_to_verify: str = Field(
        description="動作確認方法（例: 'uvicorn main:app 後 curl localhost:8000/tasks'）"
    )


class TestResult(BaseModel):
    """tester の成果物：テストコードと実行手順（M1ではまだ実行はしない）。"""

    test_code: str = Field(description="pytest のテストコード")
    how_to_run: str = Field(description="テストの実行方法")
    summary: str = Field(description="何を検証するテストかの要約")
