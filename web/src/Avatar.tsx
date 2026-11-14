// A small person drawn in code. Same seed → same person; the face follows how they feel right now.
export type Feeling = "delighted" | "interested" | "neutral" | "confused" | "annoyed" | "skeptical";

const SKIN = ["#f6d1ae", "#e8b98a", "#c98e5f", "#9b6740", "#6e4527"];
const HAIR = ["#1f1712", "#3b2618", "#6b4226", "#b5793c", "#d9b45a", "#2a2a2a"];
export const SHIRT: Record<string, string> = {
  "price-sensitive": "#ffb547", "quality-first": "#3ff0d4", "brand-loyal": "#d16bff", "function-first": "#6aa8ff",
  "first-time user": "#7be38a", skeptic: "#ff5c77", enthusiast: "#ff8fd1",
};

function rnd(seed: number) { let s = seed || 1; return () => (s = (s * 16807) % 2147483647) / 2147483647; }

const MOUTH: Record<Feeling, string> = {
  delighted: "M38 63 Q50 76 62 63 Q50 70 38 63 Z",
  interested: "M40 64 Q50 70 60 64",
  neutral: "M41 65 L59 65",
  confused: "M42 66 Q46 62 50 66 Q54 70 58 66",
  annoyed: "M40 68 Q50 60 60 68",
  skeptical: "M41 66 Q52 66 60 61",
};

export function Avatar({ seed, feeling = "neutral", archetype = "", age = 30, size = 64, busy = false }:
  { seed: number; feeling?: Feeling; archetype?: string; age?: number; size?: number; busy?: boolean }) {
  const r = rnd(seed);
  const skin = SKIN[Math.floor(r() * SKIN.length)];
  const hair = age >= 58 ? "#cfcfd4" : HAIR[Math.floor(r() * HAIR.length)];
  const style = Math.floor(r() * 4);
  const shirt = SHIRT[archetype] ?? "#8a93b8";
  const glasses = archetype === "skeptic" || archetype === "quality-first" || r() > 0.8;
  const browL = feeling === "annoyed" ? "M33 39 L44 42" : feeling === "confused" ? "M33 37 Q38 34 44 37" : "M33 39 L44 39";
  const browR = feeling === "annoyed" ? "M56 42 L67 39" : feeling === "skeptical" || feeling === "confused" ? "M56 36 Q61 33 67 36" : "M56 39 L67 39";

  return (
    <svg width={size} height={size} viewBox="0 0 100 100" className={busy ? "avatar-bob" : ""} aria-hidden>
      <defs><clipPath id={`c${seed}`}><circle cx="50" cy="50" r="50" /></clipPath></defs>
      <g clipPath={`url(#c${seed})`}>
        <rect width="100" height="100" fill="#141623" />
        <path d="M14 100 Q16 78 50 76 Q84 78 86 100 Z" fill={shirt} />
        <rect x="43" y="66" width="14" height="12" rx="4" fill={skin} />
        {style === 2 && <path d="M24 52 Q22 86 34 92 L66 92 Q78 86 76 52 Z" fill={hair} />}
        <ellipse cx="50" cy="50" rx="24" ry="27" fill={skin} />
        {style === 0 && <path d="M26 44 Q28 18 52 20 Q74 21 75 44 Q66 32 50 33 Q34 32 26 44 Z" fill={hair} />}
        {style === 1 && <path d="M25 46 Q24 16 50 18 Q78 18 76 46 L72 40 Q60 28 46 30 Q32 32 28 42 Z" fill={hair} />}
        {style === 2 && <path d="M25 48 Q24 18 50 19 Q77 19 75 48 Q70 30 50 30 Q30 30 25 48 Z" fill={hair} />}
        {style === 3 && <path d="M28 40 Q32 22 50 22 Q68 22 72 40 Q60 34 50 34 Q40 34 28 40 Z" fill={hair} />}
        <path d={browL} stroke="#2a1d14" strokeWidth="2.6" strokeLinecap="round" fill="none" />
        <path d={browR} stroke="#2a1d14" strokeWidth="2.6" strokeLinecap="round" fill="none" />
        <g className="avatar-blink">
          <ellipse cx="39" cy="48" rx={feeling === "delighted" ? 3.4 : 3} ry={feeling === "delighted" ? 2 : 3.4} fill="#1d1612" />
          <ellipse cx="61" cy="48" rx={feeling === "delighted" ? 3.4 : 3} ry={feeling === "delighted" ? 2 : 3.4} fill="#1d1612" />
        </g>
        {glasses && <g stroke="#1d1612" strokeWidth="2" fill="rgba(255,255,255,0.12)"><circle cx="39" cy="48" r="8" /><circle cx="61" cy="48" r="8" /><path d="M47 48 L53 48" /></g>}
        {feeling === "delighted" && <><circle cx="31" cy="58" r="4" fill="#ff8fa3" opacity=".45" /><circle cx="69" cy="58" r="4" fill="#ff8fa3" opacity=".45" /></>}
        <path d={MOUTH[feeling]} stroke="#5a2a22" strokeWidth="2.6" strokeLinecap="round" fill={feeling === "delighted" ? "#7a2e2a" : "none"} />
      </g>
    </svg>
  );
}
