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

import * as auth from "./auth";

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
  "quota",
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
let abort: AbortController | null = null;
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
  abort?.abort();
  current = {
    id: crypto.randomUUID(),
    task,
    status: "running",
    startedAt: Date.now(),
    events: [],
  };
  notify({ type: "__reset", data: {} });

  const push = (type: string, data: Record<string, unknown>) => {
    if (!current) return;
    current.events.push({ type, data });
    // 終端イベントは「先に確定・保存」してから通知する
    // （購読側で何が起きても履歴が確実に残るように）
    if (type === "done") {
      finish("done");
      abort?.abort(); // 接続を確実に閉じる
    } else if (type === "error") {
      finish("error");
      abort?.abort();
    }
    notify({ type, data });
  };

  // 本番（要ログイン設定）では IDトークンを Authorization ヘッダで添えて発注する。
  // URL（クエリ）に載せるとサーバのアクセスログに残るため、ヘッダで送る。
  const headers: Record<string, string> = {};
  if (auth.authRequired()) {
    const token = auth.getToken();
    if (!token) {
      push("error", { message: "発注にはGoogleログインが必要です（画面右上からログイン）" });
      return;
    }
    headers.Authorization = `Bearer ${token}`;
  }

  const ac = new AbortController();
  abort = ac;
  const url = `${API}/stream?task=${encodeURIComponent(task)}&effort=${encodeURIComponent(effort)}`;
  streamSse(url, headers, ac, push).catch((err) => {
    if (ac.signal.aborted) return; // 自分で閉じた場合はエラー扱いしない
    push("error", { message: err instanceof Error ? err.message : "接続が切れました" });
  });
}

/**
 * fetch ベースのSSE購読。
 * EventSource ではなく fetch を使うのは Authorization ヘッダを付けるため。
 * （EventSource はヘッダ不可・自動再接続の副作用もあるので、ここで自前パースする）
 */
async function streamSse(
  url: string,
  headers: Record<string, string>,
  ac: AbortController,
  push: (type: string, data: Record<string, unknown>) => void,
) {
  const res = await fetch(url, { headers, signal: ac.signal });
  if (!res.ok || !res.body) {
    throw new Error(`サーバに接続できませんでした（HTTP ${res.status}）`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  const known = new Set(EVENT_NAMES);
  let ended = false;

  const dispatch = (block: string) => {
    // SSEの1イベント（event: / data: 行の集まり。":"始まりはping用コメント）
    let event = "message";
    const dataLines: string[] = [];
    for (const line of block.split(/\r\n|\n|\r/)) {
      if (line.startsWith(":")) continue;
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
    }
    const raw = dataLines.join("\n");
    let data: Record<string, unknown> = {};
    try {
      data = raw ? JSON.parse(raw) : {};
    } catch {
      /* JSONでないdataは無視（空オブジェクトで流す） */
    }
    if (event === "error") {
      ended = true;
      push("error", { message: (data.message as string) ?? "接続が切れました" });
    } else if (known.has(event)) {
      if (event === "done") ended = true;
      push(event, data);
    }
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    // イベント区切り（空行）ごとに処理する
    for (;;) {
      const m = buf.match(/\r\n\r\n|\n\n|\r\r/);
      if (!m || m.index === undefined) break;
      const block = buf.slice(0, m.index);
      buf = buf.slice(m.index + m[0].length);
      if (block.trim()) dispatch(block);
      if (ended) return;
    }
  }
  // done/error を受け取らないまま接続が終わった＝異常切断
  if (!ended) push("error", { message: "接続が切れました" });
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
  abort?.abort();
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
