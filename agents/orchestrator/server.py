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

from agents.app.agent import make_app_implementer, make_frontend
from agents.implementer.agent import make_implementer
from agents.orchestrator.router import classify
from agents.orchestrator.workflow import build_workflow
from agents.security_reviewer.agent import security_reviewer_agent
from agents.tester.agent import tester_agent
from agents.web.agent import make_web_implementer
from shared.memory import ReasoningBank, render_memories
from shared.models import FLASH, PRO
from shared.sandbox import VerificationResult, verify_fastapi
from shared.webcheck import check_frontend, check_web
from shared.security_patterns import (
    SecurityFinding,
    SecurityReport,
    merge_review,
    scan_code,
)
from shared.telemetry import agent_span, setup_tracing


def _field(json_text: str | None, key: str) -> str:
    """Agent出力のJSONテキストから1フィールドを安全に取り出す。"""
    if not json_text:
        return ""
    try:
        return str(json.loads(json_text).get(key, "") or "")
    except (json.JSONDecodeError, AttributeError):
        return ""


def _list_field(json_text: str | None, key: str) -> list[str]:
    """Agent出力のJSONテキストからリストフィールドを安全に取り出す。"""
    if not json_text:
        return []
    try:
        value = json.loads(json_text).get(key)
        return [str(v) for v in value] if isinstance(value, list) else []
    except (json.JSONDecodeError, AttributeError):
        return []


def _page_reason(output: str) -> str:
    """ページ検証の出力から差し戻し理由の1行を取り出す。"""
    for line in output.splitlines():
        if line.startswith("- "):
            return line[2:][:120]
    return "ページ検証NG"

APP_NAME = "hive-orchestrator"
DEFAULT_TASK = "タスク管理のCRUD APIをFastAPIで作って"

# Agentの役割を可視化向けにラベル付け（F-14でキャラ職業に対応させる土台）
AGENT_ROLE = {
    "designer": "設計",
    "implementer": "実装",
    "frontend": "画面実装",
    "tester": "テスト",
    "security_reviewer": "セキュリティ監査",
}

# 経験の蓄積（F-08/F-09）と標準トレース（F-14）はプロセス全体で1つ持つ
_bank = ReasoningBank()
setup_tracing(APP_NAME)


def _sse(event_type: str, **payload) -> dict:
    """SSEの1イベントを EventSourceResponse 形式に整える。"""
    return {"event": event_type, "data": json.dumps(payload, ensure_ascii=False)}


# タスク種別ごとの実行順（F-02・差し込み式）。handoff の生成と修正ループの分岐に使う。
# app のグラフ部分は api と同じ（frontend はバックエンド検証の通過後に別フェーズで起動）
_PIPELINES = {
    "api": ["designer", "implementer", "tester"],
    "lp": ["designer", "implementer"],
    "app": ["designer", "implementer", "tester"],
}
# 編成（F-02 動的エージェント組成）。routerイベントに載せ、UIがパーティ表示に使う
_PARTY = {
    "api": ["designer", "implementer", "tester"],
    "lp": ["designer", "implementer"],
    "app": ["designer", "implementer", "frontend", "tester"],
}
# 受け渡すもの（item）と、受け手に伝える内容を抜き出すフィールド
_HANDOFF_ITEMS = {
    "api": {
        "designer": ("せっけいしょ", "overview"),
        "implementer": ("かんせいコード", "how_to_verify"),
    },
    "lp": {
        "designer": ("デザインしようしょ", "style_direction"),
    },
    "app": {
        "designer": ("せっけいしょ", "overview"),
        "implementer": ("かんせいコード", "how_to_verify"),
    },
}
# implementer の成果物が入るフィールド名
_RESULT_KEY = {"api": "code", "lp": "html", "app": "code"}
# F-13 交代時に使う implementer のファクトリ
_IMPL_FACTORY = {"api": make_implementer, "lp": make_web_implementer, "app": make_app_implementer}

MAX_ATTEMPTS = int(os.environ.get("HIVE_MAX_ATTEMPTS", "3"))
# デモ/テスト用：最初の N 回の検証を強制的に失敗扱いにし、修正ループを観察できる。
_DEMO_FAIL = int(os.environ.get("HIVE_DEMO_FAIL_ATTEMPTS", "0"))
# F-15 セキュリティ監査： "1"=両層（既定）/ "pattern"=第1層のみ（$0）/ "0"=無効
_SECURITY = os.environ.get("HIVE_SECURITY", "1")
# デモ/テスト用：最初の N 回の監査に合成のcritical指摘を注入し、差し戻しを観察できる。
_DEMO_VULN = int(os.environ.get("HIVE_DEMO_VULN_ATTEMPTS", "0"))


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


def _handoff_events(author: str, text: str, task_type: str) -> list[dict]:
    """author の成果が出た瞬間に「次の担当への受け渡し」を表すイベント列を作る。

    タスクが渡った瞬間に次Agentの agent_start を流すことで、
    UIは実際のLLM待ち時間を「考えている」演出として見せられる（F-14）。
    """
    pipeline = _PIPELINES[task_type]
    items = _HANDOFF_ITEMS[task_type]
    if author not in items:
        return []
    nxt = pipeline[pipeline.index(author) + 1]
    item, key = items[author]
    detail = _field(text, key)[:80]
    return [
        _sse("handoff", from_agent=author, to_agent=nxt, item=item, detail=detail),
        _sse("agent_start", agent=nxt, role=AGENT_ROLE.get(nxt, ""), detail=detail),
    ]


def _numbered(code: str) -> str:
    """監査用にコードへ行番号を振る（指摘の line と突き合わせるため）。"""
    return "\n".join(f"{i:4d} | {line}" for i, line in enumerate(code.splitlines(), start=1))


def _parse_security(text: str | None) -> SecurityReport | None:
    """security_reviewer の出力JSONを SecurityReport に変換する（不正なら None）。"""
    if not text:
        return None
    try:
        data = json.loads(text)
        findings = [
            SecurityFinding(
                severity=str(f.get("severity", "minor")),
                file_path=str(f.get("file_path", "main.py")),
                line=int(f.get("line", 0) or 0),
                issue=str(f.get("issue", "")),
                recommendation=str(f.get("recommendation", "")),
                detected_by="llm",
            )
            for f in data.get("findings", [])
        ]
        return SecurityReport(
            passed=bool(data.get("passed", True)),
            findings=findings,
            summary=str(data.get("summary", "")),
        )
    except (json.JSONDecodeError, AttributeError, TypeError, ValueError):
        return None


def _quality_plan(quality: str, task_type: str, scale: str) -> dict:
    """品質レベル（UI選択）を実行計画に解決する（F-02）。

    "auto"（既定）は router の判定で自動決定：重い発注（scale=heavy）と
    フルスタック（app）は最初から Pro で作る。Flashで2回失敗してから
    Pro に交代するより、速く・安く・高品質に着地するため。
    """
    if quality not in ("fast", "best"):
        quality = "best" if (scale == "heavy" or task_type == "app") else "balanced"
    if quality == "fast":
        # はやさ優先：Flashのみ・交代なし（その分リトライは軽く回る）
        return {"label": "はやさ優先", "designer": FLASH, "implementer": FLASH, "escalate": False}
    if quality == "best":
        # 品質優先：設計・実装とも最初から Pro（交代の余地なし＝最初から最強）
        return {"label": "品質優先", "designer": PRO, "implementer": PRO, "escalate": False}
    # バランス：Flashで始め、最終試行だけ Pro に交代（F-13）
    return {"label": "バランス", "designer": FLASH, "implementer": FLASH, "escalate": True}


async def _run_stream(task: str, quality: str = "auto") -> AsyncIterator[dict]:
    """発注→（実装→検証→失敗なら修正）ループ→記録、を SSE で逐次配信する（F-04）。"""
    yield _sse("task_received", task=task)
    decision = classify(task)
    task_type = decision["task_type"]
    plan = _quality_plan(quality, task_type, decision["scale"])
    # 編成（F-02 動的エージェント組成）：このタスクで働くAgentをUIに知らせる
    party = list(_PARTY[task_type])
    if _SECURITY != "0":
        party.append("security_reviewer")
    yield _sse(
        "router",
        task_type=task_type,
        scale=decision["scale"],
        quality=plan["label"],
        model=plan["implementer"],
        party=[{"agent": a, "role": AGENT_ROLE.get(a, "")} for a in party],
    )

    # 経験の想起（F-08）：同種タスクの教訓を検索し、タスク文の先頭に注入する
    memories = _bank.retrieve(task, task_type)
    if memories:
        yield _sse("memory_recall", lessons=[m.title for m in memories])
    base_prompt = render_memories(memories) + task

    outputs: dict[str, str] = {}
    result: VerificationResult | None = None
    try:
        # 試行1：WorkflowAgent グラフ（タスク種別＋品質レベルに応じたパイプライン・F-02）
        runner = InMemoryRunner(
            agent=build_workflow(task_type, plan["designer"], plan["implementer"]),
            app_name=APP_NAME,
        )
        session = await runner.session_service.create_session(app_name=APP_NAME, user_id="ui")
        message = types.Content(role="user", parts=[types.Part(text=base_prompt)])
        # 最初の担当には今この瞬間にタスクが渡る。以降は handoff が次の開始を知らせる
        yield _sse(
            "agent_start", agent="designer", role=AGENT_ROLE["designer"], detail=task[:60]
        )
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
                yield _sse("agent_output", agent=author, role=AGENT_ROLE.get(author, ""), text=text)
                for handoff_ev in _handoff_events(author, text, task_type):
                    yield handoff_ev

        design = outputs.get("designer", "")
        result_key = _RESULT_KEY[task_type]
        has_tester = "tester" in _PIPELINES[task_type]

        async def _fix(next_attempt: int, headline: str, failure_block: str) -> AsyncIterator[dict]:
            """失敗を implementer に差し戻して作り直す（F-04/F-13）。

            監査・検証役は修正しない原則：レポートを渡し、修正は implementer が行う。
            """
            yield _sse("retry", attempt=next_attempt, max=MAX_ATTEMPTS, reason=headline)
            # F-13 交代：最終試行はモデルを格上げ（Flash→Pro）した新インスタンスに交代
            # （品質優先プランは最初からPro＝交代不要。はやさ優先は交代しない約束）
            factory = _IMPL_FACTORY[task_type]
            if plan["escalate"] and next_attempt == MAX_ATTEMPTS and MAX_ATTEMPTS > 1:
                yield _sse("escalation", agent="implementer", to_model=PRO)
                implementer = factory(PRO)
            else:
                implementer = factory(plan["implementer"])
            fix_prompt = (
                f"{base_prompt}\n\n[設計]\n{design}\n\n"
                f"[前回の実装]\n{_field(outputs.get('implementer'), result_key)}\n\n"
                f"{failure_block}\n\n"
                "上記の問題を必ず修正した、完全に動作する実装を作り直してください。"
            )
            impl_out: dict = {}
            async for ev in _invoke(implementer, fix_prompt, impl_out):
                yield ev
            if impl_out.get("text"):
                outputs["implementer"] = impl_out["text"]
            if not has_tester:
                return
            # 新しい実装に合わせてテストも作り直す（受け渡しも可視化する）
            yield _sse(
                "handoff",
                from_agent="implementer",
                to_agent="tester",
                item="しゅうせいした コード",
                detail=_field(outputs.get("implementer"), "how_to_verify")[:80],
            )
            test_out: dict = {}
            async for ev in _invoke(tester_agent, outputs["implementer"], test_out):
                yield ev
            if test_out.get("text"):
                outputs["tester"] = test_out["text"]

        # 監査→検証→失敗なら修正、の自走ループ（F-04/F-15・最大 MAX_ATTEMPTS 回）
        sec_report: SecurityReport | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            code = _field(outputs.get("implementer"), result_key)
            test_code = _field(outputs.get("tester"), "test_code")
            if not code or (has_tester and not test_code):
                break

            # --- F-15 セキュリティ監査（implementer の出力直後・サンドボックスの前）---
            sec_report = None
            if _SECURITY != "0":
                yield _sse("security_start", attempt=attempt)
                pattern_findings = scan_code(code)  # 第1層：決定論的パターン（$0）
                if _DEMO_VULN and attempt <= _DEMO_VULN:
                    pattern_findings.append(
                        SecurityFinding(
                            severity="critical", line=1,
                            issue="[デモ] 合成した脆弱性（差し戻し確認用）",
                            recommendation="HIVE_DEMO_VULN_ATTEMPTS=0 で無効化",
                        )
                    )
                llm_review: SecurityReport | None = None
                if _SECURITY != "pattern":
                    # 第2層：security-reviewer（Gemini Pro 固定・implementer とは別個体）
                    if task_type == "lp":
                        audit_prompt = (
                            "以下のHTMLページを監査してください（行番号付き・file_pathは index.html）。"
                            "観点：XSS・危険なインラインscript・外部リソースの読み込み・"
                            "秘密情報の混入・フォームの送信先。\n\n"
                        )
                    else:
                        audit_prompt = "以下の実装コードを監査してください（行番号付き）。\n\n"
                    sec_out: dict = {}
                    async for ev in _invoke(
                        security_reviewer_agent, audit_prompt + _numbered(code), sec_out
                    ):
                        yield ev
                    llm_review = _parse_security(sec_out.get("text"))
                # 合成判定：LLMがOKでもパターン層がNGならNG（critical 0 件のみ合格）
                sec_report = merge_review(pattern_findings, llm_review)
                yield _sse(
                    "security_result",
                    passed=sec_report.passed,
                    summary=sec_report.summary,
                    findings=[f.model_dump() for f in sec_report.findings[:20]],
                )
                if not sec_report.passed:
                    if attempt == MAX_ATTEMPTS:
                        break
                    async for ev in _fix(
                        attempt + 1,
                        f"セキュリティ: {sec_report.headline()}",
                        f"[セキュリティ監査の指摘]\n{sec_report.render()}",
                    ):
                        yield ev
                    continue  # 修正後は再監査からやり直す

            # --- F-04 検証（api: サンドボックスでpytest / lp: ページ機械チェック）---
            verify_mode = "page" if task_type == "lp" else "pytest"
            yield _sse("verify_start", attempt=attempt, mode=verify_mode)
            if task_type == "lp":
                result = check_web(code)
            else:
                result = await _verify(code, test_code, attempt)
            yield _sse(
                "verify_result",
                passed=result.passed,
                attempt=attempt,
                mode=verify_mode,
                output=result.output[-1500:],
            )
            if result.passed or attempt == MAX_ATTEMPTS:
                break
            failure_label = "ページ検証の指摘" if task_type == "lp" else "検証の失敗ログ(pytest)"
            reason = _page_reason(result.output) if task_type == "lp" else result.headline()
            async for ev in _fix(
                attempt + 1,
                reason,
                f"[{failure_label}]\n{result.output[-1200:]}",
            ):
                yield ev

        # --- app: 画面フェーズ（バックエンド検証の通過後・F-03 前段出力＝契約）---
        fe_result: VerificationResult | None = None
        if (
            task_type == "app"
            and result is not None
            and result.passed
            and (sec_report is None or sec_report.passed)
        ):
            endpoints = _list_field(outputs.get("designer"), "endpoints")
            contract = (
                "[APIけいやくしょ]\n" + "\n".join(endpoints)
                + "\n\n[APIの動作確認方法]\n" + _field(outputs.get("implementer"), "how_to_verify")
            )
            yield _sse(
                "handoff",
                from_agent="implementer",
                to_agent="frontend",
                item="APIけいやくしょ",
                detail="; ".join(endpoints)[:80],
            )
            fe_prompt = (
                f"{base_prompt}\n\n[設計]\n{design}\n\n{contract}\n\n"
                "この契約どおりにAPIを呼び出す画面（単一ファイルの index.html）を実装してください。"
            )
            frontend = make_frontend(plan["implementer"])
            for fe_attempt in range(1, MAX_ATTEMPTS + 1):
                fe_out: dict = {}
                async for ev in _invoke(frontend, fe_prompt, fe_out):
                    yield ev
                if fe_out.get("text"):
                    outputs["frontend"] = fe_out["text"]
                html = _field(outputs.get("frontend"), "html")
                if not html:
                    break
                yield _sse("verify_start", attempt=fe_attempt, mode="page")
                fe_result = check_frontend(html, endpoints)
                yield _sse(
                    "verify_result",
                    passed=fe_result.passed,
                    attempt=fe_attempt,
                    mode="page",
                    output=fe_result.output[-1500:],
                )
                if fe_result.passed or fe_attempt == MAX_ATTEMPTS:
                    break
                # 差し戻し（修正責任は frontend 自身。F-13 交代も同様に適用）
                yield _sse(
                    "retry",
                    attempt=fe_attempt + 1,
                    max=MAX_ATTEMPTS,
                    reason=f"画面: {_page_reason(fe_result.output)}",
                )
                if plan["escalate"] and fe_attempt + 1 == MAX_ATTEMPTS and MAX_ATTEMPTS > 1:
                    yield _sse("escalation", agent="frontend", to_model=PRO)
                    frontend = make_frontend(PRO)
                fe_prompt = (
                    f"{base_prompt}\n\n[設計]\n{design}\n\n{contract}\n\n"
                    f"[前回の画面実装]\n{html}\n\n"
                    f"[画面検証の指摘]\n{fe_result.output[-1200:]}\n\n"
                    "上記の問題を必ず修正した画面を作り直してください。"
                )

        # 経験の蓄積（F-09）：最終結果から教訓を書き戻し、古い記憶を忘却する
        final_result = fe_result if fe_result is not None else result
        if sec_report is not None and not sec_report.passed:
            yield _sse("memory_write", **_remember_security(task_type, sec_report))
        elif final_result is not None:
            yield _sse("memory_write", **_remember(task_type, outputs, final_result))
        yield _sse("done")
    except Exception as exc:  # noqa: BLE001 - UIにエラーを流して終了
        yield _sse("error", message=str(exc))


def _remember_security(task_type: str, report: SecurityReport) -> dict:
    """セキュリティ監査の失敗を教訓として記録する（F-08/F-15）。"""
    head = report.headline()
    item = _bank.record(
        task_type, "failure", f"{task_type} セキュリティ: {head[:50]}", f"次回の注意: {head}"
    )
    return {"kind": item.kind, "title": item.title, "forgotten": _bank.forget()}


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
    quality = request.query_params.get("quality") or "auto"
    return EventSourceResponse(_run_stream(task, quality))


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
