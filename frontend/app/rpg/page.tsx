"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import type { HiveGame } from "./game";

// Orchestrator(SSE) のエンドポイント。デプロイ時は NEXT_PUBLIC_HIVE_API で差し替え。
const API = process.env.NEXT_PUBLIC_HIVE_API ?? "http://localhost:8000";

// ゲームへ転送するSSEイベント（描画はすべて game.ts 側のマッピングで行う）
const EVENTS = [
  "task_received",
  "router",
  "memory_recall",
  "agent_start",
  "agent_output",
  "security_start",
  "security_result",
  "verify_start",
  "verify_result",
  "retry",
  "escalation",
  "memory_write",
  "done",
];

export default function RpgPage() {
  const [task, setTask] = useState("タスク管理のCRUD APIをFastAPIで作って");
  const [running, setRunning] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const gameRef = useRef<HiveGame | null>(null);
  const esRef = useRef<EventSource | null>(null);

  // Phaser はブラウザ専用のため、マウント後に動的importで初期化する
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const { createGame } = await import("./game");
      if (!cancelled && containerRef.current && !gameRef.current) {
        gameRef.current = createGame(containerRef.current);
      }
    })();
    return () => {
      cancelled = true;
      esRef.current?.close();
      gameRef.current?.destroy();
      gameRef.current = null;
    };
  }, []);

  function start() {
    if (running || !task.trim()) return;
    esRef.current?.close();
    setRunning(true);

    const es = new EventSource(`${API}/stream?task=${encodeURIComponent(task)}`);
    esRef.current = es;

    for (const name of EVENTS) {
      es.addEventListener(name, (e) => {
        const raw = (e as MessageEvent).data;
        gameRef.current?.enqueue({ type: name, data: raw ? JSON.parse(raw) : {} });
        if (name === "done") {
          setRunning(false);
          es.close(); // SSEの自動再接続を止める（重要）
        }
      });
    }
    es.addEventListener("error", (e) => {
      const message =
        e instanceof MessageEvent && e.data ? JSON.parse(e.data).message : "接続が切れました";
      gameRef.current?.enqueue({ type: "error", data: { message } });
      setRunning(false);
      es.close();
    });
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-4xl flex-col gap-4 px-4 py-6">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-3xl">🐝</span>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Hive RPG</h1>
            <p className="text-sm text-neutral-500">
              はたらきバチたち（AIエージェント）の仕事ぶりをRPG風に見守る
            </p>
          </div>
        </div>
        <Link href="/" className="text-sm text-amber-600 hover:underline">
          📋 タイムライン表示へ
        </Link>
      </header>

      <div className="flex gap-2">
        <input
          className="flex-1 rounded-lg border border-neutral-300 px-3 py-2 text-sm outline-none focus:border-amber-400 focus:ring-2 focus:ring-amber-200 dark:border-neutral-700 dark:bg-neutral-900"
          value={task}
          onChange={(e) => setTask(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && start()}
          placeholder="例: 在庫管理のCRUD APIを作って"
          disabled={running}
        />
        <button
          onClick={start}
          disabled={running}
          className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-amber-600 disabled:opacity-50"
        >
          {running ? "ぼうけん中…" : "クエスト発注"}
        </button>
      </div>

      <div
        ref={containerRef}
        className="overflow-hidden rounded-xl border border-neutral-800 bg-black"
      />
    </main>
  );
}
