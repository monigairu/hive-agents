# OpenMythos の流用可否と、生成物品質を上げる最新Tech

> 調査日 2026-06-06 / 5系統の並列Web調査＋反証検証の統合。各主張に信頼度と出典。
> 関連実装: `shared/models.py`（Gemini 3.5）, `agents/orchestrator/retry.py` + `server.py`（自己修正ループ）, `evals/`（評価ハーネス）。

## 0. 結論（3行）

1. **OpenMythos は「モデル構造」の推測再実装で、Hive（エージェント・ハーネス）とは別レイヤー**。A2A/MCP/skills/agentコードは皆無で、コードの流用先がない。**信頼度: 高**
2. **「学習データがない→Geminiの学習データを使う」はカテゴリ錯誤**。Gemini は*モデル*をAPIで貸すのであって学習データは渡さない。Hive に学習データは不要（＝正常）。ただし**「Gemini 3.5」は実在**＝モデル更新は本物の改善レバー。**高**
3. 本命は **ADK純正の品質機構＋定番repoの構造＋実行接地の評価**。本ブランチで実装済み（§3）。

## 1. なぜ OpenMythos を「足せない」か

| 層 | 正体 | 学習データ | Hiveとの関係 |
|---|---|---|---|
| Claude Mythos（本家） | 実在する Anthropic の基盤**モデル**（2026/4発表・サイバーセキュリティ特化・Project Glasswingでゲート・構造非公開） | 非公開 | 直接無関係 |
| OpenMythos（kyegomez） | 上記の**モデル構造の推測再実装**（Recurrent-Depth Transformer + MoE + Multi-Latent Attention, PyTorch, MIT）。**リークではなく理論的再構成**と自認 | 同梱なし（外部FineWeb-Eduを流すだけ） | **別レイヤー**。agent基盤コードは皆無 |
| Hive（本プロジェクト） | ADK + A2A + MCP の**エージェント・ハーネス**。Gemini をAPIで呼ぶ | 不要 | 本丸 |

- OpenMythos を*使える*状態にするには、**自前データ＋膨大なGPUでゼロから事前学習**が必要。完成しても「Geminiより弱い未検証モデル」にしかならず、Hive にとって逆行。**高**
- **kyegomez 注意**: 誇大タイトル・スター水増し・コード品質ムラの定評（swarms商標騒動 等）。OpenMythos も53KBに2ヶ月未満で1.3万スター＋keyword-stuffed topics＝水増しのサイン。**コード流用は非推奨**。**中〜高**

## 2. それでも借りられる「設計の直感」4つ（コードでなく概念）

OpenMythos の構造から、エージェントループに翻訳できる直感（独立検証で数学的妥当性も一部確認）:

1. **目標の再注入**（各反復で入力を再注入し信号ドリフト防止）→ リトライ毎に元の発注を再注入
2. **適応的停止 ACT**（自信が出たら早期終了）→ 固定回数でなく「通った／直っていない」で停止
3. **試行番号の明示**（loop-index）→ 何回目かを伝え戦略を変える
4. **収束する精緻化**（contractive step）→ 修正ループを発散させない

→ **§3 の自己修正ループに 1〜3 を実装**。

## 3. 実装した最新Tech（本ブランチ）

| 項目 | 内容 | 対応 |
|---|---|---|
| **Gemini 3.5 更新** | `shared/models.py` の既定を `gemini-3.5-flash` / `gemini-3.5-pro` に。3.5 Flash は GA、最も安く効く一手 | F-13 |
| **自己修正リトライループ** | 検証が通るまで最大 `MAX_ATTEMPTS` 回リトライ。**目標再注入＋試行番号＋失敗フィードバック**を各試行に投入。試行間で**通過テスト数が最大の成果物を採用（Best-of-N・実行接地）**。**適応的停止**で全通過したら即終了 | F-04 / F-13 / §2 |
| **評価ハーネス** | `evals/`：①決定論ルータのゴールデンゲート（`make eval`・依存なし）②実パイプラインを**サンドボックス採点**（`make eval-full`・要ADK）。**verifier-first**で「テストが通るか」を一次基準に | F-04 |

### ADK標準 `AgentEvaluator` を主軸にしなかった理由
`AgentEvaluator` の `response_match_score` は参照文字列との **ROUGE一致（既定0.8）**。生成コードは正解が一意でなく表現も毎回変わるため、コード品質の指標として機能しにくい。よって Hive は **実行接地（execution-grounded）** を一次基準にした。`AgentEvaluator` は**ツール軌跡の検証**（designer→implementer→tester の順序）に用途を絞るのが妥当（`evals/README.md`）。

## 4. コードでなく“構造”を借りるべき定番repo（OpenMythosの代わり）

| repo | 借りるパターン | Hiveの対応 |
|---|---|---|
| MetaGPT | 役割ごとの**構造化成果物の受け渡し**（PRD→設計→タスク→コード→QA） | DesignSpec/ImplementationResult/TestResult を厳密化 |
| OpenHands | **型付きイベントログ**（Action→sandbox→Observation） | SSEイベント列を型付き契約に昇格（F-14土台） |
| SWE-agent | LLM向けに**設計されたツール面（ACI）** | implementer/tester のツール設計 |
| GitHub Spec Kit | **Spec→Plan→Tasks→Implement**＋各フェーズ検証 | F-02 Phase を仕様駆動で明文化 |

## 5. 出典（主要）
- OpenMythos: github.com/kyegomez/OpenMythos ・ main.py（RDT/MoE/MLA/ACT）・ tinycomputers.io 独立検証
- Claude Mythos: red.anthropic.com/2026/mythos-preview ・ anthropic.com/news/expanding-project-glasswing ・ TechCrunch/CNBC(2026-06-02)
- Gemini 3.5: deepmind.google/models/gemini/flash ・ Vertex `gemini-3.5-flash` docs ・ Google I/O 2026
- 学習/微調整: cloud.google.com Vertex supervised-tuning / distillation / RAG-grounding
- ADK品質: google.github.io/adk-docs（llm-agents/evaluate/callbacks/loop-agents）・ adk-python releases(2.2.0)
- 定番repo: MetaGPT arXiv 2308.00352 ・ OpenHands arXiv 2407.16741 ・ SWE-agent ・ github/spec-kit
- 信頼度注意: openai/swarm#50 ・ HN 41175061 ・ GitHub fake-stars

## 6. 信頼度・留保
- **高**: OpenMythosがモデル構造repoでagentコード皆無／Claude Mythosは実在モデル／学習データ非公開・API経由はモデルのみ／Gemini 3.5実在／ADK 2.2の品質機構／kyegomez評価が二極。
- **割引**: OpenMythosのスター数（水増し疑い）／SWE-bench数値（流動的・要実測）／Gemini 3.5 Pro はGA直後（リージョン未提供なら env で上書き）。
- **未確定**: Claude Mythos内部構造（非公開）／一部一次頁は403で二次corroborate。
