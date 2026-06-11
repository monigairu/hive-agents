"use client";

import { useEffect, useState } from "react";

import * as quest from "../lib/quest";

const STATUS_ICON: Record<string, string> = { done: "✅", error: "⚠️", running: "⏳" };

/** セッション履歴サイドバー（選択で再表示・🗑で削除）。RPG/タイムライン共用。 */
export function HistorySidebar() {
  const [items, setItems] = useState<quest.QuestRecord[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const refresh = () => {
    setItems(quest.history());
    setActiveId(quest.getCurrent()?.id ?? null);
    setRunning(quest.isRunning());
  };

  useEffect(() => {
    refresh();
    // 完了(done/error)・切り替え(__reset)のタイミングで一覧を更新する
    return quest.subscribe((e) => {
      if (e.type === "done" || e.type === "error" || e.type === "__reset") refresh();
    });
  }, []);

  return (
    <aside className="hidden w-56 shrink-0 md:block">
      <div className="sticky top-6 flex flex-col gap-1">
        <div className="px-2 pb-1 text-xs font-semibold text-neutral-500">
          📜 クエスト履歴
        </div>
        {items.length === 0 && (
          <p className="px-2 text-xs text-neutral-400">
            完了したクエストが ここに たまっていきます
          </p>
        )}
        {items.map((r) => (
          <div
            key={r.id}
            className={`group flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs ${
              r.id === activeId
                ? "bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-100"
                : "text-neutral-600 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-800"
            }`}
          >
            <button
              onClick={() => {
                if (!running) {
                  quest.load(r.id);
                }
              }}
              disabled={running}
              className="flex min-w-0 flex-1 items-center gap-1.5 text-left disabled:cursor-not-allowed"
              title={r.task}
            >
              <span className="shrink-0">{STATUS_ICON[r.status] ?? "❓"}</span>
              <span className="truncate">{r.task}</span>
            </button>
            <button
              onClick={() => {
                quest.remove(r.id);
                refresh();
              }}
              className="shrink-0 rounded p-0.5 opacity-0 transition hover:bg-red-100 hover:text-red-600 group-hover:opacity-100 dark:hover:bg-red-900/40"
              title="履歴から削除"
            >
              🗑
            </button>
          </div>
        ))}
        {running && (
          <p className="px-2 pt-1 text-[10px] text-neutral-400">
            ⏳ 実行中は履歴を切り替えられません
          </p>
        )}
      </div>
    </aside>
  );
}
