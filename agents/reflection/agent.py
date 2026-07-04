"""reflection Agent（要件 F-09 の最小版・F-08 v2.9.1）：教訓の蒸留担当。

タスク完了後に検証記録（何が失敗し、どう決着したか）を受け取り、同種タスクの
次回に再利用できる**転用可能な一般則**を1文に蒸留する。ReasoningBank（F-08）の
「記録」の質を担保する層で、出力は保存前にさらに write-gate
（shared.memory.acceptable_lesson・決定論チェック）を通る。

学習の暴走を防ぐ設計：
- 入力は機械が作った検証記録のみ（ユーザーの発注文を直接記憶させない＝注入対策）
- 「無理に教訓を作らない」を transferable フラグで構造化（false なら保存されない）
- 蒸留は安価な Flash 固定（記録1件に高級モデルは不要。品質はゲート側で担保）
"""

from __future__ import annotations

from google.adk import Agent

from agents.orchestrator.schemas import LessonDraft
from shared.models import FLASH

_INSTRUCTION = (
    "あなたは開発チームのふりかえり担当です。あるタスクの検証記録"
    "（差し戻しの理由の列と、最終的に合格したか不合格だったか）を受け取り、"
    "同種タスクの次回に再利用できる教訓を蒸留してください。\n"
    "- lesson: 「〜すること」「〜を避けること」の形の一般則を1文で（200字以内・改行なし）\n"
    "- アプリ名・関数名・変数名などタスク固有の名詞を入れない（他のタスクに転用できなくなる）\n"
    "- 記録に書かれていないことを推測で補わない\n"
    "- 記録からこのタスク限りの事情しか読み取れない場合は、無理に教訓を作らず "
    "transferable=false にすること（質の低い教訓は無いほうがよい）\n"
    "- title: どの状況の教訓かがわかる短い見出し（40字以内）"
)


def make_reflection(model: str = FLASH) -> Agent:
    """reflection を生成する。呼び出しごとに新インスタンスを作る（他Agentと同じ理由）。"""
    return Agent(
        name="reflection",
        model=model,
        description="検証記録から再利用可能な教訓を蒸留するふりかえり担当",
        output_schema=LessonDraft,
        instruction=_INSTRUCTION,
    )
