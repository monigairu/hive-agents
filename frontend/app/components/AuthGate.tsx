"use client";

import { useEffect, useRef, useState } from "react";

import * as auth from "../lib/auth";

/**
 * ログインゲート（layout.tsx でアプリ全体を包む）。
 *
 * - 未ログイン：ドラクエ風のタイトル画面（HIVE QUEST）だけを表示し、
 *   「Googleでログイン」してからアプリに入る
 * - ログイン済：アプリ本体（children）を表示
 * - NEXT_PUBLIC_GOOGLE_CLIENT_ID 未設定（ローカル開発）ではゲートなしで素通し
 *
 * ログインボタンはこのタイトル画面だけに置く（ログイン後の画面には出さない）。
 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  // localStorage はサーバに無いので、マウント前は判定せず黒画面を出す
  // （SSRとの食い違いによる hydration エラーとタイトル画面のチラつきを防ぐ）
  const [mounted, setMounted] = useState(false);
  const [user, setUser] = useState<auth.AuthUser | null>(null);
  const btnRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMounted(true);
    if (!auth.authRequired()) return;
    setUser(auth.getUser());
    return auth.subscribe(() => setUser(auth.getUser()));
  }, []);

  const needLogin = mounted && auth.authRequired() && !user;

  // タイトル画面が出ている間だけGISボタンを描画する（ログアウト後の再表示にも対応）
  useEffect(() => {
    if (!needLogin || !btnRef.current) return;
    auth.renderSignIn(btnRef.current, { size: "large" }).catch((e) => console.error(e));
  }, [needLogin]);

  if (!auth.authRequired()) return <>{children}</>;
  if (!mounted) return <div className="fixed inset-0 bg-black" />;
  if (user) return <>{children}</>;

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-8 bg-black px-4 text-center"
      style={{ fontFamily: '"DotGothic16", monospace' }}
    >
      {/* タイトルロゴ */}
      <div className="flex flex-col items-center gap-3">
        <span className="text-5xl" aria-hidden>
          🐝
        </span>
        <h1
          className="text-5xl font-bold tracking-[0.15em] text-amber-300 sm:text-7xl"
          style={{
            textShadow:
              "0 4px 0 #92400e, 0 8px 0 #451a03, 0 0 24px rgba(251,191,36,.35)",
          }}
        >
          HIVE QUEST
        </h1>
        <p className="text-sm tracking-widest text-amber-100/90 sm:text-base">
          — はたらきバチたち（AIエージェント）と ぼうけんに でよう —
        </p>
      </div>

      {/* ドラクエ風コマンドウィンドウ：ここでログインしてから はじまる */}
      <div className="rounded-lg border-4 border-white bg-black px-8 py-6 shadow-[0_0_0_4px_#000,0_0_0_6px_#fff0]">
        <p className="mb-4 text-base text-white">
          <span className="mr-1 inline-block animate-pulse text-amber-300">▼</span>
          ぼうけんを はじめる
        </p>
        <div ref={btnRef} className="flex justify-center" />
      </div>

      <p className="text-xs text-neutral-500">
        自然言語で発注すると、AIエージェントたちが 設計→実装→テストを分担します
      </p>
    </div>
  );
}
