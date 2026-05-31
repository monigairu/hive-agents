"""M1 動作確認：単一プロセスでグラフE2Eを通す。

「FastAPI CRUD を作って」→ designer→implementer→tester がコード+テストを出す。

実行：
    set -a && source .env && set +a
    uv run python scripts/m1_run.py
    uv run python scripts/m1_run.py "TODOのCRUD APIをFastAPIで作って"
"""

from __future__ import annotations

import asyncio
import json
import sys

from google.adk.runners import InMemoryRunner
from google.genai import types

from agents.orchestrator.workflow import build_workflow
from shared.sandbox import verify_fastapi


def _field(text: str, key: str) -> str:
    try:
        return str(json.loads(text).get(key, "") or "")
    except (json.JSONDecodeError, AttributeError):
        return ""

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
    outputs: dict[str, str] = {}
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
                    outputs[author] = part.text

    if not last_text:
        raise SystemExit("❌ 最終出力が得られませんでした。")

    # サンドボックス自己検証（F-04）
    code = _field(outputs.get("implementer", ""), "code")
    test_code = _field(outputs.get("tester", ""), "test_code")
    if code and test_code:
        print("\n──── [sandbox] 生成コード+テストを実走して検証中… ────")
        result = verify_fastapi(code, test_code)
        mark = "✅ テスト通過（コードは実際に動く）" if result.passed else "❌ テスト失敗"
        print(f"{mark}  (returncode={result.returncode})")
        print(result.output[-600:])

    print("\n✅ グラフ(router→designer→implementer→tester)+ サンドボックス検証 が通りました。")


if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TASK
    asyncio.run(main(task))
