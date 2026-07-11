#!/usr/bin/env bash
# F-10 Agent Identity の初期セットアップ（1回だけ実行する）
#
# 目的：全Agentが人間の全権限（ADC）を共有する状態をやめ、Agentごとに
# 専用のIAMプリンシパル（サービスアカウント）と最小権限を与える。
# プロンプトインジェクションでAgentが乗っ取られても、そのAgentは
# Vertex AI の呼び出し以外なにもできない（インフラレベルの封じ込め）。
#
# やること（Agentごと：designer / implementer / tester）：
#   1. 専用サービスアカウント hive-<agent>@... を作成（存在すればスキップ）
#   2. roles/aiplatform.user のみ付与（Gemini呼び出しに必要な最小権限）
#   3. 実行ユーザーに、そのSAへの成り代わり権限（TokenCreator）を付与
#   4. 成り代わり用ADC（impersonated_service_account 形式）を .run/identity/ に生成
#      → serve_agents.sh が各Agentプロセスに個別注入する
#
# 使い方:
#   ./scripts/setup_agent_identity.sh
#   ./scripts/serve_agents.sh start   # 以後、各Agentは自分のSAで動く
#
# 注意：TokenCreator 権限の反映には数分かかることがある。直後に
# serve_agents.sh を起動して 403 が出たら少し待って再起動する。
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && source .env; set +a

PROJECT="${GOOGLE_CLOUD_PROJECT:?GOOGLE_CLOUD_PROJECT が未設定です（.env を確認）}"
ACCOUNT="$(gcloud config get-value account 2>/dev/null)"
ADC="${GOOGLE_APPLICATION_CREDENTIALS:-$HOME/.config/gcloud/application_default_credentials.json}"
[ -f "$ADC" ] || { echo "ADCが見つかりません: $ADC（gcloud auth application-default login を実行）"; exit 1; }

AGENTS=(designer implementer tester)
OUTDIR=.run/identity
mkdir -p "$OUTDIR"

# SA作成直後はIAMへの反映に数十秒かかることがある（GCPの結果整合性）。
# 「does not exist」等で失敗したら10秒待って再試行する（最大6回＝約1分）
retry() {
  local n
  for n in 1 2 3 4 5 6; do
    if "$@" >/dev/null 2>&1; then return 0; fi
    echo "   （IAM反映待ち ${n}/6 …10秒後に再試行）"
    sleep 10
  done
  "$@"  # 最終試行はエラーを表示して失敗させる
}

for name in "${AGENTS[@]}"; do
  sa="hive-${name}"
  email="${sa}@${PROJECT}.iam.gserviceaccount.com"
  echo "== ${name}: ${email}"

  if gcloud iam service-accounts describe "$email" --project="$PROJECT" >/dev/null 2>&1; then
    echo "   SAは既に存在"
  else
    gcloud iam service-accounts create "$sa" \
      --project="$PROJECT" \
      --display-name="Hive ${name} agent (F-10 最小権限)" >/dev/null
    echo "   SAを作成"
  fi

  # 最小権限：Vertex AI（Gemini）の呼び出しだけ。ストレージもデプロイ権限も無し
  retry gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:${email}" \
    --role="roles/aiplatform.user" \
    --condition=None --quiet
  echo "   付与: roles/aiplatform.user（最小権限）"

  # 実行ユーザー → このSA への成り代わりを許可
  retry gcloud iam service-accounts add-iam-policy-binding "$email" \
    --project="$PROJECT" \
    --member="user:${ACCOUNT}" \
    --role="roles/iam.serviceAccountTokenCreator" --quiet
  echo "   付与: 成り代わり許可 (${ACCOUNT})"

  # 成り代わり用ADCを生成（source=人間のADC → target=AgentのSA）
  ADC_PATH="$ADC" EMAIL="$email" OUT="$OUTDIR/${name}.json" .venv/bin/python - <<'PY'
import json, os

source = json.load(open(os.environ["ADC_PATH"]))
out = {
    "type": "impersonated_service_account",
    "service_account_impersonation_url": (
        "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/"
        f"{os.environ['EMAIL']}:generateAccessToken"
    ),
    "source_credentials": source,
}
path = os.environ["OUT"]
with open(path, "w") as f:
    json.dump(out, f, indent=2)
os.chmod(path, 0o600)
print(f"   生成: {path}")
PY
done

echo ""
echo "完了。次回の ./scripts/serve_agents.sh start から各Agentが専用IDで動きます。"
echo "確認: Cloud Logging で principal が hive-designer@... 等に分かれていること。"
