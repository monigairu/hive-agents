"""security-reviewer Agent（要件 F-15・第2層）：生成コードのセキュリティ監査。

入力：行番号付きの実装コード（orchestrator が整形して渡す）
出力：SecurityReviewResult（passed・findings・summary）

設計上の固定事項：
- モデルは必ず Gemini Pro（最上位）を使う。implementer が Flash でも監査側は固定
  （弱いレビュアーは「チェックした」という安心感だけ与えて穴を見逃すため）
- コードを書いた implementer とは別個体・別コンテキストで監査する（レビューの独立性）
- レビュアーはコードを修正しない。報告だけを行い、修正は implementer に差し戻される
- 第1層（shared/security_patterns.py の決定論的パターン検査）とは独立に動き、
  最終判定は orchestrator 側の merge_review() で「どちらかがNGならNG」に合成される
"""

from __future__ import annotations

from google.adk import Agent

from agents.orchestrator.schemas import SecurityReviewResult
from shared.models import PRO
from shared.skills import skill_toolset

_INSTRUCTION = (
    "あなたはセキュリティ監査の専門家です。提示される行番号付きのPython(FastAPI)コードを監査し、"
    "脆弱性を報告してください。チェック観点と深刻度の判定基準は security スキルに従うこと。\n"
    "ルール：\n"
    "- すべての指摘に file_path と line（提示された行番号）を必ず付ける\n"
    "- severity は critical / important / minor のどれかを必ず付ける\n"
    "- 問題がなければ passed=true・findings=[]・summary=「問題なし」と素直に報告する。"
    "「念のため」で問題を発明しない\n"
    "- あなたはコードを修正しない。recommendation には直し方の方針だけを書き、修正コードは書かない\n"
    "- インメモリ永続化・単一ファイル・認証なしのデモCRUD APIという構成自体は欠陥として数えない"
    "（設計に認証要件が無い場合、認証の不存在は最大 minor）"
)

# F-15：監査の品質担保のため、モデルは PRO 固定（make_xxx での差し替えは提供しない）
security_reviewer_agent = Agent(
    name="security_reviewer",
    model=PRO,
    description="生成コードのセキュリティ監査を行い、深刻度付きの指摘を報告する監査担当",
    output_schema=SecurityReviewResult,
    tools=[skill_toolset("security")],
    instruction=_INSTRUCTION,
)
