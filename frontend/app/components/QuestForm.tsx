"use client";

import { SAKUSEN_OPTIONS, SakusenSelect } from "./SakusenSelect";

/**
 * クエスト発注フォーム（RPG/タイムライン共用）。
 *
 * スマホ最適化の要点：
 * - 縦2段（入力→さくせん＋ボタン）に積み、デスクトップは sm:contents で
 *   従来どおりの横1列に戻す
 * - 入力は16px（text-base）にしてiOSのフォーカス時自動ズームを防ぐ
 * - さくせんの説明はtitle属性だとタッチ端末で見えないため、選択中の説明を
 *   フォーム下に常時表示する
 */
export function QuestForm({
  task,
  onTaskChange,
  effort,
  onEffortChange,
  running,
  onStart,
  submitLabel,
  runningLabel,
}: {
  task: string;
  onTaskChange: (v: string) => void;
  effort: string;
  onEffortChange: (v: string) => void;
  running: boolean;
  onStart: () => void;
  submitLabel: string;
  runningLabel: string;
}) {
  const hint = SAKUSEN_OPTIONS.find((o) => o.value === effort)?.hint ?? "";
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          className="w-full rounded-lg border border-neutral-300 px-3 py-2.5 text-base outline-none focus:border-amber-400 focus:ring-2 focus:ring-amber-200 sm:flex-1 sm:py-2 sm:text-sm dark:border-neutral-700 dark:bg-neutral-900"
          value={task}
          onChange={(e) => onTaskChange(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onStart()}
          enterKeyHint="send"
          placeholder="クエストを発注しよう！（例: タスク管理のCRUD APIをFastAPIで作って）"
          disabled={running}
        />
        <div className="flex gap-2 sm:contents">
          <SakusenSelect
            value={effort}
            onChange={onEffortChange}
            disabled={running}
            className="min-w-0 flex-1 py-2.5 sm:flex-none sm:py-2"
          />
          <button
            onClick={onStart}
            disabled={running || !task.trim()}
            className="shrink-0 rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-amber-600 disabled:opacity-50 sm:py-2"
          >
            {running ? runningLabel : submitLabel}
          </button>
        </div>
      </div>
      <p className="text-xs text-neutral-500">💡 {hint}</p>
    </div>
  );
}
