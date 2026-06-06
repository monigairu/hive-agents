# Hive ローカル開発コマンド集
# 事前に: cp .env.example .env して値を設定し、`gcloud auth application-default login` 済みであること。
SHELL := /bin/bash
ENV := set -a && source .env && set +a

.PHONY: help test smoke run-local serve-agents stop-agents status run-a2a serve-orchestrator ui

help: ## このヘルプを表示
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

test: ## 単体テスト（google-adk非依存・隔離環境で実行）
	uv run --no-project --with pydantic --with pytest python -m pytest tests -q

smoke: ## M0: ADK→Gemini 疎通確認
	$(ENV) && uv run python scripts/m0_smoke.py

run-local: ## M1: プロセス内でグラフE2E（A2Aなし）
	$(ENV) && uv run python scripts/m1_run.py

serve-agents: ## M2: 全Agentを A2A サーバとして起動（Docker不要）
	./scripts/serve_agents.sh start

stop-agents: ## M2: 全Agentサーバを停止
	./scripts/serve_agents.sh stop

status: ## M2: 各Agentサーバの稼働確認
	./scripts/serve_agents.sh status

run-a2a: ## M2: A2A越しでグラフE2E（先に `make serve-agents` が必要）
	$(ENV) && HIVE_A2A=1 uv run python scripts/m1_run.py

serve-orchestrator: ## M3: OrchestratorのSSEサーバを起動（:8000・フロントが購読）
	$(ENV) && uv run uvicorn agents.orchestrator.server:app --host localhost --port 8000

ui: ## M3: チャットUI(Next.js)を起動（:3000・別ターミナルで serve-orchestrator も必要）
	cd frontend && npm run dev
