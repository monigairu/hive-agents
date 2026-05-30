"""tester を A2A サービスとして公開する（要件 F-03 / M2）。

起動：
    set -a && source .env && set +a
    uv run uvicorn agents.tester.main:app --host localhost --port 8003
"""

from __future__ import annotations

import os

from google.adk.a2a.utils.agent_to_a2a import to_a2a

from agents.tester.agent import tester_agent

HOST = os.environ.get("TESTER_HOST", "localhost")
PORT = int(os.environ.get("TESTER_PORT", "8003"))

app = to_a2a(tester_agent, host=HOST, port=PORT)
