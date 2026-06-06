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
import os
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

from agents.implementer.agent import implementer_agent
from agents.orchestrator.router import classify
from agents.orchestrator.workflow import build_workflow
from agents.tester.agent import tester_agent
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


MAX_ATTEMPTS = int(os.environ.get("HIVE_MAX_ATTEMPTS", "3"))
# デモ/テスト用：最初の N 回の検証を強制的に失敗扱いにし、修正ループを観察できる。
_DEMO_FAIL = int(os.environ.get("HIVE_DEMO_FAIL_ATTEMPTS", "0"))


async def _invoke(agent, prompt: str, out: dict) -> AsyncIterator[dict]:
    """単一Agentを実行し、進捗イベントを yield しつつ最終テキストを out["text"] に残す。"""
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    session = await runner.session_service.create_session(app_name=APP_NAME, user_id="ui")
    message = types.Content(role="user", parts=[types.Part(text=prompt)])
    role = AGENT_ROLE.get(agent.name, "")
    yield _sse("agent_start", agent=agent.name, role=role)
    async for event in runner.run_async(
        user_id="ui", session_id=session.id, new_message=message
    ):
        if event.content and event.content.parts:
            text = "".join(p.text for p in event.content.parts if p.text)
            if text:
                out["text"] = text
                yield _sse("agent_output", agent=agent.name, role=role, text=text)


async def _verify(code: str, test_code: str, attempt: int) -> VerificationResult:
    """サンドボックス検証。デモ用に最初の _DEMO_FAIL 回は強制失敗扱い。"""
    if _DEMO_FAIL and attempt <= _DEMO_FAIL:
        return VerificationResult(
            passed=False,
            returncode=1,
            output=f"[デモ] 試行 {attempt} を意図的に失敗扱い（修正ループ確認用）",
        )
    with agent_span("hive.verify", operation="execute_tool", agent="sandbox") as span:
        result = await asyncio.to_thread(verify_fastapi, code, test_code)
        if span:
            span.set_attribute("verify.passed", result.passed)
    return result


async def _run_stream(task: str) -> AsyncIterator[dict]:
    """発注→（実装→検証→失敗なら修正）ループ→記録、を SSE で逐次配信する（F-04）。"""
    yield _sse("task_received", task=task)
    decision = classify(task)
    task_type = decision["task_type"]
    yield _sse("router", task_type=task_type, scale=decision["scale"])

    # 経験の想起（F-08）：同種タスクの教訓を検索し、タスク文の先頭に注入する
    memories = _bank.retrieve(task, task_type)
    if memories:
        yield _sse("memory_recall", lessons=[m.title for m in memories])
    base_prompt = render_memories(memories) + task

    outputs: dict[str, str] = {}
    result: VerificationResult | None = None
    try:
        # 試行1：WorkflowAgent グラフ（router→designer→implementer→tester）
        runner = InMemoryRunner(agent=build_workflow(), app_name=APP_NAME)
        session = await runner.session_service.create_session(app_name=APP_NAME, user_id="ui")
        message = types.Content(role="user", parts=[types.Part(text=base_prompt)])
        last_author: str | None = None
        with agent_span("hive.workflow", operation="invoke_agent", **decision):
            async for event in runner.run_async(
                user_id="ui", session_id=session.id, new_message=message
            ):
                author = getattr(event, "author", None)
                text = ""
                if event.content and event.content.parts:
                    text = "".join(p.text for p in event.content.parts if p.text)
                if not author or not text:
                    continue
                outputs[author] = text
                if author != last_author:
                    yield _sse("agent_start", agent=author, role=AGENT_ROLE.get(author, ""))
                    last_author = author
                yield _sse("agent_output", agent=author, role=AGENT_ROLE.get(author, ""), text=text)

        design = outputs.get("designer", "")

        # 検証→失敗なら implementer/tester を修正再実行（F-04 自走ループ・最大 MAX_ATTEMPTS 回）
        for attempt in range(1, MAX_ATTEMPTS + 1):
            code = _field(outputs.get("implementer"), "code")
            test_code = _field(outputs.get("tester"), "test_code")
            if not (code and test_code):
                break
            yield _sse("verify_start", attempt=attempt)
            result = await _verify(code, test_code, attempt)
            yield _sse(
                "verify_result", passed=result.passed, attempt=attempt, output=result.output[-1500:]
            )
            if result.passed or attempt == MAX_ATTEMPTS:
                break

            # 失敗 → 修正サイクル（implementer に失敗ログを渡して作り直す）
            yield _sse("retry", attempt=attempt + 1, max=MAX_ATTEMPTS, reason=result.headline())
            fix_prompt = (
                f"{base_prompt}\n\n[設計]\n{design}\n\n"
                f"[前回の実装]\n{code}\n\n"
                f"[検証の失敗ログ(pytest)]\n{result.output[-1200:]}\n\n"
                "この失敗を必ず修正した、完全に動作する実装を作り直してください。"
            )
            impl_out: dict = {}
            async for ev in _invoke(implementer_agent, fix_prompt, impl_out):
                yield ev
            if impl_out.get("text"):
                outputs["implementer"] = impl_out["text"]
            # 新しい実装に合わせてテストも作り直す
            test_out: dict = {}
            async for ev in _invoke(tester_agent, outputs["implementer"], test_out):
                yield ev
            if test_out.get("text"):
                outputs["tester"] = test_out["text"]

        # 経験の蓄積（F-09）：最終結果から教訓を書き戻し、古い記憶を忘却する
        if result is not None:
            yield _sse("memory_write", **_remember(task_type, outputs, result))
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
