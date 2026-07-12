import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { AuthChip } from "./components/AuthChip";
import { AuthGate } from "./components/AuthGate";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "HIVE QUEST — 自然言語で発注する開発チーム",
  description: "ADK 2.x マルチエージェントの協働を可視化する",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="ja"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        {/* RPGキャンバス用のドット日本語フォント（Phaserのcanvas描画が参照するため
            next/font ではなく素のlinkで読み込み、フォント名を DotGothic16 のまま使う） */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=DotGothic16&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-full flex flex-col">
        {/* ログインしてからアプリに入る：未ログイン時はタイトル画面だけを表示 */}
        <AuthGate>
          <AuthChip />
          {children}
        </AuthGate>
      </body>
    </html>
  );
}
