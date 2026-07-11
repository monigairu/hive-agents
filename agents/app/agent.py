"""fullstack（API＋画面）パイプラインのAgent群（要件 F-02/F-03・M8）。

v2.9でタスク種別名を app → fullstack に改名（app はブラウザ完結の単一HTMLアプリ＝
agents/webapp/ が担当）。ファイル・Agent実装は従来のまま。

- app_designer_agent: APIと画面の両方を設計する（Agent名は "designer" で共通化）
- make_frontend / frontend_agent: 画面担当。implementer の成果（APIの契約）に
  従って index.html を実装する。**契約にないエンドポイントを発明しない**（F-03
  「前段出力＝契約」の原則）

バックエンド（implementer）とテスト（tester）はAPIパイプラインのものを再利用する。
"""

from __future__ import annotations

from google.adk import Agent

from agents.orchestrator.schemas import AppDesignSpec, WebImplementationResult
from shared.models import FLASH, gemini_with_retry
from shared.skills import skill_toolset

_DESIGNER_INSTRUCTION = (
    "あなたはフルスタックの設計者です。ユーザーの発注（どんなアプリがほしいか）を受け取り、"
    "API（バックエンド）と画面（フロントエンド）の両方の設計仕様を起こしてください。\n"
    "- overview: 何のアプリか・誰が使うか\n"
    "- endpoints: REST APIのエンドポイント一覧。画面が必要とするデータ操作を過不足なく\n"
    "- screens: 画面の構成。各画面に置く要素（一覧・フォーム・ボタン）を具体的に\n"
    "- style_direction: web-designスキルに従い、画面の性格・配色3役・書体を決める\n"
    "APIは単一ファイルのFastAPI＋インメモリ永続化で実現できる範囲に収めること。"
)

_FRONTEND_INSTRUCTION = (
    "あなたはフロントエンド実装者です。前段(designer)が出力した設計仕様のJSON"
    "（overview / endpoints / screens / style_direction）を受け取り、"
    "そのAPIを呼び出して動く画面（単一ファイルの index.html）を実装してください。\n"
    "- **契約が最優先**：fetch するのは設計の endpoints（差し戻し時は[APIけいやくしょ]）に"
    "書かれたエンドポイントだけ。勝手に新しいパスやレスポンス形を発明しない。"
    "APIの実装完成を待たず、契約だけを頼りに作る（F-03 前段出力＝契約の原則）\n"
    "- APIのベースURLは `const API = \"http://localhost:8001\";` のように定数で先頭に置き、"
    "ユーザーが書き換えられるようにする（8000はHive本体が使うため8001を既定にする）\n"
    "- 読み込み中・空データ・エラーの3状態を必ず画面に出す（fetch失敗で白画面にしない）。"
    "エラー状態には「APIが起動していません。同梱の main.py を "
    "`uvicorn main:app --port 8001` で起動してから再読み込みしてください」と"
    "具体的な復旧手順を表示すること\n"
    "- 見た目は web-design スキルの原則に従う（性格を決めて振り切る・実コピー・外部画像禁止）\n"
    "- html はMarkdownのコードフェンスで囲まず、生のHTMLだけを入れること\n"
    "- how_to_verify: APIの起動（必ず --port 8001 を付ける）→index.htmlを開く→"
    "何を確認するか、の手順"
)


def make_app_designer(model: str = FLASH) -> Agent:
    """フルスタックdesigner を生成する。グラフを組むたびに新インスタンスを作る。"""
    return Agent(
        name="designer",
        model=gemini_with_retry(model),
        description="発注からAPIと画面の両方の設計仕様を起こすフルスタック設計担当",
        output_schema=AppDesignSpec,
        tools=[skill_toolset("api-design", "web-design")],
        instruction=_DESIGNER_INSTRUCTION,
    )


app_designer_agent = make_app_designer()


# appモードの実装担当への責任範囲の限定（F-03 責任分離）。
# 設計書に screens（画面）があっても、画面は frontend 担当の仕事。
# HTMLの埋め込み・配信を実装すると構文エラーや責務混在の温床になるため明示的に禁止する。
APP_IMPLEMENTER_NOTE = (
    "\n【重要・責任範囲】設計の screens（画面）はあなたの担当外です。"
    "HTMLを生成・埋め込み・配信するコードは書かないこと（画面は別の担当が index.html として作る）。"
    "あなたは endpoints のJSON APIだけを実装する。"
    "画面からfetchで呼ばれるため、CORSミドルウェア（全オリジン許可）を必ず有効にすること。"
    "\n【重要・起動】受け取るのはコマンドを使わない人です。ファイル末尾に必ず次を書き、"
    "`python main.py` だけで起動できるようにすること（機械チェックで差し戻されます）：\n"
    'if __name__ == "__main__":\n'
    "    import uvicorn\n"
    '    uvicorn.run(app, host="127.0.0.1", port=8001)\n'
    "how_to_verify には uvicorn コマンドではなく「main.py を python main.py で実行」と書く。"
)


def make_app_implementer(model: str = FLASH) -> Agent:
    """app用implementer：API実装に責任範囲を限定した実装担当を生成する。"""
    from agents.implementer.agent import make_implementer

    return make_implementer(model, APP_IMPLEMENTER_NOTE)


def make_frontend(model: str = FLASH) -> Agent:
    """frontend を任意のモデルで生成する。F-13 の交代（Flash→Pro）で差し替える。"""
    return Agent(
        name="frontend",
        model=gemini_with_retry(model),
        description="API契約に従って画面(index.html)を実装するフロントエンド担当",
        output_schema=WebImplementationResult,
        tools=[skill_toolset("web-design")],
        instruction=_FRONTEND_INSTRUCTION,
    )


frontend_agent = make_frontend()
