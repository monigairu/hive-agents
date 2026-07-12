/**
 * ドラクエ風RPG描画（要件 F-14・v2.13）。
 *
 * M3のSSEイベントストリームを「ギルドの作業場ではたらくキャラたち」として
 * 描くだけの表示層。データ（イベント）と描画の分離が原則で、ここにビジネス
 * ロジックは置かない。サウンドは実装しない（要件で明示的に対象外）。
 *
 * v2.13の振付原則：
 * - 働くときは自分の机で働く（F-03の並列実行を画面でもそのまま同時に描く）
 * - 演出キューはシーン1本ではなくキャラごとの行動キュー
 * - handoffは相手の机まで歩いて行って渡す（瞬間移動しない）
 * - イベントが無い時間もアイドル行動（まばたき・うろつき・💤）で生きて見せる
 *
 * 表示名の原則（F-14）：キャラの見た目は職業風だが、画面に出す名前は
 * 一般の人でも工程がわかる役割名（設計担当・実装担当・テスト担当・セキュリティ監査）。
 */

import * as Phaser from "phaser";

import { CHARS, registerAllChars, registerEmotes, type EmoteKind, type Facing } from "./sprites";
import {
  BOARD,
  DESK_ROW,
  DOOR,
  ENTRANCE,
  H,
  INSPECT,
  SHELF,
  STAND_ROW,
  TABLE,
  TORCHES,
  TS,
  W,
  buildGrid,
  deskCols,
  drawGround,
  findPath,
  registerWorldTextures,
  tileXY,
  type Tile,
} from "./world";

export type HiveEvent = { type: string; data: Record<string, unknown> };

export type HiveGame = {
  enqueue: (e: HiveEvent) => void;
  /** 過去イベントを瞬間適用して途中状態を復元する（ページ遷移からの復帰用） */
  replay: (events: HiveEvent[]) => void;
  destroy: () => void;
};

// 既知のAgentの表示名カタログ。実際の編成（パーティ）は router イベントが運んでくる
// （F-02 動的エージェント組成：タスクによって働くAgentが変わる）
const LABEL: Record<string, string> = {
  designer: "設計担当",
  implementer: "実装担当",
  frontend: "画面担当",
  tester: "テスト担当",
  security_reviewer: "セキュリティ監査",
};

const FONT = {
  fontFamily: "'DotGothic16', 'MS Gothic', monospace",
  color: "#ffffff",
};

// 実装が一瞬で終わるタスクでも「働いている感」が出る最低演出時間
const MIN_WORK_MS = 2600;
const WALK_MS = 150; // 1タイルの歩行時間
const CHAR_SCALE = 4;
const EMOTE_Y = 62; // 頭上エモートの高さ
const DEPTH_UI = 1500; // ステータス窓
const DEPTH_MSG = 2000; // メッセージウィンドウ

/**
 * 表示用の切り詰め。サーバが流す説明文（設計の機能一覧など）は長文のことが
 * あるため、ぶつ切り（「…オフラ」等の不自然な日本語）を避けて
 * 句読点・区切り記号の位置で切り、切ったことがわかるよう「…」を付ける。
 */
function clip(text: string, max: number): string {
  const t = text.replace(/\s+/g, " ").trim();
  if (t.length <= max) return t;
  const head = t.slice(0, max);
  const last = (chars: string[]) => Math.max(...chars.map((ch) => head.lastIndexOf(ch)));
  // 文の区切り（。、；等）を優先し、無ければ語の区切り（空白・スラッシュ）で切る。
  // 区切りが前方すぎるときは文字数優先（短くなりすぎを防ぐ）
  const strong = last(["。", "、", "；", ";", "・"]);
  const weak = last([" ", "／", "/", "「"]);
  let boundary = -1;
  if (strong >= Math.floor(max * 0.4)) boundary = strong;
  else if (weak >= Math.floor(max * 0.55)) boundary = weak;
  const cut = boundary > 0 ? head.slice(0, boundary) : head;
  return `${cut}…`;
}

const STATUS_COLOR = {
  wait: "#9ca3af",
  work: "#fbbf24",
  done: "#34d399",
  audit: "#fb7185",
  danger: "#f87171",
  power: "#c084fc",
} as const;

type Actor = {
  name: string;
  sprite: Phaser.GameObjects.Image;
  emote: Phaser.GameObjects.Image;
  emoteKind: EmoteKind | null;
  statusText: Phaser.GameObjects.Text;
  tile: Tile;
  facing: Facing;
  flip: boolean;
  stand: Tile;
  queue: (() => Promise<void>)[];
  running: boolean;
  working: boolean;
  workFx: { bob?: Phaser.Tweens.Tween; spark?: Phaser.Time.TimerEvent };
  pro: boolean;
  /** 実イベントが最後に触った時刻（💤の判定。アイドル行動ではリセットしない） */
  lastEvent: number;
  /** 何かの行動が最後に終わった時刻（アイドル行動のペース配分） */
  lastActive: number;
};

class HiveRpgScene extends Phaser.Scene {
  private actors = new Map<string, Actor>();
  private partyUi: Phaser.GameObjects.GameObject[] = [];
  private grid: boolean[][] = buildGrid([]);

  private messages: string[] = [];
  private typingLine = "";
  private msgQueue: string[] = [];
  private typing = false;
  /** replayでの全消去時に走行中のタイプライターを打ち切るための世代番号 */
  private msgGen = 0;
  private messageText!: Phaser.GameObjects.Text;
  private cursor!: Phaser.GameObjects.Text;

  /** handoff で受け取った「次は何をするか」をagent_startの台詞に使う */
  private pendingDetail = new Map<string, string>();
  private startedAt = new Map<string, number>();

  private ready = false;
  private preQueue: HiveEvent[] = [];
  private pendingReplay: HiveEvent[] | null = null;
  private destroyed = false;

  constructor() {
    super("hive-rpg");
  }

  enqueue(e: HiveEvent) {
    if (!this.ready) {
      this.preQueue.push(e);
      return;
    }
    this.dispatch(e);
  }

  /** 過去イベントを瞬間適用して途中状態を復元する。create前に呼ばれたら保留する。 */
  replay(events: HiveEvent[]) {
    if (!this.ready) {
      this.pendingReplay = events;
      return;
    }
    this.clearParty();
    this.msgQueue = [];
    this.msgGen++;
    this.typing = false;
    this.typingLine = "";
    this.messages = [];
    this.renderMessages();
    if (events.length === 0) {
      this.addMessage("クエストを 発注すると オーケストレーターが はたらきバチを へんせいする…");
      return;
    }
    for (const e of events) this.applyInstant(e);
    this.renderMessages();
  }

  create() {
    this.cameras.main.setBackgroundColor("#100d16");
    registerWorldTextures(this);
    registerAllChars(this);
    registerEmotes(this);
    drawGround(this);
    this.placeFurnitureBase();
    this.drawMessageWindow();
    this.time.addEvent({ delay: 1100, loop: true, callback: () => this.idleTick() });
    this.addMessage("クエストを 発注すると オーケストレーターが はたらきバチを へんせいする…");
    this.ready = true;
    if (this.pendingReplay) {
      const events = this.pendingReplay;
      this.pendingReplay = null;
      this.replay(events);
    }
    for (const e of this.preQueue.splice(0)) this.dispatch(e);
    this.events.once(Phaser.Scenes.Events.DESTROY, () => {
      this.destroyed = true;
    });
  }

  // --- 舞台の常設物 -----------------------------------------------------------

  private placeFurnitureBase() {
    // 中央テーブル（キャラより上＝南側を歩くと手前に来るよう底辺で深度を決める）
    this.add
      .image(TABLE.c1 * TS, TABLE.r1 * TS, "furn.table")
      .setOrigin(0, 0)
      .setScale(3)
      .setDepth((TABLE.r2 + 1) * TS - 6);
    // たいまつ（ゆらめく炎）
    const flames: Phaser.GameObjects.Image[] = [];
    for (const c of TORCHES) {
      const x = c * TS + TS / 2;
      this.add.image(x, TS + 34, "deco.sconce").setScale(3).setDepth(2);
      flames.push(this.add.image(x, TS + 16, "fx.flame0").setScale(3).setDepth(3));
    }
    this.time.addEvent({
      delay: 240,
      loop: true,
      callback: () => {
        for (const f of flames) {
          f.setTexture(Math.random() < 0.5 ? "fx.flame0" : "fx.flame1");
          f.setAlpha(0.85 + Math.random() * 0.15);
        }
      },
    });
  }

  // --- パーティ編成 -----------------------------------------------------------

  private clearParty() {
    this.tweens.killAll();
    this.actors.forEach((a) => {
      a.workFx.spark?.remove();
      a.sprite.destroy();
      a.emote.destroy();
      a.queue = [];
    });
    this.actors.clear();
    for (const obj of this.partyUi) obj.destroy();
    this.partyUi = [];
    this.pendingDetail.clear();
    this.startedAt.clear();
    this.grid = buildGrid([]);
  }

  /** router の編成結果に従ってパーティを出現させる（F-02 動的エージェント組成）。 */
  private spawnParty(party: { agent: string; role: string }[], instant: boolean) {
    this.clearParty();
    const cols = deskCols(party.length);
    this.grid = buildGrid(cols.slice(0, party.length));

    party.forEach(({ agent, role }, i) => {
      const c = cols[i];
      const deskX = c * TS + TS / 2;
      // 机（持ち場）
      this.partyUi.push(
        this.add
          .image(deskX, (DESK_ROW + 1) * TS, "furn.desk")
          .setOrigin(0.5, 1)
          .setScale(3)
          .setDepth((DESK_ROW + 1) * TS - 6),
      );
      // ステータス窓（なまえ・じょうたい）を机の下に
      const px = deskX - 66;
      this.partyUi.push(this.drawWindow(px, 338, 132, 46, DEPTH_UI));
      const name = this.add
        .text(px + 9, 344, LABEL[agent] ?? role ?? agent, { ...FONT, fontSize: "11px" })
        .setResolution(2)
        .setDepth(DEPTH_UI + 1);
      const status = this.add
        .text(px + 9, 362, "じょうたい：まち", {
          ...FONT,
          fontSize: "10px",
          color: STATUS_COLOR.wait,
        })
        .setResolution(2)
        .setDepth(DEPTH_UI + 1);
      this.partyUi.push(name, status);

      // キャラ本体
      const stand: Tile = { c, r: STAND_ROW };
      const texKey = CHARS[agent] ? agent : "implementer";
      const start = instant ? tileXY(stand) : tileXY(DOOR);
      const sprite = this.add
        .image(start.x, start.y, `${texKey}.down0`)
        .setScale(CHAR_SCALE)
        .setOrigin(0.5, 1)
        .setAlpha(instant ? 1 : 0);
      const emote = this.add.image(start.x, start.y - EMOTE_Y, "emote.think").setScale(3).setVisible(false);
      const actor: Actor = {
        name: texKey,
        sprite,
        emote,
        emoteKind: null,
        statusText: status,
        tile: instant ? stand : { ...ENTRANCE },
        facing: "down",
        flip: false,
        stand,
        queue: [],
        running: false,
        working: false,
        workFx: {},
        pro: false,
        lastEvent: this.time.now,
        lastActive: this.time.now,
      };
      this.actors.set(agent, actor);
      this.follow(actor);

      if (!instant) {
        // ギルドの扉から一人ずつ入場して持ち場へ歩く
        this.pushAction(agent, async () => {
          await this.sleep(200 + i * 480);
          this.face(actor, "down");
          sprite.setAlpha(1);
          await this.tweenP({
            targets: sprite,
            y: tileXY(ENTRANCE).y,
            duration: WALK_MS * 2,
            onUpdate: () => this.walkFrame(actor),
          });
          actor.tile = { ...ENTRANCE };
          await this.walkTo(actor, stand);
          this.face(actor, "down");
        });
      }
    });
  }

  // --- キャラの基本動作 -------------------------------------------------------

  private texBase(a: Actor): string {
    return a.pro && CHARS[`${a.name}_pro`] ? `${a.name}_pro` : a.name;
  }

  private setFrame(a: Actor, phase: 0 | 1) {
    a.sprite.setTexture(`${this.texBase(a)}.${a.facing}${phase}`);
    a.sprite.setFlipX(a.facing === "side" && a.flip);
  }

  private face(a: Actor, facing: Facing, flip = false) {
    a.facing = facing;
    a.flip = flip;
    this.setFrame(a, 0);
  }

  private faceToward(a: Actor, x: number) {
    this.face(a, "side", x < a.sprite.x);
  }

  private walkFrame(a: Actor) {
    this.setFrame(a, (Math.floor(this.time.now / 130) % 2) as 0 | 1);
    this.follow(a);
  }

  private follow(a: Actor) {
    a.sprite.setDepth(a.sprite.y);
    a.emote.setPosition(a.sprite.x, a.sprite.y - EMOTE_Y).setDepth(a.sprite.y + 1);
  }

  private async walkTo(a: Actor, dest: Tile) {
    // 仲間が立っているタイルは避けて歩く（重なり防止）。避けると届かない場合だけ素通りを許す
    const occupied = this.grid.map((row) => [...row]);
    this.actors.forEach((other) => {
      if (other !== a) occupied[other.tile.r][other.tile.c] = false;
    });
    let path = findPath(occupied, a.tile, dest);
    if (path.length === 0) path = findPath(this.grid, a.tile, dest);
    for (const step of path) {
      const dc = step.c - a.tile.c;
      if (dc !== 0) {
        a.facing = "side";
        a.flip = dc < 0;
      } else {
        a.facing = step.r - a.tile.r > 0 ? "down" : "up";
      }
      const { x, y } = tileXY(step);
      await this.tweenP({
        targets: a.sprite,
        x,
        y,
        duration: WALK_MS,
        onUpdate: () => this.walkFrame(a),
      });
      a.tile = step;
    }
    this.setFrame(a, 0);
    this.follow(a);
  }

  private setEmote(a: Actor, kind: EmoteKind | null) {
    a.emoteKind = kind;
    if (kind) a.emote.setTexture(`emote.${kind}`).setVisible(true);
    else a.emote.setVisible(false);
    this.follow(a);
  }

  private setStatus(agent: string, state: string, color: string) {
    this.actors.get(agent)?.statusText.setText(`じょうたい：${state}`).setColor(color);
  }

  private startWork(a: Actor) {
    if (a.working) return;
    a.working = true;
    this.setEmote(a, "think");
    const baseY = tileXY(a.tile).y;
    a.workFx.bob = this.tweens.add({
      targets: a.sprite,
      y: baseY - 3,
      duration: 270,
      yoyo: true,
      repeat: -1,
      onUpdate: () => this.follow(a),
    });
    a.workFx.spark = this.time.addEvent({
      delay: 2700,
      loop: true,
      callback: () => this.sparkle(a.sprite.x + 14, a.sprite.y + 20, 0xfde047, 3),
    });
  }

  private stopWork(a: Actor) {
    a.working = false;
    a.workFx.bob?.remove();
    a.workFx.spark?.remove();
    a.workFx = {};
    a.sprite.setY(tileXY(a.tile).y);
    if (a.emoteKind === "think") this.setEmote(a, null);
    this.follow(a);
  }

  // --- キャラごとの行動キュー ---------------------------------------------------

  private pushAction(agent: string, fn: () => Promise<void>, isEvent = true) {
    const a = this.actors.get(agent);
    if (!a) return;
    if (isEvent) a.lastEvent = this.time.now;
    a.queue.push(fn);
    if (!a.running) void this.pumpActor(a);
  }

  private async pumpActor(a: Actor) {
    a.running = true;
    while (a.queue.length > 0 && !this.destroyed) {
      if (a.emoteKind === "sleep") this.setEmote(a, null);
      const fn = a.queue.shift() as () => Promise<void>;
      try {
        await fn();
      } catch {
        /* 演出の失敗でキューを止めない */
      }
      a.lastActive = this.time.now;
    }
    a.running = false;
  }

  /** 待機中のキャラに命を吹き込む（まばたき・うろつき・💤）。 */
  private idleTick() {
    this.actors.forEach((a) => {
      if (a.working || a.running || a.queue.length > 0) return;
      const sinceEvent = this.time.now - a.lastEvent;
      if (sinceEvent > 45000) {
        if (a.emoteKind !== "sleep") this.setEmote(a, "sleep");
        return;
      }
      if (this.time.now - a.lastActive < 2600 || Math.random() > 0.3) return;
      const roll = Math.random();
      if (roll < 0.5 && a.facing === "down") {
        // まばたき
        this.pushAction(
          this.keyOf(a),
          async () => {
            a.sprite.setTexture(`${this.texBase(a)}.blink`);
            await this.sleep(140);
            this.setFrame(a, 0);
          },
          false,
        );
      } else if (roll < 0.8) {
        // 近くをうろつく
        const spots: Tile[] = [
          { c: a.stand.c - 1, r: a.stand.r },
          { c: a.stand.c + 1, r: a.stand.r },
          { c: a.stand.c, r: a.stand.r - 1 },
        ].filter((t) => this.grid[t.r]?.[t.c]);
        if (spots.length === 0) return;
        const spot = spots[Math.floor(Math.random() * spots.length)];
        this.pushAction(
          this.keyOf(a),
          async () => {
            await this.walkTo(a, spot);
            await this.sleep(500 + Math.random() * 700);
            await this.walkTo(a, a.stand);
            this.face(a, "down");
          },
          false,
        );
      } else {
        // よそ見
        this.pushAction(
          this.keyOf(a),
          async () => {
            this.face(a, "side", Math.random() < 0.5);
            await this.sleep(700);
            this.face(a, "down");
          },
          false,
        );
      }
    });
  }

  private keyOf(a: Actor): string {
    for (const [key, actor] of this.actors) if (actor === a) return key;
    return a.name;
  }

  // --- エフェクト -------------------------------------------------------------

  private sparkle(x: number, y: number, color: number, n = 6) {
    for (let i = 0; i < n; i++) {
      const s = this.add
        .image(x, y, "fx.spark")
        .setScale(2 + Math.random() * 2)
        .setTint(color)
        .setDepth(1200);
      this.tweens.add({
        targets: s,
        x: x + (Math.random() - 0.5) * 64,
        y: y - 10 - Math.random() * 34,
        alpha: 0,
        duration: 480 + Math.random() * 320,
        onComplete: () => s.destroy(),
      });
    }
  }

  private glowShelf(color: number) {
    const g = this.add
      .rectangle(SHELF.c * TS, SHELF.r * TS, SHELF.w * TS, TS, color, 0.4)
      .setOrigin(0, 0)
      .setDepth(10)
      .setAlpha(0);
    this.tweens.add({
      targets: g,
      alpha: 1,
      duration: 350,
      yoyo: true,
      repeat: 2,
      onComplete: () => g.destroy(),
    });
    this.sparkle(SHELF.c * TS + (SHELF.w * TS) / 2, SHELF.r * TS + TS / 2, color, 5);
  }

  private tableCenter() {
    return { x: TABLE.c1 * TS + TS, y: TABLE.r1 * TS + TS };
  }

  private magicCircle() {
    const { x, y } = this.tableCenter();
    const g = this.add.graphics().setDepth(1100);
    g.lineStyle(3, 0x67e8f9, 0.9).strokeEllipse(x, y + 26, 108, 44);
    g.lineStyle(2, 0x22d3ee, 0.7).strokeEllipse(x, y + 26, 76, 30);
    g.setAlpha(0);
    this.tweens.add({
      targets: g,
      alpha: 1,
      duration: 300,
      yoyo: true,
      repeat: 3,
      onComplete: () => g.destroy(),
    });
  }

  private confetti() {
    const colors = [0xf87171, 0xfbbf24, 0x34d399, 0x60a5fa, 0xc084fc, 0xf8fafc];
    for (let i = 0; i < 44; i++) {
      const x = W / 2 + (Math.random() - 0.5) * 420;
      const piece = this.add
        .image(x, 40 + Math.random() * 60, "fx.confetti")
        .setScale(2 + Math.random() * 2)
        .setTint(colors[i % colors.length])
        .setDepth(1300)
        .setAlpha(0.95);
      this.tweens.add({
        targets: piece,
        y: 320 + Math.random() * 60,
        x: x + (Math.random() - 0.5) * 90,
        angle: (Math.random() - 0.5) * 360,
        alpha: 0,
        duration: 1500 + Math.random() * 900,
        delay: Math.random() * 500,
        ease: "Sine.easeIn",
        onComplete: () => piece.destroy(),
      });
    }
  }

  // --- メッセージウィンドウ（タイプライター＋▼点滅） ---------------------------

  /** ドラクエ風ウィンドウ（黒地・白の二重枠）。 */
  private drawWindow(x: number, y: number, w: number, h: number, depth: number) {
    const g = this.add.graphics().setDepth(depth);
    g.fillStyle(0x000000, 0.92).fillRoundedRect(x, y, w, h, 6);
    g.lineStyle(2, 0xffffff, 1).strokeRoundedRect(x + 2, y + 2, w - 4, h - 4, 5);
    g.lineStyle(1, 0xffffff, 0.6).strokeRoundedRect(x + 5, y + 5, w - 10, h - 10, 4);
    return g;
  }

  private drawMessageWindow() {
    this.drawWindow(8, 392, W - 16, H - 400, DEPTH_MSG);
    this.messageText = this.add
      .text(26, 406, "", { ...FONT, fontSize: "15px", lineSpacing: 9, wordWrap: { width: W - 52 } })
      .setResolution(2)
      .setDepth(DEPTH_MSG + 1);
    this.cursor = this.add
      .text(W - 34, H - 28, "▼", { ...FONT, fontSize: "13px" })
      .setResolution(2)
      .setDepth(DEPTH_MSG + 1);
    this.time.addEvent({
      delay: 420,
      loop: true,
      callback: () => this.cursor.setVisible(!this.typing && !this.cursor.visible),
    });
  }

  private addMessage(text: string) {
    this.msgQueue.push(text);
    void this.pumpMessages();
  }

  private commitLine(line: string) {
    this.messages = [...this.messages, line].slice(-3);
    this.typingLine = "";
    this.renderMessages();
  }

  private renderMessages() {
    const lines = this.typingLine
      ? [...this.messages.slice(-2), this.typingLine]
      : this.messages;
    this.messageText?.setText(lines.join("\n"));
  }

  private async pumpMessages() {
    if (this.typing) return;
    this.typing = true;
    // replayが窓を全消去したら世代が進む。古い世代のループは何も触らず即終了する
    // （放置すると新旧2本のループが1文字ずつ交互に書いて「ククエエスストト」になる）
    const gen = this.msgGen;
    while (this.msgQueue.length > 0 && !this.destroyed) {
      const line = `＊ ${this.msgQueue.shift()}`;
      // イベントが溜まっているときは文字送りをやめて追いつく（実況を遅延させない）
      if (this.msgQueue.length >= 2) {
        this.commitLine(line);
        continue;
      }
      this.typingLine = "";
      for (const ch of line) {
        this.typingLine += ch;
        this.renderMessages();
        await this.sleep(20);
        if (gen !== this.msgGen) return;
        if (this.msgQueue.length >= 2) break;
      }
      this.commitLine(line);
      await this.sleep(140);
      if (gen !== this.msgGen) return;
    }
    this.typing = false;
  }

  // --- 小さなPromiseユーティリティ ---------------------------------------------

  private sleep(ms: number) {
    return new Promise<void>((resolve) => this.time.delayedCall(ms, resolve));
  }

  private tweenP(config: Phaser.Types.Tweens.TweenBuilderConfig | object) {
    return new Promise<void>((resolve) => {
      this.tweens.add({
        ...(config as Phaser.Types.Tweens.TweenBuilderConfig),
        onComplete: () => resolve(),
      });
    });
  }

  // --- イベント → 振付 ---------------------------------------------------------

  private dispatch(e: HiveEvent) {
    const d = e.data;
    const agent = String(d.agent ?? "");
    switch (e.type) {
      case "task_received": {
        this.addMessage(`クエスト：${clip(String(d.task ?? ""), 40)}`);
        this.sparkle((BOARD.c + 1) * TS, BOARD.r * TS + TS / 2, 0xfbbf24, 6);
        return;
      }
      case "armor": {
        const allowed = String(d.allowed) !== "false";
        const checked = String(d.checked) === "true";
        if (!checked && allowed) return; // 検査スキップは映さない
        if (String(d.stage) === "prompt") {
          if (allowed) this.addMessage("けっかい（Model Armor）が 発注文を しらべた ── あんぜん！");
          else {
            this.cameras.main.flash(400, 220, 38, 38);
            const matched = (d.matched as string[]) ?? [];
            this.addMessage(`けっかいが はつどう！ あやしい発注文を はじいた（${matched.join("・")}）`);
          }
        } else {
          this.addMessage(
            allowed
              ? "のうひん前の さいしゅうけんさ ── もんだいなし"
              : "のうひん前の さいしゅうけんさ ── きけんな内容を けんしゅつ！",
          );
        }
        return;
      }
      case "intake_start":
        return this.addMessage("うけつけが 依頼書を かいている…");
      case "order_spec": {
        const what = String(d.what ?? "");
        if (what) this.addMessage(`依頼書：${clip(what, 40)}`);
        return;
      }
      case "router": {
        const party = (d.party as { agent: string; role: string }[]) ?? [];
        const rank = String(d.rank ?? "?");
        const sakusen = String(d.sakusen ?? d.quality ?? "");
        const model = String(d.model ?? "").includes("pro") ? "Pro" : "Flash";
        this.addMessage(`クエストなんいど：討伐ランク ${rank}（${String(d.task_type ?? "")}）`);
        if (sakusen) this.addMessage(`さくせん：${sakusen}（モデル ${model}）`);
        if (party.length > 0) {
          this.spawnParty(party, false);
          this.addMessage(`なかま：${party.map((p) => LABEL[p.agent] ?? p.agent).join("・")}`);
        }
        return;
      }
      case "memory_recall": {
        const lessons = (d.lessons as string[]) ?? [];
        this.glowShelf(0xfbbf24);
        return this.addMessage(
          `むかしの きおくを おもいだした：${clip(lessons[0] ?? "", 30)}`,
        );
      }
      case "agent_start": {
        if (!this.actors.has(agent)) return;
        const detail = String(d.detail ?? "") || this.pendingDetail.get(agent) || "";
        this.pendingDetail.delete(agent);
        return this.pushAction(agent, async () => {
          const a = this.actors.get(agent);
          if (!a) return;
          await this.walkTo(a, a.stand);
          this.face(a, "down");
          this.startedAt.set(agent, this.time.now);
          this.setStatus(agent, "しごとちゅう", STATUS_COLOR.work);
          this.addMessage(
            detail
              ? `${LABEL[agent] ?? agent}は 「${clip(detail, 28)}」に とりくんでいる…`
              : `${LABEL[agent] ?? agent}は かんがえている…`,
          );
          this.startWork(a);
        });
      }
      case "agent_output": {
        if (!this.actors.has(agent)) return;
        return this.pushAction(agent, async () => {
          const a = this.actors.get(agent);
          if (!a) return;
          // 一瞬で終わったタスクも MIN_WORK_MS は「働いている姿」を見せる
          const started = this.startedAt.get(agent) ?? 0;
          await this.sleep(Math.max(0, MIN_WORK_MS - (this.time.now - started)));
          this.stopWork(a);
          this.setEmote(a, "alert");
          this.setStatus(agent, "かんりょう", STATUS_COLOR.done);
          this.addMessage(`${LABEL[agent] ?? agent}の しごとが おわった`);
          await this.sleep(800);
          if (a.emoteKind === "alert") this.setEmote(a, null);
        });
      }
      case "handoff": {
        const from = String(d.from_agent ?? "");
        const to = String(d.to_agent ?? "");
        const item = String(d.item ?? "せいかぶつ");
        const detail = String(d.detail ?? "");
        if (detail) this.pendingDetail.set(to, detail);
        const fromA = this.actors.get(from);
        const toA = this.actors.get(to);
        if (!fromA || !toA) {
          this.addMessage(`${LABEL[from] ?? from}が ${item}を ${LABEL[to] ?? to}に わたした`);
          return;
        }
        // 2体のランデブー：渡す側が相手の机まで歩いて行って手渡す（A2Aの可視化）
        let releaseMeet!: () => void;
        const met = new Promise<void>((r) => (releaseMeet = r));
        let releaseTalk!: () => void;
        const talked = new Promise<void>((r) => (releaseTalk = r));
        this.pushAction(from, async () => {
          try {
            this.stopWork(fromA);
            this.setStatus(from, "かんりょう", STATUS_COLOR.done);
            const side = fromA.stand.c < toA.stand.c ? -1 : 1;
            let meet: Tile = { c: toA.stand.c + side, r: STAND_ROW };
            if (!this.grid[meet.r]?.[meet.c]) meet = { c: toA.stand.c - side, r: STAND_ROW };
            await this.walkTo(fromA, meet);
            this.faceToward(fromA, toA.sprite.x);
            this.setEmote(fromA, "talk");
            this.addMessage(`${LABEL[from] ?? from}「${item}が できたぞ！」`);
            releaseMeet();
            await this.sleep(1100);
            this.addMessage(`${LABEL[to] ?? to}「まかせろ！」── ${item}を うけとった`);
            this.setEmote(fromA, null);
            this.sparkle((fromA.sprite.x + toA.sprite.x) / 2, fromA.sprite.y - 30, 0xfbbf24, 7);
            releaseTalk();
            await this.sleep(250);
            await this.walkTo(fromA, fromA.stand);
            this.face(fromA, "down");
          } finally {
            releaseMeet();
            releaseTalk();
          }
        });
        return this.pushAction(to, async () => {
          await met;
          this.faceToward(toA, fromA.sprite.x);
          await talked;
          this.setEmote(toA, "alert");
          await this.sleep(400);
          this.setEmote(toA, null);
        });
      }
      case "security_start": {
        if (!this.actors.has("security_reviewer")) return;
        return this.pushAction("security_reviewer", async () => {
          const a = this.actors.get("security_reviewer");
          if (!a) return;
          this.setStatus("security_reviewer", "かんさちゅう", STATUS_COLOR.audit);
          this.addMessage("セキュリティかんさ かいし！ せいかぶつを けんぶんする…");
          await this.walkTo(a, INSPECT);
          this.faceToward(a, this.tableCenter().x);
          this.setEmote(a, "think");
          this.startedAt.set("security_reviewer", this.time.now);
        });
      }
      case "security_result": {
        const passed = String(d.passed) === "true";
        const findings = (d.findings as { severity: string }[]) ?? [];
        const criticals = findings.filter((f) => f.severity === "critical").length;
        if (!this.actors.has("security_reviewer")) {
          this.addMessage(passed ? "セキュリティかんさ クリア" : "ぜいじゃくせいあり！");
          return;
        }
        return this.pushAction("security_reviewer", async () => {
          const a = this.actors.get("security_reviewer");
          if (!a) return;
          const started = this.startedAt.get("security_reviewer") ?? 0;
          await this.sleep(Math.max(0, 1200 - (this.time.now - started)));
          this.setEmote(a, null);
          if (passed) {
            this.addMessage(`かんさ クリア！ ${String(d.summary ?? "もんだいなし")}`);
            this.setStatus("security_reviewer", "かんりょう", STATUS_COLOR.done);
            this.sparkle(this.tableCenter().x, this.tableCenter().y, 0x34d399, 8);
          } else {
            this.cameras.main.flash(400, 220, 38, 38);
            this.cameras.main.shake(300, 0.004);
            this.setEmote(a, "alert");
            this.addMessage(`このコードに ぜいじゃくせいあり！（critical ${criticals}件）`);
            this.setStatus("security_reviewer", "ようちゅうい", STATUS_COLOR.danger);
          }
          await this.sleep(700);
          if (a.emoteKind === "alert") this.setEmote(a, null);
          await this.walkTo(a, a.stand);
          this.face(a, "down");
        });
      }
      case "verify_start": {
        this.addMessage(
          String(d.mode) === "page"
            ? "ページが ちゃんと できているか しらべている…"
            : "サンドボックスで コードを ためしている…",
        );
        this.magicCircle();
        return;
      }
      case "verify_result": {
        const passed = String(d.passed) === "true";
        const isPage = String(d.mode) === "page";
        if (passed) {
          this.cameras.main.flash(300, 52, 211, 153);
          this.sparkle(this.tableCenter().x, this.tableCenter().y, 0x34d399, 10);
          this.addMessage(
            isPage
              ? "けんしょう クリア！ ページは ちゃんと できている"
              : "けんしょう クリア！ コードは ほんとうに うごいた",
          );
        } else {
          this.cameras.main.shake(300, 0.004);
          this.addMessage(
            isPage
              ? "けんしょう しっぱい… ページに もんだいが ある"
              : "けんしょう しっぱい… テストが とおらない",
          );
        }
        return;
      }
      case "retry": {
        this.addMessage(`もういちど ちょうせん！（${String(d.attempt)}/${String(d.max)}）`);
        const reason = String(d.reason ?? "");
        if (reason) this.addMessage(`りゆう：${clip(reason, 34)}`);
        return;
      }
      case "escalation": {
        const target = this.actors.has(agent) ? agent : "implementer";
        if (!this.actors.has(target)) {
          this.addMessage("しょうかんかいじょ！ 上位モデルに こうたいした");
          return;
        }
        return this.pushAction(target, async () => {
          const a = this.actors.get(target);
          if (!a) return;
          this.cameras.main.flash(500, 255, 255, 255);
          this.addMessage("しょうかんかいじょ！");
          await this.sleep(500);
          a.pro = true;
          this.setFrame(a, 0);
          this.sparkle(a.sprite.x, a.sprite.y - 26, 0xfde68a, 12);
          this.setStatus(target, "パワーアップ", STATUS_COLOR.power);
          this.addMessage(
            `あたらしい${LABEL[target] ?? target}（上位モデル）が なかまに くわわった！`,
          );
          await this.sleep(500);
        });
      }
      case "memory_write": {
        this.glowShelf(0x60a5fa);
        return this.addMessage(
          `ぼうけんのしょに きろくした：${clip(String(d.title ?? ""), 30)}`,
        );
      }
      case "done": {
        this.addMessage("クエスト かんりょう！ せいかぶつを のうひんした");
        const spots: Tile[] = [
          { c: 7, r: 5 },
          { c: 8, r: 5 },
          { c: 6, r: 4 },
          { c: 9, r: 4 },
          { c: 6, r: 5 },
          { c: 9, r: 5 },
        ];
        let i = 0;
        this.actors.forEach((a, key) => {
          const spot = spots[i % spots.length];
          i += 1;
          this.pushAction(key, async () => {
            this.stopWork(a);
            this.setEmote(a, null);
            await this.walkTo(a, spot);
            this.face(a, "down");
            await this.tweenP({
              targets: a.sprite,
              y: a.sprite.y - 16,
              duration: 150,
              yoyo: true,
              repeat: 2,
              onUpdate: () => this.follow(a),
            });
            this.follow(a);
          });
        });
        this.time.delayedCall(1300, () => this.confetti());
        return;
      }
      case "error": {
        this.cameras.main.shake(250, 0.003);
        this.addMessage(`エラーが おきた：${clip(String(d.message ?? ""), 40)}`);
        this.actors.forEach((a, key) => {
          this.pushAction(key, async () => {
            this.stopWork(a);
            this.setEmote(a, "alert");
            await this.sleep(900);
            this.setEmote(a, null);
          });
        });
        return;
      }
      default:
        return;
    }
  }

  // --- リプレイ（瞬間復元） -----------------------------------------------------

  private pushInstantMessage(text: string) {
    this.messages = [...this.messages, `＊ ${text}`].slice(-3);
  }

  /** 1イベントをアニメーションなしで適用する（dispatch() の瞬間版）。 */
  private applyInstant(e: HiveEvent) {
    const d = e.data;
    const agent = String(d.agent ?? "");
    const placeAtStand = (key: string) => {
      const a = this.actors.get(key);
      if (!a) return;
      const { x, y } = tileXY(a.stand);
      a.sprite.setPosition(x, y);
      a.tile = { ...a.stand };
      this.face(a, "down");
      this.follow(a);
    };
    switch (e.type) {
      case "task_received":
        return this.pushInstantMessage(`クエスト：${clip(String(d.task ?? ""), 40)}`);
      case "router": {
        const party = (d.party as { agent: string; role: string }[]) ?? [];
        if (party.length > 0) this.spawnParty(party, true);
        const names = party.map((p) => LABEL[p.agent] ?? p.agent).join("・");
        const rank = String(d.rank ?? "?");
        const sakusen = String(d.sakusen ?? d.quality ?? "");
        this.pushInstantMessage(
          `討伐ランク ${rank}${sakusen ? "／さくせん：" + sakusen : ""}${names ? "／なかま：" + names : ""}`,
        );
        return;
      }
      case "memory_recall": {
        const lessons = (d.lessons as string[]) ?? [];
        return this.pushInstantMessage(
          `むかしの きおくを おもいだした：${clip(lessons[0] ?? "", 30)}`,
        );
      }
      case "agent_start": {
        const a = this.actors.get(agent);
        if (!a) return;
        placeAtStand(agent);
        this.setStatus(agent, "しごとちゅう", STATUS_COLOR.work);
        // 復元直後にライブの完了が届いても余計に待たせない
        this.startedAt.set(agent, this.time.now - MIN_WORK_MS);
        this.startWork(a);
        return this.pushInstantMessage(`${LABEL[agent] ?? agent}は はたらいている…`);
      }
      case "agent_output": {
        const a = this.actors.get(agent);
        if (!a) return;
        this.stopWork(a);
        this.setStatus(agent, "かんりょう", STATUS_COLOR.done);
        return this.pushInstantMessage(`${LABEL[agent] ?? agent}の しごとが おわった`);
      }
      case "handoff": {
        const from = String(d.from_agent ?? "");
        const to = String(d.to_agent ?? "");
        const item = String(d.item ?? "せいかぶつ");
        const detail = String(d.detail ?? "");
        if (detail) this.pendingDetail.set(to, detail);
        this.pushInstantMessage(`${LABEL[from] ?? from}が ${item}を ${LABEL[to] ?? to}に わたした`);
        const fromA = this.actors.get(from);
        if (fromA) {
          this.stopWork(fromA);
          this.setStatus(from, "かんりょう", STATUS_COLOR.done);
        }
        const toA = this.actors.get(to);
        if (toA) {
          this.setStatus(to, "しごとちゅう", STATUS_COLOR.work);
          this.startedAt.set(to, this.time.now - MIN_WORK_MS);
          this.startWork(toA);
        }
        return;
      }
      case "security_start": {
        const a = this.actors.get("security_reviewer");
        if (!a) return;
        this.setStatus("security_reviewer", "かんさちゅう", STATUS_COLOR.audit);
        const { x, y } = tileXY(INSPECT);
        a.sprite.setPosition(x, y);
        a.tile = { ...INSPECT };
        this.faceToward(a, this.tableCenter().x);
        this.follow(a);
        return;
      }
      case "security_result": {
        const passed = String(d.passed) === "true";
        this.pushInstantMessage(passed ? "セキュリティかんさ クリア" : "ぜいじゃくせいあり！");
        if (this.actors.has("security_reviewer")) {
          this.setStatus(
            "security_reviewer",
            passed ? "かんりょう" : "ようちゅうい",
            passed ? STATUS_COLOR.done : STATUS_COLOR.danger,
          );
          placeAtStand("security_reviewer");
        }
        return;
      }
      case "verify_result": {
        const passed = String(d.passed) === "true";
        return this.pushInstantMessage(passed ? "けんしょう クリア！" : "けんしょう しっぱい…");
      }
      case "retry":
        return this.pushInstantMessage(
          `もういちど ちょうせん！（${String(d.attempt)}/${String(d.max)}）`,
        );
      case "escalation": {
        const target = this.actors.has(agent) ? agent : "implementer";
        const a = this.actors.get(target);
        if (a) {
          a.pro = true;
          this.setFrame(a, 0);
          this.setStatus(target, "パワーアップ", STATUS_COLOR.power);
        }
        return this.pushInstantMessage("しょうかんかいじょ！ 上位モデルに こうたいした");
      }
      case "memory_write":
        return this.pushInstantMessage(
          `ぼうけんのしょに きろくした：${clip(String(d.title ?? ""), 30)}`,
        );
      case "done":
        return this.pushInstantMessage("クエスト かんりょう！ せいかぶつを のうひんした");
      case "error":
        return this.pushInstantMessage(`エラーが おきた：${clip(String(d.message ?? ""), 40)}`);
      default:
        return;
    }
  }
}

export function createGame(parent: HTMLElement): HiveGame {
  const scene = new HiveRpgScene();
  const game = new Phaser.Game({
    type: Phaser.AUTO,
    parent,
    width: W,
    height: H,
    pixelArt: true,
    roundPixels: true,
    backgroundColor: "#100d16",
    scale: {
      mode: Phaser.Scale.FIT,
      autoCenter: Phaser.Scale.CENTER_HORIZONTALLY,
      // 親のスタイルをPhaserにいじらせない（親の高さはページ側のCSSが正）。
      // 高さが自動（キャンバス由来）だとFITとの押し合いで拡大ループになる
      expandParent: false,
    },
    scene: [scene],
  });
  return {
    enqueue: (e) => scene.enqueue(e),
    replay: (events) => scene.replay(events),
    destroy: () => game.destroy(true),
  };
}
