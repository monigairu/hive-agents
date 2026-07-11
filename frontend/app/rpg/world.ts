/**
 * F-14 ギルド作業場のマップ（v2.13）。
 *
 * 16×8タイル（1タイル=16px・表示3倍=48px）の固定レイアウト。
 * - 行0-1：壁（たいまつ・クエスト掲示板・ぼうけんのしょ本棚）
 * - 行3-4 列7-8：中央テーブル（handoff・監査・機械検証の舞台）
 * - 行6：担当ごとの机（編成人数に応じて列を割り付け）。キャラは机の上（行5）に立って働く
 * - 下端中央がギルドの入口（編成はここから歩いて入場する）
 *
 * タイル絵はすべて手続き描画（外部アセットなし）。
 */

import * as Phaser from "phaser";

export const TILE = 16;
export const SCALE = 3;
export const TS = TILE * SCALE; // 画面上のタイルサイズ(48px)
export const COLS = 16;
export const ROWS = 8;
export const W = COLS * TS; // 768
export const H = 528; // 下部はメッセージウィンドウ

export type Tile = { c: number; r: number };

// 家具・見どころの位置（タイル座標）
export const TABLE = { c1: 7, c2: 8, r1: 3, r2: 4 };
export const BOARD = { c: 3, r: 1, w: 2 }; // クエスト掲示板
export const SHELF = { c: 10, r: 1, w: 3 }; // ぼうけんのしょ本棚
export const TORCHES = [1, 14]; // たいまつの列（行1）
export const DOOR: Tile = { c: 6, r: 1 }; // ギルドの扉（壁の中）
export const ENTRANCE: Tile = { c: 6, r: 2 }; // 扉から入って最初に立つ床
export const DESK_ROW = 6; // 机の行
export const STAND_ROW = 5; // 働くとき立つ行（机の上側）
/** 中央テーブルの検分位置（監査担当が立つ） */
export const INSPECT: Tile = { c: 6, r: 4 };

/** 編成人数→机の列の割り付け（左右対称に散らす）。 */
export function deskCols(n: number): number[] {
  const pools: Record<number, number[]> = {
    1: [8],
    2: [5, 11],
    3: [3, 8, 13],
    4: [2, 6, 10, 14],
    5: [2, 5, 8, 11, 14],
  };
  return pools[Math.min(Math.max(n, 1), 5)] ?? pools[5];
}

/** タイル→画面座標（キャラの足元＝タイル下端のやや上）。 */
export function tileXY(t: Tile): { x: number; y: number } {
  return { x: t.c * TS + TS / 2, y: t.r * TS + TS - 4 };
}

/** 歩ける場所のグリッドを作る（壁・テーブル・机は通れない）。 */
export function buildGrid(desks: number[]): boolean[][] {
  const grid: boolean[][] = [];
  for (let r = 0; r < ROWS; r++) {
    grid.push(Array(COLS).fill(r >= 2));
  }
  for (let r = TABLE.r1; r <= TABLE.r2; r++) {
    for (let c = TABLE.c1; c <= TABLE.c2; c++) grid[r][c] = false;
  }
  for (const c of desks) grid[DESK_ROW][c] = false;
  return grid;
}

/** BFSの最短経路（開始タイルは含まない）。届かなければ空配列。 */
export function findPath(grid: boolean[][], from: Tile, to: Tile): Tile[] {
  if (from.c === to.c && from.r === to.r) return [];
  const key = (c: number, r: number) => r * COLS + c;
  const prev = new Map<number, number>();
  const queue: Tile[] = [from];
  const seen = new Set<number>([key(from.c, from.r)]);
  const dirs = [
    [0, -1],
    [0, 1],
    [-1, 0],
    [1, 0],
  ];
  while (queue.length > 0) {
    const cur = queue.shift() as Tile;
    if (cur.c === to.c && cur.r === to.r) break;
    for (const [dc, dr] of dirs) {
      const c = cur.c + dc;
      const r = cur.r + dr;
      if (c < 0 || c >= COLS || r < 0 || r >= ROWS) continue;
      if (!grid[r]?.[c] || seen.has(key(c, r))) continue;
      seen.add(key(c, r));
      prev.set(key(c, r), key(cur.c, cur.r));
      queue.push({ c, r });
    }
  }
  if (!seen.has(key(to.c, to.r))) return [];
  const path: Tile[] = [];
  let cur = key(to.c, to.r);
  while (cur !== key(from.c, from.r)) {
    path.unshift({ c: cur % COLS, r: Math.floor(cur / COLS) });
    const p = prev.get(cur);
    if (p === undefined) return [];
    cur = p;
  }
  return path;
}

// --- タイル・家具の手続き描画 ------------------------------------------------

function tex(
  scene: Phaser.Scene,
  key: string,
  w: number,
  h: number,
  draw: (ctx: CanvasRenderingContext2D) => void,
) {
  if (scene.textures.exists(key)) return;
  const canvas = scene.textures.createCanvas(key, w, h);
  if (!canvas) return;
  draw(canvas.getContext());
  canvas.refresh();
}

/** 決定論ノイズ（同じ座標なら常に同じ値）。 */
function noise(x: number, y: number): number {
  return ((x * 73 + y * 151 + 29) * 7919) % 97;
}

export function registerWorldTextures(scene: Phaser.Scene) {
  // 石畳の床
  tex(scene, "tile.floor", TILE, TILE, (ctx) => {
    ctx.fillStyle = "#474254";
    ctx.fillRect(0, 0, TILE, TILE);
    ctx.fillStyle = "#332f3e";
    ctx.fillRect(0, TILE - 1, TILE, 1);
    ctx.fillRect(TILE - 1, 0, 1, TILE);
    ctx.fillStyle = "#524d61";
    ctx.fillRect(0, 0, TILE, 1);
    ctx.fillRect(0, 0, 1, TILE);
    for (let y = 2; y < TILE - 2; y += 3) {
      for (let x = 2; x < TILE - 2; x += 3) {
        if (noise(x, y) < 18) {
          ctx.fillStyle = "#3d3949";
          ctx.fillRect(x, y, 2, 1);
        }
      }
    }
  });
  // 赤じゅうたん（入口から中央テーブルへ）
  tex(scene, "tile.carpet", TILE, TILE, (ctx) => {
    ctx.fillStyle = "#7f1d1d";
    ctx.fillRect(0, 0, TILE, TILE);
    ctx.fillStyle = "#991f1f";
    for (let y = 1; y < TILE; y += 4) {
      for (let x = (y % 8 === 1 ? 1 : 3); x < TILE; x += 4) ctx.fillRect(x, y, 1, 1);
    }
    ctx.fillStyle = "#601616";
    ctx.fillRect(0, TILE - 1, TILE, 1);
  });
  tex(scene, "tile.carpetEdge", TILE, 2, (ctx) => {
    ctx.fillStyle = "#fbbf24";
    ctx.fillRect(0, 0, TILE, 1);
    ctx.fillStyle = "#601616";
    ctx.fillRect(0, 1, TILE, 1);
  });
  // 壁（上段＝暗がり、下段＝石レンガ）
  tex(scene, "tile.wallTop", TILE, TILE, (ctx) => {
    ctx.fillStyle = "#1a1723";
    ctx.fillRect(0, 0, TILE, TILE);
    ctx.fillStyle = "#232030";
    for (let y = 0; y < TILE; y += 4) {
      ctx.fillRect(0, y, TILE, 1);
    }
  });
  tex(scene, "tile.wallFace", TILE, TILE, (ctx) => {
    ctx.fillStyle = "#57534e";
    ctx.fillRect(0, 0, TILE, TILE);
    ctx.fillStyle = "#292524";
    for (let y = 3; y < TILE; y += 4) ctx.fillRect(0, y, TILE, 1);
    for (let y = 0; y < TILE; y += 4) {
      const off = (y / 4) % 2 === 0 ? 3 : 9;
      ctx.fillRect(off, y, 1, 4);
      ctx.fillRect((off + 8) % TILE, y, 1, 4);
    }
    ctx.fillStyle = "#3f3c38";
    ctx.fillRect(0, TILE - 2, TILE, 2);
  });
  // クエスト掲示板（2タイル幅）
  tex(scene, "deco.board", TILE * BOARD.w, TILE, (ctx) => {
    ctx.fillStyle = "#5c3a1e";
    ctx.fillRect(1, 1, TILE * BOARD.w - 2, TILE - 2);
    ctx.fillStyle = "#7c4a24";
    ctx.fillRect(2, 2, TILE * BOARD.w - 4, TILE - 4);
    ctx.fillStyle = "#f5f0e6";
    ctx.fillRect(5, 4, 5, 7);
    ctx.fillRect(13, 5, 5, 6);
    ctx.fillRect(21, 4, 5, 7);
    ctx.fillStyle = "#b91c1c";
    ctx.fillRect(6, 5, 1, 1);
    ctx.fillRect(14, 6, 1, 1);
    ctx.fillRect(22, 5, 1, 1);
    ctx.fillStyle = "#94794f";
    ctx.fillRect(6, 8, 3, 1);
    ctx.fillRect(14, 8, 3, 1);
    ctx.fillRect(22, 8, 3, 1);
  });
  // ぼうけんのしょ本棚（3タイル幅）
  tex(scene, "deco.shelf", TILE * SHELF.w, TILE, (ctx) => {
    const w = TILE * SHELF.w;
    ctx.fillStyle = "#4a2f18";
    ctx.fillRect(0, 0, w, TILE);
    ctx.fillStyle = "#2e1d0f";
    ctx.fillRect(0, 6, w, 1);
    ctx.fillRect(0, TILE - 2, w, 2);
    const spines = ["#dc2626", "#2563eb", "#16a34a", "#d97706", "#7c3aed", "#0d9488"];
    for (let x = 2; x < w - 3; x += 3) {
      const i = Math.floor(x / 3);
      ctx.fillStyle = spines[i % spines.length];
      ctx.fillRect(x, 1, 2, 5);
      ctx.fillStyle = spines[(i + 3) % spines.length];
      ctx.fillRect(x, 8, 2, 6);
    }
  });
  // たいまつ（受け金具＋2フレームの炎）
  tex(scene, "deco.sconce", 6, 6, (ctx) => {
    ctx.fillStyle = "#78716c";
    ctx.fillRect(2, 0, 2, 4);
    ctx.fillStyle = "#57534e";
    ctx.fillRect(1, 4, 4, 2);
  });
  tex(scene, "fx.flame0", 6, 8, (ctx) => {
    ctx.fillStyle = "#f97316";
    ctx.fillRect(1, 3, 4, 4);
    ctx.fillRect(2, 1, 2, 2);
    ctx.fillStyle = "#fde047";
    ctx.fillRect(2, 4, 2, 3);
  });
  tex(scene, "fx.flame1", 6, 8, (ctx) => {
    ctx.fillStyle = "#f97316";
    ctx.fillRect(1, 2, 4, 5);
    ctx.fillRect(3, 0, 2, 2);
    ctx.fillStyle = "#fde047";
    ctx.fillRect(2, 3, 2, 4);
    ctx.fillRect(3, 1, 1, 2);
  });
  // 中央テーブル（2×2タイル・成果物の置き場）
  tex(scene, "furn.table", TILE * 2, TILE * 2, (ctx) => {
    ctx.fillStyle = "#8a5a32";
    ctx.fillRect(1, 2, 30, 18);
    ctx.fillStyle = "#9a6b3f";
    ctx.fillRect(2, 3, 28, 16);
    ctx.fillStyle = "#8a5a32";
    for (let y = 6; y < 18; y += 4) ctx.fillRect(2, y, 28, 1);
    // 手前の板面と脚
    ctx.fillStyle = "#6b4423";
    ctx.fillRect(1, 20, 30, 6);
    ctx.fillRect(3, 26, 3, 5);
    ctx.fillRect(26, 26, 3, 5);
    // 天板の上：羊皮紙とインク瓶（成果物）
    ctx.fillStyle = "#f5f0e6";
    ctx.fillRect(6, 6, 8, 10);
    ctx.fillStyle = "#94794f";
    ctx.fillRect(7, 8, 6, 1);
    ctx.fillRect(7, 11, 6, 1);
    ctx.fillRect(7, 14, 4, 1);
    ctx.fillStyle = "#1e3a8a";
    ctx.fillRect(20, 8, 4, 5);
    ctx.fillStyle = "#60a5fa";
    ctx.fillRect(21, 9, 2, 2);
  });
  // 担当の机（1タイル）
  tex(scene, "furn.desk", TILE, TILE, (ctx) => {
    ctx.fillStyle = "#8a5a32";
    ctx.fillRect(0, 1, TILE, 6);
    ctx.fillStyle = "#9a6b3f";
    ctx.fillRect(1, 2, TILE - 2, 4);
    ctx.fillStyle = "#6b4423";
    ctx.fillRect(0, 7, TILE, 5);
    ctx.fillRect(1, 12, 2, 4);
    ctx.fillRect(TILE - 3, 12, 2, 4);
    // 机上の書きかけの羊皮紙
    ctx.fillStyle = "#f5f0e6";
    ctx.fillRect(5, 2, 6, 4);
    ctx.fillStyle = "#94794f";
    ctx.fillRect(6, 3, 4, 1);
    ctx.fillRect(6, 5, 3, 1);
  });
  // エフェクト素材
  tex(scene, "fx.spark", 3, 3, (ctx) => {
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(1, 0, 1, 3);
    ctx.fillRect(0, 1, 3, 1);
  });
  tex(scene, "fx.confetti", 2, 2, (ctx) => {
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, 2, 2);
  });
}

/**
 * 背景（床・壁・じゅうたん・掲示板・本棚）を1枚のcanvasテクスチャに合成して置く。
 * 動きのあるもの（炎・机・テーブル）は呼び出し側が個別スプライトで重ねる。
 */
export function drawGround(scene: Phaser.Scene) {
  const key = "world.ground";
  if (!scene.textures.exists(key)) {
    const canvas = scene.textures.createCanvas(key, COLS * TILE, ROWS * TILE);
    if (!canvas) return;
    const ctx = canvas.getContext();
    const stamp = (tile: string, c: number, r: number) => {
      const src = scene.textures.get(tile).getSourceImage() as HTMLCanvasElement;
      ctx.drawImage(src, c * TILE, r * TILE);
    };
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        stamp(r === 0 ? "tile.wallTop" : r === 1 ? "tile.wallFace" : "tile.floor", c, r);
      }
    }
    // 入口→テーブルの赤じゅうたん（金の縁取り）
    for (let r = 5; r < ROWS; r++) {
      stamp("tile.carpet", 7, r);
      stamp("tile.carpet", 8, r);
    }
    const edge = scene.textures.get("tile.carpetEdge").getSourceImage() as HTMLCanvasElement;
    ctx.drawImage(edge, 7 * TILE, 5 * TILE);
    ctx.drawImage(edge, 8 * TILE, 5 * TILE);
    stamp("deco.board", BOARD.c, BOARD.r);
    ctx.drawImage(
      scene.textures.get("deco.shelf").getSourceImage() as HTMLCanvasElement,
      SHELF.c * TILE,
      SHELF.r * TILE,
    );
    // ギルドの扉（編成はここから入場する）
    const dx = DOOR.c * TILE;
    const dy = DOOR.r * TILE;
    ctx.fillStyle = "#3b2410";
    ctx.fillRect(dx, dy - 2, TILE, TILE + 2);
    ctx.fillStyle = "#120b06";
    ctx.fillRect(dx + 2, dy, TILE - 4, TILE);
    ctx.fillStyle = "#5c3a1e";
    ctx.fillRect(dx, dy - 2, 2, TILE + 2);
    ctx.fillRect(dx + TILE - 2, dy - 2, 2, TILE + 2);
    ctx.fillRect(dx, dy - 2, TILE, 2);
    canvas.refresh();
  }
  scene.add.image(0, 0, key).setOrigin(0, 0).setScale(SCALE).setDepth(0);
}
