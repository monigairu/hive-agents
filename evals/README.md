# evals — 生成物品質の評価ハーネス（F-04 / 品質ゲート）

「賢いモデルより検証（verifier）を先に作る」原則に基づく評価ハーネス。
ゴールデンタスク（`golden_tasks.json`）を正本に、2段階で品質を測る。

## 1. 決定論ゲート（高速・依存なし）

`router.classify` の種別・規模判定をゴールデンに対して検証する。LLMを使わないので
隔離環境で即実行でき、CIの第1関門になる。

```bash
make eval        # = uv run --no-project --with pydantic --with pytest pytest evals/test_router_golden.py -q
```

## 2. 実パイプライン採点（要 ADK + GCP認証）

orchestrator を実走し、生成コードを Hive のサンドボックス（`verify_fastapi`）で検証。
**「テストが通るか」で採点**し、通過率が `threshold` 未満なら非ゼロ終了する。

```bash
make eval-full   # = uv run python evals/run_full_eval.py
```

## なぜ ADK 標準の `AgentEvaluator` を主軸にしないか

ADK の `AgentEvaluator` は有用だが、最終応答を `response_match_score`
（参照文字列との ROUGE 一致・既定0.8）で評価する。**生成コードは正解が一意でなく
表現も毎回変わる**ため、ROUGE一致はコード生成の品質指標として機能しにくい。
そこで Hive では「実行して通るか」を一次の合否基準に置いた（execution-grounded /
verifier-first）。

`AgentEvaluator` を併用する場合は、**ツール軌跡の検証**（`tool_trajectory_avg_score`：
designer→implementer→tester の順で呼ばれたか）に用途を絞り、`.evalset.json` を
`adk eval` で生成・検証してから追加するのが安全。
