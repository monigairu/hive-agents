"""designer を A2A サービスとして公開する（要件 F-03 / M2）。

起動：
    set -a && source .env && set +a
    uv run uvicorn agents.designer.main:app --host localhost --port 8001

AgentCard は to_a2a が自動生成し、/.well-known/ 配下で配信される。
"""

from __future__ import annotations

import os

from google.adk.a2a.utils.agent_to_a2a import to_a2a

from agents.designer.agent import designer_agent

HOST = os.environ.get("DESIGNER_HOST", "localhost")
PORT = int(os.environ.get("DESIGNER_PORT", "8001"))

app = to_a2a(designer_agent, host=HOST, port=PORT)
