"""Orchestrator の HTTP サービス（要件 F-01 / F-14土台・M3a）。

グラフ実行中の「やり取り」を SSE(Server-Sent Events) として配信する。
このイベントストリームが可視化の本体で、タイムライン表示(M3b)も
ドラクエ風描画(M7)も、このストリームを描くだけになる（データと描画の分離）。

起動：
    set -a && source .env && set +a
    uv run uvicorn agents.orchestrator.server:app --host localhost --port 8000

確認：
    curl -N "http://localhost:8000/stream?task=TODOのCRUD APIを作って"
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from google.adk.runners import InMemoryRunner
from google.genai import types
from sse_starlette.sse import EventSourceResponse
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from agents.orchestrator.router import classify
from agents.orchestrator.workflow import build_workflow

APP_NAME = "hive-orchestrator"
DEFAULT_TASK = "タスク管理のCRUD APIをFastAPIで作って"

# Agentの役割を可視化向けにラベル付け（F-14でキャラ職業に対応させる土台）
AGENT_ROLE = {
    "designer": "設計",
    "implementer": "実装",
    "tester": "テスト",
}


def _sse(event_type: str, **payload) -> dict:
    """SSEの1イベントを EventSourceResponse 形式に整える。"""
    return {"event": event_type, "data": json.dumps(payload, ensure_ascii=False)}


async def _run_stream(task: str) -> AsyncIterator[dict]:
    """ワークフローを実行し、進捗を SSE イベントとして逐次 yield する。"""
    yield _sse("task_received", task=task)

    # router（Functionノード相当）の判断を可視化
    decision = classify(task)
    yield _sse("router", task_type=decision["task_type"], scale=decision["scale"])

    workflow = build_workflow()
    runner = InMemoryRunner(agent=workflow, app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id="ui"
    )
    message = types.Content(role="user", parts=[types.Part(text=task)])

    last_author: str | None = None
    try:
        async for event in runner.run_async(
            user_id="ui", session_id=session.id, new_message=message
        ):
            author = getattr(event, "author", None)
            text = ""
            if event.content and event.content.parts:
                text = "".join(p.text for p in event.content.parts if p.text)
            if not author or not text:
                continue
            # 新しいAgentが喋り始めた → 「思考中」演出の起点
            if author != last_author:
                yield _sse("agent_start", agent=author, role=AGENT_ROLE.get(author, ""))
                last_author = author
            yield _sse(
                "agent_output",
                agent=author,
                role=AGENT_ROLE.get(author, ""),
                text=text,
            )
        yield _sse("done")
    except Exception as exc:  # noqa: BLE001 - UIにエラーを流して終了
        yield _sse("error", message=str(exc))


async def stream(request: Request) -> EventSourceResponse:
    task = request.query_params.get("task") or DEFAULT_TASK
    return EventSourceResponse(_run_stream(task))


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "app": APP_NAME})


app = Starlette(
    routes=[
        Route("/", health),
        Route("/stream", stream),
    ],
    middleware=[
        # ローカル開発用：フロント(Next.js :3000)からのアクセスを許可
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ],
)
