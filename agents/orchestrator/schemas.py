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


class OrderSpec(BaseModel):
    """発注ゲートの成果物：発注文の解釈＝「クエスト依頼書」（要件 F-01）。

    ワークフロー起動前に発注文を正規化して designer に渡し、
    「AIが発注をどう解釈したか」を order_spec イベントとしてUIに開示する（透明性）。
    トリガー発注（F-01拡張・将来）の「自己完結した発注の原則」と同じ雛形：
    チャット発注では不足を推測で補って assumed に開示し、トリガー発注では
    同じ不足をエラーとして返す使い分けになる。
    """

    what: str = Field(description="何を作るか（1文・発注の言い換え）")
    features: list[str] = Field(
        default_factory=list, description="発注から読み取れる主要機能（3〜6個）"
    )
    success_criteria: list[str] = Field(
        default_factory=list,
        description="発注者自身がブラウザ操作等で確認できる成功条件",
    )
    assumed: list[str] = Field(
        default_factory=list,
        description="発注文に書かれておらず推測で補った重要事項（無ければ空）",
    )


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


class WebAppSpec(BaseModel):
    """webapp designer の成果物：単一HTMLアプリの設計仕様（v2.9・appパイプライン）。"""

    overview: str = Field(description="何のアプリか・誰がどう使うか")
    features: list[str] = Field(
        default_factory=list,
        description="機能一覧。「ユーザーが〜できる」形式で過不足なく（例: '石を置くと相手の石が裏返る'）",
    )
    acceptance_criteria: list[str] = Field(
        default_factory=list,
        description="ブラウザ操作で確認できる受け入れ基準（例: 'リロードしても登録した収支が残っている'）",
    )
    persistence: str = Field(
        default="none",
        description='"localstorage"（ユーザーのデータを保存するアプリ）| "none"（ゲーム等・保存不要）',
    )
    style_direction: str = Field(
        default="", description="画面の性格と配色3役・書体の方向性（web-designスキル）"
    )
    check_script: str = Field(
        default="",
        description=(
            "受け入れ基準をブラウザで機械検証するJavaScript（hiveAssert('基準名', 条件) の列・"
            "F-04 v2.10）。操作する要素は notes に列挙した id で特定する"
        ),
    )
    notes: str = Field(default="", description="設計上の補足（ゲームならルールの要点・検証で使う要素idの一覧等）")


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


class LessonDraft(BaseModel):
    """reflection の成果物：蒸留された教訓の下書き（F-08/F-09・v2.9.1）。

    保存前に write-gate（shared.memory.acceptable_lesson の決定論チェック）を通す。
    transferable=false の下書きは保存しない＝「無理に教訓を作らない」を構造で強制する。
    """

    transferable: bool = Field(
        description="同種タスク全般に転用できる一般則が読み取れたら true。このタスク限りの事情しか無ければ false"
    )
    title: str = Field(description="どの状況の教訓かがわかる短い見出し（40字以内）")
    lesson: str = Field(
        description="次回に再利用できる教訓を1文で（200字以内・改行なし・アプリ名等の固有名詞なし）"
    )


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
