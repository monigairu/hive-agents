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

/** 完了時に表示する成果物（各Agentの最終出力JSONから組み立てる）。 */
type Artifact = {
  overview: string;
  endpoints: string[];
  code: string;
  howToVerify: string;
  testSummary: string;
  testCode: string;
};

function buildArtifact(outputs: Record<string, string>): Artifact | null {
  const parse = (agent: string): Record<string, unknown> => {
    try {
      return JSON.parse(outputs[agent] ?? "");
    } catch {
      return {};
    }
  };
  const design = parse("designer");
  const impl = parse("implementer");
  const test = parse("tester");
  if (!impl.code) return null;
  return {
    overview: String(design.overview ?? ""),
    endpoints: (design.endpoints as string[]) ?? [],
    code: String(impl.code ?? ""),
    howToVerify: String(impl.how_to_verify ?? ""),
    testSummary: String(test.summary ?? ""),
    testCode: String(test.test_code ?? ""),
  };
}

export default function RpgPage() {
  const [task, setTask] = useState("タスク管理のCRUD APIをFastAPIで作って");
  const [running, setRunning] = useState(false);
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const gameRef = useRef<HiveGame | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const outputsRef = useRef<Record<string, string>>({});

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
    setArtifact(null);
    outputsRef.current = {};

    const es = new EventSource(`${API}/stream?task=${encodeURIComponent(task)}`);
    esRef.current = es;

    for (const name of EVENTS) {
      es.addEventListener(name, (e) => {
        const raw = (e as MessageEvent).data;
        const data = raw ? JSON.parse(raw) : {};
        gameRef.current?.enqueue({ type: name, data });
        if (name === "agent_output") {
          outputsRef.current[String(data.agent)] = String(data.text ?? "");
        }
        if (name === "done") {
          setArtifact(buildArtifact(outputsRef.current));
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

      {artifact && (
        <section className="rounded-xl border-2 border-amber-400 bg-amber-50 p-4 text-sm dark:bg-amber-950/30">
          <h2 className="text-base font-bold text-amber-900 dark:text-amber-200">
            🏆 ほうしゅう（できあがった成果物）
          </h2>
          {artifact.overview && (
            <p className="mt-2 text-neutral-800 dark:text-neutral-200">{artifact.overview}</p>
          )}
          {artifact.endpoints.length > 0 && (
            <div className="mt-3">
              <div className="font-semibold text-neutral-700 dark:text-neutral-300">
                つかえるAPI（エンドポイント）
              </div>
              <ul className="mt-1 list-disc pl-5 text-neutral-600 dark:text-neutral-400">
                {artifact.endpoints.map((ep, i) => (
                  <li key={i}>
                    <code className="text-xs">{ep}</code>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {artifact.howToVerify && (
            <div className="mt-3">
              <div className="font-semibold text-neutral-700 dark:text-neutral-300">
                ✅ 自分のPCで動かして確認する方法
              </div>
              <pre className="mt-1 overflow-auto whitespace-pre-wrap rounded-lg bg-neutral-950 p-3 text-[11px] leading-relaxed text-neutral-100">
                {artifact.howToVerify}
              </pre>
            </div>
          )}
          {artifact.testSummary && (
            <p className="mt-3 text-xs text-neutral-600 dark:text-neutral-400">
              🧪 テスト：{artifact.testSummary}（サンドボックスで実際に動くことを確認済み）
            </p>
          )}
          <div className="mt-3 flex flex-col gap-2">
            {artifact.code && (
              <details>
                <summary className="cursor-pointer text-xs font-semibold text-amber-700">
                  📜 生成されたコードを見る（main.py）
                </summary>
                <pre className="mt-1 max-h-80 overflow-auto rounded-lg bg-neutral-950 p-3 text-[11px] leading-relaxed text-neutral-100">
                  {artifact.code}
                </pre>
              </details>
            )}
            {artifact.testCode && (
              <details>
                <summary className="cursor-pointer text-xs font-semibold text-amber-700">
                  🧪 テストコードを見る（test_main.py）
                </summary>
                <pre className="mt-1 max-h-80 overflow-auto rounded-lg bg-neutral-950 p-3 text-[11px] leading-relaxed text-neutral-100">
                  {artifact.testCode}
                </pre>
              </details>
            )}
          </div>
        </section>
      )}
    </main>
  );
}
