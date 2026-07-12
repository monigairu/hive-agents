"use client";

import { useEffect, useState } from "react";

import * as auth from "../lib/auth";
import * as quest from "../lib/quest";

/**
 * 画面右上のログイン情報チップ（RPG/タイムライン共用・layout.tsx で全ページに載せる）。
 *
 * ログイン済のときだけ、名前＋今週ののこり発注回数（quota SSEイベントで更新）＋
 * ログアウトを表示する。「Googleでログイン」ボタンはここには置かない＝
 * ログイン前のタイトル画面（AuthGate）だけに出す。
 * NEXT_PUBLIC_GOOGLE_CLIENT_ID 未設定（ローカル開発）では何も描画しない。
 */
export function AuthChip() {
  const [user, setUser] = useState<auth.AuthUser | null>(null);
  const [remaining, setRemaining] = useState<number | null | undefined>(undefined);

  useEffect(() => {
    if (!auth.authRequired()) return;
    setUser(auth.getUser());
    const offAuth = auth.subscribe(() => setUser(auth.getUser()));
    // 発注のたびにサーバが quota イベントで残数を教えてくれる
    const offQuest = quest.subscribe((e) => {
      if (e.type === "quota") {
        setRemaining((e.data.remaining as number | null) ?? null);
      }
    });
    return () => {
      offAuth();
      offQuest();
    };
  }, []);

  if (!auth.authRequired() || !user) return null;

  return (
    <div className="fixed right-3 top-3 z-50">
      <div className="flex items-center gap-2 rounded-full border border-amber-900/40 bg-stone-900/90 px-3 py-1.5 text-xs text-amber-100 shadow">
        <span>🪪 {user.name}</span>
        {remaining !== undefined && (
          <span className="text-amber-300">
            {remaining === null ? "のこり：∞" : `今週のこり ${remaining} 回`}
          </span>
        )}
        <button
          onClick={() => auth.signOut()}
          className="rounded border border-amber-900/40 px-1.5 py-0.5 text-amber-200/70 hover:text-amber-100"
        >
          ログアウト
        </button>
      </div>
    </div>
  );
}
