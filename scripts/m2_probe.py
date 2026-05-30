"""M2 1ホップ確認：RemoteA2aAgent で designer サービスを A2A 越しに呼ぶ。

前提：別プロセスで designer サーバが起動していること
    uv run uvicorn agents.designer.main:app --host localhost --port 8001

実行：
    set -a && source .env && set +a
    uv run python scripts/m2_probe.py
"""

from __future__ import annotations

import asyncio

from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.runners import InMemoryRunner
from google.genai import types

CARD_URL = "http://localhost:8001/.well-known/agent-card.json"
APP_NAME = "hive-m2-probe"
USER_ID = "m2-user"
TASK = "タスク管理のCRUD APIをFastAPIで作って。"


async def main() -> None:
    remote_designer = RemoteA2aAgent(
        name="designer",
        agent_card=CARD_URL,
        description="A2A越しのdesigner",
    )
    runner = InMemoryRunner(agent=remote_designer, app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID
    )
    message = types.Content(role="user", parts=[types.Part(text=TASK)])

    print(f"[task→A2A] {TASK}")
    got = ""
    async for event in runner.run_async(
        user_id=USER_ID, session_id=session.id, new_message=message
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(f"[designer@8001] {part.text.strip()}")
                    got = part.text

    if got:
        print("\n✅ M2 1ホップOK: A2A越しに designer が応答しました。")
    else:
        raise SystemExit("❌ A2A応答が得られませんでした。")


if __name__ == "__main__":
    asyncio.run(main())
