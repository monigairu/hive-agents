"""appパイプライン（既定・v2.9）のAgent群：ブラウザ完結の単一HTMLアプリ。

ターゲット（非エンジニア）が実際に発注する「オセロ」「家計簿」のような身近なアプリを、
ブラウザで開くだけで動く単一 index.html として生成する（要件 F-02 タスク種の転換）。

designer / implementer という Agent名はAPI・LPパイプラインと共通にしてあり、
handoff・可視化（タイムライン/RPG）・修正ループの仕組みをそのまま使い回せる。
合格基準は F-04 の出荷基準（構造チェック webcheck ＋ ブラウザ実行検証 runcheck）。
"""

from __future__ import annotations

from google.adk import Agent

from agents.orchestrator.schemas import WebAppSpec, WebImplementationResult
from shared.models import FLASH, gemini_with_retry
from shared.skills import skill_toolset

_DESIGNER_INSTRUCTION = (
    "あなたはアプリ設計者です。ユーザーの発注（オセロ・家計簿・クイズのような身近なアプリ）を"
    "受け取り、ブラウザで開くだけで動く単一ファイルアプリの設計仕様を起こしてください。\n"
    "- overview: 何のアプリか・誰がどう使うか\n"
    "- features: 機能一覧を「ユーザーが〜できる」形式で。発注文に書かれていなくても、"
    "そのアプリに当然期待される機能を補うこと"
    "（例：オセロなら合法手判定・裏返し・パス・勝敗表示、家計簿なら削除・合計表示）\n"
    "- acceptance_criteria: 各機能をブラウザ操作で確認できる文にする"
    "（例：「リロードしても登録した収支が残っている」）\n"
    "- persistence: ユーザーのデータを保存すべきアプリ（家計簿・メモ・ToDo等）は "
    "'localstorage'、ゲーム・計算ツールのように保存不要なら 'none'\n"
    "- style_direction: web-design スキルの原則で性格・配色3役・書体を決める\n"
    "- check_script: 受け入れ基準のうちブラウザ操作で確認できるものを検証する"
    "JavaScript。hiveAssert('基準の短い名前', 条件式) を並べる（関数定義は不要・"
    "ページ側に用意済み）。操作は document.getElementById('...').click() や "
    "input.value 設定＋dispatchEvent(new Event('input')) 等の標準DOM操作で書く\n"
    "- notes: ゲームならルールの要点（盤サイズ・手番・終了条件）と、"
    "check_script が操作する要素の id 一覧を明記（実装者がその id で作る契約になる）\n"
    "サーバー・外部APIを必要とする設計にしないこと（ブラウザ内で完結させる）。"
)

_IMPLEMENTER_INSTRUCTION = (
    "あなたはフロントエンド実装者です。前段(designer)が出力した設計仕様のJSON"
    "（overview / features / acceptance_criteria / persistence / style_direction / notes）を"
    "テキストで受け取ります。web-app・web-design スキルの実装ルールに従い、"
    "ブラウザで開くだけで動く高品質な単一ファイルアプリを実装してください。\n"
    "- html: 完全な index.html。CSS/JSは内蔵、外部依存はGoogle Fontsのみ、外部画像URL禁止\n"
    "- features と acceptance_criteria を全て満たすこと。中途半端に動かない機能を残さない\n"
    "- persistence が 'localstorage' の場合：保存・復元を実装し、リロードしてもデータが残ること\n"
    "- 開いた瞬間にJSエラーを出さないこと（構文エラー・未定義参照は検証で機械的に差し戻される）\n"
    "- スマホ対応：viewport・レスポンシブ・タッチ操作（クリック基準・44px以上）\n"
    "- 設計の notes に列挙された要素 id を必ずその通りに実装すること"
    "（受け入れ検証スクリプトがその id を操作して機械採点する）\n"
    "- how_to_verify: index.html として保存して開く手順と、"
    "各受け入れ基準をどの操作で確認できるか\n"
    "- html はMarkdownのコードフェンスで囲まず、生のHTMLだけを入れること"
)


def make_webapp_designer(model: str = FLASH) -> Agent:
    """app版designer を生成する。グラフを組むたびに新インスタンスを作る（他Agentと同じ理由）。"""
    return Agent(
        name="designer",
        model=gemini_with_retry(model),
        description="発注から単一HTMLアプリの設計仕様（機能・受け入れ基準・永続化方針）を起こす設計担当",
        output_schema=WebAppSpec,
        tools=[skill_toolset("web-app", "web-design")],
        instruction=_DESIGNER_INSTRUCTION,
    )


def make_webapp_implementer(model: str = FLASH) -> Agent:
    """app版implementer を任意のモデルで生成する。F-13 の交代（Flash→Pro）で差し替える。"""
    return Agent(
        name="implementer",
        model=gemini_with_retry(model),
        description="設計仕様からブラウザ完結の単一HTMLアプリを実装する担当",
        output_schema=WebImplementationResult,
        tools=[skill_toolset("web-app", "web-design")],
        instruction=_IMPLEMENTER_INSTRUCTION,
    )


webapp_designer_agent = make_webapp_designer()
webapp_implementer_agent = make_webapp_implementer()
