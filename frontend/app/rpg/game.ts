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
  destroy: () => void;
};

const W = 760;
const H = 540;

const AGENTS = ["designer", "implementer", "tester", "security_reviewer"] as const;
type AgentName = (typeof AGENTS)[number];

const LABEL: Record<AgentName, string> = {
  designer: "設計担当",
  implementer: "実装担当",
  tester: "テスト担当",
  security_reviewer: "セキュリティ監査",
};

// 持ち場（画面下段）と中央ステージ
const HOME: Record<AgentName, { x: number; y: number }> = {
  designer: { x: 120, y: 330 },
  implementer: { x: 290, y: 330 },
  tester: { x: 460, y: 330 },
  security_reviewer: { x: 630, y: 330 },
};
const STAGE = { x: 380, y: 210 };

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

  private chars = new Map<AgentName, Phaser.GameObjects.Image>();
  private bubbles = new Map<AgentName, Phaser.GameObjects.Text>();
  private statusText = new Map<AgentName, Phaser.GameObjects.Text>();
  private messages: string[] = [];
  private messageText!: Phaser.GameObjects.Text;
  private centered: AgentName | null = null;
  /** 各Agentが働き始めた時刻（最低演出時間の計算用） */
  private startedAt = new Map<AgentName, number>();
  /** handoff で受け取った「次は何をするか」をagent_startの台詞に使う */
  private pendingDetail = new Map<AgentName, string>();

  constructor() {
    super("hive-rpg");
  }

  enqueue(e: HiveEvent) {
    this.queue.push(e);
  }

  create() {
    this.cameras.main.setBackgroundColor("#0a0f0a");
    for (const [key, def] of Object.entries(SPRITES)) {
      this.makeTexture(key, def.rows, def.palette);
    }
    this.drawGround();
    this.drawStatusWindows();
    this.drawMessageWindow();
    for (const name of AGENTS) {
      const img = this.add.image(HOME[name].x, HOME[name].y, name).setScale(4);
      img.setOrigin(0.5, 1);
      this.chars.set(name, img);
      const bubble = this.add
        .text(HOME[name].x, HOME[name].y - 64, "", { ...FONT, fontSize: "18px" })
        .setOrigin(0.5, 1);
      this.bubbles.set(name, bubble);
    }
    this.addMessage("はたらきバチたちは クエストを まっている…");
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

  private drawStatusWindows() {
    AGENTS.forEach((name, i) => {
      const x = 8 + i * 187;
      this.drawWindow(x, 8, 180, 58);
      this.add.text(x + 12, 16, LABEL[name], { ...FONT, fontSize: "13px" }).setResolution(2);
      const st = this.add
        .text(x + 12, 38, "じょうたい：まち", { ...FONT, fontSize: "12px", color: "#9ca3af" })
        .setResolution(2);
      this.statusText.set(name, st);
    });
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

  private setStatus(name: AgentName, state: string, color = "#ffffff") {
    this.statusText.get(name)?.setText(`じょうたい：${state}`).setColor(color);
  }

  private setBubble(name: AgentName, text: string) {
    this.bubbles.get(name)?.setText(text);
  }

  private moveChar(name: AgentName, x: number, y: number, onDone?: () => void) {
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
  private walkToCenter(name: AgentName, onDone: () => void) {
    if (this.centered === name) return onDone();
    const goCenter = () => {
      this.centered = name;
      this.moveChar(name, STAGE.x, STAGE.y, onDone);
    };
    // 別のキャラが中央に居たら先に持ち場へ帰す
    if (this.centered && this.centered !== name) {
      const prev = this.centered;
      this.centered = null;
      this.setBubble(prev, "");
      this.moveChar(prev, HOME[prev].x, HOME[prev].y, goCenter);
    } else {
      goCenter();
    }
  }

  private walkHome(name: AgentName, onDone?: () => void) {
    if (this.centered === name) this.centered = null;
    this.setBubble(name, "");
    this.moveChar(name, HOME[name].x, HOME[name].y, onDone);
  }

  private finish(delay = 250) {
    this.time.delayedCall(delay, () => {
      this.busy = false;
    });
  }

  // --- イベント → 演出 -------------------------------------------------------

  private handle(e: HiveEvent) {
    const d = e.data;
    const agent = String(d.agent ?? "") as AgentName;
    switch (e.type) {
      case "task_received":
        this.addMessage(`クエスト：${String(d.task ?? "").slice(0, 40)}`);
        return this.finish(900);
      case "router":
        this.addMessage(`はたらきバチを へんせいした（${String(d.task_type ?? "")}・${String(d.scale ?? "")}）`);
        return this.finish(700);
      case "memory_recall": {
        const lessons = (d.lessons as string[]) ?? [];
        this.addMessage(`むかしの きおくを おもいだした：${(lessons[0] ?? "").slice(0, 30)}`);
        return this.finish(800);
      }
      case "agent_start": {
        if (!AGENTS.includes(agent)) return this.finish(0);
        this.startedAt.set(agent, this.time.now);
        this.setStatus(agent, "しごとちゅう", "#fbbf24");
        const detail = String(d.detail ?? "") || this.pendingDetail.get(agent) || "";
        this.pendingDetail.delete(agent);
        this.addMessage(
          detail
            ? `${LABEL[agent]}は 「${detail.slice(0, 28)}」に とりくんでいる…`
            : `${LABEL[agent]}は かんがえている…`,
        );
        return this.walkToCenter(agent, () => {
          this.setBubble(agent, "…");
          this.finish(300);
        });
      }
      case "agent_output": {
        if (!AGENTS.includes(agent)) return this.finish(0);
        // 一瞬で終わったタスクも MIN_WORK_MS は「働いている姿」を見せる
        const started = this.startedAt.get(agent) ?? 0;
        const wait = Math.max(0, MIN_WORK_MS - (this.time.now - started));
        return this.time.delayedCall(wait, () => {
          this.setBubble(agent, "！");
          this.addMessage(`${LABEL[agent]}の しごとが おわった`);
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
        const from = String(d.from_agent ?? "") as AgentName;
        const to = String(d.to_agent ?? "") as AgentName;
        if (!AGENTS.includes(from) || !AGENTS.includes(to)) return this.finish(0);
        const item = String(d.item ?? "せいかぶつ");
        const detail = String(d.detail ?? "");
        if (detail) this.pendingDetail.set(to, detail);
        // 2体が中央で向かい合い、会話してタスクを渡す（A2Aの可視化）
        this.centered = null;
        this.setBubble(from, "");
        this.addMessage(`${LABEL[from]}「${item}が できたぞ！」`);
        this.setStatus(from, "かんりょう", "#34d399");
        this.moveChar(from, STAGE.x - 48, STAGE.y);
        return this.moveChar(to, STAGE.x + 48, STAGE.y, () => {
          this.setBubble(from, "💬");
          this.setBubble(to, "…");
          this.time.delayedCall(1000, () => {
            this.addMessage(`${LABEL[to]}「まかせろ！」── ${item}を うけとった`);
            this.setBubble(from, "");
            this.setBubble(to, "！");
            this.setStatus(to, "しごとちゅう", "#fbbf24");
            this.startedAt.set(to, this.time.now);
            this.moveChar(from, HOME[from].x, HOME[from].y);
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
        this.cameras.main.flash(500, 255, 255, 255);
        this.addMessage("しょうかんかいじょ！");
        const impl = this.chars.get("implementer");
        return this.time.delayedCall(600, () => {
          impl?.setTexture("implementer_pro");
          this.addMessage(`あたらしい${LABEL.implementer}（上位モデル）が なかまに くわわった！`);
          this.setStatus("implementer", "パワーアップ", "#c084fc");
          this.finish(900);
        });
      }
      case "memory_write":
        this.addMessage(`ぼうけんのしょに きろくした：${String(d.title ?? "").slice(0, 30)}`);
        return this.finish(800);
      case "done": {
        this.addMessage("クエスト かんりょう！ せいかぶつを のうひんした");
        for (const name of AGENTS) {
          const img = this.chars.get(name);
          if (img) this.tweens.add({ targets: img, y: img.y - 14, duration: 160, yoyo: true, repeat: 2 });
        }
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
    destroy: () => game.destroy(true),
  };
}
