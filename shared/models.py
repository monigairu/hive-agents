"""Hive のモデル方針を一元管理する（要件 F-13 / F-15）。

- FLASH: 通常の実装系Agentが使う安価・高速モデル
- PRO  : security-reviewer 固定・F-13 の交代（格上げ）先の上位モデル

既定値は 2026-06 時点で hive-dev-2026 に対し実APIで疎通確認した版：
- FLASH = gemini-3.5-flash（GA・確認済み）
- PRO   = gemini-3.1-pro-preview（確認済み）。※ gemini-3.5-pro は当プロジェクトで 404
  （未提供）だったため採用せず。提供開始後は .env の HIVE_MODEL_PRO で上書きする。
"""

import os

FLASH: str = os.environ.get("HIVE_MODEL_FLASH", "gemini-3.5-flash")
PRO: str = os.environ.get("HIVE_MODEL_PRO", "gemini-3.1-pro-preview")


def gemini_with_retry(name: str):
    """一時的なAPI障害に自動再試行するGeminiクライアントを作る（F-03 安定化）。

    google-genai は retry_options を渡さない限り一切再試行しない。
    HttpRetryOptions() を渡すとライブラリ標準の再試行が効く：
    計5回・指数バックオフ（1→2→4→8秒）・対象は 408/429/5xx と接続断。
    再試行しても駄目な障害は従来どおり例外＝server.py の見張り（watchdog）が拾う。
    全Agentファクトリはモデル名の文字列でなくこれを使う。
    ADK は遅延import（tests/ の隔離実行を保つため）。
    """
    from google.adk.models.google_llm import Gemini
    from google.genai import types

    return Gemini(model=name, retry_options=types.HttpRetryOptions())


def with_thinking(agent, level: str | None):
    """Agentに思考レベル（Gemini 3 の thinking_level）を設定して返す（F-02）。

    level は "MINIMAL" | "LOW" | "MEDIUM" | "HIGH"。None なら何もしない
    （モデル既定のまま）。google-genai は遅延import（tests/ の隔離実行を保つため）。
    """
    if level:
        from google.genai import types

        agent.generate_content_config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level=level)
        )
    return agent
