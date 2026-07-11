/**
 * F-14 デモモード（v2.13）：`/rpg?demo=1` でバックエンドなしに演出一式を通しで再生する。
 *
 * 代表的なイベント列（並列作業・handoff・監査・機械検証・差し戻し・交代・完了）を
 * 実際のSSEと同じ形で流すだけ。デモ本番の保険＋headlessブラウザでの見た目検証に使う。
 */

import type { HiveGame } from "./game";

type Step = { at: number; type: string; data: Record<string, unknown> };

const PARTY = ["designer", "implementer", "frontend", "tester", "security_reviewer"].map(
  (agent) => ({ agent, role: "" }),
);

const SCRIPT: Step[] = [
  { at: 300, type: "task_received", data: { task: "喫茶店のおしゃれなLPと予約APIを作って" } },
  { at: 1300, type: "armor", data: { stage: "prompt", allowed: true, checked: true, matched: [] } },
  { at: 2200, type: "intake_start", data: {} },
  { at: 3600, type: "order_spec", data: { what: "喫茶店のLP＋予約API（フルスタック）" } },
  {
    at: 4600,
    type: "router",
    data: {
      task_type: "fullstack",
      rank: "S",
      rank_basis: "種別fullstack・機能6個",
      sakusen: "いのちだいじに",
      model: "gemini-2.5-pro",
      party: PARTY,
    },
  },
  {
    at: 6400,
    type: "memory_recall",
    data: { lessons: ["予約フォームは送信後に確認画面を出す"] },
  },
  { at: 7400, type: "agent_start", data: { agent: "designer", detail: "喫茶店LP＋予約APIの設計" } },
  { at: 13500, type: "agent_output", data: { agent: "designer", text: "{}" } },
  {
    at: 13700,
    type: "handoff",
    data: { from_agent: "designer", to_agent: "implementer", item: "せっけいしょ", detail: "予約APIの実装" },
  },
  { at: 13800, type: "agent_start", data: { agent: "implementer", detail: "予約APIの実装" } },
  {
    at: 17400,
    type: "handoff",
    data: { from_agent: "designer", to_agent: "frontend", item: "せっけいしょ", detail: "LPページの実装" },
  },
  // ここから実装担当と画面担当が並列で働く（F-03の可視化）
  { at: 17500, type: "agent_start", data: { agent: "frontend", detail: "LPページの実装" } },
  { at: 26000, type: "agent_output", data: { agent: "implementer", text: "{}" } },
  {
    at: 26300,
    type: "handoff",
    data: { from_agent: "implementer", to_agent: "tester", item: "コード", detail: "予約APIのテスト" },
  },
  { at: 26400, type: "agent_start", data: { agent: "tester", detail: "予約APIのテスト" } },
  { at: 30500, type: "agent_output", data: { agent: "frontend", text: "{}" } },
  { at: 33500, type: "agent_output", data: { agent: "tester", text: "{}" } },
  // 監査（LLM）と機械検証（$0）は並列に走る（v2.11）
  { at: 34400, type: "security_start", data: { attempt: 1 } },
  { at: 34800, type: "verify_start", data: { attempt: 1, mode: "page" } },
  { at: 38200, type: "security_result", data: { passed: true, summary: "もんだいなし" } },
  { at: 39400, type: "verify_result", data: { passed: false, mode: "page" } },
  { at: 40600, type: "retry", data: { attempt: 2, max: 3, reason: "スマホ幅で ボタンが おせない" } },
  { at: 41800, type: "escalation", data: { agent: "frontend", to_model: "pro" } },
  { at: 43600, type: "agent_start", data: { agent: "frontend", detail: "スマホ幅の修正" } },
  { at: 49500, type: "agent_output", data: { agent: "frontend", text: "{}" } },
  { at: 50200, type: "verify_start", data: { attempt: 2, mode: "page" } },
  { at: 52600, type: "verify_result", data: { passed: true, mode: "page" } },
  {
    at: 53800,
    type: "memory_write",
    data: { title: "スマホ幅はボタンを44px以上にする" },
  },
  { at: 54800, type: "armor", data: { stage: "response", allowed: true, checked: true } },
  { at: 55600, type: "done", data: {} },
];

/** デモを開始する。戻り値は中断関数。 */
export function runDemo(game: HiveGame): () => void {
  const timers = SCRIPT.map((s) =>
    window.setTimeout(() => game.enqueue({ type: s.type, data: s.data }), s.at),
  );
  return () => timers.forEach((t) => window.clearTimeout(t));
}
