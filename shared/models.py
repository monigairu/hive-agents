"""Hive のモデル方針を一元管理する（要件 F-13 / F-15）。

- FLASH: 通常の実装系Agentが使う安価・高速モデル
- PRO  : security-reviewer 固定・F-13 の交代（格上げ）先の上位モデル

既定値は 2026-06 時点の最新世代 Gemini 3.5。3.5 Flash は GA、3.5 Pro は提供開始直後のため、
リージョン等で未提供なら .env（HIVE_MODEL_FLASH / HIVE_MODEL_PRO）で上書きする。
"""

import os

FLASH: str = os.environ.get("HIVE_MODEL_FLASH", "gemini-3.5-flash")
PRO: str = os.environ.get("HIVE_MODEL_PRO", "gemini-3.5-pro")
