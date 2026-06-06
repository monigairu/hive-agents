# Hive — 要件定義書 v2.3

## 0. このファイルについて

Claude Codeが開発に入る前に読み込む要件定義書。
実装の判断に迷ったときはここに立ち返ること。

**v2.3の主な変更（ADK 2.1 GA対応）**
- **ADK 2.0が正式版（GA）になったため、ベータ前提・リスク受容の記述を全面削除**
- **使用バージョンを ADK 2.1.0（最新安定版）に確定**
- v2.1.0の新機能（スナップショットからのサンドボックス作成）をF-04/F-13に活用
- `pip install google-adk`（`--pre`不要）で導入

> **ADKバージョンについて（事実確認済み）**
> - ADK 2.0は2026年5月19日に正式版（GA）リリース。もうベータではない。
> - 最新安定版は **v2.1.0（2026年5月23日リリース）**。
> - 通常の `pip install google-adk` で v2.1.0 が入る（`--pre`は不要）。
> - ADK 2.0/2.1はWorkflow Runtimeを導入し、階層型エージェント実行からグラフベース実行エンジンに移行。Agent・Tool・Functionがワークフローグラフ内の個別ノードとして評価される。
> - 1.xからの破壊的変更があるため、サンプルコードは2.x系のものを参照すること。

**v2.2からの継続**
- F-13 エージェントの交代（モデル格上げによるエスカレーション）
- F-14 ドラクエ風エージェント可視化
- 差別化軸：Antigravityのブラックボックスを透明化する

**設計の方向性（GAで裏付け済み）**
- ADK 2.xのグラフワークフロー（WorkflowAgent）に基づく動的組成
- Memory StoreをVertex AI Agent EngineのMemory Bank（公式機能）に変更
- SKILL.mdをADK 2.x公式のSkillToolset（3層構造）に変更
- google-agents-cli（7スキル注入）を開発環境に追加
- Agent Identity（IAM個別付与）・Model Armor（セマンティックFW）を任意機能として追加
- Rewindを使った行動の木探索（チャレンジ枠）
- サンドボックス自己検証（v2.1のスナップショット機能で強化）

---

## 1. プロダクト概要

### 1.1 プロダクト名
**Hive**

> 名前の由来：Orchestrator＝女王蜂、各Agent＝働き蜂。マルチエージェント構造と比喩が一致しており、説明なしで伝わる。

### 1.2 一言コンセプト
> 自然言語でソフトウェアを発注できる、**使うたびに賢くなる** Google Cloudネイティブのマルチエージェント開発チーム

### 1.3 背景・解決する課題
- Claude Codeが「個人＋AIチームで会社を立ち上げられる」時代を切り開いている
- しかしClaude Codeは「CLAUDE.mdにペルソナを書いた1つのLLMが全部やる」実態であり、真のマルチエージェントではない
- HiveはADK 2.0 + A2A + MCPを使い、各AgentがCloud Runに独立デプロイされた真のマルチエージェントとして実現する
- 既存のコード生成ツールは「1つのプロンプト→1つの出力」止まり
- **設計→実装→テスト→デプロイ** を複数エージェントが分業・連携して完結するシステムはまだ少ない

### 1.4 Claude Codeとの差別化（ポジション整理）

| 観点 | Claude Code | Hive |
|---|---|---|
| 動作環境 | ローカルのターミナル | Cloud Run（どこからでもAPI呼び出し） |
| Agent実態 | 1つのLLMが複数ペルソナを演じる | 各AgentがCloud Runに独立デプロイ |
| Agent間通信 | なし | A2AプロトコルでHTTP通信 |
| 並列処理 | なし | 複数Agentが同時に動く（Phase 2〜） |
| GCP連携 | 手動 | IAM・Agent Engine・Cloud Loggingと統合 |
| 対象 | 開発者個人 | チーム・他システムからもAPI呼び出し可能 |
| 技術新規性 | プロンプト設計 | ADK 2.0 + A2A + MCP（2026年最先端） |
| 経験の蓄積 | セッションごとにリセット | Agent Engine Memory Bankで成功・失敗が永続化 |

> **Hiveは「Claude Codeの代替」ではなく「Google Cloudネイティブの開発自動化基盤」として位置づける。**
> GCPをすでに使っている企業・チームが、開発自動化をGCPの中で完結させたいニーズに応える。

### 1.4.1 Google Antigravity 2.0との差別化（最重要）

Google I/O 2026でAntigravity 2.0が発表され、「自然言語で発注→マルチエージェントが開発→5分でデプロイ」という機能はGoogle公式が実現した。HiveはAntigravityと正面から機能で competeしない。差別化軸を「透明性」に置く。

| 観点 | Antigravity 2.0 | Hive |
|---|---|---|
| 内部プロセス | ブラックボックス（何が起きているか見えない） | **完全可視化**（Agentの思考・議論・失敗・交代が見える） |
| 思想 | 結果重視（速くデプロイ） | 過程重視（AIが何を考えどう判断したかを人間が理解・監査できる） |
| 実装 | Google製の完成品 | ADK 2.0で内部構造を自前再現＝学習・研究価値 |
| 体験 | 入力→出力 | RPG風にAgentの協働を観察できる（F-14） |

> **Hiveのストーリー**：
> 「Antigravityは個人開発者に開発チームを与えた。しかしそのチームが何を考え、なぜその判断をしたのかは誰も知らない。HiveはADKでAntigravityと同等のことを実現しながら、エージェントの思考プロセスを完全に可視化する。AIが何をしているかを人間が理解・監査できる開発チームを作った。」
> Antigravityは内部構造・論文を公開していないため、これをADKで再現すること自体に学習・研究価値がある。

### 1.5 ターゲットユーザー
- 個人開発者・スタートアップファウンダー
- 「アイデアはあるが実装リソースがない」非エンジニア層
- GCPを使っており開発工数を圧縮したい小規模チーム

### 1.6 提供価値
「自然言語で発注して、数分後にデプロイ済みのプロダクトURLが返ってくる」体験

### 1.7 設計思想：ハーネスエンジニアリング

Hiveの設計は、2026年に急浮上した最新パラダイム **ハーネスエンジニアリング（Harness Engineering）** を体現している。2026年4月のAI Engineer Europe（ロンドン）でOpenAIのRyan Lopopoloが基調講演「Humans Steer, Agents Execute」で論じたホットな概念（※AI Engineer World's Fairは2026/6/29-7/2でまだ未開催のため混同しないこと）。概念の系譜は査読済みのACI（Agent-Computer Interface, Princeton SWE-agent, NeurIPS 2024）に遡れる＝「モデルでなく環境設計が成果を決める」を実証した土台がある。詳細な最新事例比較・導入提案は `docs/harness-engineering-comparison.md` を参照。

- 定義：「エージェント＝モデル＋ハーネス」。モデルの賢さではなく、**モデルが動作する環境（ハーネス）の設計**が成果を決めるという思想
- 核心：「エージェントがミスをするたびに、二度と同じミスをしないよう環境を改善する」（Human Steer, Agent Execute）

**ハーネスの4要素とHiveの対応：**

| ハーネスの4要素 | Hiveの対応機能 |
|---|---|
| ① リポジトリ知識を正本にする | F-08 Memory Bank（成功・失敗・コードベース知識の蓄積） |
| ② エージェントが読める状態にする | F-07 SkillToolset（知識の3層構造） |
| ③ 生成→修正の自走ループ | F-04 フィードバックループ＋サンドボックス自己検証＋F-15 |
| ④ 原則の機械的強制・継続的な掃除 | F-09 Reflection Agent（Memory整理）＋F-13 交代 |

> **審査での訴求**：「Hiveは単なるマルチエージェントではなく、ハーネスエンジニアリングの実装である。各エージェントがミスをするたびにMemory Bankが環境を改善し、二度と同じミスをしない。モデルの賢さではなく環境設計で品質を上げる、2026年最新のパラダイムを体現している。」

---

## 2. 機能要件

### 優先度の定義
- **P0**：MVPに必須。これがなければデモにならない
- **P1**：コア機能。ハッカソン提出までに実装したい
- **P2**：時間があれば実装。なくてもデモは成立する

---

### F-01｜自然言語タスク発注（P0）
- ユーザーがチャットUIで「〇〇を作って」と日本語入力
- Orchestrator が要件を解釈し、グラフワークフローのエントリポイントに渡す
- 入力例：「タスク管理APIを作って」「簡単なLPを作って」

### F-02｜動的エージェント組成（P0）
- **ADK 2.x WorkflowAgent（グラフ構造）で実装**（v1.xのLLMプロンプト任せから変更）
- `router` Function Node がタスク内容を解析し、必要なAgentへ条件分岐
- Function Nodeによる分岐はコスト$0・レイテンシほぼゼロで安定動作
- LLMは各Agentノード内の処理にのみ使用し、ルーティング判断はコードで制御
- 出力スキーマ例（Pydantic + ADK 2.x output_schema）：
  ```python
  class AgentPlan(BaseModel):
      agents: list[str]
      reason: str
      execution_order: list[str]
      phase: str        # どのフェーズに属するか
      scale: str        # "light" | "heavy"（動員規模）
  ```
- 例：
  - 「API作って」→ designer → implementer → tester → devops
  - 「LP作って」→ designer → implementer（HTML/CSS）

- **Phase構造（Discover / Implement / Verify）**
  - Claude CodeのDynamic Workflowsと同様に、ワークフローをフェーズ単位で構成する
  - 例：`Discover`（調査・設計）→ `Implement`（実装）→ `Verify`（検証）
  - グラフをフェーズ単位で設計することで、進捗の可視性（F-14）が高まり、各フェーズ末で検証してから次に進める
  - 各フェーズ内で必要なAgentを並列 or 直列で動かす

- **タスク規模に応じた動員数の自動調整（コスト・速さ・品質を同時に最適化）**
  - routerがタスク規模を判定し、動員するAgent数とモデルを動的に決める
    - **小規模タスク（APIを1つ作る等）** → 3体・直列・Flash中心。速くて安い。非機能要件「5分以内」を死守
    - **大規模タスク（システム全体の設計等）** → 多数・並列・Pro混在。遅いが高品質。デモの目玉
  - 「賢く必要な分だけ動員する」ことで、無駄なトークン消費（=コスト）を抑える
  - Claude CodeのDynamic Workflowsは1回938kトークン消費し「小タスクに使うとコスパが悪い」と公式に警告されている。Hiveはこれを**routerが自動で規模判断する**ことで解決＝差別化ポイント

> **参考：Claude Code「Dynamic Workflows」との関係**
> 2026年、Claude CodeにDynamic Workflows（`workflow`入力で発動、Phase構造＋多数Agent並列＋収束）が追加され、HiveのF-02/F-03とほぼ同方向の実装が実在することが確認された。CyberAgentの実運用コメントでも「単発サブエージェントとフルチーム構築の間のギャップを埋め、visibilityを失わず長時間実行を信頼できる」と評価されている。HiveはこれをGCP（ADK）上で実現し、かつドラクエ風可視化（F-14）と規模自動調整で差別化する。

> **タスク種の方針：設計は複数対応・実装はゴールデンパス1本から（重要）**
> - 個人開発の工数制約下で「広く浅く」を避け、**1種類を完璧に・その過程が全部見える**を狙う。
> - **深さの題材＝「FastAPI CRUD API」に確定**。理由：サンドボックスで起動して `curl` / `pytest` が機械的に白黒つく＝**検証オラクルが最もきれい**で、F-04の自己検証ループ・品質向上の仕組みが綺麗に回る。LP/フロントは「良し悪し」が主観的でオラクルを作りにくいため後回し。
> - ただし **routerの分岐ルールとSkillToolsetは“差し込み式”に設計**し、2本目（LP等）の追加が「分岐1個＋skill1セット＋検証方法の定義」で済むようにしておく。WorkflowAgent・A2A・Memory・可視化などの土台（作業の約8割）は全タスク種で再利用できるため、最初から複数対応しても作業は減らず、リスクの高い初期にデバッグ対象が増えるだけ。
> - **結論：枠は複数対応で開けておき、実装はAPI1本から。複数タスク対応はM8（ストレッチ）で拡張する。**

### F-03｜マルチエージェント実行（P0→直列はP0・並列はP1）
- 各AgentはA2AプロトコルでCloud Runに独立デプロイされた独立サービス
- **Phase 1（MVP）では直列実行**で動作確認を優先する
- **Phase 2以降**でADK 2.x ParallelAgentによる並列実行を追加
- UIに進捗をリアルタイム表示（どのAgentが何をしているか）
- implementerの出力スキーマに`how_to_verify`を含める：
  ```python
  class ImplementationResult(BaseModel):
      code: str
      file_structure: list[str]
      how_to_verify: str  # 例：「curl localhost:8000/tasks で確認できます」
  ```

### F-04｜Agent間フィードバックループ（P1）
- 実装→テスト→レビューの順でAgent間を連携
- ADK 2.x LoopAgent でリトライを実装（最大3回）
- テスト失敗・レビューNGの場合、ループが自動的に implementer に差し戻し
- この「自律的な修正サイクル」がClaude Codeと同様の動きをインフラレベルで実現する
- **サンドボックス自己検証（正攻法として採用）**
  - ADK 2.xの `AgentEngineSandboxCodeExecutor` / `BashTool` を使用
  - **v2.1.0の新機能**：テンプレート・スナップショットからサンドボックスを作成できるため、毎回ゼロから環境構築せず高速に検証環境を立てられる
  - implementerが生成したコードをサンドボックスで実際に実行
  - 失敗ログをimplementerに食わせて自己修正させる
  - LLMが提案・サンドボックスが判定する決定論的なオラクル構造

### F-05｜GitHub連携（MCP経由）（P1）
- 完成コードをGitHubリポジトリにPR自動作成
- GitHub MCP Serverを使用

### F-06｜Cloud Runへの自動デプロイ（P1）
- PRマージ後、GitHub ActionsでCI/CD実行
- Cloud Runに自動デプロイ
- 完成プロダクトのURLをユーザーに返却

### F-07｜SkillToolset（専門知識の段階的開示）（P1に格上げ）
- **ADK 2.x公式の`SkillToolset`を使用**（v1.xの自前SKILL.md実装から変更）
- 3層構造でコンテキスト消費を約90%削減：
  - L1 メタデータ（〜100トークン/スキル）：スキル名・概要。起動時に全スキル分ロード
  - L2 インストラクション（〜5,000トークン）：詳細手順。Agentが必要と判断した時のみロード
  - L3 リソース（可変）：スタイルガイド・APIスキーマ等。L2が要求した時のみ取得
- 対象スキル例：
  - `architecture` → designer
  - `fastapi` → implementer
  - `pytest` → tester
  - `cloud-run` → devops

### F-08｜Memory Store（経験の蓄積）（P1）
- **Vertex AI Agent EngineのMemory Bank（公式機能）を使用**
  - 短期記憶（Sessions）：会話ごとのコンテキスト・思考プロセス・履歴をTTL付きで保持
  - 長期記憶（Memory Bank）：複数会話横断で成功・失敗パターンを永続保存
- v1.xのFirestore自前実装は不要になったため廃止
- 保存する内容：
  - タスクの成功条件・完了戦略
  - よくある失敗とその原因
  - コードベース固有の知識
  - 過去の調査結果（重複調査を防ぐ）
  - 他のAgentが学んだこと（集合知）

- **WTFルール（全AgentのInstructionに追加）**
  - Cursorの「黙って乗り越えるな」思想をAgent Instructionに仕込む
  - タスク実行中に以下を発見したら成果物と一緒に`report`に含める：
    - 詰まった箇所とその原因
    - 想定と違った仕様・挙動
    - 改善できると思ったプロセス
  - 報告がMemory Bankに蓄積され、チーム全体の品質向上につながる

- **MemoryEntryスキーマ**
  ```python
  class MemoryEntry(BaseModel):
      task_id: str
      agent_name: str
      success_patterns: list[str]
      failure_patterns: list[str]
      wtf_reports: list[str]   # WTFルールで報告された内容
      created_at: datetime
  ```

- **AX（エージェント体験）設計（条件付きP1）**
  - Memory Bankの実装が完了し余裕があれば実装・説明軸として追加する
  - 審査説明に使える言葉：「HiveはAX（Agent Experience）を設計しています」
  - **判断基準**：Phase 1終了時点でMemory Bankが安定稼働していれば着手。不安定なら省略。

### F-09｜Reflection Agent（非同期Dreaming相当）（P2）
- タスク完了後に非同期で起動し、本番Agentのレイテンシに影響を与えない
- 処理内容：
  - 複数セッションのログを横断分析して共通の成功・失敗パターンを発見
  - 古い・重複したMemoryを整理・統合
  - 次回AgentのためにMemory Bankを最適化
- デモでの見せ方：「昨日より今日の方が同じミスをしない」を実演

### F-10｜Agent Identity（IAM個別付与）（できたら実施）
- 各AgentにGCPの正規IAMプリンシパルを個別に割り当て
- 最小権限の原則を適用し、Agentが操作できるインフラを制限
- プロンプトインジェクション経由の意図しない操作をインフラレベルで防止
- 審査の「実装力・本番品質」で加点を狙う

### F-11｜Model Armor（セマンティックFW）（できたら実施）
- プロンプトインジェクション・ジェイルブレイク試行をモデルへの到達前にブロック
- 出力保護：クレジットカード番号・APIキー等のPIIを自動マスク（150種類以上）
- Agent Engineとの統合設定

### F-12｜Rewindを使った行動の木探索（チャレンジ枠・P2）
- **ADK 2.x の Rewind / resume を本来の用途とズラして使う「意外性」狙いの目玉機能**
- 本来Rewindは「やり直し」機能だが、これをセーブ＆ロード（アンドゥ）として転用
- 実装イメージ：
  ```
  implementerが同じ地点から複数パターンのコードを生成
    ↓ 各パターンをRewindで分岐シミュレート
    ↓ testerが各パターンを採点
    ↓ 一番スコアの高い枝だけを採用
  ```
- LLMの非決定性を「探索」に変える＝意思決定に対するモンテカルロ木探索／バックトラッキング
- 審査基準「意外性・実装力」に直接訴求する
- **注意**：v2.1.0時点でRewindは「初期セッション状態を保持する」修正済み。実装時はADK 2.x公式サンプルでAPIシグネチャ（`ctx.run_node()`・Rewindの呼び出し方）を確認すること

### F-13｜エージェントの交代（エスカレーション）（P1・品質向上のコア）
- F-04のフィードバックループの発展形。**完成物の品質を確実に上げるための仕組み**
- 同一Agentが規定回数（既定3回）失敗したら、Orchestratorがそのインスタンスを終了し、**上位モデルの新インスタンスに交代**する
- 交代方法は「モデル格上げ」を採用：
  ```
  Gemini Flash で実装 → 失敗
    ↓ リトライ（同じFlashで再挑戦）も失敗
    ↓ エスカレーション（クビ）
  Gemini Pro に格上げした新インスタンスに交代 → 成功率が上がる
  ```
- **採用理由**：失敗の主因は多くがモデルの能力不足。根本原因（モデル能力）を直接叩くのが最も確実で実装も容易
- **副次効果（コスト効率）**：普段は安価なFlashで処理し、詰まったタスクだけPro に格上げ＝「簡単は安く・難しいは賢く」を両立。審査の「実装力」でも説明しやすい
- Cursorの「1回目で失敗したらOpusに上げる」思想と一致
- Phase 3で余裕があれば、モデル格上げに加えてプロンプト変更（別戦略）も併用し「別の新人に交代」感を強化

### F-14｜ドラクエ風エージェント可視化（P2・差別化の目玉）
- **Antigravityがブラックボックスである内部プロセスを、RPG風に完全可視化する**
- A2A通信を「エージェント同士が歩み寄って会話するRPG」として表現
- 可視化する内容：
  - A2A通信 → 関係する2体のキャラが画面中央に歩み寄って会話（💬マーク）
  - 単独作業 → 1体が中央に出て思考中（…）マーク
  - 会話終了 → それぞれ持ち場に戻る
  - パーティーステータス（なまえ・しごと・じょうたい）をドラクエUIで表示
  - F-13の交代 → 「しょうかんかいじょ」「あたらしいAgentがなかまにくわわった」演出
  - WTFレポート → メッセージウィンドウに記録として表示
  - Rewind木探索（F-12）→ 複数案の分岐をツリーで描画
- **データと描画の分離（沼回避の鍵）**
  - Agent間のやり取りを **SSEイベントストリームとして確定**させる（誰→誰・何を・結果）＝これが機能の本体。M3で先に作る。
  - ドラクエ風描画(Phaser.js)は、**同じイベントストリームを「キャラが歩み寄って会話」として描くだけの表示層**＝M7。
  - こうすると、RPG描画が間に合わなくても**機能（タイムライン表示）は残る**。可視化（エージェント間のやり取り）を目玉にするため、まずこのイベント設計を丁寧にやる。
- 技術スタック：
  - ドット絵描画：Phaser.js（HTML5ゲームエンジン）
  - リアルタイム通信：SSE（ADKの各Agent状態・A2Aやり取りを受信）
  - ホスティング：Cloud Run（既存のまま）
  - **サウンドは実装しない**（Tone.js等は対象外。工数を可視化の本体＝やり取りの表現に集中させる）
- **速度問題の解決**：LLM処理の待ち時間（20〜50秒）を、ドラクエの「間（ま）」＝「●●はかんがえている…」演出に転化する
- キャラデザインはエージェントの種類確定後に設計（役割を職業に対応：例 designer=魔法使い系、implementer=戦士系、tester=僧侶系）
- **注意**：可視化レイヤーなので、Hive本体（ADK + Agent）が動いてから着手する。本体未完成のままドット絵から作らない

### F-15｜セキュリティレビューAgent（多層防御）（Phase 2：P1の土台 / Phase 3：ツール武装）
- Claude Codeの公式セキュリティプラグインの設計思想をHiveに移植する
- **コード生成時にセキュリティ監査を行い、脆弱性を検出したらimplementerに差し戻す**（F-04のループに乗せる）
- チェック対象：認可バイパス、安全でない直接オブジェクト参照（IDOR）、インジェクション（SQL/コマンド）、SSRF、弱い暗号、XSS、APIキー露出、危険な権限設定

- **レビュアーの品質を担保する三重構造（最重要）**
  - 弱いレビュアーは「チェックした」という安心感だけ与えて穴を見逃すため、監査側の品質が決定的に重要
  - ① **最上位モデルを固定**：implementerはFlashでも、security-reviewerは必ずGemini Pro（最上位）を使う。Anthropicの公式プラグインもレビューにOpus 4.7を固定使用している
  - ② **決定論的パターンマッチ（第1層・コスト$0）**：`eval(` `os.system` `innerHTML` `sk_live_` 等の既知の危険パターンを機械的に検出。LLMが見落としても確実に拾う土台
  - ③ **実ツール武装（第2層・Phase 3）**：static解析ツール（bandit / semgrep）・依存関係スキャナを実行し、LLMの主観をツールの客観で補強。「LLMがOKと言ってもツールがNGならNG」

- **レビューの独立性**：コードを書いたimplementer自身に採点させず、新しいコンテキストとセキュリティ特化プロンプトを持つ別個体のsecurity-reviewer Agentが監査する（F-04のサンドボックス自己検証・Cursorの赤チーム発想と一致）

- **多層防御（defense in depth）の整理**
  | レイヤー | 担当 | タイミング |
  |---|---|---|
  | コード生成時の監査 | F-15 security-reviewer | implementerの出力直後 |
  | 実行時の入力防御 | F-11 Model Armor | デプロイ後のリクエスト時 |
  - F-15（生成時）とF-11（実行時）は別レイヤー。両方あって多層防御が成立する

- **段階的実装**
  - Phase 2：① 最上位モデル固定 ＋ ② 決定論的パターンマッチ
  - Phase 3：③ 静的解析ツール武装を追加
- ドラクエ可視化（F-14）との相性：security-reviewerを僧侶/賢者系キャラにして「このコードに ぜいじゃくせいあり！」と警告する演出

---

## 3. 非機能要件

| 項目 | 要件 |
|---|---|
| パフォーマンス | 小規模タスク（APIを1つ作る）は目安5分。ただし**5分は厳守ラインではなく、品質を優先してタスクや必要に応じて延ばしてよい**（A2Aホップ＋サンドボックス起動＋リトライを含むと超過し得るため）。大規模タスクは品質優先で時間がかかってよい（規模はrouterが自動判定・F-02） |
| 可用性 | デモ期間中（2026/7/10前後）はダウンしないこと |
| セキュリティ | GitHub・GCPの認証情報は環境変数で管理。ハードコード禁止 |
| 拡張性 | 新しいAgentをA2Aに準拠して追加できる構造にする |
| コスト | 原則は無料枠・サンドボックスで動作させるが、**ハッカソンクーポン（〜5万円相当）の範囲で課金してよい**。Vertex AI Agent Engine（Memory Bank/Sandbox）・Cloud Run複数サービス・security-reviewerのGemini Pro固定は無料枠に収まらない前提で、クーポン内に収める。ハードコードした認証情報の使用は禁止（環境変数管理） |

---

## 4. アーキテクチャ

### 4.1 全体構成図

```
┌──────────────────────────────────────────────────┐
│  Frontend (Next.js + Tailwind CSS)               │
│  Cloud Run にデプロイ                            │
│  - チャットUI                                    │
│  - 進捗リアルタイム表示（SSE）                   │
│  - 完成URLの表示                                 │
└───────────────────┬──────────────────────────────┘
                    │ HTTPS / SSE
                    ▼
┌──────────────────────────────────────────────────┐
│  Orchestrator WorkflowAgent (Cloud Run + ADK 2.x)│
│                                                  │
│  START → [router: Function Node]                 │
│               ↓ 条件分岐（コスト$0）             │
│    ┌──────────┼──────────┬──────────┐            │
│    ▼          ▼          ▼          ▼            │
│  API系      LP系       Script系   その他         │
│  パイプ     パイプ      パイプ                   │
│    └──────────┴──────────┴──────────┘            │
│               ↓                                  │
│         [LoopAgent: リトライ制御]               │
└───┬─────────┬─────────┬─────────┬────────────────┘
    │ A2A     │ A2A     │ A2A     │ A2A
    ▼         ▼         ▼         ▼
┌────────┐┌──────────┐┌────────┐┌────────┐
│designer││implementer││tester  ││devops  │ ...動的に追加可能
│Agent   ││Agent     ││Agent   ││Agent   │
└───┬────┘└───┬───────┘└────────┘└───┬────┘
    │ MCP     │ MCP                  │ MCP
    ▼         ▼                      ▼
┌──────────────────────────────────────────┐
│  GitHub / Cloud Storage / Cloud Run      │
└──────────────────────────────────────────┘
                    ↑
          GitHub Actions (CI/CD)

【Memory Layer（Vertex AI Agent Engine）】
┌──────────────────────────────────────────┐
│  Agent Engine Memory Bank（公式機能）    │
│  - 短期記憶（Sessions）：TTL付き会話履歴 │
│  - 長期記憶（Memory Bank）：永続知識     │
│  ↑↓ 各Agentがタスク前後に読み書き      │
└──────────────┬───────────────────────────┘
               │ 非同期（タスク完了後に起動）
               ▼
┌──────────────────────────────────────────┐
│  Reflection Agent（Dreaming相当・P2）    │
│  - 複数セッションログを横断分析          │
│  - 共通パターン発見・Memory整理・統合    │
│  - 古い/重複Memoryを削除                │
└──────────────────────────────────────────┘
```

### 4.2 技術スタック

| レイヤー | 採用技術 | ハッカソン要件 | 変更 |
|---|---|---|---|
| エージェントFW | **Google ADK 2.1**（最新安定版GA） | 必須②AI技術 ✅ | v2.1 GA |
| ワークフロー制御 | **ADK 2.x WorkflowAgent**（グラフ構造） | 必須②AI技術 ✅ | 新規 |
| LLM | Gemini（Vertex AI / Gemini Enterprise Agent Platform経由） | 必須②AI技術 ✅ | - |
| エージェント間通信 | A2A Protocol（ADKネイティブ） | 最新技術 ✅ | - |
| ツール接続 | MCP（GitHub MCP Server） | 最新技術 ✅ | - |
| アプリ実行環境 | Cloud Run（Agent・フロントエンド全て統一） | 必須①アプリ実行 ✅ | - |
| Memory Store | **Vertex AI Agent Engine Memory Bank**（公式機能） | - | Firestore自前→公式 |
| Skills管理 | **ADK 2.x SkillToolset**（3層構造） | - | 自前→公式 |
| フロントエンド | Next.js + Tailwind CSS | 任意 | - |
| CI/CD | GitHub Actions + Workload Identity Federation | DevOps要素 ✅ | - |
| 監視・ログ | Cloud Logging / Cloud Trace | DevOps要素 ✅ | - |
| コンテナ管理 | Artifact Registry（asia-northeast1） | - | - |
| セキュリティ | Agent Identity + Model Armor（できたら） | - | 新規 |

### 4.3 ADK 2.x ノード構成

| ノード種別 | 用途 | コスト |
|---|---|---|
| LLM Node | 各Agentの推論・コード生成 | トークン消費あり |
| Function Node | routerによる条件分岐・データ変換 | $0・ほぼゼロレイテンシ |
| LoopAgent | フィードバックループ・リトライ制御 | 制御のみ |
| ParallelAgent | 並列実行（Phase 2〜） | 制御のみ |
| SequentialAgent | 直列実行（Phase 1） | 制御のみ |

### 4.4 エージェント一覧

| Agent名 | 役割 | SkillToolset | Phase |
|---|---|---|---|
| Orchestrator（女王蜂） | グラフワークフロー制御・router・Memory参照 | - | 1〜 |
| designer | 仕様書・設計書・ディレクトリ構成の生成 | `architecture` | 1〜 |
| implementer | コード生成（FastAPI等） + how_to_verify | `fastapi` | 1〜 |
| tester | テストコード生成・実行・結果返却 | `pytest` | 1〜 |
| reviewer | コード品質チェック・フィードバック生成 | `code-review` | 2〜 |
| devops | Cloud Runデプロイ・CI/CD設定・URL返却 | `cloud-run` | 2〜 |
| security-reviewer | セキュリティ監査（最上位モデル固定・パターンマッチ・ツール武装） | `security` | 2〜 |
| reflection | セッションログ横断分析・Memory整理（Dreaming相当） | - | 3〜 |

> **security-reviewer のモデル方針**：他Agentと違い、品質担保のため必ずGemini Pro（最上位）を固定使用する。

---

## 5. ユーザーフロー（理想系）

```
Step 1: ユーザーがチャットで入力
        「タスク管理APIを作って。PythonのFastAPIで、
          タスクのCRUDができるもの」

Step 2: WorkflowAgentが起動
        → router（Function Node）がタスクを解析
        → 「API系パイプライン」に分岐
        → UIに「働き蜂を編成しました」と表示

Step 3: SequentialAgentが各Agentを順次呼び出し（Phase 1）
        designer    → 仕様書・ディレクトリ構成を生成
        implementer → FastAPIコード + how_to_verify を生成
        tester      → pytestコードを生成

Step 4: LoopAgentがフィードバックループを制御（Phase 2〜）
        → reviewer がNGなら implementer に差し戻し
        → OKになるまで最大3回リトライ

Step 5: devopsがGitHubにPR自動作成（Phase 2〜）
        → GitHub ActionsでCI/CD実行
        → Cloud Runにデプロイ

Step 6: ユーザーに完成URLを返却
        「✅ デプロイ完了！ https://xxx.run.app」

Step 7: （非同期）Memory Bankに経験を記録
        → 次回タスク開始時に参照して品質向上
```

---

## 6. 開発フェーズ（マイルストーン M0〜M8）

**原則：各マイルストーン末で必ず「見せられるもの」がある**＝途中で時間切れになっても提出物として体裁が整う、垂直スライス方式。

**設計上の最重要な並べ替え（v2.7）**
- **A2A独立デプロイは最初ではなくM2に後ろ倒し**：まず1プロセス内でワークフローを通し（M1）、頭脳のバグとA2A/ネットワークのバグを分離してから外出しする。A2A独立デプロイは審査の差別化核①なので**必ず実装する**が、順序のみ後ろにする。
- **透明性の可視化（やり取り）をM3に前倒し**：差別化核②が一番後回しで切られる事態を防ぐ。RPG描画(M7)の前に、最小可視化（SSEイベント＋タイムライン）を確保する。
- **品質の核（サンドボックス検証・交代・セキュリティ）をMUSTに格上げ**：成果物の品質にこだわるため。

**提出可能ライン（MVP）＝ M3 まで**（自然言語発注→真のマルチエージェントが分業→過程が見える、が成立）。M4以降はすべて品質・体験の強化。

| M | 内容 | 対応F | 区分 | 目安 |
|---|---|---|---|---|
| **M0 地ならし** | uv + ADK 2.1 導入、`LlmAgent`1体がGeminiでローカル応答、Memory Bank API疎通確認 | - | MUST | 〜6/2 |
| **M1 単一プロセスE2E** | WorkflowAgent + router(Function Node) + SequentialAgentで designer→implementer→tester。出力スキーマ確定。**FastAPI CRUDを1本**通す（A2Aなし） | F-01/02/03 | MUST | 〜6/6 |
| **M2 A2A化** | M1のAgentを1体ずつ独立サービス化→composeで全体疎通→Cloud Run。**真のマルチエージェント成立（差別化核①）** | F-03 | MUST | 〜6/13 |
| **M3 可視化（最小・目玉の土台）** | Next.jsチャット + **A2Aやり取りのSSEイベントストリーム＋タイムライン表示（差別化核②）**。RPGではなくまず素の可視化 | F-01/14前倒し | MUST | 〜6/18 |
| **M4 Skill + Memory** | SkillToolset 3層を各Agentに、Memory Bank 読み書き + WTFルール | F-07/08 | MUST | 〜6/22 |
| **M5 品質の核** | サンドボックス自己検証 + LoopAgentフィードバックループ + 交代(Flash→Pro) | F-04/13 | MUST（昇格） | 〜6/28 |
| **M6 セキュリティ** | security-reviewer（Gemini Pro固定 + 決定論的パターンマッチ） | F-15 | MUST（昇格） | 〜7/1 |
| **M7 RPG描画** | M3のイベントを Phaser.js でドラクエ風に描画（**音なし**）。交代＝「しょうかんかいじょ／なかまにくわわった」、脆弱性＝「ぜいじゃくせいあり！」等の演出 | F-14 | SHOULD（目玉） | 〜7/6 |
| **M8 仕上げ・拡張** | GitHub PR/Cloud RunデプロイURL返却(F-05/06)、複数タスク対応拡張(LP等)、F-09 Reflection、F-12 Rewind木探索、F-10/F-11、デモ動画、Proto Pedia | F-05/06/09/12/10/11 | CUT可〜SHOULD | 〜7/10 |

> **M8の中の優先度**：GitHub連携/デプロイURL返却（体験の派手さ）と複数タスク対応（拡張性のアピール）を優先。F-09 Reflection・F-12 Rewind木探索は「面白いが無くてもデモは成立」枠＝明確にCUT可。F-10 Agent Identity・F-11 Model Armorは時間が余れば。
>
> **Phaseの細分化方針**：各Mは必要に応じてさらに小さく割ってよい（例：M2を「1体A2A化」→「全体A2A化」→「Cloud Run化」に分割）。常にデモ可能を維持できる粒度で進める。

---

## 7. ハッカソン提出要件

| 項目 | 内容 |
|---|---|
| 提出〆切 | 2026年7月10日（金）23:59 |
| GitHub URL | 公開リポジトリであること |
| デプロイURL | 動作確認できる状態にしておくこと |
| Proto Pedia | 作品登録プラットフォームから登録 |

---

## 8. 審査基準との対応

| 審査基準 | 本プロダクトの対応 |
|---|---|
| AIエージェントが価値の中心 | WorkflowAgent + 複数Agentの動的組成・分業がなければ成立しない構造 |
| 課題へのアプローチ力 | 「個人が開発チームを持てる民主化」＋「Antigravityのブラックボックスを透明化する」＋ハーネスエンジニアリングの実装というストーリー |
| ユーザビリティ | 自然言語で発注できるチャットUI。専門知識不要 |
| 実用性・体験価値 | 数分でデプロイ＋使うたびに賢くなる＋AIの協働をRPGで観察できる（F-14）＋セキュリティ監査込み |
| 実装力 | ADK 2.x + A2A + MCP + SkillToolset + Memory Bank + Rewind木探索 + モデル格上げ + 多層セキュリティの最先端スタック |

---

## 9. リポジトリ構成

```
hive-agents/
├── agents/
│   ├── orchestrator/
│   │   ├── workflow.py       # WorkflowAgent定義（グラフ・ノード・エッジ）
│   │   ├── router.py         # Function Node（規模判定・条件分岐ロジック）
│   │   ├── schemas.py        # AgentPlan・各出力スキーマ（Pydantic）
│   │   ├── main.py           # uvicorn起動エントリポイント
│   │   ├── Dockerfile
│   │   └── pyproject.toml    # uvで依存管理
│   ├── designer/
│   │   ├── agent.py          # LlmAgent定義
│   │   ├── skills/           # SkillToolset（L1/L2/L3）
│   │   │   └── architecture/
│   │   │       ├── meta.yaml      # L1メタデータ（〜100トークン）
│   │   │       ├── instruction.md # L2インストラクション
│   │   │       └── resources/     # L3リソース
│   │   ├── main.py
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   ├── implementer/          # skills/fastapi/ を含む
│   ├── tester/               # skills/pytest/ を含む
│   ├── reviewer/             # Phase 2〜（コード品質レビュー）
│   ├── security-reviewer/    # Phase 2〜（F-15・skills/security/ を含む・モデルはPro固定）
│   ├── devops/               # Phase 2〜 skills/cloud-run/ を含む
│   └── reflection/           # Phase 3〜（Dreaming相当）
│
├── shared/                   # Agent共通モジュール
│   ├── memory.py             # Agent Engine Memory Bank の読み書きラッパー
│   ├── escalation.py         # F-13 モデル格上げ交代ロジック
│   └── security_patterns.yaml # F-15 決定論的パターンマッチ用ルール
│
├── frontend/                 # Next.js + Tailwind CSS
│   ├── app/
│   │   ├── page.tsx          # メインチャット画面
│   │   └── api/stream/route.ts  # SSEエンドポイント
│   ├── components/
│   │   ├── ChatInput.tsx
│   │   ├── AgentProgressPanel.tsx
│   │   └── ResultDisplay.tsx
│   ├── game/                 # F-14 ドラクエ風可視化（Phaser.js）
│   ├── Dockerfile            # Cloud Runデプロイ用
│   └── package.json
│
├── .github/
│   └── workflows/
│       ├── deploy-agents.yml     # Cloud Run自動デプロイ（Agent群）
│       └── deploy-frontend.yml   # Cloud Run自動デプロイ（フロントエンド）
│
├── Makefile                  # ローカル全Agent起動・停止コマンド
├── compose.yaml              # ローカルで全Agentを同時起動（Docker Compose）
├── REQUIREMENTS.md
└── README.md
```

> **構成の補足**
> - Memory Bank（F-08）はAgent Engineの公式機能を使うため、自前の`memory/`実装フォルダは不要。読み書きラッパーのみ`shared/memory.py`に置く。
> - Python依存管理は **uv**（`pyproject.toml`）を使用。各Agentは独立したサービスなのでAgentごとに依存を管理。
> - ローカルでは`compose.yaml`で全Agentを同時起動し、A2A通信を検証する。

---

## 10. エラーハンドリング方針（MVP基準）

### タイムアウト設定（2層構造）

| スコープ | タイムアウト | 理由 |
|---|---|---|
| 1回のLLM呼び出し | 60秒 | LLMコード生成の実測値（20〜50秒）に余裕を持たせる |
| パイプライン全体 | 300秒 | 非機能要件「5分以内に完成」と整合させる |

### リトライ

- 最大3回（ADK 2.x LoopAgentで実装）
- インターバル：指数バックオフ（5秒 → 10秒 → 20秒）
- **リトライ対象**（エラー種別で区別）：
  - インフラエラー（タイムアウト・5xx）→ バックオフ後リトライ
  - Structured Output形式エラー（JSONパース失敗）→ プロンプトを補正して即リトライ
  - 4xxクライアントエラー → リトライなし（設定ミスのため）

### 全リトライ失敗時
- ユーザーにエラーメッセージを返して終了
- 途中成果物は返さない（全体失敗扱い）

---

## 11. GCP環境構成

### 確定済み設定
- **プロジェクトID**：`hive-dev-2026`
- **デフォルトリージョン**：`asia-northeast1`（東京）
- **Artifact Registry**：`hive-agents`（Dockerリポジトリ）
- **Vertex AI Agent Engine**：Memory Bank有効化

### 有効化済みAPI
```
aiplatform.googleapis.com        # Vertex AI / Agent Engine / Gemini
run.googleapis.com               # Cloud Run
cloudbuild.googleapis.com
secretmanager.googleapis.com
firestore.googleapis.com         # 補助用途
artifactregistry.googleapis.com
storage.googleapis.com
cloudtrace.googleapis.com
iamcredentials.googleapis.com
iam.googleapis.com
```

### GitHub Actions認証
- Workload Identity Federation（サービスアカウントキー不要）
- サービスアカウント：`hive-agent-runner@hive-dev-2026.iam.gserviceaccount.com`
- GitHub Secretsに以下を登録（リポジトリ作成後に設定）：
  - `GCP_PROJECT_ID`
  - `GCP_WORKLOAD_IDENTITY_PROVIDER`
  - `GCP_SERVICE_ACCOUNT`

---

## 12. 開発環境

| 項目 | 内容 |
|---|---|
| OS | Windows + WSL2（Ubuntu） |
| エディタ | **Antigravity IDE**（WSL対応版・要個別ダウンロード） |
| CLI | **google-agents-cli**（ADKコーディング・デプロイ・評価の7スキルをClaude Codeに注入） |
| 言語 | Python 3.11 / TypeScript（Next.js） |
| ADK | google-adk>=2.1.0（`pip install google-adk` で導入。`--pre`不要） |
| Python依存管理 | **uv**（高速・pyproject.tomlで管理。venv/pipの上位互換） |
| コンテナ | Docker（WSL内）＋ Docker Compose（全Agent同時起動） |
| バージョン管理 | Git / GitHub（リポジトリ名：`hive-agents`） |

> **パッケージ管理方針（uv採用）**
> - ローカル開発の依存解決・仮想環境は **uv** に統一（`uv venv` / `uv add` / `uv run`）。pip+venvより圧倒的に高速で、`pyproject.toml`で管理できる。
> - Dockerイメージ内も `uv` でインストールするとビルドが速い。
> - Cloud Runへは各Agentを個別のコンテナとしてデプロイするため、Agentごとに`pyproject.toml`を持つ。

> **⚠️ Gemini CLI廃止注意**
> 2026年6月18日にGemini CLIが完全停止。
> WSL開発を続けるには「Antigravity IDE」を個別ダウンロードする必要あり（スタンドアロン版では不可）。
> 有料APIキー経由のGemini利用はHive本体に影響なし。

> **google-agents-cliについて**
> セットアップするとClaude Code・CursorなどのコーディングエージェントにADK専門スキルが注入される。
> 既にセットアップ済みの可能性あり。未確認の場合はインストールを推奨。

---

## 13. 確定済み設計決定（変更時は理由を記録すること）

| 決定事項 | 内容 | 理由 |
|---|---|---|
| プロダクト名 | Hive | Orchestrator＝女王蜂・Agent＝働き蜂の比喩が構造と一致 |
| ADKバージョン | **ADK 2.1（最新安定版GA）に統一** | 2026/5/19にGA化。ベータではなく安定版として最新グラフ機能をフル活用できる |
| Agent組成ロジック | ADK 2.x WorkflowAgent + router（Function Node） | プロンプト任せより決定論的・ハルシネーション防止・コスト$0 |
| 動員数の自動調整 | routerがタスク規模を判定し動員数・モデルを変える | 小タスクは安く速く、大タスクは高品質。コスト・速さ・品質を同時最適化 |
| ワークフロー構造 | Phase（Discover/Implement/Verify）単位で構成 | 可視性が高まり、各フェーズ末で検証してから次へ進める。Dynamic Workflowsと同方向 |
| チャレンジ枠 | Rewindを使った行動の木探索（F-12） | 審査の「意外性」に直接訴求。ADK 2.xのRewind primitiveを応用 |
| A2A実装方式 | ADKネイティブ（`to_a2a()` / `RemoteA2aAgent`） | 手動HTTP比でIAM統合・プロトコル管理が自動化される |
| MVP実行方式 | SequentialAgent（並列化はPhase 2） | A2A＋並列のデバッグ複雑度を避け、E2E通過を最優先 |
| 開発の進め方 | マイルストーンM0〜M8の垂直スライス（各M末で常にデモ可能） | 個人開発6週間で途中時間切れでも提出物が成立する構造にする |
| A2Aの実装順序 | 最初ではなくM2（まず1プロセス内E2E→外出し） | 頭脳のバグとA2A/ネットワークのバグを分離。A2A独立デプロイ自体は差別化核①として必ず実装 |
| 対象タスク種 | 実装はFastAPI CRUD 1本から（router/skillは差し込み式・複数対応はM8拡張） | APIは検証オラクルが最もきれいで品質ループが回る。土台は全タスク種で再利用でき、初期の複数対応はリスクのみ増える |
| 品質の核の優先度 | サンドボックス検証/交代/セキュリティをMUSTに格上げ | 成果物の品質にこだわるため。品質の劇的な瞬間が可視化の見せ場にもなり一石二鳥 |
| 可視化の実装方式 | データ(SSEイベント)と描画(Phaser)を分離。最小可視化をM3、RPGをM7 | やり取りの可視化を目玉にしつつ、RPG描画が間に合わなくても機能が残る |
| F-14のサウンド | 実装しない（Tone.js対象外） | 工数を可視化の本体＝エージェント間のやり取りの表現に集中させる |
| Memory Store | Vertex AI Agent Engine Memory Bank（公式機能） | Firestore自前実装より工数削減・公式サポート |
| Skills管理 | ADK 2.x SkillToolset（3層構造） | コンテキスト約90%削減・公式パターンに乗れる |
| フィードバック検証 | サンドボックス自己検証（BashTool） | LLM提案・サンドボックス判定の決定論的オラクル |
| 品質向上の仕組み | エージェント交代＝モデル格上げ（Flash→Pro）（F-13） | 失敗の主因はモデル能力不足。根本原因を直接叩くのが最も確実・実装容易・コスト効率も両立 |
| 差別化軸 | Antigravityのブラックボックスを透明化（可視化） | 機能で正面 compete せず「過程の透明性」で差別化。F-14がその体験を担う |
| 可視化方式 | ドラクエ風RPG（Phaser.js + SSE）（F-14） | LLMの待ち時間をRPGの「間」に転化。Antigravityにない記憶に残る体験 |
| フロントエンド | Next.js + Tailwind CSS | AIチャットUIのサンプルが豊富・SSEが実装しやすい・実務転用性高 |
| フロントホスティング | Cloud Run | Firebase App Hostingはベータ。Cloud Runに統一してインフラをシンプルに保つ |
| CI/CD認証 | Workload Identity Federation | サービスアカウントキーのGitHub保存はセキュリティリスク |

---

*作成日：2026年5月*
*更新日：2026年5月30日（v2.7）*
*変更内容（v2.7）：実現可能性レビューを経て開発計画を実態に合わせて確定。① 6章フェーズを M0〜M8 の垂直スライス（常にデモ可能・提出可能ラインはM3）に再構成。② A2A独立デプロイを最初からM2へ後ろ倒し（頭脳のバグとA2Aのバグを分離）、透明性の可視化をM3へ前倒し。③ 対象タスク種を「FastAPI CRUD 1本から（router/skillは差し込み式・複数対応はM8拡張）」に確定（F-02）。④ 品質の核（サンドボックス検証F-04・交代F-13・セキュリティF-15）をMUSTに格上げ。⑤ F-14のサウンド(Tone.js)を廃止し、データ(SSEイベント)と描画(Phaser)を分離してやり取りの可視化を目玉に集中。⑥ 13章 確定事項に上記を追記。なおADK 2.1 GA・SkillToolset・Rewind・AgentEngineSandboxCodeExecutor・Antigravity 2.0・Gemini CLI停止(6/18)はWeb調査で事実確認済み（v2.6の前提は維持）。*
*更新日：2026年5月30日（v2.6）*
*変更内容（v2.6）：リポジトリ構成を最新機能に合わせて更新（security-reviewer追加、shared/に共通モジュール集約、Memory Bankは公式機能のため自前memory/フォルダ削除、frontend/game/にPhaser.js可視化、compose.yaml追加）。リポジトリ名を`hive-agents`に確定。Python依存管理をuv、ローカル全Agent起動をDocker Composeに確定し開発環境セクションに明記。*
*作成者：Tomoki（個人プロジェクト・Findy DevOps AI Agent Hackathon 2026参加作品）*
