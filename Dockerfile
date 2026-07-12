# Cloud Run 手動デプロイ用（orchestrator を M1 プロセス内モードで動かす）
# ビルドは gcloud run deploy --source . が Cloud Build 上で実行する。
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_LINK_MODE=copy

# 依存だけ先に入れてレイヤーキャッシュを効かせる
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 実行に必要なのは agents / shared / skills（shared/skills.py が skills/ を実行時に読む）
COPY agents ./agents
COPY shared ./shared
COPY skills ./skills
RUN uv sync --frozen --no-dev

# Cloud Run は $PORT で待ち受け必須（0.0.0.0 でないと起動失敗）
CMD ["sh", "-c", "uv run --no-sync uvicorn agents.orchestrator.server:app --host 0.0.0.0 --port ${PORT:-8080}"]
