"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { HistorySidebar } from "./components/HistorySidebar";
import { QuestForm } from "./components/QuestForm";
import * as quest from "./lib/quest";
import type { HiveGame } from "./rpg/game";

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
  const [task, setTask] = useState("");
  const [effort, setEffort] = useState("auto");
  const [running, setRunning] = useState(false);
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  // スマホ用：キャンバス内の実況は縮小されて読めないため、HTMLにも同じ実況を映す
  const [msgs, setMsgs] = useState<string[]>([]);
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
    let stopDemo: (() => void) | undefined;
    (async () => {
      // ドット日本語フォントの読み込みを待ってからキャンバスを作る（文字化け防止）。
      // Google FontsのCJKは文字範囲ごとの分割配信で、canvas描画はサブセットの
      // 自動読み込みを起こさないため、固定UI（ステータス窓等）で使う文字を
      // 明示的に指定して必要なサブセットまで先に読み込む
      try {
        await document.fonts.load(
          '16px "DotGothic16"',
          "設計担当実装画面テスト監査セキュリティ討伐ランク依頼書上位モデル" +
            "じょうたいまちしごとちゅうかんりょうさようパワーアップ",
        );
      } catch {
        /* フォントが取れなくてもフォールバックで描画する */
      }
      const { createGame } = await import("./rpg/game");
      if (cancelled || !containerRef.current || gameRef.current) return;
      gameRef.current = createGame(containerRef.current);
      gameRef.current.setOnMessages((lines) => setMsgs([...lines]));
      // デモモード（F-14）：バックエンドなしで演出一式を通しで再生する
      if (new URLSearchParams(window.location.search).has("demo")) {
        const { runDemo } = await import("./rpg/demo");
        stopDemo = runDemo(gameRef.current);
        return;
      }
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
      stopDemo?.();
      gameRef.current?.setOnMessages(null);
      gameRef.current?.destroy();
      gameRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function start() {
    if (!task.trim() || quest.isRunning()) return;
    quest.start(task, effort); // __reset が飛び、subscribe 経由で表示が切り替わる
  }

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-4 py-4 md:flex-row md:gap-5 md:py-6">
      <HistorySidebar />
      <div className="flex min-w-0 flex-1 flex-col gap-3 md:min-h-screen md:gap-4">
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="flex min-w-0 items-center gap-3">
          <span className="text-2xl sm:text-3xl">🐝</span>
          <div className="min-w-0">
            <h1 className="text-xl font-bold tracking-tight sm:text-2xl">HIVE QUEST</h1>
            <p className="text-xs text-neutral-500 sm:text-sm">
              自然言語で発注すると、はたらきバチたち（AIエージェント）が設計→実装→テストを分担する
            </p>
          </div>
        </div>
        <Link
          href="/timeline"
          className="shrink-0 rounded-full border border-amber-300 px-3 py-1.5 text-sm text-amber-700 transition hover:bg-amber-50 dark:border-amber-700 dark:text-amber-300 dark:hover:bg-amber-950/40"
        >
          💬 チャット形式で見る
        </Link>
      </header>

      <QuestForm
        task={task}
        onTaskChange={setTask}
        effort={effort}
        onEffortChange={setEffort}
        running={running}
        onStart={start}
        submitLabel="クエスト発注"
        runningLabel="ぼうけん中…"
      />

      {/* キャンバスの親は「幅から決まる固定アスペクト比の箱」にする（高さ指定が肝）。
          高さをキャンバス任せ（auto）にすると、Phaser FIT が枠線込みの親サイズに
          合わせてキャンバスを広げる→親も広がる…の無限ループで、ページ全体が
          0.5秒ごとに数pxずつ下がり続けるバグになる（実測で確認済み）。
          スマホでは左右の余白をなくして少しでも大きく表示する（full-bleed） */}
      <div
        ref={containerRef}
        className="-mx-4 aspect-[16/11] max-h-[560px] overflow-hidden border-y border-neutral-800 bg-black sm:mx-0 sm:w-full sm:rounded-xl sm:border"
      />

      {/* スマホ用の実況ウィンドウ：キャンバス内のメッセージは縮小されて
          読めないため、同じ実況をHTML（ドラクエ風の窓）でも流す */}
      {msgs.length > 0 && (
        <div
          className="rounded-lg border-2 border-white bg-black px-3 py-2 text-[13px] leading-relaxed text-white sm:hidden"
          style={{ fontFamily: '"DotGothic16", monospace' }}
          aria-live="polite"
        >
          {msgs.map((m, i) => (
            <p key={i} className={i === msgs.length - 1 ? "" : "opacity-55"}>
              {m}
            </p>
          ))}
        </div>
      )}

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
              {/* allow-scripts のみ許可（allow-same-origin は付けない）：srcDoc は
                  一意のオリジンで隔離されるため、生成コードのJSは動くが本体の
                  Cookie/localStorage には触れない。本番デプロイでも安全な構成 */}
              <iframe
                srcDoc={artifact.html}
                sandbox="allow-scripts"
                title="できあがった画面のプレビュー"
                className="h-[320px] w-full rounded-lg border border-neutral-300 bg-white sm:h-[420px]"
              />
              {artifact.kind === "app" && (
                <p className="text-[11px] text-neutral-500">
                  ※プレビューはAPI未起動のため空（またはエラー表示）の状態です。下の「確認する方法」の手順でAPIを起動すると実際に動きます
                </p>
              )}
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => openHtml(artifact.html)}
                  className="rounded-lg bg-amber-500 px-3 py-2 text-sm font-semibold text-white hover:bg-amber-600 sm:py-1.5 sm:text-xs"
                >
                  🔍 べつタブで ひらく
                </button>
                <button
                  onClick={() => downloadFile("index.html", artifact.html)}
                  className="rounded-lg border border-amber-500 px-3 py-2 text-sm font-semibold text-amber-700 hover:bg-amber-100 sm:py-1.5 sm:text-xs"
                >
                  💾 index.html を ダウンロード
                </button>
                {artifact.kind === "app" && artifact.code && (
                  <button
                    onClick={() => downloadFile("main.py", artifact.code)}
                    className="rounded-lg border border-amber-500 px-3 py-2 text-sm font-semibold text-amber-700 hover:bg-amber-100 sm:py-1.5 sm:text-xs"
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
