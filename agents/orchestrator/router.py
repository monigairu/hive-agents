"""router = Function ノード（要件 F-02）。

LLMを使わずコードでルーティング判断する＝コスト$0・決定論的・ハルシネーションなし。
M1では分岐先が「APIパイプライン」1本のみなので、ここではタスク種別・規模を判定して
state に書き出し（後続Agentやログ・可視化が参照）、リクエスト本文をそのまま後続に渡す。

2本目（LP等・M8）を足すときは、戻り値を Event(route=...) にして
workflow 側の edges を {route: node} 形式の分岐に切り替える。
"""

from __future__ import annotations


def classify(text: str) -> dict[str, str]:
    """タスク文から種別・規模を判定する（副作用なし）。

    server.py（可視化）と route_task の両方から使う共通ロジック。
    """
    text = (text or "").strip()
    lowered = text.lower()
    if any(k in lowered for k in ("api", "crud", "fastapi", "エンドポイント")):
        task_type = "api"  # APIを明示した発注が最優先
    elif any(k in lowered for k in ("lp", "ランディング", "ホームページ", "サイト", "ページ")):
        task_type = "lp"
    elif any(
        k in lowered for k in ("アプリ", "画面", "ダッシュボード", "管理画面", "フルスタック", "ui")
    ):
        task_type = "app"  # API + 画面のフルスタック（M8）
    else:
        task_type = "api"  # 既定はAPIパイプライン
    scale = "heavy" if len(text) > 200 else "light"
    return {"task_type": task_type, "scale": scale}


def route_task(node_input: str) -> str:
    """ユーザーのタスク文を受け取り、種別・規模を判定して本文を後続へ渡す。

    Args:
        node_input: ユーザーが発注した自然言語のタスク文。

    Returns:
        後続（designer）に渡すタスク文。M1ではそのまま透過。
    """
    text = (node_input or "").strip()
    decision = classify(text)
    print(
        f"[router] task_type={decision['task_type']} "
        f"scale={decision['scale']} len={len(text)}"
    )
    return text
