"""tester Agent（要件 F-03）：実装コードに対する pytest を生成する。

入力：ImplementationResult
出力：TestResult（test_code・how_to_run・summary）
M1ではテストの「生成」までを対象とし、実際の実行（サンドボックス）はM5で追加する。
"""

from __future__ import annotations

from google.adk import Agent

from agents.orchestrator.schemas import TestResult
from shared.models import FLASH, gemini_with_retry
from shared.skills import skill_toolset

def make_tester() -> Agent:
    """tester を生成する。グラフを組むたびに新インスタンスを作る（designer と同じ理由）。"""
    return Agent(
        name="tester",
        model=gemini_with_retry(FLASH),
        description="実装コードに対するpytestテストを生成するテスト担当",
        output_schema=TestResult,
        tools=[skill_toolset("pytest", "python-style")],
        instruction=(
            "あなたはテストエンジニアです。前段(implementer)が出力した実装結果のJSON"
            "（code フィールドに FastAPI のコードが入っている）をテキストで受け取ります。"
            "その code を読み、FastAPI の TestClient を使った pytest を生成してください。\n"
            "- test_code: 主要なCRUD操作（作成→取得→更新→削除）を検証する pytest。"
            "Markdownのコードフェンスで囲まず生のPythonだけを入れる。\n"
            "- how_to_run: テストの実行コマンド（例: 'pytest test_main.py -q'）\n"
            "- summary: 何を検証するテストかを1〜2文で\n"
            "実装に存在しないエンドポイントはテストしないこと。"
        ),
    )


tester_agent = make_tester()
