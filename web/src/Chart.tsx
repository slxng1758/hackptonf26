import type { Gen } from "./types";

const SERIES = [
  { key: "belief", label: "Belief (true cause survives)", color: "var(--color-belief)" },
  { key: "practice", label: "Practice (people still do it)", color: "var(--color-practice)" },
  { key: "myth", label: "Myth (explanation turned sacred)", color: "var(--color-myth)", dash: "5 4" },
] as const;

export function Chart({ gens, total, selected, onSelect }: { gens: Gen[]; total: number; selected: number; onSelect: (g: number) => void }) {
  const W = 720, H = 220, P = { l: 36, r: 16, t: 14, b: 28 };
  const n = Math.max(total, 1);
  const x = (g: number) => P.l + (g / n) * (W - P.l - P.r);
  const y = (v: number) => P.t + (1 - v) * (H - P.t - P.b);
  const scored = gens.filter((g) => g.score);

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Belief, practice and myth across generations">
        {[0, 0.5, 1].map((v) => (
          <g key={v}>
            <line x1={P.l} x2={W - P.r} y1={y(v)} y2={y(v)} stroke="rgb(43 33 24 / .1)" />
            <text x={P.l - 8} y={y(v) + 4} textAnchor="end" className="fill-ink3 font-mono" fontSize="10">{v}</text>
          </g>
        ))}
        {Array.from({ length: n + 1 }, (_, g) => (
          <text key={g} x={x(g)} y={H - 8} textAnchor="middle" className="fill-ink3 font-mono" fontSize="10">{g}</text>
        ))}
        <line x1={x(selected)} x2={x(selected)} y1={P.t} y2={H - P.b} stroke="var(--color-seal)" strokeWidth="1.5" strokeDasharray="3 3" />
        {SERIES.map((s) => {
          const pts = scored.map((g) => `${x(g.gen)},${y(g.score![s.key])}`).join(" ");
          return (
            <g key={s.key}>
              {s.key !== "myth" && scored.length > 1 && (
                <polygon points={`${x(scored[0].gen)},${y(0)} ${pts} ${x(scored[scored.length - 1].gen)},${y(0)}`} fill={s.color} opacity={0.08} />
              )}
              <polyline points={pts} fill="none" stroke={s.color} strokeWidth="2.5" strokeDasharray={"dash" in s ? s.dash : undefined} strokeLinejoin="round" />
              {scored.map((g) => (
                <circle key={g.gen} cx={x(g.gen)} cy={y(g.score![s.key])} r={g.gen === selected ? 5 : 3.5} fill={s.color} stroke="var(--color-card)" strokeWidth="1.5" />
              ))}
            </g>
          );
        })}
        {Array.from({ length: n + 1 }, (_, g) => (
          <rect key={g} x={x(g) - (W - P.l - P.r) / n / 2} y={0} width={(W - P.l - P.r) / n} height={H} fill="transparent" className="cursor-pointer" onClick={() => onSelect(g)} />
        ))}
      </svg>
      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-ink2">
        {SERIES.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-5" style={{ background: s.color }} /> {s.label}
          </span>
        ))}
      </div>
    </div>
  );
}
