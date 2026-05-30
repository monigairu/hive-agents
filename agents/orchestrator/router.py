"""router = Function ノード（要件 F-02）。

LLMを使わずコードでルーティング判断する＝コスト$0・決定論的・ハルシネーションなし。
M1では分岐先が「APIパイプライン」1本のみなので、ここではタスク種別・規模を判定して
state に書き出し（後続Agentやログ・可視化が参照）、リクエスト本文をそのまま後続に渡す。

2本目（LP等・M8）を足すときは、戻り値を Event(route=...) にして
workflow 側の edges を {route: node} 形式の分岐に切り替える。
"""

from __future__ import annotations


def route_task(node_input: str) -> str:
    """ユーザーのタスク文を受け取り、種別・規模を判定して本文を後続へ渡す。

    Args:
        node_input: ユーザーが発注した自然言語のタスク文。

    Returns:
        後続（designer）に渡すタスク文。M1ではそのまま透過。
    """
    text = (node_input or "").strip()

    # --- タスク種別の簡易判定（M1はAPI固定。判定ロジックの置き場所を確定させる）---
    lowered = text.lower()
    if any(k in lowered for k in ("api", "crud", "fastapi", "エンドポイント")):
        task_type = "api"
    elif any(k in lowered for k in ("lp", "ランディング", "html", "サイト")):
        task_type = "lp"
    else:
        task_type = "api"  # M1の既定はAPIパイプライン

    # --- 規模判定（要件 F-02: light/heavy で動員数・モデルを変える土台）---
    scale = "heavy" if len(text) > 200 else "light"

    print(f"[router] task_type={task_type} scale={scale} len={len(text)}")
    return text
