"""router = Function ノード（要件 F-02）。

LLMを使わずコードでルーティング判断する＝コスト$0・決定論的・ハルシネーションなし。
M1では分岐先が「APIパイプライン」1本のみなので、ここではタスク種別・規模を判定して
state に書き出し（後続Agentやログ・可視化が参照）、リクエスト本文をそのまま後続に渡す。

2本目（LP等・M8）を足すときは、戻り値を Event(route=...) にして
workflow 側の edges を {route: node} 形式の分岐に切り替える。
"""

from __future__ import annotations


# サーバー側の実装を明示する語彙（ITを知る人しか使わない＝明示があるときだけAPI系に振る）
_SERVER_WORDS = ("api", "crud", "fastapi", "エンドポイント", "サーバ", "データベース", "restful")
# ページ（読み物）を求める語彙
_PAGE_WORDS = ("lp", "ランディング", "ホームページ", "サイト", "ページ")
# 画面・アプリを求める語彙（サーバー語彙と同時に出たら fullstack）
_UI_WORDS = ("アプリ", "画面", "ゲーム", "ダッシュボード", "管理画面", "ui", "ツール")


def classify(text: str) -> dict[str, str]:
    """タスク文から種別・規模を判定する（副作用なし）。

    server.py（可視化）と route_task の両方から使う共通ロジック。
    既定は app（クライアント完結の単一HTMLアプリ・v2.9）：ターゲットの非エンジニアは
    「オセロ作って」「家計簿アプリ作って」のように発注し、API単体は発注の語彙に無い。
    APIやサーバーを明示した発注だけを api / fullstack に振る。
    """
    text = (text or "").strip()
    lowered = text.lower()
    server = any(k in lowered for k in _SERVER_WORDS)
    ui = any(k in lowered for k in _UI_WORDS)
    if server and ui:
        task_type = "fullstack"  # API + 画面（旧app・M8）
    elif server:
        task_type = "api"  # APIを明示した発注
    elif ui:
        task_type = "app"  # アプリ・ゲーム等の明示（「家計簿アプリのページ」もapp優先）
    elif any(k in lowered for k in _PAGE_WORDS):
        task_type = "lp"
    else:
        task_type = "app"  # 既定＝ブラウザで開くだけで動く単一HTMLアプリ（v2.9）
    scale = "heavy" if len(text) > 200 else "light"
    return {"task_type": task_type, "scale": scale}


def difficulty_rank(task_type: str, scale: str) -> str:
    """クエスト難易度＝討伐ランク（E/C/S）を決定論で判定する（F-02）。

    ユーザーが選ぶ「さくせん（エフォート）」とは独立した軸で、
    発注内容そのものの重さを表す。加点式で透明性を保つ：
    - フルスタック（fullstack）＝API+画面の2成果物 → +1
    - 大規模な発注（scale=heavy） → +1
    0点=E（かんたん）/ 1点=C（ふつう）/ 2点=S（むずかしい）
    """
    points = (1 if task_type == "fullstack" else 0) + (1 if scale == "heavy" else 0)
    return {0: "E", 1: "C", 2: "S"}[points]


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
