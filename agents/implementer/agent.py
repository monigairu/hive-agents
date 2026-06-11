"""implementer Agent（要件 F-03）：設計仕様から FastAPI コードを生成する。

入力：DesignSpec
出力：ImplementationResult（code・file_structure・how_to_verify）
"""

from __future__ import annotations

from google.adk import Agent

from agents.orchestrator.schemas import ImplementationResult
from shared.models import FLASH
from shared.skills import skill_toolset

_INSTRUCTION = (
    "あなたは実装エンジニアです。前段(designer)が出力した設計仕様のJSON"
    "（overview / endpoints / file_structure / notes を持つ）をテキストで受け取ります。"
    "その設計に基づき FastAPI のコードを生成してください。\n"
    "- code: 単一ファイル(main.py)で完結する、そのまま動くFastAPIコード。"
    "外部DBは使わずインメモリ(dict等)で永続化し、追加依存は fastapi と uvicorn のみ。\n"
    "- file_structure: 生成物のファイル構成（M1は ['main.py'] 想定）\n"
    "- how_to_verify: 起動コマンドと、CRUDを確認できる具体的な curl 例を必ず含める\n"
    "設計のendpointsを全て実装すること。コードはMarkdownのコードフェンスで囲まず、生のPythonだけを code に入れること。"
)


def make_implementer(model: str = FLASH, extra_instruction: str = "") -> Agent:
    """implementer を任意のモデルで生成する。F-13 の交代（Flash→Pro）で model を差し替える。

    extra_instruction: パイプライン固有の追加指示（appモードの責任範囲の限定など）。
    """
    return Agent(
        name="implementer",
        model=model,
        description="設計仕様から動作するFastAPIコードを生成する実装担当",
        output_schema=ImplementationResult,
        tools=[skill_toolset("python-style", "fastapi")],
        instruction=_INSTRUCTION + extra_instruction,
    )


# 既定（Flash）のシングルトン。A2Aサーバ・グラフはこれを使う。
implementer_agent = make_implementer()
