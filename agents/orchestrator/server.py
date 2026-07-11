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
from agents.orchestrator.intake import make_intake, parse_order, render_order
from agents.orchestrator.router import classify, difficulty_rank, rank_reasons, thinking_level
from agents.orchestrator.workflow import build_workflow
from agents.reflection.agent import make_reflection
from agents.security_reviewer.agent import security_reviewer_agent
from agents.tester.agent import tester_agent
from agents.web.agent import make_web_implementer
from agents.webapp.agent import make_webapp_implementer
from shared.armor import armor_on, sanitize_prompt, sanitize_response
from shared.memory import ReasoningBank, acceptable_lesson, render_memories
from shared.models import FLASH, PRO, with_thinking
from shared.layoutcheck import check_layout
from shared.runcheck import check_acceptance, check_browser
from shared.sandbox import VerificationResult, verify_fastapi
from shared.webcheck import check_app, check_frontend, check_web
from shared.security_patterns import (
    SecurityFinding,
    SecurityReport,
    merge_review,
    scan_code,
)
from shared.telemetry import agent_span, setup_tracing
from shared.watchdog import guard_silence


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
DEFAULT_TASK = "オセロを作って"

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
# app＝ブラウザ完結の単一HTMLアプリ（既定・v2.9）。fullstack（旧app）のグラフ部分は
# api と同じ（frontend はバックエンド検証の通過後に別フェーズで起動）
_PIPELINES = {
    "app": ["designer", "implementer"],
    "api": ["designer", "implementer", "tester"],
    "lp": ["designer", "implementer"],
    "fullstack": ["designer", "implementer", "tester"],
}
# 編成（F-02 動的エージェント組成）。routerイベントに載せ、UIがパーティ表示に使う
_PARTY = {
    "app": ["designer", "implementer"],
    "api": ["designer", "implementer", "tester"],
    "lp": ["designer", "implementer"],
    "fullstack": ["designer", "implementer", "frontend", "tester"],
}
# 受け渡し：author → [(受け手, 渡すもの, 内容を抜き出すフィールド)]。
# fullstack の designer は API班（implementer）と画面班（frontend）の
# 2手に同時に渡す（v2.11 並列ファンアウト）
_HANDOFF_ITEMS = {
    "app": {
        "designer": [("implementer", "せっけいしょ", "overview")],
    },
    "api": {
        "designer": [("implementer", "せっけいしょ", "overview")],
        "implementer": [("tester", "かんせいコード", "how_to_verify")],
    },
    "lp": {
        "designer": [("implementer", "デザインしようしょ", "style_direction")],
    },
    "fullstack": {
        "designer": [
            ("implementer", "せっけいしょ", "overview"),
            ("frontend", "APIけいやくしょ", "endpoints"),
        ],
        "implementer": [("tester", "かんせいコード", "how_to_verify")],
    },
}
# implementer の成果物が入るフィールド名
_RESULT_KEY = {"app": "html", "api": "code", "lp": "html", "fullstack": "code"}
# F-13 交代時に使う implementer のファクトリ
_IMPL_FACTORY = {
    "app": make_webapp_implementer,
    "api": make_implementer,
    "lp": make_web_implementer,
    "fullstack": make_app_implementer,
}

MAX_ATTEMPTS = int(os.environ.get("HIVE_MAX_ATTEMPTS", "3"))
# F-03 安定化：LLM/A2A呼び出しの沈黙タイムアウト（秒）。イベントがこの秒数
# 途絶えたら、固まったまま待ち続けずに明示的に失敗させてUIに知らせる。"0"で無効
_AGENT_TIMEOUT = float(os.environ.get("HIVE_AGENT_TIMEOUT", "300"))
# デモ/テスト用：最初の N 回の検証を強制的に失敗扱いにし、修正ループを観察できる。
_DEMO_FAIL = int(os.environ.get("HIVE_DEMO_FAIL_ATTEMPTS", "0"))
# F-15 セキュリティ監査： "1"=両層（既定）/ "pattern"=第1層のみ（$0）/ "0"=無効
_SECURITY = os.environ.get("HIVE_SECURITY", "1")
# F-08 経験の学習（オフスイッチ）："0"で想起・記録を丸ごと止め、学習あり/なしをA/B比較できる
_MEMORY_ON = os.environ.get("HIVE_MEMORY", "1") != "0"
# F-01 発注ゲート（オフスイッチ）："0"で正規化を止め、発注の原文だけで実行する
_INTAKE_ON = os.environ.get("HIVE_INTAKE", "1") != "0"
# F-04 スマホ表示のvision判定（v2.10・レポートのみ）："0"でスクショ判定を止める
_LAYOUT_ON = os.environ.get("HIVE_LAYOUT", "1") != "0"
# F-02 おまかせの節約モード（v2.10・実験スイッチ）："1"でE級appをFlash＋思考HIGHで作る。
# 出荷基準evalの実測が 1/3（2026-07-09・単発実行）だったため既定はOFF＝最初からPro。
# モデルが世代交代したら `HIVE_AUTO_ECON=1 make eval-full` で再実測して判断する
_AUTO_ECON = os.environ.get("HIVE_AUTO_ECON", "0") == "1"
# デモ/テスト用：最初の N 回の監査に合成のcritical指摘を注入し、差し戻しを観察できる。
_DEMO_VULN = int(os.environ.get("HIVE_DEMO_VULN_ATTEMPTS", "0"))


async def _run_silent(agent, prompt: str) -> str | None:
    """単一Agentを実行して最終テキストだけ返す（SSEイベントは流さない）。

    reflection（教訓の蒸留）のような内部処理用。タイムライン/RPGの描画対象にしない。
    """
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    session = await runner.session_service.create_session(app_name=APP_NAME, user_id="ui")
    message = types.Content(role="user", parts=[types.Part(text=prompt)])
    text: str | None = None
    events = runner.run_async(user_id="ui", session_id=session.id, new_message=message)
    async for event in guard_silence(events, _AGENT_TIMEOUT):
        if event.content and event.content.parts:
            t = "".join(p.text for p in event.content.parts if p.text)
            if t:
                text = t
    return text


async def _invoke(agent, prompt: str, out: dict) -> AsyncIterator[dict]:
    """単一Agentを実行し、進捗イベントを yield しつつ最終テキストを out["text"] に残す。"""
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    session = await runner.session_service.create_session(app_name=APP_NAME, user_id="ui")
    message = types.Content(role="user", parts=[types.Part(text=prompt)])
    role = AGENT_ROLE.get(agent.name, "")
    yield _sse("agent_start", agent=agent.name, role=role)
    events = runner.run_async(user_id="ui", session_id=session.id, new_message=message)
    async for event in guard_silence(events, _AGENT_TIMEOUT):
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


async def _verify_artifact(
    task_type: str, outputs: dict[str, str], attempt: int
) -> VerificationResult:
    """成果物1回ぶんの機械検証を実行し、結果だけ返す（F-04）。

    - app: 出荷基準の多段オラクル（構造チェック→ブラウザ実行→受け入れ検証→
      スマホ表示のvision判定※レポートのみ・合否は変えない）
    - lp : ページの決定論チェック
    - api / fullstack: uv隔離サンドボックスで pytest

    SSEイベントを出さない純粋な検証部品にしてある：セキュリティ監査（F-15・LLM）と
    並列に走らせるため（監査のLLM待ち時間の裏で$0の機械検証を済ませる・v2.11）。
    """
    code = _field(outputs.get("implementer"), _RESULT_KEY[task_type])
    if task_type == "lp":
        return check_web(code)
    if task_type == "app":
        # 出荷基準の2段オラクル（F-04・v2.9）：構造チェック→ブラウザ実行検証
        persistence = _field(outputs.get("designer"), "persistence").lower()
        result = check_app(code, persistence)
        if result.passed:
            with agent_span(
                "hive.runcheck", operation="execute_tool", agent="browser"
            ) as span:
                browser_result = await asyncio.to_thread(check_browser, code)
                if span:
                    span.set_attribute("verify.passed", browser_result.passed)
            result = VerificationResult(
                passed=browser_result.passed,
                returncode=browser_result.returncode,
                output=f"{result.output}\n{browser_result.output}",
            )
        # 第3段オラクル（F-04・v2.10）：designerが書いた受け入れ検証スクリプトを
        # ブラウザで実行し「要求どおり操作できるか」を機械採点する
        check_script = _field(outputs.get("designer"), "check_script")
        if result.passed and check_script:
            acc = await asyncio.to_thread(check_acceptance, code, check_script)
            result = VerificationResult(
                passed=acc.passed,
                returncode=acc.returncode,
                output=f"{result.output}\n{acc.output}",
            )
        # スマホ表示のvision判定（F-04・v2.10）：レポートのみ＝合否は変えない
        if result.passed and _LAYOUT_ON:
            layout_note = await asyncio.to_thread(check_layout, code)
            if layout_note:
                result = VerificationResult(
                    passed=True,
                    returncode=0,
                    output=f"{result.output}\n{layout_note}",
                )
        return result
    return await _verify(code, _field(outputs.get("tester"), "test_code"), attempt)


def _handoff_events(author: str, text: str, task_type: str) -> list[dict]:
    """author の成果が出た瞬間に「次の担当への受け渡し」を表すイベント列を作る。

    タスクが渡った瞬間に次Agentの agent_start を流すことで、
    UIは実際のLLM待ち時間を「考えている」演出として見せられる（F-14）。
    受け手が複数のとき（fullstackのdesigner）は全員ぶんを順に流す。
    """
    events: list[dict] = []
    for to_agent, item, key in _HANDOFF_ITEMS[task_type].get(author, []):
        # detail はリストのフィールド（endpoints等）と文字列の両方に対応する
        values = _list_field(text, key)
        detail = ("; ".join(values) if values else _field(text, key))[:80]
        events.append(
            _sse("handoff", from_agent=author, to_agent=to_agent, item=item, detail=detail)
        )
        events.append(
            _sse("agent_start", agent=to_agent, role=AGENT_ROLE.get(to_agent, ""), detail=detail)
        )
    return events


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


async def _distill(task_type: str, notes: list[str], result: VerificationResult) -> dict | None:
    """検証記録から転用可能な教訓を蒸留する（F-08/F-09・v2.9.1）。

    「いらない学習」を書かないための二重ゲート：
    - reflection 自身が transferable=false と判断したら保存しない（無理に教訓を作らない）
    - 出力が壊れている／acceptable_lesson（決定論チェック）を通らなければ保存しない
    入力は機械が作った検証記録のみ（ユーザーの発注文を直接記憶させない＝注入対策）。
    """
    outcome = "最終的に検証に合格" if result.passed else "最大試行回数を使っても不合格"
    listed = notes[-5:] or ["（差し戻しなし）"]
    prompt = (
        f"[タスク種別] {task_type}\n[検証記録（差し戻しの理由）]\n"
        + "\n".join(f"- {n[:200]}" for n in listed)
        + f"\n[結末] {outcome}（最終検証: {result.headline()[:200]}）"
    )
    try:
        text = await _run_silent(make_reflection(), prompt)
        data = json.loads(text or "")
    except Exception:  # noqa: BLE001 - 蒸留の失敗は「記録しない」に倒す（本体を壊さない）
        return None
    if not isinstance(data, dict) or not data.get("transferable"):
        return None
    title = str(data.get("title") or "").strip()
    lesson = str(data.get("lesson") or "").strip()
    if not acceptable_lesson(title, lesson):
        return None
    return {"title": f"{task_type} {title}"[:80], "lesson": lesson}


# 「さくせん」（F-02）：ユーザーが選ぶエフォート。タスク規模（討伐ランク）とは独立の軸。
# ラベルはドラクエ「さくせん」のパロディだが商標回避のため一文字ひねったオリジナル表現。
_SAKUSEN = {
    "all_hands": "みんなでがんばれ",
    "go_hard": "がんがんつくろうぜ",
    "adaptive": "てきどにがんばれ",
    "cost_saver": "コストだいじに",
    "auto": "おまかせ",
}
# 旧quality値（v2.8初版）からの互換マッピング
_LEGACY_EFFORT = {"fast": "cost_saver", "best": "go_hard", "balanced": "adaptive"}


def _effort_plan(effort: str, task_type: str, scale: str, rank: str = "") -> dict:
    """「さくせん」（ユーザー選択のエフォート）を実行計画に解決する（F-02）。

    "auto"（おまかせ・既定）は router の判定で自動決定：アプリ（app/fullstack）と
    重い発注（scale=heavy）は go_hard 相当（最初からPro）。Flashで2回失敗してから
    Pro に交代するより速く・安く・高品質に着地し、さらに app はゲームロジック等の
    正しさを機械オラクルで完全判定できないため、モデル品質で先に担保する（v2.9）。

    例外＝節約モード（v2.10・HIVE_AUTO_ECON=1・既定OFF）：**E級のapp**だけを
    Flash＋思考HIGH で作る実験。出荷基準evalの実測は 1/3（2026-07-09）で
    「深く考えるFlash」でもProの代わりにならなかったため、既定では使わない。

    返り値（マッピング層のみ。モデル選択・パイプライン構成の既存ロジックは不変）:
    - designer / implementer: 使用モデル
    - escalate: F-13（Flash→Pro交代）を使うか
    - thinking: 思考レベルの上書き（無ければランク連動の既定を使う）
    - force_security: F-15 監査を環境変数に関係なく強制ONにするか（all_hands）
    - tree_search: F-12（Rewind木探索）予約フラグ。実装後に all_hands で自動ON
    """
    effort = _LEGACY_EFFORT.get(effort, effort)
    econ = False
    if effort not in _SAKUSEN or effort == "auto":
        econ = _AUTO_ECON and task_type == "app" and rank == "E"
        if econ:
            effort = "adaptive"
        else:
            effort = (
                "go_hard"
                if (scale == "heavy" or task_type in ("app", "fullstack"))
                else "adaptive"
            )
    base = {
        "effort": effort,
        "label": _SAKUSEN[effort],
        "force_security": False,
        "tree_search": False,
    }
    if econ:
        base["thinking"] = "HIGH"
    if effort == "all_hands":
        # いちばん丁寧：Pro＋セキュリティ監査強制（＋F-12は実装後にここでON）
        return base | {
            "designer": PRO, "implementer": PRO, "escalate": False,
            "force_security": True, "tree_search": True,
        }
    if effort == "go_hard":
        # 最初からPro（交代の余地なし＝最初から最強）
        return base | {"designer": PRO, "implementer": PRO, "escalate": False}
    if effort == "cost_saver":
        # いちばん安い・速い：Flashのみ・交代なし
        return base | {"designer": FLASH, "implementer": FLASH, "escalate": False}
    # adaptive：Flashで始め、失敗が続いたら最終試行だけ Pro に交代（F-13の作戦化）
    return base | {"designer": FLASH, "implementer": FLASH, "escalate": True}


async def _run_stream(task: str, effort: str = "auto") -> AsyncIterator[dict]:
    """発注→（実装→検証→失敗なら修正）ループ→記録、を SSE で逐次配信する（F-04）。"""
    yield _sse("task_received", task=task)

    # 実行時入力防御（F-11 Model Armor）：発注文がモデルに届く前に検査する。
    # プロンプトインジェクション等を検出したら実行そのものを止める（F-15とは別レイヤー）。
    # API未整備の環境では checked=False で素通し（フェイルオープン・intakeと同じ思想）
    if armor_on():
        gate = await asyncio.to_thread(sanitize_prompt, task)
        if gate.checked or not gate.allowed:
            yield _sse("armor", stage="prompt", **gate.model_dump())
        if not gate.allowed:
            yield _sse(
                "error",
                message="発注文が実行時安全フィルタ（Model Armor）にブロックされました："
                + "・".join(gate.matched),
            )
            return

    decision = classify(task)
    task_type = decision["task_type"]

    # 発注ゲート（F-01）：発注文を「クエスト依頼書」に正規化し、解釈をUIに開示する。
    # 依頼書の機能数は討伐ランクの判定材料にもなる（F-02）。
    # 解釈に失敗しても止めず、原文だけで進める（フェイルオープン）
    order = None
    if _INTAKE_ON:
        yield _sse("intake_start")
        try:
            order = parse_order(await _run_silent(make_intake(), task))
        except Exception:  # noqa: BLE001 - 受付の不調は「原文で続行」に倒す
            order = None
        if order:
            yield _sse("order_spec", **order.model_dump())
        else:
            # 解釈できなかった合図（UIは受付カードを閉じるだけ）
            yield _sse("order_spec", what="")

    feature_count = len(order.features) if order else 0
    rank = difficulty_rank(task_type, decision["scale"], feature_count)
    plan = _effort_plan(effort, task_type, decision["scale"], rank)
    # 思考レベル（F-02）：基本はランク連動（むずかしいほど深く考える）。
    # 節約モード（E級app＝Flash）は思考HIGHで品質を補う（planが上書きを持つ）
    think = plan.get("thinking") or thinking_level(rank)
    security_on = _SECURITY != "0" or plan["force_security"]
    security_full = (_SECURITY not in ("0", "pattern")) or plan["force_security"]
    # 編成（F-02 動的エージェント組成）：このタスクで働くAgentをUIに知らせる
    party = list(_PARTY[task_type])
    if security_on:
        party.append("security_reviewer")
    yield _sse(
        "router",
        task_type=task_type,
        scale=decision["scale"],
        rank=rank,
        rank_basis="・".join(rank_reasons(task_type, decision["scale"], feature_count)),
        thinking=think,
        effort=plan["effort"],
        sakusen=plan["label"],
        # 互換: v2.8初版のUI（quality表示）も壊さない
        quality=plan["label"],
        model=plan["implementer"],
        party=[{"agent": a, "role": AGENT_ROLE.get(a, "")} for a in party],
    )

    # 経験の想起（F-08）：同種タスクの教訓を検索し、タスク文の先頭に注入する
    # （HIVE_MEMORY=0 で丸ごと無効化＝学習あり/なしのA/B比較用オフスイッチ）
    memories = _bank.retrieve(task, task_type) if _MEMORY_ON else []
    if memories:
        yield _sse("memory_recall", lessons=[m.title for m in memories])
    base_prompt = render_memories(memories) + (render_order(order) if order else "") + task

    outputs: dict[str, str] = {}
    failure_notes: list[str] = []  # 差し戻し理由の記録（F-08 蒸留の材料・機械産の情報のみ）
    result: VerificationResult | None = None
    verify_task: asyncio.Task | None = None  # 監査と並列に走らせる機械検証（v2.11）
    try:
        # 試行1：WorkflowAgent グラフ（タスク種別＋品質レベルに応じたパイプライン・F-02）
        runner = InMemoryRunner(
            agent=build_workflow(task_type, plan["designer"], plan["implementer"], think),
            app_name=APP_NAME,
        )
        session = await runner.session_service.create_session(app_name=APP_NAME, user_id="ui")
        message = types.Content(role="user", parts=[types.Part(text=base_prompt)])
        # 最初の担当には今この瞬間にタスクが渡る。以降は handoff が次の開始を知らせる
        yield _sse(
            "agent_start", agent="designer", role=AGENT_ROLE["designer"], detail=task[:60]
        )
        with agent_span("hive.workflow", operation="invoke_agent", **decision):
            events = runner.run_async(
                user_id="ui", session_id=session.id, new_message=message
            )
            async for event in guard_silence(events, _AGENT_TIMEOUT):
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
                implementer = with_thinking(factory(PRO), think)
            else:
                implementer = with_thinking(factory(plan["implementer"]), think)
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

            # 機械検証（F-04・$0）を先に裏で走らせておく（v2.11 並列化）。
            # 監査（F-15・LLMで数十秒）と機械検証は同じ成果物を読むだけで
            # 互いの結果を使わないため、同時に走らせて1試行あたりの待ちを縮める。
            # SSEイベントの順序は従来どおり（監査→検証）＝UI側の変更は不要
            verify_task = asyncio.create_task(_verify_artifact(task_type, outputs, attempt))

            # --- F-15 セキュリティ監査（implementer の出力直後・機械検証と並列）---
            # 「みんなでがんばれ」は環境変数に関係なく監査を強制ON（force_security）
            sec_report = None
            if security_on:
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
                if security_full:
                    # 第2層：security-reviewer（Gemini Pro 固定・implementer とは別個体）
                    if task_type in ("lp", "app"):
                        audit_prompt = (
                            "以下のHTMLページ（アプリ）を監査してください"
                            "（行番号付き・file_pathは index.html）。"
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
                    # 監査NGの修正が先。裏の検証は結果を使わず止める（$0なので損はない）
                    verify_task.cancel()
                    failure_notes.append(f"セキュリティ監査NG: {sec_report.headline()}")
                    if attempt == MAX_ATTEMPTS:
                        break
                    async for ev in _fix(
                        attempt + 1,
                        f"セキュリティ: {sec_report.headline()}",
                        f"[セキュリティ監査の指摘]\n{sec_report.render()}",
                    ):
                        yield ev
                    continue  # 修正後は再監査からやり直す

            # --- F-04 検証（中身は _verify_artifact。監査と並列に走り終えている）---
            verify_mode = {"lp": "page", "app": "browser"}.get(task_type, "pytest")
            yield _sse("verify_start", attempt=attempt, mode=verify_mode)
            result = await verify_task
            yield _sse(
                "verify_result",
                passed=result.passed,
                attempt=attempt,
                mode=verify_mode,
                output=result.output[-1500:],
            )
            if result.passed or attempt == MAX_ATTEMPTS:
                break
            if task_type == "lp":
                failure_label, reason = "ページ検証の指摘", _page_reason(result.output)
            elif task_type == "app":
                failure_label, reason = "アプリ検証の指摘", _page_reason(result.output)
            else:
                failure_label, reason = "検証の失敗ログ(pytest)", result.headline()
            failure_notes.append(f"検証NG({verify_mode}): {reason}")
            async for ev in _fix(
                attempt + 1,
                reason,
                f"[{failure_label}]\n{result.output[-1200:]}",
            ):
                yield ev

        # --- fullstack: 画面フェーズ（バックエンド検証の通過後・F-03 前段出力＝契約）---
        # 画面そのものはグラフ内で設計直後にAPI班と並列で生成済み（v2.11）。
        # ここではバックエンドの合格を確認してから、画面の検証→失敗なら差し戻しを行う
        # （API側が差し戻しで作り直されても契約＝設計の endpoints は不変なので、
        # 並列生成した画面はそのまま使える）
        fe_result: VerificationResult | None = None
        if (
            task_type == "fullstack"
            and result is not None
            and result.passed
            and (sec_report is None or sec_report.passed)
        ):
            endpoints = _list_field(outputs.get("designer"), "endpoints")
            contract = (
                "[APIけいやくしょ]\n" + "\n".join(endpoints)
                + "\n\n[APIの動作確認方法]\n" + _field(outputs.get("implementer"), "how_to_verify")
            )
            fe_prompt = (
                f"{base_prompt}\n\n[設計]\n{design}\n\n{contract}\n\n"
                "この契約どおりにAPIを呼び出す画面（単一ファイルの index.html）を実装してください。"
            )
            frontend = with_thinking(make_frontend(plan["implementer"]), think)
            for fe_attempt in range(1, MAX_ATTEMPTS + 1):
                html = _field(outputs.get("frontend"), "html")
                # 並列生成済みの画面があれば初回は検証から入る。
                # 無いとき（グラフで生成できなかった）と差し戻し後は作り（直し）
                if fe_attempt > 1 or not html:
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
                failure_notes.append(f"画面検証NG: {_page_reason(fe_result.output)}")
                yield _sse(
                    "retry",
                    attempt=fe_attempt + 1,
                    max=MAX_ATTEMPTS,
                    reason=f"画面: {_page_reason(fe_result.output)}",
                )
                if plan["escalate"] and fe_attempt + 1 == MAX_ATTEMPTS and MAX_ATTEMPTS > 1:
                    yield _sse("escalation", agent="frontend", to_model=PRO)
                    frontend = with_thinking(make_frontend(PRO), think)
                fe_prompt = (
                    f"{base_prompt}\n\n[設計]\n{design}\n\n{contract}\n\n"
                    f"[前回の画面実装]\n{html}\n\n"
                    f"[画面検証の指摘]\n{fe_result.output[-1200:]}\n\n"
                    "上記の問題を必ず修正した画面を作り直してください。"
                )

        # 経験の蓄積（F-08/F-09・v2.9.1）：機械検証の結果だけを信号に学習する
        final_result = fe_result if fe_result is not None else result
        if _MEMORY_ON:
            if memories and final_result is not None:
                # 有用性の実測：想起した教訓が成功に寄与したか（隔離・自浄の判断材料）
                _bank.feedback([m.id for m in memories], final_result.passed)
            if sec_report is not None and not sec_report.passed:
                yield _sse("memory_write", **_remember_security(task_type, sec_report))
            elif final_result is not None and (failure_notes or not final_result.passed):
                # 差し戻しが起きたタスクだけ学習する。初回一発合格は新しい情報が無いので
                # 記録しない（「成功しました」だけのゴミ教訓を作らない）
                draft = await _distill(task_type, failure_notes, final_result)
                if draft is not None:
                    kind = "success" if final_result.passed else "failure"
                    item = _bank.record(task_type, kind, draft["title"], draft["lesson"])
                    yield _sse(
                        "memory_write",
                        kind=item.kind,
                        title=item.title,
                        distilled=True,
                        forgotten=_bank.forget(),
                    )
        # 出力保護（F-11 Model Armor）：納品物に機密データ（PII・APIキー等）が
        # 混ざっていないか最終検査する。報告のみ＝納品は止めず、判断はUIに開示する
        if armor_on():
            deliverable = "\n".join(
                outputs.get(a) or "" for a in ("implementer", "frontend")
            ).strip()
            if deliverable:
                seal = await asyncio.to_thread(sanitize_response, deliverable)
                if seal.checked:
                    yield _sse("armor", stage="response", **seal.model_dump())
        yield _sse("done")
    except TimeoutError:
        # 見張り（guard_silence）の発報：固まったまま待たせず、明示的に知らせる（F-03）
        yield _sse(
            "error",
            message=(
                f"エージェントの応答が{int(_AGENT_TIMEOUT)}秒間途絶えたため中断しました"
                "（HIVE_AGENT_TIMEOUT で調整できます）"
            ),
        )
    except Exception as exc:  # noqa: BLE001 - UIにエラーを流して終了
        yield _sse("error", message=str(exc))
    finally:
        # 裏で走らせた機械検証が残っていれば片付ける（中断時の後始末）
        if verify_task is not None and not verify_task.done():
            verify_task.cancel()


def _remember_security(task_type: str, report: SecurityReport) -> dict:
    """セキュリティ監査の失敗を教訓として記録する（F-08/F-15）。"""
    head = report.headline()
    item = _bank.record(
        task_type, "failure", f"{task_type} セキュリティ: {head[:50]}", f"次回の注意: {head}"
    )
    return {"kind": item.kind, "title": item.title, "forgotten": _bank.forget()}


async def stream(request: Request) -> EventSourceResponse:
    task = request.query_params.get("task") or DEFAULT_TASK
    # effort（さくせん）が正。旧パラメータ quality も互換で受ける
    effort = (
        request.query_params.get("effort")
        or request.query_params.get("quality")
        or "auto"
    )
    return EventSourceResponse(_run_stream(task, effort))


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
