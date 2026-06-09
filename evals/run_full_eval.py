"""実パイプラインのゴールデン評価ハーネス（要 google-adk + GCP認証）。

各APIタスクで orchestrator を実走し、生成コードを Hive のサンドボックスで検証する
（verifier-first：LLM審判やROUGE一致でなく「テストが通るか」で採点）。通過率が
golden_tasks.json の threshold 未満なら非ゼロ終了＝生成物品質のCIゲートになる。

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


async def _run_once(task: str) -> dict[str, str]:
    """orchestrator を1回実走し、各Agentの最終出力を返す。"""
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    from agents.orchestrator.workflow import build_workflow

    runner = InMemoryRunner(agent=build_workflow(), app_name="hive-eval")
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


async def main() -> int:
    from shared.sandbox import verify_fastapi

    scored = [t for t in _GOLDEN["tasks"] if t.get("must_pass_tests")]
    passed = 0
    for task in scored:
        outputs = await _run_once(task["task"])
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
