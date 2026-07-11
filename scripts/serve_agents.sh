#!/usr/bin/env bash
# Hive ローカル全Agent起動/停止（Docker不要・A2A多プロセス検証用・M2）
# 使い方:
#   ./scripts/serve_agents.sh start   # designer/implementer/tester を A2A サーバ起動
#   ./scripts/serve_agents.sh stop    # 全停止
#   ./scripts/serve_agents.sh status  # 稼働確認
set -euo pipefail
cd "$(dirname "$0")/.."

set -a; [ -f .env ] && source .env; set +a

RUNDIR=.run
mkdir -p "$RUNDIR"

# name:port
AGENTS=("designer:8001" "implementer:8002" "tester:8003")

start() {
  for entry in "${AGENTS[@]}"; do
    name="${entry%%:*}"; port="${entry##*:}"
    # F-10 Agent Identity：成り代わりADCがあればAgent専用IDで動かす（無ければ従来通り人間のADC）
    # 生成は ./scripts/setup_agent_identity.sh（1回だけ）
    id_env=()
    id_file="$PWD/$RUNDIR/identity/${name}.json"
    if [ -f "$id_file" ]; then
      id_env=("GOOGLE_APPLICATION_CREDENTIALS=${id_file}")
      echo "identity: ${name} は専用SA（hive-${name}）で起動"
    fi
    nohup env "${id_env[@]}" uv run uvicorn "agents.${name}.main:app" --host localhost --port "$port" \
      > "$RUNDIR/${name}.log" 2>&1 &
    echo $! > "$RUNDIR/${name}.pid"
    echo "started ${name} on :${port} (pid $(cat "$RUNDIR/${name}.pid"))"
  done
  echo "AgentCard を待機中..."
  for entry in "${AGENTS[@]}"; do
    port="${entry##*:}"
    for _ in $(seq 1 30); do
      code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${port}/.well-known/agent-card.json" || true)
      [ "$code" = "200" ] && break
      sleep 1
    done
    echo "  :${port} -> ${code}"
  done
}

stop() {
  for entry in "${AGENTS[@]}"; do
    name="${entry%%:*}"; port="${entry##*:}"
    fuser -k "${port}/tcp" 2>/dev/null || true
    rm -f "$RUNDIR/${name}.pid"
    echo "stopped ${name} (:${port})"
  done
}

status() {
  for entry in "${AGENTS[@]}"; do
    name="${entry%%:*}"; port="${entry##*:}"
    code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${port}/.well-known/agent-card.json" || true)
    echo "${name} :${port} -> ${code}"
  done
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  *) echo "usage: $0 {start|stop|status}"; exit 1 ;;
esac
