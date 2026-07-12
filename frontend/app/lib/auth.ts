"use client";

/**
 * Googleログイン（Google Identity Services）の共有ストア。
 *
 * NEXT_PUBLIC_GOOGLE_CLIENT_ID がある時だけ有効（＝本番デプロイ用）。
 * 未設定のローカル開発では authRequired() が false になり、従来どおり
 * ログインなしで発注できる。
 *
 * 取得した IDトークン(JWT) は localStorage に保存し、/stream の
 * クエリパラメータ token でバックエンドに渡す（EventSource はヘッダを
 * 付けられないため）。検証はバックエンド側で行う。
 */

const CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ?? "";
const STORAGE_KEY = "hive-google-credential-v1";

export type AuthUser = { name: string; email: string; picture?: string };

type Listener = () => void;
const listeners = new Set<Listener>();

export function authRequired(): boolean {
  return CLIENT_ID !== "";
}

export function subscribe(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function notify() {
  listeners.forEach((fn) => {
    try {
      fn();
    } catch (e) {
      console.error("auth listener error:", e);
    }
  });
}

/**
 * base64url文字列をUTF-8文字列としてデコードする。
 * atob() の戻り値は1バイト=1文字の「バイナリ文字列」（Latin-1相当）なので、
 * そのまま JSON.parse すると日本語などの多バイト文字が文字化けする。
 * バイト列に戻してから TextDecoder で正しくUTF-8デコードする。
 */
function base64UrlDecode(b64url: string): string {
  const binary = atob(b64url.replace(/-/g, "+").replace(/_/g, "/"));
  const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
  return new TextDecoder("utf-8").decode(bytes);
}

/** JWTのペイロード部をデコードする（検証はサーバの仕事。表示用途のみ）。 */
function decode(jwt: string): (AuthUser & { exp: number }) | null {
  try {
    const payload = JSON.parse(base64UrlDecode(jwt.split(".")[1]));
    return {
      name: payload.name ?? payload.email ?? "",
      email: payload.email ?? "",
      picture: payload.picture,
      exp: Number(payload.exp ?? 0),
    };
  } catch {
    return null;
  }
}

/** 有効期限内のIDトークンを返す。無ければ null（＝要ログイン）。 */
export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  const jwt = localStorage.getItem(STORAGE_KEY);
  if (!jwt) return null;
  const p = decode(jwt);
  // 期限切れ間近（残り60秒未満）も無効扱いにして、実行中の失効を避ける
  if (!p || p.exp * 1000 < Date.now() + 60_000) {
    localStorage.removeItem(STORAGE_KEY);
    return null;
  }
  return jwt;
}

export function getUser(): AuthUser | null {
  const jwt = getToken();
  if (!jwt) return null;
  const p = decode(jwt);
  return p ? { name: p.name, email: p.email, picture: p.picture } : null;
}

export function signOut() {
  localStorage.removeItem(STORAGE_KEY);
  notify();
}

// --- Google Identity Services の読み込みとボタン描画 -------------------------

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: object) => void;
          renderButton: (el: HTMLElement, options: object) => void;
        };
      };
    };
  }
}

let gisLoading: Promise<void> | null = null;

function loadGis(): Promise<void> {
  if (gisLoading) return gisLoading;
  gisLoading = new Promise((resolve, reject) => {
    if (window.google?.accounts) return resolve();
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Googleログインの読み込みに失敗しました"));
    document.head.appendChild(s);
  });
  return gisLoading;
}

/** 指定要素に「Googleでログイン」ボタンを描画する。 */
export async function renderSignIn(el: HTMLElement, options?: object) {
  if (!authRequired()) return;
  await loadGis();
  window.google!.accounts.id.initialize({
    client_id: CLIENT_ID,
    callback: (res: { credential: string }) => {
      localStorage.setItem(STORAGE_KEY, res.credential);
      notify();
    },
  });
  window.google!.accounts.id.renderButton(el, {
    type: "standard",
    theme: "outline",
    size: "medium",
    text: "signin_with",
    locale: "ja",
    ...options,
  });
}
