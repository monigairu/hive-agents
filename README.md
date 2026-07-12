# HIVE QUEST 🐝

> 自然言語でソフトウェアを発注できる、**使うたびに賢くなる** Google Cloud ネイティブのマルチエージェント開発チーム

「オセロを作って」と一言発注するだけで、設計・実装・テスト・セキュリティ監査を分業する AI エージェントチームが動き出し、ブラウザで開くだけで動くアプリを納品します。その過程はドラクエ風のレトロ RPG 画面でリアルタイムに可視化され、**誰が・何を・なぜしているか**がすべて見えます。

名前の由来：Orchestrator＝女王蜂、各 Agent＝働き蜂の巣（Hive）に、発注＝クエストを掛けて **HIVE QUEST**。システム内部の名称（リポジトリ・ブランチ prefix・環境変数等）は従来どおり `hive` を使います。

## 特徴

- **自然言語で発注** — 受付 Agent が発注文を「作るもの・主要機能・成功条件」のクエスト依頼書に正規化し、解釈を画面に開示
- **難易度に応じた思考の深さ** — 発注内容から討伐ランク（E/C/S）を自動判定し、Gemini の thinking_level にマッピング。むずかしいクエストほど深く考える
- **出荷基準（Shipping Bar）による機械検証** — 「テストが通る」ではなく「世に出せる」が品質の定義。生成アプリを headless ブラウザで実際に開き、①URL を開くだけで動く ②リロードしてもデータが消えない ③スマホで崩れない ④JS エラーがない、を機械採点して不合格なら差し戻し
- **エージェントの交代（エスカレーション）** — 失敗が続いたら Flash → Pro へモデルを格上げして再挑戦
- **ReasoningBank（経験の蓄積）** — 差し戻しから「転用可能な一般則」を蒸留して永続保存し、次のタスクに注入。害が実測された教訓は隔離・忘却する自浄機能つき
- **三層防御のセキュリティ** — コード生成時の監査（security-reviewer）＋実行時の入力防御（Model Armor）＋インフラの最小権限（Agent 別サービスアカウント）
- **ドラクエ風 RPG 可視化** — タイルマップのギルド作業場で、各エージェントが自分の机で働き、成果物を持って相手の机まで歩いて渡す。並列実行も handoff もそのまま画面に描く「嘘のない可視化」。`?demo=1` でバックエンドなしの通し再生も可能

## アーキテクチャ

各 Agent は Cloud Run 上の独立サービスとしてデプロイでき、公開標準の A2A プロトコルで HTTP 通信します。

```
Frontend (Next.js)  ── SSE ──▶  Orchestrator (ADK 2.x WorkflowAgent)
                                   │ router（決定論・$0）で
                                   │ タスク種別ごとのパイプラインへ分岐
                                   │ 検証ループ・エスカレーション制御
                                   ▼ A2A
        ┌──────────┬─────────────┬────────┬──────────┬───────────────────┐
        │ designer │ implementer │ tester │ frontend │ security-reviewer │
        └──────────┴─────────────┴────────┴──────────┴───────────────────┘
                                   │
                     ReasoningBank（教訓の蒸留・想起・忘却）
```

### エージェント一覧

| Agent | 役割 |
|---|---|
| Orchestrator（女王蜂） | ワークフロー制御・router・検証ループ・Memory 読み書き |
| designer | 設計仕様の生成（features / 受け入れ基準 / 検証スクリプト） |
| implementer | コード生成（単一 HTML アプリ / FastAPI / LP） |
| frontend | API 契約に従う画面実装（fullstack のみ） |
| tester | テストコード生成（実行はサンドボックスが担当） |
| security-reviewer | セキュリティ監査（Gemini Pro 固定） |
| reflection | 差し戻し理由から教訓を蒸留（write-gate 付き） |

### 技術スタック

| レイヤー | 採用技術 |
|---|---|
| エージェント FW | Google ADK 2.x（WorkflowAgent・グラフ実行） |
| LLM | Gemini（Vertex AI 経由・Flash / Pro を使い分け） |
| エージェント間通信 | A2A Protocol |
| ツール接続 | MCP |
| 実行環境 | Cloud Run |
| フロントエンド | Next.js + Tailwind CSS |
| セキュリティ | Model Armor + Agent Identity（IAM 個別付与） |

## クイックスタート

### 前提

- Python 3.11+ / [uv](https://docs.astral.sh/uv/)
- Node.js（フロントエンド用）
- Google Cloud プロジェクト（Vertex AI API 有効化済み）

### セットアップ

```bash
# 1. 認証（ADC）
gcloud auth application-default login
gcloud auth application-default set-quota-project <PROJECT_ID>

# 2. 環境変数
cp .env.example .env   # GOOGLE_CLOUD_PROJECT 等を設定

# 3. 疎通確認
make smoke
```

### 起動

```bash
# ターミナル1: Orchestrator（SSE サーバ・:8000）
make serve-orchestrator

# ターミナル2: チャット UI（:3000）
make ui
```

ブラウザで http://localhost:3000 を開き、作りたいものを日本語で発注してください。

### 主なコマンド

```bash
make help               # コマンド一覧
make test               # 単体テスト（GCP 不要・隔離環境）
make eval               # ルータのゴールデンテスト（依存なし）
make eval-full          # 実パイプラインのサンドボックス採点（要 GCP 認証）
make run-local          # プロセス内でグラフ E2E（A2A なし）
make serve-agents       # 全 Agent を A2A サーバとして起動
make run-a2a            # A2A 越しでグラフ E2E
make armor-setup        # F-11: Model Armor セットアップ（1回だけ・任意）
make identity-setup     # F-10: Agent 別サービスアカウント作成（1回だけ・任意）
```

### 主な環境変数

| 変数 | 既定 | 説明 |
|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | — | GCP プロジェクト ID（必須） |
| `HIVE_SECURITY` | `1` | セキュリティ監査（`pattern`=決定論のみ / `0`=無効） |
| `HIVE_ARMOR` | `1` | Model Armor 実行時防御（未セットアップ環境では自動スキップ） |
| `HIVE_MEMORY` | `1` | ReasoningBank の想起・記録（`0` で無効化） |
| `HIVE_INTAKE` | `1` | 発注ゲート＝クエスト依頼書（`0` で無効化） |
| `HIVE_AGENT_TIMEOUT` | `300` | 沈黙タイムアウト秒（イベント間の無応答を監視） |

セキュリティ機能はすべて**フェイルオープン**：未整備の環境では検査をスキップして通常運転し、セキュリティ機能の不調で本体を止めません。

## リポジトリ構成

```
agents/          各 Agent（orchestrator / designer / implementer / tester / ...）
shared/          共有ライブラリ（モデル選択・サンドボックス・検証・Memory・Armor）
skills/          SkillToolset 用の専門知識カタログ（web-app / fastapi / security / ...）
frontend/        Next.js チャット UI ＋ RPG 可視化
scripts/         起動・疎通確認・セットアップスクリプト
tests/           単体テスト
evals/           評価ハーネス（ゴールデンテスト・出荷基準 eval）
REQUIREMENTS.md  要件定義書（実装判断の基準はここに立ち返る）
```

## ライセンス

[MIT](LICENSE)
