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

import asyncio
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

from agents.orchestrator.retry import MAX_ATTEMPTS, build_attempt_message
from agents.orchestrator.router import classify
from agents.orchestrator.workflow import build_workflow
from shared.memory import ReasoningBank, render_memories
from shared.sandbox import VerificationResult, verify_fastapi
from shared.telemetry import agent_span, setup_tracing


def _field(json_text: str | None, key: str) -> str:
    """Agent出力のJSONテキストから1フィールドを安全に取り出す。"""
    if not json_text:
        return ""
    try:
        return str(json.loads(json_text).get(key, "") or "")
    except (json.JSONDecodeError, AttributeError):
        return ""

APP_NAME = "hive-orchestrator"
DEFAULT_TASK = "タスク管理のCRUD APIをFastAPIで作って"

# Agentの役割を可視化向けにラベル付け（F-14でキャラ職業に対応させる土台）
AGENT_ROLE = {
    "designer": "設計",
    "implementer": "実装",
    "tester": "テスト",
}

# 経験の蓄積（F-08/F-09）と標準トレース（F-14）はプロセス全体で1つ持つ
_bank = ReasoningBank()
setup_tracing(APP_NAME)


def _sse(event_type: str, **payload) -> dict:
    """SSEの1イベントを EventSourceResponse 形式に整える。"""
    return {"event": event_type, "data": json.dumps(payload, ensure_ascii=False)}


async def _run_pipeline(
    runner: InMemoryRunner,
    session_id: str,
    message: types.Content,
    outputs: dict[str, str],
    attempt: int,
    decision: dict[str, str],
) -> AsyncIterator[dict]:
    """ワークフローを1回実行し、各Agentの出力をSSEで流しつつ outputs を埋める。"""
    last_author: str | None = None
    with agent_span("hive.workflow", operation="invoke_agent", attempt=attempt, **decision):
        async for event in runner.run_async(
            user_id="ui", session_id=session_id, new_message=message
        ):
            author = getattr(event, "author", None)
            text = ""
            if event.content and event.content.parts:
                text = "".join(p.text for p in event.content.parts if p.text)
            if not author or not text:
                continue
            outputs[author] = text  # 最新の出力を保持（検証で使う）
            # 新しいAgentが喋り始めた → 「思考中」演出の起点
            if author != last_author:
                yield _sse("agent_start", agent=author, role=AGENT_ROLE.get(author, ""))
                last_author = author
            yield _sse("agent_output", agent=author, role=AGENT_ROLE.get(author, ""), text=text)


async def _run_stream(task: str) -> AsyncIterator[dict]:
    """発注を自己修正ループで実行し、進捗を SSE イベントとして逐次 yield する。

    検証が通るまで最大 MAX_ATTEMPTS 回リトライ（F-04）。各試行に元の発注と前回の
    失敗要因を再注入し（目標再注入）、試行間で通過テスト数が最大の成果物を採用する
    （Best-of-N・実行接地の選別）。
    """
    yield _sse("task_received", task=task)

    # router（Functionノード相当）の判断を可視化
    decision = classify(task)
    task_type = decision["task_type"]
    yield _sse("router", task_type=task_type, scale=decision["scale"])

    # 経験の想起（F-08）：同種タスクの教訓を検索し、各試行の先頭に注入する文脈にする
    memories = _bank.retrieve(task, task_type)
    if memories:
        yield _sse("memory_recall", lessons=[m.title for m in memories])
    context = render_memories(memories)

    runner = InMemoryRunner(agent=build_workflow(), app_name=APP_NAME)
    best: VerificationResult | None = None
    best_outputs: dict[str, str] = {}
    feedback = ""
    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if attempt > 1:
                yield _sse("retry", attempt=attempt, reason=feedback)
            # 試行ごとに独立セッション＝前回の履歴に汚染されない決定論的な再実行
            session = await runner.session_service.create_session(
                app_name=APP_NAME, user_id="ui"
            )
            message = types.Content(
                role="user",
                parts=[types.Part(text=build_attempt_message(context, task, attempt, feedback))],
            )
            outputs: dict[str, str] = {}
            async for evt in _run_pipeline(runner, session.id, message, outputs, attempt, decision):
                yield evt

            # サンドボックス自己検証（F-04）：生成コード+テストを実走して判定
            code = _field(outputs.get("implementer"), "code")
            test_code = _field(outputs.get("tester"), "test_code")
            if not (code and test_code):
                break  # 検証材料が無ければリトライしても無意味

            yield _sse("verify_start", attempt=attempt)
            with agent_span("hive.verify", operation="execute_tool", agent="sandbox") as span:
                result = await asyncio.to_thread(verify_fastapi, code, test_code)
                if span:
                    span.set_attribute("verify.passed", result.passed)
            yield _sse(
                "verify_result",
                attempt=attempt,
                passed=result.passed,
                passed_count=result.passed_count,
                output=result.output[-1500:],
            )

            # Best-of-N（実行接地）：通過テスト数が最大の試行を最良として保持
            if best is None or result.passed_count > best.passed_count:
                best, best_outputs = result, outputs
            if result.passed:
                break  # 適応的停止：全テスト通過で即終了
            feedback = result.headline()

        # 経験の蓄積（F-09）：最良の試行から教訓を書き戻し、古い記憶を忘却する
        if best is not None:
            yield _sse("memory_write", **_remember(task_type, best_outputs, best))
        yield _sse("done")
    except Exception as exc:  # noqa: BLE001 - UIにエラーを流して終了
        yield _sse("error", message=str(exc))


def _remember(task_type: str, outputs: dict[str, str], result: VerificationResult) -> dict:
    """検証結果を成功/失敗の教訓として記録し、忘却を実行して結果を返す。"""
    overview = _field(outputs.get("designer"), "overview")
    if result.passed:
        item = _bank.record(
            task_type, "success", f"{task_type} 成功: {overview[:50]}", overview or "実装・テストに成功"
        )
    else:
        head = result.headline()
        item = _bank.record(task_type, "failure", f"{task_type} 失敗: {head[:50]}", f"次回の注意: {head}")
    return {"kind": item.kind, "title": item.title, "forgotten": _bank.forget()}


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
