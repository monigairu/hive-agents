/**
 * F-14 コード生成ドット絵（v2.13）。
 *
 * 絵素材はすべてここの文字列グリッドから生成する（外部PNG等は同梱しない）。
 * キャラは1枚のベース絵から歩行4方向×2フレームを機械的に導出する：
 * - 歩行フレーム＝脚の行だけ左右に開く（DQ初期作の2フレーム交互）
 * - 後ろ向き＝目を消す／横向き＝目を進行方向側の1つに寄せる（flipXで左右共用）
 */

import * as Phaser from "phaser";

type CharDef = { rows: string[]; palette: Record<string, string> };

// A=帽子/頭, S=肌, E=目, B=胴, L=脚, F=足, X=アクセント（'.'は透過）
export const CHARS: Record<string, CharDef> = {
  designer: {
    // とんがり帽子のローブ姿（魔法使い風）
    rows: [
      ".....AA.....",
      "....AAAA....",
      "...AAAAAA...",
      "..AAAAAAAA..",
      "...SSSSSS...",
      "...SESSES...",
      "...SSSSSS...",
      "..BBBBBBBB..",
      ".BBBBBBBBBB.",
      ".BBXBBBBXBB.",
      ".BBBBBBBBBB.",
      "..BBBBBBBB..",
      "...LL..LL...",
      "...FF..FF...",
    ],
    palette: {
      A: "#7c3aed", S: "#fcd7b0", E: "#1f2937", B: "#8b5cf6",
      X: "#fbbf24", L: "#374151", F: "#1f2937",
    },
  },
  implementer: {
    // 兜と鎧（戦士風）
    rows: [
      "..X......X..",
      "...AAAAAA...",
      "..AAAAAAAA..",
      "..AAAAAAAA..",
      "...SSSSSS...",
      "...SESSES...",
      "...SSSSSS...",
      "..BBBBBBBB..",
      ".BBXXBBXXBB.",
      ".BBBBBBBBBB.",
      ".BBBBBBBBBB.",
      "..BBBBBBBB..",
      "...LL..LL...",
      "...FF..FF...",
    ],
    palette: {
      A: "#9ca3af", S: "#fcd7b0", E: "#1f2937", B: "#f59e0b",
      X: "#6b7280", L: "#374151", F: "#1f2937",
    },
  },
  tester: {
    // フードのローブ姿（僧侶風）
    rows: [
      "....AAAA....",
      "...AAAAAA...",
      "..AAAAAAAA..",
      "..AASSSSAA..",
      "...SESSES...",
      "...SSSSSS...",
      "..BBBBBBBB..",
      ".BBBBXXBBBB.",
      ".BBBBXXBBBB.",
      ".BBBBBBBBBB.",
      ".BBBBBBBBBB.",
      "..BBBBBBBB..",
      "...LL..LL...",
      "...FF..FF...",
    ],
    palette: {
      A: "#7dd3fc", S: "#fcd7b0", E: "#1f2937", B: "#38bdf8",
      X: "#f8fafc", L: "#374151", F: "#1f2937",
    },
  },
  security_reviewer: {
    // 盾を構えた衛兵風
    rows: [
      "...AAAAAA...",
      "..AAAAAAAA..",
      "..AXXXXXXA..",
      "...SSSSSS...",
      "...SESSES...",
      "...SSSSSS...",
      "..BBBBBBBB..",
      "XXXBBBBBBBB.",
      "XXXBBBBBBBB.",
      "XXXBBBBBBBB.",
      ".BBBBBBBBBB.",
      "..BBBBBBBB..",
      "...LL..LL...",
      "...FF..FF...",
    ],
    palette: {
      A: "#fb7185", S: "#fcd7b0", E: "#1f2937", B: "#e11d48",
      X: "#facc15", L: "#374151", F: "#1f2937",
    },
  },
  frontend: {
    // ベレー帽と筆（画面職人風）
    rows: [
      "..AAAAAAA...",
      ".AAAAAAAAA..",
      "..AAAAAA....",
      "...SSSSSS...",
      "...SESSES...",
      "...SSSSSS...",
      "..BBBBBBBB..",
      ".BBBBBBBBXX.",
      ".BBXBBBBBXX.",
      ".BBBBBBBBBB.",
      "..BBBBBBBB..",
      "...LL..LL...",
      "...LL..LL...",
      "...FF..FF...",
    ],
    palette: {
      A: "#0d9488", S: "#fcd7b0", E: "#1f2937", B: "#2dd4bf",
      X: "#f59e0b", L: "#374151", F: "#1f2937",
    },
  },
  // F-13 交代後の画面担当（上位モデル）：金のベレー
  frontend_pro: {
    rows: [
      "..AAAAAAA...",
      ".AAAAAAAAA..",
      "..AAAAAA....",
      "...SSSSSS...",
      "...SESSES...",
      "...SSSSSS...",
      "..BBBBBBBB..",
      ".BBBBBBBBXX.",
      ".BBXBBBBBXX.",
      ".BBBBBBBBBB.",
      "..BBBBBBBB..",
      "...LL..LL...",
      "...LL..LL...",
      "...FF..FF...",
    ],
    palette: {
      A: "#fbbf24", S: "#fcd7b0", E: "#1f2937", B: "#a855f7",
      X: "#fde68a", L: "#374151", F: "#1f2937",
    },
  },
  // F-13 交代後の実装担当（上位モデル）：金色の鎧
  implementer_pro: {
    rows: [
      "..X......X..",
      "...AAAAAA...",
      "..AAAAAAAA..",
      "..AAAAAAAA..",
      "...SSSSSS...",
      "...SESSES...",
      "...SSSSSS...",
      "..BBBBBBBB..",
      ".BBXXBBXXBB.",
      ".BBBBBBBBBB.",
      ".BBBBBBBBBB.",
      "..BBBBBBBB..",
      "...LL..LL...",
      "...FF..FF...",
    ],
    palette: {
      A: "#fbbf24", S: "#fcd7b0", E: "#1f2937", B: "#a855f7",
      X: "#fde68a", L: "#374151", F: "#1f2937",
    },
  },
};

export type Facing = "down" | "up" | "side";

/** 脚の行（.とL/Fだけの行）を左右に1pxずつ開いて「歩き」の2枚目を作る。 */
function spreadLegs(rows: string[]): string[] {
  return rows.map((row) => {
    if (!/^[.LF]+$/.test(row) || !/[LF]/.test(row)) return row;
    const w = row.length;
    const out: string[] = Array(w).fill(".");
    [...row].forEach((ch, i) => {
      if (ch === ".") return;
      const j = i < w / 2 ? Math.max(0, i - 1) : Math.min(w - 1, i + 1);
      out[j] = ch;
    });
    return out.join("");
  });
}

/** 目の行を置換する（後ろ向き＝目なし、横向き＝進行方向側に1つ）。 */
function withEyes(rows: string[], to: string): string[] {
  return rows.map((r) => r.replace("SESSES", to));
}

/** 文字列グリッドからテクスチャを作る（既存キーはスキップ）。 */
export function makeGridTexture(
  scene: Phaser.Scene,
  key: string,
  rows: string[],
  palette: Record<string, string>,
) {
  if (scene.textures.exists(key)) return;
  const w = rows[0].length;
  const h = rows.length;
  const canvas = scene.textures.createCanvas(key, w, h);
  if (!canvas) return;
  const ctx = canvas.getContext();
  rows.forEach((row, y) => {
    [...row].forEach((ch, x) => {
      const color = palette[ch];
      if (color) {
        ctx.fillStyle = color;
        ctx.fillRect(x, y, 1, 1);
      }
    });
  });
  canvas.refresh();
}

/**
 * 1キャラ分のフレーム一式を登録する。
 * キー：`{name}.down0/down1/up0/up1/side0/side1/blink`
 */
export function registerCharTextures(scene: Phaser.Scene, name: string, def: CharDef) {
  const eyeless = withEyes(def.rows, "SSSSSS");
  const side = withEyes(def.rows, "SSSSES");
  const frames: Record<string, string[]> = {
    down0: def.rows,
    down1: spreadLegs(def.rows),
    up0: eyeless,
    up1: spreadLegs(eyeless),
    side0: side,
    side1: spreadLegs(side),
    blink: eyeless,
  };
  for (const [frame, rows] of Object.entries(frames)) {
    makeGridTexture(scene, `${name}.${frame}`, rows, def.palette);
  }
}

/** 全キャラのフレームを登録する。 */
export function registerAllChars(scene: Phaser.Scene) {
  for (const [name, def] of Object.entries(CHARS)) {
    registerCharTextures(scene, name, def);
  }
}

// --- エモート（頭上の気持ちマーク・ドット絵） -------------------------------

const EMOTE_PAL = { W: "#f8fafc", B: "#1f2430", Y: "#fde047", C: "#a5f3fc" };

const EMOTE_ROWS: Record<string, string[]> = {
  // かんがえちゅう（…）
  think: [
    "WW..WW..WW",
    "WW..WW..WW",
  ],
  // きづき・かんりょう（！）
  alert: [
    ".YY.",
    ".YY.",
    ".YY.",
    ".YY.",
    "....",
    ".YY.",
  ],
  // かいわ（吹き出し）
  talk: [
    ".WWWWWWWW.",
    "WBBBBBBBBW",
    "WBWBWBWBBW",
    "WBBBBBBBBW",
    ".WWWWWWWW.",
    "...WB.....",
    "....W.....",
  ],
  // おやすみ（Z）
  sleep: [
    "CCCCC..",
    "...C...",
    "..C..CC",
    ".C....C",
    "CCCCC.C",
    "......C",
  ],
};

export type EmoteKind = keyof typeof EMOTE_ROWS;

export function registerEmotes(scene: Phaser.Scene) {
  for (const [kind, rows] of Object.entries(EMOTE_ROWS)) {
    makeGridTexture(scene, `emote.${kind}`, rows, EMOTE_PAL);
  }
}
