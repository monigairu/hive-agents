"use client";

/**
 * 「さくせん」セレクタ（F-02：ユーザーが選ぶエフォート軸）。
 *
 * ラベルはドラクエ「さくせん」のパロディだが、商標回避のため全て一文字
 * ひねったオリジナル表現にしてある。このニュアンスを壊さないこと。
 * 並びは上ほど高コスト（視線が最初に当たる位置に最上位＝アンカリング）。
 */
export const SAKUSEN_OPTIONS = [
  {
    value: "all_hands",
    label: "みんなでがんばれ",
    hint: "💰💰💰 Pro＋セキュリティ監査を必ず実施（将来は木探索も）。いちばん丁寧で高品質",
  },
  {
    value: "go_hard",
    label: "がんがんつくろうぜ",
    hint: "💰💰 最初からPro・フルパワーで一発を狙う",
  },
  {
    value: "adaptive",
    label: "てきどにがんばれ",
    hint: "💰〜💰💰 Flashで始め、失敗したエージェントだけProに昇格",
  },
  {
    value: "cost_saver",
    label: "コストだいじに",
    hint: "💰 いちばん安い・速い。Flashのみ、試し打ち向き",
  },
  {
    value: "auto",
    label: "おまかせ",
    hint: "routerが自動で見極める。コストは内容しだい",
  },
];

export function SakusenSelect({
  value,
  onChange,
  disabled,
  className = "",
}: {
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  className?: string;
}) {
  const hint = SAKUSEN_OPTIONS.find((o) => o.value === value)?.hint ?? "";
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      title={`さくせん：${hint}`}
      className={`rounded-lg border border-neutral-300 px-2 py-2 text-sm outline-none focus:border-amber-400 dark:border-neutral-700 dark:bg-neutral-900 ${className}`}
    >
      {SAKUSEN_OPTIONS.map((o) => (
        <option key={o.value} value={o.value}>
          さくせん：{o.label}
        </option>
      ))}
    </select>
  );
}
