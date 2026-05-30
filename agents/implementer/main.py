"""implementer を A2A サービスとして公開する（要件 F-03 / M2）。

起動：
    set -a && source .env && set +a
    uv run uvicorn agents.implementer.main:app --host localhost --port 8002
"""

from __future__ import annotations

import os

from google.adk.a2a.utils.agent_to_a2a import to_a2a

from agents.implementer.agent import implementer_agent

HOST = os.environ.get("IMPLEMENTER_HOST", "localhost")
PORT = int(os.environ.get("IMPLEMENTER_PORT", "8002"))

app = to_a2a(implementer_agent, host=HOST, port=PORT)
