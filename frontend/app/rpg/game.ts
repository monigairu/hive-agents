/**
 * ドラクエ風RPG描画（要件 F-14・M7）。
 *
 * M3のSSEイベントストリームを「キャラが中央に出て働き、持ち場に戻る」として
 * 描くだけの表示層。データ（イベント）と描画の分離が原則で、ここにビジネス
 * ロジックは置かない。サウンドは実装しない（要件で明示的に対象外）。
 *
 * 表示名の原則（F-14）：キャラの見た目は職業風だが、画面に出す名前は
 * 一般の人でも工程がわかる役割名（設計担当・実装担当・テスト担当・セキュリティ監査）。
 */

import * as Phaser from "phaser";

export type HiveEvent = { type: string; data: Record<string, unknown> };

export type HiveGame = {
  enqueue: (e: HiveEvent) => void;
  /** 過去イベントを瞬間適用して途中状態を復元する（ページ遷移からの復帰用） */
  replay: (events: HiveEvent[]) => void;
  destroy: () => void;
};

const W = 760;
const H = 540;

// 既知のAgentの表示名カタログ。実際の編成（パーティ）は router イベントが運んでくる
// （F-02 動的エージェント組成：タスクによって働くAgentが変わる）
const LABEL: Record<string, string> = {
  designer: "設計担当",
  implementer: "実装担当",
  frontend: "画面担当",
  tester: "テスト担当",
  security_reviewer: "セキュリティ監査",
};

const STAGE = { x: 380, y: 210 };
const HOME_Y = 330;

// --- ドット絵定義（12x14・'.'は透過） -------------------------------------
// A=帽子/頭, S=肌, E=目, B=胴, L=脚, F=足, X=アクセント
const SPRITES: Record<string, { rows: string[]; palette: Record<string, string> }> = {
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

const FONT = {
  fontFamily: "'DotGothic16', 'MS Gothic', monospace",
  color: "#ffffff",
};

// 実装が一瞬で終わるタスクでも「働いている感」が出る最低演出時間
const MIN_WORK_MS = 2600;

class HiveRpgScene extends Phaser.Scene {
  private queue: HiveEvent[] = [];
  private busy = false;

  private chars = new Map<string, Phaser.GameObjects.Image>();
  private bubbles = new Map<string, Phaser.GameObjects.Text>();
  private statusText = new Map<string, Phaser.GameObjects.Text>();
  /** 持ち場（編成人数に応じて spawnParty が計算する） */
  private homes = new Map<string, { x: number; y: number }>();
  /** 編成ごとに作り直すUI（ステータス窓など） */
  private partyUi: Phaser.GameObjects.GameObject[] = [];
  private messages: string[] = [];
  private messageText!: Phaser.GameObjects.Text;
  private centered: string | null = null;
  /** 各Agentが働き始めた時刻（最低演出時間の計算用） */
  private startedAt = new Map<string, number>();
  /** handoff で受け取った「次は何をするか」をagent_startの台詞に使う */
  private pendingDetail = new Map<string, string>();
  private ready = false;
  private pendingReplay: HiveEvent[] | null = null;

  constructor() {
    super("hive-rpg");
  }

  enqueue(e: HiveEvent) {
    this.queue.push(e);
  }

  /** 過去イベントを瞬間適用して途中状態を復元する。create前に呼ばれたら保留する。 */
  replay(events: HiveEvent[]) {
    if (!this.ready) {
      this.pendingReplay = events;
      return;
    }
    this.tweens.killAll();
    this.queue = [];
    this.busy = false;
    this.messages = [];
    this.messageText.setText("");
    this.clearParty();
    if (events.length === 0) {
      this.addMessage("クエストを 発注すると オーケストレーターが はたらきバチを へんせいする…");
      return;
    }
    for (const e of events) this.applyInstant(e);
    // spawnParty の登場アニメ等が適用後に位置を動かさないよう止め、最終位置を確定する
    this.tweens.killAll();
    this.chars.forEach((_, name) => {
      if (name === this.centered) {
        this.placeAt(name, STAGE.x, STAGE.y);
        this.setBubble(name, "…");
      } else {
        const home = this.homes.get(name);
        if (home) this.placeAt(name, home.x, home.y);
      }
    });
  }

  create() {
    this.cameras.main.setBackgroundColor("#0a0f0a");
    for (const [key, def] of Object.entries(SPRITES)) {
      this.makeTexture(key, def.rows, def.palette);
    }
    this.drawGround();
    this.drawMessageWindow();
    this.addMessage("クエストを 発注すると オーケストレーターが はたらきバチを へんせいする…");
    this.ready = true;
    if (this.pendingReplay) {
      const events = this.pendingReplay;
      this.pendingReplay = null;
      this.replay(events);
    }
  }

  /** 編成を片付ける（再編成・リプレイの前処理）。 */
  private clearParty() {
    for (const obj of this.partyUi) obj.destroy();
    this.partyUi = [];
    this.chars.forEach((c) => c.destroy());
    this.bubbles.forEach((b) => b.destroy());
    this.chars.clear();
    this.bubbles.clear();
    this.statusText.clear();
    this.homes.clear();
    this.centered = null;
  }

  /** router の編成結果に従ってパーティを出現させる（F-02 動的エージェント組成）。 */
  private spawnParty(party: { agent: string; role: string }[]) {
    this.clearParty();

    const n = party.length;
    const winW = Math.min(180, Math.floor((W - 16) / n) - 6);
    party.forEach(({ agent, role }, i) => {
      // ステータス窓（なまえ・じょうたい）
      const x = 8 + i * (winW + 6);
      this.partyUi.push(this.drawWindow(x, 8, winW, 58));
      const name = this.add
        .text(x + 10, 16, LABEL[agent] ?? role ?? agent, { ...FONT, fontSize: "12px" })
        .setResolution(2);
      const st = this.add
        .text(x + 10, 38, "じょうたい：まち", { ...FONT, fontSize: "11px", color: "#9ca3af" })
        .setResolution(2);
      this.partyUi.push(name, st);
      this.statusText.set(agent, st);
      // キャラ（編成人数で持ち場を等間隔に割り付け、上から降ってきて参加）
      const hx = Math.round((W / (n + 1)) * (i + 1));
      this.homes.set(agent, { x: hx, y: HOME_Y });
      const texKey = this.textures.exists(agent) ? agent : "implementer";
      const img = this.add.image(hx, HOME_Y - 40, texKey).setScale(4).setOrigin(0.5, 1);
      this.chars.set(agent, img);
      const bubble = this.add
        .text(hx, HOME_Y - 64, "", { ...FONT, fontSize: "18px" })
        .setOrigin(0.5, 1);
      this.bubbles.set(agent, bubble);
      this.tweens.add({
        targets: img,
        y: HOME_Y,
        duration: 320,
        ease: "Bounce.easeOut",
        delay: i * 110,
      });
    });
  }

  update() {
    if (!this.busy && this.queue.length > 0) {
      this.busy = true;
      this.handle(this.queue.shift() as HiveEvent);
    }
  }

  // --- 描画部品 -------------------------------------------------------------

  private makeTexture(key: string, rows: string[], palette: Record<string, string>) {
    const w = rows[0].length;
    const h = rows.length;
    const canvas = this.textures.createCanvas(key, w, h);
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

  /** ドラクエ風ウィンドウ（黒地・白の二重枠）。 */
  private drawWindow(x: number, y: number, w: number, h: number) {
    const g = this.add.graphics();
    g.fillStyle(0x000000, 0.92).fillRoundedRect(x, y, w, h, 6);
    g.lineStyle(2, 0xffffff, 1).strokeRoundedRect(x + 2, y + 2, w - 4, h - 4, 5);
    g.lineStyle(1, 0xffffff, 0.6).strokeRoundedRect(x + 5, y + 5, w - 10, h - 10, 4);
    return g;
  }

  private drawGround() {
    const g = this.add.graphics();
    g.fillStyle(0x14532d, 0.35);
    for (let y = 120; y < 360; y += 24) {
      for (let x = 24 + (y % 48 === 0 ? 12 : 0); x < W - 16; x += 24) {
        g.fillRect(x, y, 3, 3);
      }
    }
  }

  private drawMessageWindow() {
    this.drawWindow(8, H - 110, W - 16, 102);
    this.messageText = this.add
      .text(24, H - 96, "", { ...FONT, fontSize: "15px", lineSpacing: 8, wordWrap: { width: W - 48 } })
      .setResolution(2);
  }

  private addMessage(text: string) {
    this.messages.push(`▼ ${text}`);
    this.messages = this.messages.slice(-3);
    this.messageText.setText(this.messages.join("\n"));
  }

  private setStatus(name: string, state: string, color = "#ffffff") {
    this.statusText.get(name)?.setText(`じょうたい：${state}`).setColor(color);
  }

  private setBubble(name: string, text: string) {
    this.bubbles.get(name)?.setText(text);
  }

  private moveChar(name: string, x: number, y: number, onDone?: () => void) {
    const img = this.chars.get(name);
    const bubble = this.bubbles.get(name);
    if (!img) return onDone?.();
    this.tweens.add({
      targets: img,
      x,
      y,
      duration: 550,
      ease: "Sine.easeInOut",
      onUpdate: () => bubble?.setPosition(img.x, img.y - 64),
      onComplete: () => onDone?.(),
    });
    // 歩いている感を出す小さな上下バウンド
    this.tweens.add({ targets: img, scaleY: 3.85, duration: 110, yoyo: true, repeat: 4 });
  }

  /** 中央ステージへ。既に中央にいる場合は何もしない（監査の二重イベント対策）。 */
  private walkToCenter(name: string, onDone: () => void) {
    if (this.centered === name) return onDone();
    const goCenter = () => {
      this.centered = name;
      this.moveChar(name, STAGE.x, STAGE.y, onDone);
    };
    // 別のキャラが中央に居たら先に持ち場へ帰す
    if (this.centered && this.centered !== name) {
      const prev = this.centered;
      const home = this.homes.get(prev);
      this.centered = null;
      this.setBubble(prev, "");
      if (home) this.moveChar(prev, home.x, home.y, goCenter);
      else goCenter();
    } else {
      goCenter();
    }
  }

  private walkHome(name: string, onDone?: () => void) {
    if (this.centered === name) this.centered = null;
    this.setBubble(name, "");
    const home = this.homes.get(name);
    if (!home) return onDone?.();
    this.moveChar(name, home.x, home.y, onDone);
  }

  private finish(delay = 250) {
    this.time.delayedCall(delay, () => {
      this.busy = false;
    });
  }

  // --- リプレイ（瞬間復元）----------------------------------------------------

  private placeAt(agent: string, x: number, y: number) {
    this.chars.get(agent)?.setPosition(x, y);
    this.bubbles.get(agent)?.setPosition(x, y - 64);
  }

  private placeHome(agent: string) {
    const home = this.homes.get(agent);
    if (home) this.placeAt(agent, home.x, home.y);
    this.setBubble(agent, "");
    if (this.centered === agent) this.centered = null;
  }

  private placeCenter(agent: string) {
    if (this.centered && this.centered !== agent) this.placeHome(this.centered);
    this.centered = agent;
    this.placeAt(agent, STAGE.x, STAGE.y);
    this.setBubble(agent, "…");
  }

  /** 1イベントをアニメーションなしで適用する（handle() の瞬間版）。 */
  private applyInstant(e: HiveEvent) {
    const d = e.data;
    const agent = String(d.agent ?? "");
    switch (e.type) {
      case "task_received":
        return this.addMessage(`クエスト：${String(d.task ?? "").slice(0, 40)}`);
      case "router": {
        const party = (d.party as { agent: string; role: string }[]) ?? [];
        if (party.length > 0) this.spawnParty(party);
        const names = party.map((p) => LABEL[p.agent] ?? p.agent).join("・");
        if (names) this.addMessage(`なかま：${names}`);
        return;
      }
      case "memory_recall": {
        const lessons = (d.lessons as string[]) ?? [];
        return this.addMessage(`むかしの きおくを おもいだした：${(lessons[0] ?? "").slice(0, 30)}`);
      }
      case "agent_start":
        if (!this.chars.has(agent)) return;
        this.setStatus(agent, "しごとちゅう", "#fbbf24");
        // 復元直後にライブの完了が届いても余計に待たせない
        this.startedAt.set(agent, this.time.now - MIN_WORK_MS);
        this.addMessage(`${LABEL[agent] ?? agent}は はたらいている…`);
        return this.placeCenter(agent);
      case "agent_output":
        if (!this.chars.has(agent)) return;
        this.setStatus(agent, "かんりょう", "#34d399");
        this.addMessage(`${LABEL[agent] ?? agent}の しごとが おわった`);
        return this.placeHome(agent);
      case "handoff": {
        const from = String(d.from_agent ?? "");
        const to = String(d.to_agent ?? "");
        const item = String(d.item ?? "せいかぶつ");
        const detail = String(d.detail ?? "");
        if (detail) this.pendingDetail.set(to, detail);
        this.addMessage(`${LABEL[from] ?? from}が ${item}を ${LABEL[to] ?? to}に わたした`);
        if (this.chars.has(from)) {
          this.setStatus(from, "かんりょう", "#34d399");
          this.placeHome(from);
        }
        if (this.chars.has(to)) {
          this.setStatus(to, "しごとちゅう", "#fbbf24");
          this.startedAt.set(to, this.time.now - MIN_WORK_MS);
          this.placeCenter(to);
        }
        return;
      }
      case "security_start":
        if (!this.chars.has("security_reviewer")) return;
        this.setStatus("security_reviewer", "かんさちゅう", "#fb7185");
        return this.placeCenter("security_reviewer");
      case "security_result": {
        const passed = String(d.passed) === "true";
        this.addMessage(passed ? "セキュリティかんさ クリア" : "ぜいじゃくせいあり！");
        if (this.chars.has("security_reviewer")) {
          this.setStatus(
            "security_reviewer",
            passed ? "かんりょう" : "ようちゅうい",
            passed ? "#34d399" : "#f87171",
          );
          this.placeHome("security_reviewer");
        }
        return;
      }
      case "verify_result": {
        const passed = String(d.passed) === "true";
        return this.addMessage(passed ? "けんしょう クリア！" : "けんしょう しっぱい…");
      }
      case "retry":
        return this.addMessage(`もういちど ちょうせん！（${String(d.attempt)}/${String(d.max)}）`);
      case "escalation": {
        const target = this.chars.has(agent) ? agent : "implementer";
        if (this.textures.exists(`${target}_pro`)) {
          this.chars.get(target)?.setTexture(`${target}_pro`);
        }
        this.setStatus(target, "パワーアップ", "#c084fc");
        return this.addMessage("しょうかんかいじょ！ 上位モデルに こうたいした");
      }
      case "memory_write":
        return this.addMessage(`ぼうけんのしょに きろくした：${String(d.title ?? "").slice(0, 30)}`);
      case "done":
        return this.addMessage("クエスト かんりょう！ せいかぶつを のうひんした");
      case "error":
        return this.addMessage(`エラーが おきた：${String(d.message ?? "").slice(0, 40)}`);
      default:
        return;
    }
  }

  // --- イベント → 演出 -------------------------------------------------------

  private handle(e: HiveEvent) {
    const d = e.data;
    const agent = String(d.agent ?? "");
    switch (e.type) {
      case "task_received":
        this.addMessage(`クエスト：${String(d.task ?? "").slice(0, 40)}`);
        return this.finish(900);
      case "router": {
        const party = (d.party as { agent: string; role: string }[]) ?? [];
        if (party.length > 0) this.spawnParty(party);
        const names = party.map((p) => LABEL[p.agent] ?? p.agent).join("・");
        const quality = String(d.quality ?? "");
        this.addMessage(
          `オーケストレーターが はたらきバチを へんせいした！（${String(d.task_type ?? "")}${quality ? "・" + quality : ""}）`,
        );
        if (names) this.addMessage(`なかま：${names}`);
        return this.finish(1100);
      }
      case "memory_recall": {
        const lessons = (d.lessons as string[]) ?? [];
        this.addMessage(`むかしの きおくを おもいだした：${(lessons[0] ?? "").slice(0, 30)}`);
        return this.finish(800);
      }
      case "agent_start": {
        if (!this.chars.has(agent)) return this.finish(0);
        this.startedAt.set(agent, this.time.now);
        this.setStatus(agent, "しごとちゅう", "#fbbf24");
        const detail = String(d.detail ?? "") || this.pendingDetail.get(agent) || "";
        this.pendingDetail.delete(agent);
        this.addMessage(
          detail
            ? `${LABEL[agent] ?? agent}は 「${detail.slice(0, 28)}」に とりくんでいる…`
            : `${LABEL[agent] ?? agent}は かんがえている…`,
        );
        return this.walkToCenter(agent, () => {
          this.setBubble(agent, "…");
          this.finish(300);
        });
      }
      case "agent_output": {
        if (!this.chars.has(agent)) return this.finish(0);
        // 一瞬で終わったタスクも MIN_WORK_MS は「働いている姿」を見せる
        const started = this.startedAt.get(agent) ?? 0;
        const wait = Math.max(0, MIN_WORK_MS - (this.time.now - started));
        return this.time.delayedCall(wait, () => {
          this.setBubble(agent, "！");
          this.addMessage(`${LABEL[agent] ?? agent}の しごとが おわった`);
          this.setStatus(agent, "かんりょう", "#34d399");
          // 直後に受け渡し(handoff)が控えている場合は、その場で待つ（行って戻りを防ぐ）
          const next = this.queue[0];
          if (next?.type === "handoff" && String(next.data.from_agent) === agent) {
            return this.finish(350);
          }
          this.time.delayedCall(450, () => this.walkHome(agent, () => this.finish(150)));
        });
      }
      case "handoff": {
        const from = String(d.from_agent ?? "");
        const to = String(d.to_agent ?? "");
        if (!this.chars.has(from) || !this.chars.has(to)) return this.finish(0);
        const item = String(d.item ?? "せいかぶつ");
        const detail = String(d.detail ?? "");
        if (detail) this.pendingDetail.set(to, detail);
        // 2体が中央で向かい合い、会話してタスクを渡す（A2Aの可視化）
        this.centered = null;
        this.setBubble(from, "");
        this.addMessage(`${LABEL[from] ?? from}「${item}が できたぞ！」`);
        this.setStatus(from, "かんりょう", "#34d399");
        this.moveChar(from, STAGE.x - 48, STAGE.y);
        return this.moveChar(to, STAGE.x + 48, STAGE.y, () => {
          this.setBubble(from, "💬");
          this.setBubble(to, "…");
          this.time.delayedCall(1000, () => {
            this.addMessage(`${LABEL[to] ?? to}「まかせろ！」── ${item}を うけとった`);
            this.setBubble(from, "");
            this.setBubble(to, "！");
            this.setStatus(to, "しごとちゅう", "#fbbf24");
            this.startedAt.set(to, this.time.now);
            const fromHome = this.homes.get(from);
            if (fromHome) this.moveChar(from, fromHome.x, fromHome.y);
            this.time.delayedCall(350, () => {
              this.centered = to;
              this.moveChar(to, STAGE.x, STAGE.y, () => {
                this.setBubble(to, "…");
                this.finish(250);
              });
            });
          });
        });
      }
      case "security_start":
        if (!this.chars.has("security_reviewer")) return this.finish(0);
        this.setStatus("security_reviewer", "かんさちゅう", "#fb7185");
        this.addMessage("セキュリティかんさ かいし！");
        return this.walkToCenter("security_reviewer", () => {
          this.setBubble("security_reviewer", "…");
          this.finish(300);
        });
      case "security_result": {
        const passed = String(d.passed) === "true";
        const findings = (d.findings as { severity: string }[]) ?? [];
        const criticals = findings.filter((f) => f.severity === "critical").length;
        if (passed) {
          this.addMessage(`かんさ クリア！ ${String(d.summary ?? "もんだいなし")}`);
          this.setStatus("security_reviewer", "かんりょう", "#34d399");
        } else {
          this.cameras.main.flash(400, 220, 38, 38);
          this.cameras.main.shake(300, 0.004);
          this.addMessage(`このコードに ぜいじゃくせいあり！（critical ${criticals}件）`);
          this.setStatus("security_reviewer", "ようちゅうい", "#f87171");
        }
        return this.time.delayedCall(600, () =>
          this.walkHome("security_reviewer", () => this.finish(200)),
        );
      }
      case "verify_start":
        this.addMessage(
          String(d.mode) === "page"
            ? "ページが ちゃんと できているか しらべている…"
            : "サンドボックスで コードを ためしている…",
        );
        return this.finish(700);
      case "verify_result": {
        const passed = String(d.passed) === "true";
        const isPage = String(d.mode) === "page";
        if (passed) {
          this.cameras.main.flash(300, 52, 211, 153);
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
        return this.finish(900);
      }
      case "retry":
        this.addMessage(`もういちど ちょうせん！（${String(d.attempt)}/${String(d.max)}）`);
        return this.finish(800);
      case "escalation": {
        const target = this.chars.has(agent) ? agent : "implementer";
        this.cameras.main.flash(500, 255, 255, 255);
        this.addMessage("しょうかんかいじょ！");
        const char = this.chars.get(target);
        return this.time.delayedCall(600, () => {
          if (this.textures.exists(`${target}_pro`)) char?.setTexture(`${target}_pro`);
          this.addMessage(
            `あたらしい${LABEL[target] ?? target}（上位モデル）が なかまに くわわった！`,
          );
          this.setStatus(target, "パワーアップ", "#c084fc");
          this.finish(900);
        });
      }
      case "memory_write":
        this.addMessage(`ぼうけんのしょに きろくした：${String(d.title ?? "").slice(0, 30)}`);
        return this.finish(800);
      case "done": {
        this.addMessage("クエスト かんりょう！ せいかぶつを のうひんした");
        this.chars.forEach((img) => {
          this.tweens.add({ targets: img, y: img.y - 14, duration: 160, yoyo: true, repeat: 2 });
        });
        return this.finish(500);
      }
      case "error":
        this.addMessage(`エラーが おきた：${String(d.message ?? "").slice(0, 40)}`);
        return this.finish(500);
      default:
        return this.finish(0);
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
    backgroundColor: "#0a0f0a",
    scale: { mode: Phaser.Scale.FIT, autoCenter: Phaser.Scale.CENTER_HORIZONTALLY },
    scene: [scene],
  });
  return {
    enqueue: (e) => scene.enqueue(e),
    replay: (events) => scene.replay(events),
    destroy: () => game.destroy(true),
  };
}
