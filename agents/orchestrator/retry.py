"""自己修正リトライの純粋ロジック（要件 F-04 / F-13）。

サーバの実行ループから副作用を切り離し、単体テスト可能にした部分。
OpenMythos 調査から得た設計直感を反映する:
- 目標の再注入: 各試行で元の発注仕様を必ず先頭に戻し、文脈ドリフトを防ぐ
- 試行番号の明示: 何回目かを伝え、リトライ毎に戦略を変えさせる
- 失敗フィードバック: 直前の検証失敗の要因を次の試行に渡す
"""

from __future__ import annotations

import os

# 検証が通るまでの最大試行回数（既定3）。F-13のエスカレーション判断にも使う。
MAX_ATTEMPTS: int = int(os.environ.get("HIVE_MAX_ATTEMPTS", "3"))


def build_attempt_message(context: str, task: str, attempt: int, feedback: str) -> str:
    """1試行ぶんの入力メッセージを組み立てる。

    Args:
        context: タスク先頭に常に差し込む文脈（想起した過去の教訓など）。
        task: ユーザーの元の発注仕様（毎回そのまま再注入する）。
        attempt: 1始まりの試行番号。
        feedback: 直前の試行の検証失敗の要因（初回は空）。

    Returns:
        designer 以降に渡す入力テキスト。
    """
    if attempt == 1:
        return context + task
    return (
        f"{context}{task}\n\n"
        f"[再実行 {attempt}/{MAX_ATTEMPTS}] 前回の検証は失敗しました。"
        f"原因: {feedback}\n上記を必ず修正し、同じ失敗を繰り返さないこと。"
    )
