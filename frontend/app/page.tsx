"use client";

import { useRef, useState } from "react";

// Orchestrator(SSE) のエンドポイント。デプロイ時は NEXT_PUBLIC_HIVE_API で差し替え。
const API = process.env.NEXT_PUBLIC_HIVE_API ?? "http://localhost:8000";

// 役割をドラクエ職業に対応（要件 F-14 の伏線：M7でドット絵キャラに昇格）
const JOB: Record<string, { emoji: string; job: string; ring: string }> = {
  designer: { emoji: "🧙", job: "まほうつかい", ring: "ring-violet-400" },
  implementer: { emoji: "⚔️", job: "せんし", ring: "ring-amber-400" },
  tester: { emoji: "⛪", job: "そうりょ", ring: "ring-sky-400" },
  security_reviewer: { emoji: "🛡️", job: "けんじゃ", ring: "ring-rose-400" },
};

type SecurityFinding = {
  severity: string;
  file_path: string;
  line: number;
  issue: string;
  recommendation?: string;
};

type TimelineItem =
  | { id: number; kind: "task"; task: string }
  | { id: number; kind: "router"; taskType: string; scale: string }
  | { id: number; kind: "recall"; lessons: string[] }
  | { id: number; kind: "thinking"; agent: string; role: string }
  | { id: number; kind: "output"; agent: string; role: string; text: string }
  | { id: number; kind: "verifying" }
  | { id: number; kind: "verify"; passed: boolean; output: string }
  | { id: number; kind: "securing" }
  | {
      id: number;
      kind: "security";
      passed: boolean;
      summary: string;
      findings: SecurityFinding[];
    }
  | { id: number; kind: "retry"; attempt: number; max: number; reason: string }
  | { id: number; kind: "escalation"; agent: string; toModel: string }
  | { id: number; kind: "remember"; success: boolean; title: string; forgotten: number }
  | { id: number; kind: "done" }
  | { id: number; kind: "error"; message: string };

let _id = 0;
const nextId = () => ++_id;

/** agent_output の JSON を画面表示用に要約する。 */
function summarize(agent: string, text: string) {
  try {
    const o = JSON.parse(text);
    if (agent === "designer")
      return { title: o.overview as string, list: (o.endpoints as string[]) ?? [] };
    if (agent === "implementer")
      return { title: "実装が完成した", verify: o.how_to_verify as string, code: o.code as string };
    if (agent === "tester")
      return { title: o.summary as string, code: o.test_code as string };
    if (agent === "security_reviewer")
      return {
        title: (o.summary as string) || "監査完了",
        list: ((o.findings as SecurityFinding[]) ?? []).map(
          (f) => `[${f.severity}] ${f.file_path}:${f.line} ${f.issue}`,
        ),
      };
  } catch {
    /* JSONでなければ生テキスト表示 */
  }
  return { title: "", raw: text };
}

export default function Home() {
  const [task, setTask] = useState("タスク管理のCRUD APIをFastAPIで作って");
  const [items, setItems] = useState<TimelineItem[]>([]);
  const [running, setRunning] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  const push = (item: TimelineItem) => setItems((prev) => [...prev, item]);

  function start() {
    if (running || !task.trim()) return;
    esRef.current?.close();
    setItems([]);
    setRunning(true);

    const es = new EventSource(`${API}/stream?task=${encodeURIComponent(task)}`);
    esRef.current = es;

    // カスタムイベントは Event 型で渡るため MessageEvent にキャストして data を読む。
    // SSEペイロードは動的なため data は any 扱い（型はTimelineItem側で固定する）。
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const on = (name: string, fn: (data: any) => void) =>
      es.addEventListener(name, (e) => {
        const raw = (e as MessageEvent).data;
        fn(raw ? JSON.parse(raw) : {});
      });

    on("task_received", (d) => push({ id: nextId(), kind: "task", task: d.task }));
    on("router", (d) =>
      push({ id: nextId(), kind: "router", taskType: d.task_type, scale: d.scale }),
    );
    on("memory_recall", (d) =>
      push({ id: nextId(), kind: "recall", lessons: d.lessons ?? [] }),
    );
    on("agent_start", (d) =>
      push({ id: nextId(), kind: "thinking", agent: d.agent, role: d.role }),
    );
    on("agent_output", (d) => {
      // 直前の「かんがえている…」を消して成果に置き換える
      setItems((prev) => {
        const filtered = prev.filter(
          (it) => !(it.kind === "thinking" && it.agent === d.agent),
        );
        return [
          ...filtered,
          { id: nextId(), kind: "output", agent: d.agent, role: d.role, text: d.text },
        ];
      });
    });
    on("security_start", () => push({ id: nextId(), kind: "securing" }));
    on("security_result", (d) => {
      setItems((prev) => {
        const filtered = prev.filter((it) => it.kind !== "securing");
        return [
          ...filtered,
          {
            id: nextId(),
            kind: "security",
            passed: String(d.passed) === "true",
            summary: d.summary ?? "",
            findings: (d.findings as SecurityFinding[]) ?? [],
          },
        ];
      });
    });
    on("verify_start", () => push({ id: nextId(), kind: "verifying" }));
    on("verify_result", (d) => {
      setItems((prev) => {
        const filtered = prev.filter((it) => it.kind !== "verifying");
        return [
          ...filtered,
          {
            id: nextId(),
            kind: "verify",
            passed: String(d.passed) === "true",
            output: d.output,
          },
        ];
      });
    });
    on("memory_write", (d) =>
      push({
        id: nextId(),
        kind: "remember",
        success: d.kind === "success",
        title: d.title,
        forgotten: Number(d.forgotten ?? 0),
      }),
    );
    on("retry", (d) =>
      push({
        id: nextId(),
        kind: "retry",
        attempt: Number(d.attempt),
        max: Number(d.max),
        reason: d.reason ?? "",
      }),
    );
    on("escalation", (d) =>
      push({ id: nextId(), kind: "escalation", agent: d.agent, toModel: d.to_model }),
    );
    on("done", () => {
      push({ id: nextId(), kind: "done" });
      setRunning(false);
      es.close(); // SSEの自動再接続を止める（重要）
    });
    es.addEventListener("error", (e) => {
      // アプリ起因のエラーイベント（dataあり）と接続断（dataなし）の両方を処理
      const msg =
        e instanceof MessageEvent && e.data ? JSON.parse(e.data).message : "接続が切れました";
      push({ id: nextId(), kind: "error", message: msg });
      setRunning(false);
      es.close();
    });
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-6 px-4 py-8">
      <header className="flex items-center gap-3">
        <span className="text-3xl">🐝</span>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Hive</h1>
          <p className="text-sm text-neutral-500">
            自然言語で発注すると、はたらきバチたちが設計→実装→テストを分担する
          </p>
        </div>
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
          {running ? "進行中…" : "発注する"}
        </button>
      </div>

      <ol className="flex flex-col gap-3">
        {items.map((it) => (
          <li key={it.id}>{renderItem(it)}</li>
        ))}
      </ol>
    </main>
  );
}

function Avatar({ agent, role }: { agent: string; role: string }) {
  const j = JOB[agent] ?? { emoji: "🐝", job: role, ring: "ring-neutral-300" };
  return (
    <div className="flex w-16 shrink-0 flex-col items-center">
      <div
        className={`flex h-12 w-12 items-center justify-center rounded-full bg-neutral-100 text-2xl ring-2 ${j.ring} dark:bg-neutral-800`}
      >
        {j.emoji}
      </div>
      <span className="mt-1 text-[10px] text-neutral-500">{j.job}</span>
    </div>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-3 rounded-xl border border-neutral-200 bg-white p-3 shadow-sm dark:border-neutral-800 dark:bg-neutral-900">
      {children}
    </div>
  );
}

function renderItem(it: TimelineItem) {
  switch (it.kind) {
    case "task":
      return (
        <div className="rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          📜 発注：{it.task}
        </div>
      );
    case "router":
      return (
        <div className="text-center text-xs text-neutral-500">
          ⚙️ ルーター判定：種別 <b>{it.taskType}</b> / 規模 <b>{it.scale}</b> → はたらきバチを編成
        </div>
      );
    case "recall":
      return (
        <div className="rounded-xl bg-indigo-50 px-4 py-3 text-sm text-indigo-900 dark:bg-indigo-950/40 dark:text-indigo-200">
          <div className="font-semibold">💭 過去の教訓を想起（同種タスクの経験から）</div>
          <ul className="mt-1 list-disc pl-5 text-indigo-700 dark:text-indigo-300">
            {it.lessons.map((l, i) => (
              <li key={i}>{l}</li>
            ))}
          </ul>
        </div>
      );
    case "thinking":
      return (
        <Card>
          <Avatar agent={it.agent} role={it.role} />
          <div className="flex items-center text-sm text-neutral-500">
            <span className="font-medium text-neutral-700 dark:text-neutral-300">
              {it.agent}
            </span>
            は かんがえている
            <span className="ml-1 inline-flex animate-pulse">…</span>
          </div>
        </Card>
      );
    case "output": {
      const s = summarize(it.agent, it.text);
      return (
        <Card>
          <Avatar agent={it.agent} role={it.role} />
          <div className="min-w-0 flex-1 text-sm">
            <div className="font-semibold">{it.agent}</div>
            {s.title && <p className="mt-0.5 text-neutral-700 dark:text-neutral-300">{s.title}</p>}
            {"list" in s && s.list && (
              <ul className="mt-1 list-disc pl-5 text-neutral-600 dark:text-neutral-400">
                {s.list.map((x, i) => (
                  <li key={i}>{x}</li>
                ))}
              </ul>
            )}
            {"verify" in s && s.verify && (
              <p className="mt-1 whitespace-pre-wrap text-xs text-neutral-500">
                ✅ 確認方法：{s.verify}
              </p>
            )}
            {"code" in s && s.code && (
              <details className="mt-2">
                <summary className="cursor-pointer text-xs text-amber-700">コードを見る</summary>
                <pre className="mt-1 max-h-72 overflow-auto rounded-lg bg-neutral-950 p-3 text-[11px] leading-relaxed text-neutral-100">
                  {s.code}
                </pre>
              </details>
            )}
            {"raw" in s && s.raw && (
              <pre className="mt-1 max-h-72 overflow-auto whitespace-pre-wrap text-xs text-neutral-600">
                {s.raw}
              </pre>
            )}
          </div>
        </Card>
      );
    }
    case "securing":
      return (
        <Card>
          <div className="flex w-16 shrink-0 flex-col items-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-neutral-100 text-2xl ring-2 ring-rose-400 dark:bg-neutral-800">
              🛡️
            </div>
            <span className="mt-1 text-[10px] text-neutral-500">かんさ</span>
          </div>
          <div className="flex items-center text-sm text-neutral-500">
            けんじゃがコードのぜいじゃくせいを しらべている
            <span className="ml-1 inline-flex animate-pulse">…</span>
          </div>
        </Card>
      );
    case "security": {
      const badge = (sev: string) =>
        sev === "critical"
          ? "bg-red-600 text-white"
          : sev === "important"
            ? "bg-orange-500 text-white"
            : "bg-neutral-400 text-white";
      return (
        <div
          className={`rounded-xl px-4 py-3 text-sm ${
            it.passed
              ? "bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200"
              : "bg-red-50 text-red-800 dark:bg-red-950/40 dark:text-red-200"
          }`}
        >
          <div className="font-semibold">
            {it.passed
              ? `🛡️✅ セキュリティ監査：${it.summary || "問題なし"}`
              : "🛡️⚠️ このコードに ぜいじゃくせいあり！"}
          </div>
          {!it.passed && it.summary && (
            <p className="mt-0.5 text-xs opacity-80">{it.summary}</p>
          )}
          {it.findings.length > 0 && (
            <ul className="mt-2 flex flex-col gap-1">
              {it.findings.map((f, i) => (
                <li key={i} className="flex items-start gap-2 text-xs">
                  <span
                    className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${badge(f.severity)}`}
                  >
                    {f.severity}
                  </span>
                  <span>
                    <code className="opacity-70">
                      {f.file_path}:{f.line}
                    </code>{" "}
                    {f.issue}
                    {f.recommendation && (
                      <span className="opacity-70">（推奨: {f.recommendation}）</span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      );
    }
    case "verifying":
      return (
        <Card>
          <div className="flex w-16 shrink-0 flex-col items-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-neutral-100 text-2xl ring-2 ring-emerald-400 dark:bg-neutral-800">
              🧪
            </div>
            <span className="mt-1 text-[10px] text-neutral-500">けんしょう</span>
          </div>
          <div className="flex items-center text-sm text-neutral-500">
            サンドボックスで実際に起動してテスト中
            <span className="ml-1 inline-flex animate-pulse">…</span>
          </div>
        </Card>
      );
    case "verify":
      return (
        <div
          className={`rounded-xl px-4 py-3 text-sm ${
            it.passed
              ? "bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200"
              : "bg-red-50 text-red-800 dark:bg-red-950/40 dark:text-red-200"
          }`}
        >
          <div className="font-semibold">
            {it.passed ? "🧪✅ サンドボックス検証：テスト通過（コードは実際に動く）" : "🧪❌ サンドボックス検証：テスト失敗"}
          </div>
          <details className="mt-1">
            <summary className="cursor-pointer text-xs opacity-70">pytest の出力</summary>
            <pre className="mt-1 max-h-60 overflow-auto whitespace-pre-wrap rounded-lg bg-neutral-950 p-3 text-[11px] text-neutral-100">
              {it.output}
            </pre>
          </details>
        </div>
      );
    case "retry":
      return (
        <div className="rounded-xl bg-orange-50 px-4 py-3 text-sm text-orange-900 dark:bg-orange-950/40 dark:text-orange-200">
          <div className="font-semibold">
            🔁 検証に失敗 → 修正してやり直し（試行 {it.attempt}/{it.max}）
          </div>
          {it.reason && <p className="mt-0.5 text-xs text-orange-700 dark:text-orange-300">理由：{it.reason}</p>}
        </div>
      );
    case "escalation":
      return (
        <div className="rounded-xl bg-fuchsia-50 px-4 py-3 text-sm text-fuchsia-900 dark:bg-fuchsia-950/40 dark:text-fuchsia-200">
          <div className="font-semibold">⚔️→🔮 しょうかんかいじょ！ あたらしい仲間がくわわった</div>
          <p className="mt-0.5 text-xs text-fuchsia-700 dark:text-fuchsia-300">
            {it.agent} を上位モデル（{it.toModel}）に格上げして再挑戦
          </p>
        </div>
      );
    case "remember":
      return (
        <div className="rounded-xl bg-indigo-50 px-4 py-3 text-sm text-indigo-900 dark:bg-indigo-950/40 dark:text-indigo-200">
          🧠 教訓を記録（{it.success ? "成功" : "失敗"}）：{it.title}
          {it.forgotten > 0 && (
            <span className="ml-1 text-xs text-indigo-500">／古い記憶を{it.forgotten}件忘却</span>
          )}
        </div>
      );
    case "done":
      return (
        <div className="rounded-xl bg-emerald-50 px-4 py-3 text-center text-sm font-semibold text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
          ✅ クエスト完了！ はたらきバチたちが成果を納品した
        </div>
      );
    case "error":
      return (
        <div className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          ⚠️ エラー：{it.message}
        </div>
      );
  }
}
