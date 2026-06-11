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


class WebDesignSpec(BaseModel):
    """web系designer の成果物：ページのデザイン仕様（M8・LPパイプライン）。"""

    overview: str = Field(description="何のページか・誰に向けたページか")
    personality: str = Field(description="ページの性格（例：高級感／親しみ／ミニマル）")
    sections: list[str] = Field(
        default_factory=list,
        description="セクション構成（例：'ヒーロー：店名＋キャッチコピー＋予約CTA'）",
    )
    style_direction: str = Field(
        description="配色・書体・余白の方向性（例：深緑×生成り、見出しはShippori Mincho）"
    )
    notes: str = Field(default="", description="設計上の補足・前提")


class WebImplementationResult(BaseModel):
    """web系implementer の成果物：単一ファイルのHTML（M8・LPパイプライン）。"""

    html: str = Field(description="完全な単一 index.html（CSS/JS内蔵・生のHTMLのみ）")
    how_to_verify: str = Field(
        description="確認方法（例：index.html として保存しブラウザで開く。確認すべき見どころ）"
    )
    design_notes: str = Field(
        default="", description="採用したデザイン判断の要約（性格・配色・書体）"
    )


class AppDesignSpec(BaseModel):
    """フルスタックdesigner の成果物：API＋画面の設計仕様（M8・appパイプライン）。"""

    overview: str = Field(description="何のアプリか・誰が使うか")
    endpoints: list[str] = Field(
        default_factory=list,
        description="APIエンドポイントの一覧（例: 'POST /expenses 収支の登録'）",
    )
    screens: list[str] = Field(
        default_factory=list,
        description="画面の構成（例: '一覧画面：収支をテーブル表示・追加フォーム付き'）",
    )
    style_direction: str = Field(
        default="", description="画面の性格と配色・書体の方向性（web-designスキルの3役）"
    )
    notes: str = Field(default="", description="設計上の補足・前提")


class SecurityFindingItem(BaseModel):
    """security-reviewer の指摘1件（要件 F-15）。ファイルパス・行番号は必須。"""

    severity: str = Field(description='"critical" | "important" | "minor"')
    file_path: str = Field(default="main.py", description="該当ファイル")
    line: int = Field(description="提示されたコードの該当行番号")
    issue: str = Field(description="何が問題か（1〜2文）")
    recommendation: str = Field(default="", description="推奨する直し方（修正コードは書かない）")


class SecurityReviewResult(BaseModel):
    """security-reviewer の成果物：監査レポート（要件 F-15）。

    レビュアーはコードを修正しない（検証役は修正しない原則・F-04）。
    """

    passed: bool = Field(description="critical の指摘が無ければ true")
    findings: list[SecurityFindingItem] = Field(default_factory=list)
    summary: str = Field(description="1行要約。問題がなければ「問題なし」と書く")
