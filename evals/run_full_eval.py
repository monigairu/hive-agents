"""実パイプラインのゴールデン評価ハーネス（要 google-adk + GCP認証）。

orchestrator を実走し、生成物を Hive 自身のオラクルで検証する
（verifier-first：LLM審判やROUGE一致でなく機械判定で採点）：
- api タスク：サンドボックスで pytest 実行（must_pass_tests）
- app タスク：構造チェック＋ブラウザ実行検証＝出荷基準（must_pass_app・v2.9）
通過率が golden_tasks.json の threshold 未満なら非ゼロ終了＝生成物品質のCIゲートになる。

実行: make eval-full  （内部: uv run python evals/run_full_eval.py）
google-adk 未導入時はスキップ（終了コード0）。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_GOLDEN = json.loads((Path(__file__).parent / "golden_tasks.json").read_text(encoding="utf-8"))


def _extract(outputs: dict[str, str], author: str, key: str) -> str:
    """Agent出力のJSONテキストから1フィールドを取り出す。"""
    try:
        return str(json.loads(outputs.get(author, "")).get(key, "") or "")
    except (json.JSONDecodeError, AttributeError):
        return ""


async def _run_once(task: str, task_type: str) -> dict[str, str]:
    """orchestrator を1回実走し、各Agentの最終出力を返す。"""
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    from agents.orchestrator.workflow import build_workflow

    runner = InMemoryRunner(agent=build_workflow(task_type), app_name="hive-eval")
    session = await runner.session_service.create_session(app_name="hive-eval", user_id="eval")
    message = types.Content(role="user", parts=[types.Part(text=task)])
    outputs: dict[str, str] = {}
    async for event in runner.run_async(
        user_id="eval", session_id=session.id, new_message=message
    ):
        author = getattr(event, "author", None)
        if author and event.content and event.content.parts:
            text = "".join(p.text for p in event.content.parts if p.text)
            if text:
                outputs[author] = text
    return outputs


def _score_app(outputs: dict[str, str]):
    """app タスクを出荷基準（構造＋ブラウザ実行・F-04 v2.9）で採点する。"""
    from shared.runcheck import check_browser
    from shared.webcheck import check_app

    html = _extract(outputs, "implementer", "html")
    if not html:
        return None
    persistence = _extract(outputs, "designer", "persistence").lower()
    result = check_app(html, persistence)
    return check_browser(html) if result.passed else result


async def main() -> int:
    from shared.sandbox import verify_fastapi

    scored = [
        t for t in _GOLDEN["tasks"] if t.get("must_pass_tests") or t.get("must_pass_app")
    ]
    passed = 0
    for task in scored:
        outputs = await _run_once(task["task"], task["task_type"])
        if task.get("must_pass_app"):
            result = _score_app(outputs)
        else:
            code = _extract(outputs, "implementer", "code")
            test_code = _extract(outputs, "tester", "test_code")
            result = verify_fastapi(code, test_code) if code and test_code else None
        ok = bool(result and result.passed)
        passed += ok
        detail = result.headline() if result else "生成物が得られず"
        print(f"[{'PASS' if ok else 'FAIL'}] {task['id']}: {detail}")

    rate = passed / len(scored) if scored else 1.0
    threshold = _GOLDEN.get("threshold", 0.5)
    print(f"\nスコア: {passed}/{len(scored)} = {rate:.0%}（閾値 {threshold:.0%}）")
    return 0 if rate >= threshold else 1


if __name__ == "__main__":
    try:
        import google.adk  # noqa: F401
    except ImportError:
        print("google-adk 未導入のためスキップ（実評価には ADK + GCP認証が必要）")
        sys.exit(0)
    sys.exit(asyncio.run(main()))
