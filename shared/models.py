"""Hive のモデル方針を一元管理する（要件 F-13 / F-15）。

- FLASH: 通常の実装系Agentが使う安価・高速モデル
- PRO  : security-reviewer 固定・F-13 の交代（格上げ）先の上位モデル

実モデル名は .env で上書き可能（既定値は gemini-api スキルで確認した最新版）。
"""

import os

FLASH: str = os.environ.get("HIVE_MODEL_FLASH", "gemini-3-flash-preview")
PRO: str = os.environ.get("HIVE_MODEL_PRO", "gemini-3.1-pro-preview")
