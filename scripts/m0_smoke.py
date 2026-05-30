"""M0 動作確認スクリプト。

目的：ADK 2.1 の LlmAgent が Vertex AI 経由で Gemini を呼べることを、
ローカルで最小構成（InMemoryRunner）で確認する。

実行：
    set -a && source .env && set +a
    uv run python scripts/m0_smoke.py
"""

import asyncio
import os

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types

APP_NAME = "hive-m0-smoke"
USER_ID = "smoke-user"
FLASH = os.environ.get("HIVE_MODEL_FLASH", "gemini-3-flash-preview")


def build_agent() -> LlmAgent:
    return LlmAgent(
        name="smoke_agent",
        model=FLASH,
        description="M0 接続確認用のエージェント",
        instruction=(
            "あなたは Hive の動作確認用エージェントです。"
            "日本語で1〜2文だけ簡潔に答えてください。"
        ),
    )


async def main() -> None:
    print(f"[config] project={os.environ.get('GOOGLE_CLOUD_PROJECT')} "
          f"location={os.environ.get('GOOGLE_CLOUD_LOCATION')} "
          f"vertexai={os.environ.get('GOOGLE_GENAI_USE_VERTEXAI')} model={FLASH}")

    runner = InMemoryRunner(agent=build_agent(), app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID
    )

    prompt = "あなたは何のモデルですか？ 一文で自己紹介してください。"
    message = types.Content(role="user", parts=[types.Part(text=prompt)])

    print(f"[user] {prompt}")
    answered = False
    async for event in runner.run_async(
        user_id=USER_ID, session_id=session.id, new_message=message
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(f"[agent] {part.text.strip()}")
                    answered = True

    if answered:
        print("\n✅ M0 OK: ADK 2.1 から Gemini への呼び出しに成功しました。")
    else:
        raise SystemExit("❌ 応答テキストが得られませんでした。")


if __name__ == "__main__":
    asyncio.run(main())
