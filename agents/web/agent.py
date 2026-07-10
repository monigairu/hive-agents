"""Webページ（LP）パイプラインのAgent群（要件 F-02 複数タスク対応・M8）。

designer / implementer という Agent名はAPIパイプラインと共通にしてある。
名前を揃えることで、handoff・可視化（タイムライン/RPG）・修正ループの仕組みを
タスク種別に関係なくそのまま使い回せる（差し込み式の設計）。

デザイン品質は skills/web-design に集約し、両Agentに装着する。
"""

from __future__ import annotations

from google.adk import Agent

from agents.orchestrator.schemas import WebDesignSpec, WebImplementationResult
from shared.models import FLASH, gemini_with_retry
from shared.skills import skill_toolset

_DESIGNER_INSTRUCTION = (
    "あなたはWebデザイナーです。ユーザーの発注（どんなページがほしいか）を受け取り、"
    "web-design スキルの原則に従ってページのデザイン仕様を起こしてください。\n"
    "- overview: 何のページか・誰に向けたものか\n"
    "- personality: ページの性格を1語で決めて振り切る（高級感／親しみ／ミニマル等）\n"
    "- sections: ヒーローからフッターまでのセクション構成。各セクションに入れる実コンテンツの要点も書く\n"
    "- style_direction: 配色（3役）と書体（Google Fonts 2書体）と余白の方針\n"
    "発注に固有名詞がなければ自然な仮名（店名等）を決めること。"
)

_IMPLEMENTER_INSTRUCTION = (
    "あなたはフロントエンド実装者です。前段(designer)が出力したデザイン仕様のJSON"
    "（overview / personality / sections / style_direction / notes）をテキストで受け取ります。"
    "その仕様と web-design スキルの実装ルールに従い、高品質な単一ファイルのHTMLを作ってください。\n"
    "- html: 完全な index.html。CSSは<style>内蔵、外部依存はGoogle Fontsのみ、"
    "外部画像URL禁止（ビジュアルはCSS/インラインSVGで）。実物のコピーを書く（プレースホルダ禁止）\n"
    "- how_to_verify: 保存してブラウザで開く手順と、デザインの見どころ\n"
    "- design_notes: 採用した性格・配色・書体の要約\n"
    "htmlはMarkdownのコードフェンスで囲まず、生のHTMLだけを入れること。"
)


def make_web_designer(model: str = FLASH) -> Agent:
    """web版designer を生成する。グラフを組むたびに新インスタンスを作る。"""
    return Agent(
        name="designer",
        model=gemini_with_retry(model),
        description="発注からWebページのデザイン仕様（性格・構成・スタイル方針）を起こす設計担当",
        output_schema=WebDesignSpec,
        tools=[skill_toolset("web-design")],
        instruction=_DESIGNER_INSTRUCTION,
    )


web_designer_agent = make_web_designer()


def make_web_implementer(model: str = FLASH) -> Agent:
    """web版implementer を任意のモデルで生成する。F-13 の交代（Flash→Pro）で差し替える。"""
    return Agent(
        name="implementer",
        model=gemini_with_retry(model),
        description="デザイン仕様から単一ファイルの高品質なHTMLページを実装する担当",
        output_schema=WebImplementationResult,
        tools=[skill_toolset("web-design")],
        instruction=_IMPLEMENTER_INSTRUCTION,
    )


web_implementer_agent = make_web_implementer()
