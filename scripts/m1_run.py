"""M1 動作確認：単一プロセスでグラフE2Eを通す。

「FastAPI CRUD を作って」→ designer→implementer→tester がコード+テストを出す。

実行：
    set -a && source .env && set +a
    uv run python scripts/m1_run.py
    uv run python scripts/m1_run.py "TODOのCRUD APIをFastAPIで作って"
"""

from __future__ import annotations

import asyncio
import sys

from google.adk.runners import InMemoryRunner
from google.genai import types

from agents.orchestrator.workflow import build_workflow

APP_NAME = "hive-m1"
USER_ID = "m1-user"
DEFAULT_TASK = "タスク管理のCRUD APIをPythonのFastAPIで作って。タスクの作成・一覧・取得・更新・削除ができること。"


async def main(task: str) -> None:
    workflow = build_workflow()
    runner = InMemoryRunner(agent=workflow, app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID
    )
    message = types.Content(role="user", parts=[types.Part(text=task)])

    print(f"[task] {task}\n")
    last_text = ""
    async for event in runner.run_async(
        user_id=USER_ID, session_id=session.id, new_message=message
    ):
        author = getattr(event, "author", "?")
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(f"\n──── [{author}] ────")
                    print(part.text.strip())
                    last_text = part.text

    if last_text:
        print("\n✅ M1 OK: グラフ(router→designer→implementer→tester)が通りました。")
    else:
        raise SystemExit("❌ 最終出力が得られませんでした。")


if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TASK
    asyncio.run(main(task))
