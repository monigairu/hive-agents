"use client";

/**
 * クエスト（発注）の共有ストア。
 *
 * SSE接続・イベントログ・セッション履歴をReactページの外で保持する。
 * これにより：
 * - RPG⇔タイムラインをページ遷移しても進行中のクエストが途切れない
 *   （各ページはマウント時に events を再生して途中から表示を復元する）
 * - 履歴は localStorage に保存し、サイドバーから再表示・削除できる
 */

export type HiveEventMsg = { type: string; data: Record<string, unknown> };

export type QuestRecord = {
  id: string;
  task: string;
  status: "running" | "done" | "error";
  startedAt: number;
  events: HiveEventMsg[];
};

const API = process.env.NEXT_PUBLIC_HIVE_API ?? "http://localhost:8000";
const STORAGE_KEY = "hive-quest-history-v1";
const HISTORY_LIMIT = 10;

// サーバが流すSSEイベント名（描画はすべて購読側のマッピングで行う）
const EVENT_NAMES = [
  "task_received",
  "armor",
  "router",
  "intake_start",
  "order_spec",
  "memory_recall",
  "agent_start",
  "agent_output",
  "handoff",
  "security_start",
  "security_result",
  "verify_start",
  "verify_result",
  "retry",
  "escalation",
  "memory_write",
  "done",
];

/** "__reset" は「表示中のクエストが切り替わった（最初から再生し直せ）」の合図。 */
export type QuestListener = (e: HiveEventMsg) => void;

let current: QuestRecord | null = null;
let es: EventSource | null = null;
const listeners = new Set<QuestListener>();

function notify(e: HiveEventMsg) {
  // 購読側の例外でストアの状態管理（履歴保存など）を巻き込まない
  listeners.forEach((fn) => {
    try {
      fn(e);
    } catch (err) {
      console.error("quest listener error:", err);
    }
  });
}

export function subscribe(fn: QuestListener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function getCurrent(): QuestRecord | null {
  return current;
}

export function isRunning(): boolean {
  return current?.status === "running";
}

export function start(task: string, effort: string = "auto") {
  if (isRunning() || !task.trim()) return;
  es?.close();
  current = {
    id: crypto.randomUUID(),
    task,
    status: "running",
    startedAt: Date.now(),
    events: [],
  };
  notify({ type: "__reset", data: {} });

  const src = new EventSource(
    `${API}/stream?task=${encodeURIComponent(task)}&effort=${encodeURIComponent(effort)}`,
  );
  es = src;
  const push = (type: string, data: Record<string, unknown>) => {
    if (!current) return;
    current.events.push({ type, data });
    // 終端イベントは「先に確定・保存」してから通知する
    // （購読側で何が起きても履歴が確実に残るように）
    if (type === "done") {
      finish("done");
      src.close(); // SSEの自動再接続を止める（重要）
    } else if (type === "error") {
      finish("error");
      src.close();
    }
    notify({ type, data });
  };
  for (const name of EVENT_NAMES) {
    src.addEventListener(name, (e) => {
      const raw = (e as MessageEvent).data;
      push(name, raw ? JSON.parse(raw) : {});
    });
  }
  src.addEventListener("error", (e) => {
    const message =
      e instanceof MessageEvent && e.data ? JSON.parse(e.data).message : "接続が切れました";
    push("error", { message });
  });
}

function finish(status: "done" | "error") {
  if (!current) return;
  current.status = status;
  saveToHistory(current);
}

// --- 履歴（localStorage） ---------------------------------------------------

export function history(): QuestRecord[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]") as QuestRecord[];
  } catch {
    return [];
  }
}

function saveToHistory(rec: QuestRecord) {
  try {
    const rest = history().filter((r) => r.id !== rec.id);
    localStorage.setItem(STORAGE_KEY, JSON.stringify([rec, ...rest].slice(0, HISTORY_LIMIT)));
  } catch {
    /* 容量超過などは履歴保存をあきらめる（クエスト自体は継続） */
  }
}

/** 履歴のクエストを表示対象として読み込む（実行はしない）。 */
export function load(id: string) {
  if (isRunning()) return;
  const rec = history().find((r) => r.id === id);
  if (!rec) return;
  es?.close();
  current = rec;
  notify({ type: "__reset", data: {} });
}

/** 履歴から削除する。表示中のものを消しても画面はそのまま（次の発注で上書き）。 */
export function remove(id: string) {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(history().filter((r) => r.id !== id)),
    );
  } catch {
    /* noop */
  }
}
