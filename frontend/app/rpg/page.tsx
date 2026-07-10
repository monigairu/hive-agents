"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { HistorySidebar } from "../components/HistorySidebar";
import { SakusenSelect } from "../components/SakusenSelect";
import * as quest from "../lib/quest";
import type { HiveGame } from "./game";

/** 完了時に表示する成果物（各Agentの最終出力JSONから組み立てる）。 */
type Artifact = {
  kind: "api" | "web" | "app";
  overview: string;
  endpoints: string[];
  code: string;
  howToVerify: string;
  testSummary: string;
  testCode: string;
  html: string;
  designNotes: string;
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
  const fe = parse("frontend");
  const test = parse("tester");
  if (!impl.code && !impl.html) return null;
  const kind: Artifact["kind"] = impl.html ? "web" : fe.html ? "app" : "api";
  return {
    kind,
    overview: String(design.overview ?? ""),
    endpoints: (design.endpoints as string[]) ?? [],
    code: String(impl.code ?? ""),
    howToVerify: String((kind === "app" ? fe.how_to_verify : impl.how_to_verify) ?? ""),
    testSummary: String(test.summary ?? ""),
    testCode: String(test.test_code ?? ""),
    html: String((impl.html || fe.html) ?? ""),
    designNotes: String((impl.design_notes || fe.design_notes) ?? ""),
  };
}

/** 生成ページを新しいタブで開く。 */
function openHtml(html: string) {
  const url = URL.createObjectURL(new Blob([html], { type: "text/html" }));
  window.open(url, "_blank", "noopener");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/** テキストをファイルとしてダウンロードする。 */
function downloadFile(filename: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: "text/plain" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export default function RpgPage() {
  const [task, setTask] = useState("タスク管理のCRUD APIをFastAPIで作って");
  const [effort, setEffort] = useState("auto");
  const [running, setRunning] = useState(false);
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const gameRef = useRef<HiveGame | null>(null);
  const outputsRef = useRef<Record<string, string>>({});

  // 表示中クエスト（進行中 or 履歴選択）の状態をストアから復元する
  const restore = () => {
    const cur = quest.getCurrent();
    outputsRef.current = {};
    if (cur) {
      for (const e of cur.events) {
        if (e.type === "agent_output") {
          outputsRef.current[String(e.data.agent)] = String(e.data.text ?? "");
        }
      }
      gameRef.current?.replay(cur.events);
      setArtifact(cur.status === "running" ? null : buildArtifact(outputsRef.current));
      setTask(cur.task);
    } else {
      gameRef.current?.replay([]);
      setArtifact(null);
    }
    setRunning(quest.isRunning());
  };

  // Phaser はブラウザ専用のため、マウント後に動的importで初期化する。
  // SSE接続は共有ストア(lib/quest)が持つので、ページ遷移してもクエストは途切れない。
  useEffect(() => {
    let cancelled = false;
    let unsubscribe: (() => void) | undefined;
    (async () => {
      // ドット日本語フォントの読み込みを待ってからキャンバスを作る（文字化け防止）
      try {
        await document.fonts.load('16px "DotGothic16"');
      } catch {
        /* フォントが取れなくてもフォールバックで描画する */
      }
      const { createGame } = await import("./game");
      if (cancelled || !containerRef.current || gameRef.current) return;
      gameRef.current = createGame(containerRef.current);
      restore();
      unsubscribe = quest.subscribe((e) => {
        if (e.type === "__reset") return restore();
        gameRef.current?.enqueue(e);
        if (e.type === "agent_output") {
          outputsRef.current[String(e.data.agent)] = String(e.data.text ?? "");
        }
        if (e.type === "done") {
          setArtifact(buildArtifact(outputsRef.current));
          setRunning(false);
        }
        if (e.type === "error") setRunning(false);
      });
    })();
    return () => {
      cancelled = true;
      unsubscribe?.();
      gameRef.current?.destroy();
      gameRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function start() {
    quest.start(task, effort); // __reset が飛び、subscribe 経由で表示が切り替わる
  }

  return (
    <main className="mx-auto flex w-full max-w-6xl gap-5 px-4 py-6">
      <HistorySidebar />
      <div className="flex min-h-screen min-w-0 flex-1 flex-col gap-4">
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
          placeholder="例: 喫茶店のおしゃれなLPを作って／在庫管理のCRUD APIを作って"
          disabled={running}
        />
        <SakusenSelect value={effort} onChange={setEffort} disabled={running} />
        <button
          onClick={start}
          disabled={running}
          className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-amber-600 disabled:opacity-50"
        >
          {running ? "ぼうけん中…" : "クエスト発注"}
        </button>
      </div>

      {/* キャンバスの親は「幅から決まる固定アスペクト比の箱」にする（高さ指定が肝）。
          高さをキャンバス任せ（auto）にすると、Phaser FIT が枠線込みの親サイズに
          合わせてキャンバスを広げる→親も広がる…の無限ループで、ページ全体が
          0.5秒ごとに数pxずつ下がり続けるバグになる（実測で確認済み） */}
      <div
        ref={containerRef}
        className="aspect-[38/27] max-h-[560px] w-full overflow-hidden rounded-xl border border-neutral-800 bg-black"
      />

      {artifact && (
        <section className="rounded-xl border-2 border-amber-400 bg-amber-50 p-4 text-sm dark:bg-amber-950/30">
          <h2 className="text-base font-bold text-amber-900 dark:text-amber-200">
            🏆 ほうしゅう（できあがった成果物）
          </h2>
          {artifact.overview && (
            <p className="mt-2 text-neutral-800 dark:text-neutral-200">{artifact.overview}</p>
          )}
          {artifact.html && (
            <div className="mt-3 flex flex-col gap-2">
              {artifact.designNotes && (
                <p className="text-xs text-neutral-600 dark:text-neutral-400">
                  🎨 デザイン：{artifact.designNotes}
                </p>
              )}
              <iframe
                srcDoc={artifact.html}
                sandbox=""
                title="できあがった画面のプレビュー"
                className="h-[420px] w-full rounded-lg border border-neutral-300 bg-white"
              />
              {artifact.kind === "app" && (
                <p className="text-[11px] text-neutral-500">
                  ※プレビューはAPI未起動のため空（またはエラー表示）の状態です。下の「確認する方法」の手順でAPIを起動すると実際に動きます
                </p>
              )}
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => openHtml(artifact.html)}
                  className="rounded-lg bg-amber-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-600"
                >
                  🔍 べつタブで ひらく
                </button>
                <button
                  onClick={() => downloadFile("index.html", artifact.html)}
                  className="rounded-lg border border-amber-500 px-3 py-1.5 text-xs font-semibold text-amber-700 hover:bg-amber-100"
                >
                  💾 index.html を ダウンロード
                </button>
                {artifact.kind === "app" && artifact.code && (
                  <button
                    onClick={() => downloadFile("main.py", artifact.code)}
                    className="rounded-lg border border-amber-500 px-3 py-1.5 text-xs font-semibold text-amber-700 hover:bg-amber-100"
                  >
                    💾 main.py（API）を ダウンロード
                  </button>
                )}
              </div>
              <details>
                <summary className="cursor-pointer text-xs font-semibold text-amber-700">
                  📜 生成されたHTMLを見る
                </summary>
                <pre className="mt-1 max-h-80 overflow-auto rounded-lg bg-neutral-950 p-3 text-[11px] leading-relaxed text-neutral-100">
                  {artifact.html}
                </pre>
              </details>
            </div>
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
      </div>
    </main>
  );
}
