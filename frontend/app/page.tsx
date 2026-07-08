"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { HistorySidebar } from "./components/HistorySidebar";
import { SakusenSelect } from "./components/SakusenSelect";
import * as quest from "./lib/quest";

// Orchestrator(SSE) のエンドポイント。デプロイ時は NEXT_PUBLIC_HIVE_API で差し替え。
// Agentの表示定義（要件 F-14：M7でドット絵キャラに昇格）
// ドラクエ風は絵文字・口調・演出で出し、表示名は「何をしている係か」が
// 一般の人にも一目でわかる役割名を主表示にする（職業名は使わない）。
const JOB: Record<string, { emoji: string; label: string; ring: string }> = {
  designer: { emoji: "🧙", label: "設計担当", ring: "ring-violet-400" },
  implementer: { emoji: "⚔️", label: "実装担当", ring: "ring-amber-400" },
  frontend: { emoji: "🎨", label: "画面担当", ring: "ring-teal-400" },
  tester: { emoji: "⛪", label: "テスト担当", ring: "ring-sky-400" },
  security_reviewer: { emoji: "🛡️", label: "セキュリティ監査", ring: "ring-rose-400" },
};

/** Agent内部名 → 役割がわかる表示名。 */
const labelOf = (agent: string) => JOB[agent]?.label ?? agent;

type SecurityFinding = {
  severity: string;
  file_path: string;
  line: number;
  issue: string;
  recommendation?: string;
};

type TimelineItem =
  | { id: number; kind: "task"; task: string }
  | {
      id: number;
      kind: "router";
      taskType: string;
      scale: string;
      rank: string;
      sakusen: string;
      model: string;
      party: string[];
    }
  | { id: number; kind: "intaking" }
  | {
      id: number;
      kind: "order";
      what: string;
      features: string[];
      successCriteria: string[];
      assumed: string[];
    }
  | { id: number; kind: "recall"; lessons: string[] }
  | { id: number; kind: "thinking"; agent: string; role: string }
  | { id: number; kind: "output"; agent: string; role: string; text: string }
  | { id: number; kind: "handoff"; from: string; to: string; item: string; detail: string }
  | { id: number; kind: "verifying"; mode: string }
  | { id: number; kind: "verify"; passed: boolean; output: string; mode: string }
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

/** 1つのSSEイベントをタイムライン一覧に適用する（ライブ・復元の両方で使う）。 */
// SSEペイロードは動的なため data は any 扱い（型はTimelineItem側で固定する）
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function applyEvent(prev: TimelineItem[], type: string, d: any): TimelineItem[] {
  switch (type) {
    case "task_received":
      return [...prev, { id: nextId(), kind: "task", task: d.task }];
    case "router":
      return [
        ...prev,
        {
          id: nextId(),
          kind: "router",
          taskType: d.task_type,
          scale: d.scale,
          rank: d.rank ?? "",
          sakusen: d.sakusen ?? d.quality ?? "",
          model: String(d.model ?? "").includes("pro") ? "Pro" : "Flash",
          party: ((d.party as { agent: string }[]) ?? []).map((p) => labelOf(p.agent)),
        },
      ];
    case "intake_start":
      return [...prev, { id: nextId(), kind: "intaking" }];
    case "order_spec":
      // 受付中カードを閉じる。解釈できなかったとき（what空）は依頼書を出さず原文で進む
      return [
        ...prev.filter((it) => it.kind !== "intaking"),
        ...(d.what
          ? [
              {
                id: nextId(),
                kind: "order" as const,
                what: d.what as string,
                features: (d.features as string[]) ?? [],
                successCriteria: (d.success_criteria as string[]) ?? [],
                assumed: (d.assumed as string[]) ?? [],
              },
            ]
          : []),
      ];
    case "memory_recall":
      return [...prev, { id: nextId(), kind: "recall", lessons: d.lessons ?? [] }];
    case "agent_start":
      return [...prev, { id: nextId(), kind: "thinking", agent: d.agent, role: d.role }];
    case "agent_output":
      // 直前の「かんがえている…」を消して成果に置き換える
      return [
        ...prev.filter((it) => !(it.kind === "thinking" && it.agent === d.agent)),
        { id: nextId(), kind: "output", agent: d.agent, role: d.role, text: d.text },
      ];
    case "handoff":
      return [
        ...prev,
        {
          id: nextId(),
          kind: "handoff",
          from: d.from_agent,
          to: d.to_agent,
          item: d.item ?? "",
          detail: d.detail ?? "",
        },
      ];
    case "security_start":
      return [...prev, { id: nextId(), kind: "securing" }];
    case "security_result":
      return [
        ...prev.filter((it) => it.kind !== "securing"),
        {
          id: nextId(),
          kind: "security",
          passed: String(d.passed) === "true",
          summary: d.summary ?? "",
          findings: (d.findings as SecurityFinding[]) ?? [],
        },
      ];
    case "verify_start":
      return [...prev, { id: nextId(), kind: "verifying", mode: d.mode ?? "pytest" }];
    case "verify_result":
      return [
        ...prev.filter((it) => it.kind !== "verifying"),
        {
          id: nextId(),
          kind: "verify",
          passed: String(d.passed) === "true",
          output: d.output,
          mode: d.mode ?? "pytest",
        },
      ];
    case "memory_write":
      return [
        ...prev,
        {
          id: nextId(),
          kind: "remember",
          success: d.kind === "success",
          title: d.title,
          forgotten: Number(d.forgotten ?? 0),
        },
      ];
    case "retry":
      return [
        ...prev,
        {
          id: nextId(),
          kind: "retry",
          attempt: Number(d.attempt),
          max: Number(d.max),
          reason: d.reason ?? "",
        },
      ];
    case "escalation":
      return [
        ...prev,
        { id: nextId(), kind: "escalation", agent: d.agent, toModel: d.to_model },
      ];
    case "done":
      return [...prev, { id: nextId(), kind: "done" }];
    case "error":
      return [
        ...prev,
        { id: nextId(), kind: "error", message: d.message ?? "接続が切れました" },
      ];
    default:
      return prev;
  }
}

/** agent_output の JSON を画面表示用に要約する。 */
function summarize(agent: string, text: string) {
  try {
    const o = JSON.parse(text);
    if (agent === "designer")
      return {
        title: o.overview as string,
        list: (o.endpoints as string[]) ?? (o.sections as string[]) ?? [],
      };
    if (agent === "implementer")
      return {
        title: o.html ? "Webページが完成した" : "実装が完成した",
        verify: o.how_to_verify as string,
        code: (o.code ?? o.html) as string,
      };
    if (agent === "frontend")
      return {
        title: "画面が完成した",
        verify: o.how_to_verify as string,
        code: o.html as string,
      };
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
  const [effort, setEffort] = useState("auto");
  const [items, setItems] = useState<TimelineItem[]>([]);
  const [running, setRunning] = useState(false);

  // 表示中クエスト（進行中 or 履歴選択）の一覧をストアから組み立て直す
  const rebuild = () => {
    const cur = quest.getCurrent();
    if (cur) setTask(cur.task);
    setItems(
      (cur?.events ?? []).reduce(
        (acc, e) => applyEvent(acc, e.type, e.data),
        [] as TimelineItem[],
      ),
    );
    setRunning(quest.isRunning());
  };

  // SSE接続は共有ストア(lib/quest)が持つので、ページ遷移しても一覧を復元できる
  useEffect(() => {
    rebuild();
    return quest.subscribe((e) => {
      if (e.type === "__reset") return rebuild();
      setItems((prev) => applyEvent(prev, e.type, e.data));
      if (e.type === "done" || e.type === "error") setRunning(false);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function start() {
    quest.start(task, effort); // __reset が飛び、subscribe 経由で一覧が切り替わる
  }

  return (
    <main className="mx-auto flex w-full max-w-5xl gap-5 px-4 py-8">
      <HistorySidebar />
      <div className="flex min-h-screen min-w-0 flex-1 flex-col gap-6">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-3xl">🐝</span>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Hive</h1>
            <p className="text-sm text-neutral-500">
              自然言語で発注すると、はたらきバチたちが設計→実装→テストを分担する
            </p>
          </div>
        </div>
        <Link href="/rpg" className="shrink-0 text-sm text-amber-600 hover:underline">
          🎮 RPGモードへ
        </Link>
      </header>

      <div className="flex gap-2">
        <input
          className="flex-1 rounded-lg border border-neutral-300 px-3 py-2 text-sm outline-none focus:border-amber-400 focus:ring-2 focus:ring-amber-200 dark:border-neutral-700 dark:bg-neutral-900"
          value={task}
          onChange={(e) => setTask(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && start()}
          placeholder="例: 在庫管理のCRUD APIを作って／喫茶店のおしゃれなLPを作って"
          disabled={running}
        />
        <SakusenSelect value={effort} onChange={setEffort} disabled={running} />
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
      </div>
    </main>
  );
}

function Avatar({ agent, role }: { agent: string; role: string }) {
  const j = JOB[agent] ?? { emoji: "🐝", label: role || agent, ring: "ring-neutral-300" };
  return (
    <div className="flex w-16 shrink-0 flex-col items-center">
      <div
        className={`flex h-12 w-12 items-center justify-center rounded-full bg-neutral-100 text-2xl ring-2 ${j.ring} dark:bg-neutral-800`}
      >
        {j.emoji}
      </div>
      <span className="mt-1 text-center text-[10px] leading-tight text-neutral-500">
        {j.label}
      </span>
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
          ⚙️ ルーター判定：討伐ランク{" "}
          <b className="text-amber-600">{it.rank || "?"}</b>（種別 {it.taskType} / 規模{" "}
          {it.scale}）
          {it.sakusen && (
            <span>
              {" "}
              ・さくせん <b>{it.sakusen}</b>（{it.model}）
            </span>
          )}{" "}
          → はたらきバチを編成
          {it.party.length > 0 && (
            <span className="ml-1">（{it.party.join("・")}）</span>
          )}
        </div>
      );
    case "intaking":
      return (
        <Card>
          <div className="flex w-16 shrink-0 flex-col items-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-neutral-100 text-2xl ring-2 ring-amber-300 dark:bg-neutral-800">
              📋
            </div>
            <span className="mt-1 text-[10px] text-neutral-500">受付</span>
          </div>
          <div className="flex items-center text-sm text-neutral-500">
            受付が 依頼内容を せいりしている
            <span className="ml-1 inline-flex animate-pulse">…</span>
          </div>
        </Card>
      );
    case "order":
      return (
        <div className="rounded-xl border border-amber-200 bg-amber-50/60 px-4 py-3 text-sm text-neutral-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-neutral-200">
          <div className="font-semibold">📋 クエスト依頼書（発注の解釈）</div>
          <p className="mt-1">{it.what}</p>
          {it.features.length > 0 && (
            <ul className="mt-1 list-disc pl-5 text-neutral-600 dark:text-neutral-400">
              {it.features.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          )}
          {it.successCriteria.length > 0 && (
            <p className="mt-1 text-xs text-neutral-500">
              ✅ 成功条件：{it.successCriteria.join(" ／ ")}
            </p>
          )}
          {it.assumed.length > 0 && (
            <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">
              💡 発注文に無かったので補った点：{it.assumed.join(" ／ ")}
            </p>
          )}
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
              {labelOf(it.agent)}
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
            <div className="font-semibold">
              {labelOf(it.agent)}
              <span className="ml-1.5 text-xs font-normal text-neutral-400">{it.agent}</span>
            </div>
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
    case "handoff":
      return (
        <div className="text-center text-xs text-neutral-500">
          🤝 <b>{labelOf(it.from)}</b> が <b>{labelOf(it.to)}</b> に {it.item}を渡した
          {it.detail && <span className="ml-1 opacity-70">（{it.detail.slice(0, 40)}）</span>}
        </div>
      );
    case "securing":
      return (
        <Card>
          <div className="flex w-16 shrink-0 flex-col items-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-neutral-100 text-2xl ring-2 ring-rose-400 dark:bg-neutral-800">
              🛡️
            </div>
            <span className="mt-1 text-center text-[10px] leading-tight text-neutral-500">
              セキュリティ監査
            </span>
          </div>
          <div className="flex items-center text-sm text-neutral-500">
            セキュリティ監査が コードの ぜいじゃくせいを しらべている
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
            {it.mode === "page"
              ? "ページが正しくできているか機械チェック中"
              : "サンドボックスで実際に起動してテスト中"}
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
            {it.mode === "page"
              ? it.passed
                ? "🧪✅ ページ検証：必須要素・リンク・実コンテンツOK"
                : "🧪❌ ページ検証：問題を検出"
              : it.passed
                ? "🧪✅ サンドボックス検証：テスト通過（コードは実際に動く）"
                : "🧪❌ サンドボックス検証：テスト失敗"}
          </div>
          <details className="mt-1">
            <summary className="cursor-pointer text-xs opacity-70">
              {it.mode === "page" ? "チェック結果" : "pytest の出力"}
            </summary>
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
            {labelOf(it.agent)}を上位モデル（{it.toModel}）に交代して再挑戦
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
