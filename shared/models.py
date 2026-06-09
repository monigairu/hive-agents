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
