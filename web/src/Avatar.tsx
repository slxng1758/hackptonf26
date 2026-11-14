// A small person, drawn in code like a soft clay render: shaded spheres lit from the top left, glossy eyes, no outlines.
// Same seed → same person; the face follows how they feel right now.
import { useId } from "react";

export type Feeling = "delighted" | "interested" | "neutral" | "confused" | "annoyed" | "skeptical";

const SKIN = ["#f7d7bd", "#ecbf98", "#d39a6a", "#a8704a", "#734a30"];
const HAIR = ["#2a201b", "#4a3226", "#7a4e2f", "#c08a4a", "#e2c06d", "#3a3a40"];
export const SHIRT: Record<string, string> = {
  "price-sensitive": "#ffb547", "quality-first": "#3ff0d4", "brand-loyal": "#d16bff", "function-first": "#6aa8ff",
  "first-time user": "#7be38a", skeptic: "#ff5c77", enthusiast: "#ff8fd1", "AI agent": "#9aa4b8",
};
export const MODEL_GLOW: Record<string, string> = { Gemini: "#4f8bff", Claude: "#ff8a4c", GPT: "#19c37d", "Amazon Nova": "#ff9900", Llama: "#7a5cff", Grok: "#e5e5e5" };

// AI shopping agents get a small robot: brushed-metal head, visor, eyes lit in their model's color.
function Robot({ size, feeling, model, busy, uid }: { size: number; feeling: Feeling; model: string; busy: boolean; uid: string }) {
  const glow = MODEL_GLOW[model] ?? "#3ff0d4";
  const id = (k: string) => `${k}${uid}`;
  const happy = feeling === "delighted" || feeling === "interested";
  const sad = feeling === "annoyed" || feeling === "skeptical" || feeling === "confused";
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" className={busy ? "avatar-bob" : ""} aria-hidden>
      <defs>
        <clipPath id={id("rc")}><circle cx="50" cy="50" r="50" /></clipPath>
        <linearGradient id={id("metal")} x1="0" y1="0" x2=".4" y2="1"><stop offset="0" stopColor="#f4f6fa" /><stop offset=".55" stopColor="#c3cad6" /><stop offset="1" stopColor="#8a93a3" /></linearGradient>
        <linearGradient id={id("visor")} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#1b2030" /><stop offset="1" stopColor="#0b0e16" /></linearGradient>
        <radialGradient id={id("eye")}><stop offset="0" stopColor="#fff" /><stop offset=".35" stopColor={glow} /><stop offset="1" stopColor={glow} stopOpacity="0" /></radialGradient>
      </defs>
      <g clipPath={`url(#${id("rc")})`}>
        <rect width="100" height="100" style={{ fill: "var(--avatar-bg)" }} />
        <path d="M18 106 Q19 80 50 77 Q81 80 82 106 Z" fill={`url(#${id("metal")})`} />
        <circle cx="50" cy="90" r="4" fill={glow} opacity=".9" />
        <rect x="44" y="64" width="12" height="12" rx="3" fill="#9aa3b2" />
        <line x1="50" y1="22" x2="50" y2="13" stroke="#9aa3b2" strokeWidth="2.5" strokeLinecap="round" />
        <circle cx="50" cy="11" r="4" fill={glow}>{busy && <animate attributeName="opacity" values="1;.3;1" dur="1.2s" repeatCount="indefinite" />}</circle>
        <rect x="24" y="22" width="52" height="46" rx="16" fill={`url(#${id("metal")})`} />
        <ellipse cx="38" cy="28" rx="10" ry="3" fill="#fff" opacity=".55" />
        <rect x="30" y="34" width="40" height="22" rx="10" fill={`url(#${id("visor")})`} />
        <circle cx="41" cy="45" r="7" fill={`url(#${id("eye")})`} />
        <circle cx="59" cy="45" r="7" fill={`url(#${id("eye")})`} />
        {happy && <path d="M44 52 Q50 55 56 52" stroke={glow} strokeWidth="1.8" fill="none" strokeLinecap="round" />}
        {sad && <path d="M44 54 Q50 51 56 54" stroke={glow} strokeWidth="1.8" fill="none" strokeLinecap="round" />}
      </g>
    </svg>
  );
}

function rnd(seed: number) {
  // mix the seed first: small seeds made the first draw tiny, so every skin tone came out the same
  let s = (Math.imul(seed || 1, 2654435761) >>> 0) % 2147483646 + 1;
  const next = () => (s = (s * 16807) % 2147483647) / 2147483647;
  next(); next();
  return next;
}

function shade(hex: string, amt: number) {
  const n = parseInt(hex.slice(1), 16);
  const f = (c: number) => Math.max(0, Math.min(255, Math.round(amt > 0 ? c + (255 - c) * amt : c * (1 + amt))));
  return `#${[(n >> 16) & 255, (n >> 8) & 255, n & 255].map((c) => f(c).toString(16).padStart(2, "0")).join("")}`;
}

const MOUTH: Record<Feeling, string> = {
  delighted: "M42.5 57.5 Q50 66 57.5 57.5 Q50 61.5 42.5 57.5 Z",
  interested: "M44.5 58.5 Q50 62.5 55.5 58.5",
  neutral: "M45.5 59.5 L54.5 59.5",
  confused: "M44.5 60.5 Q47.2 57.8 50 60.5 Q52.8 63.2 55.5 60.5",
  annoyed: "M44.5 61.5 Q50 56.8 55.5 61.5",
  skeptical: "M44.5 60.5 Q51 60.5 55.8 57",
};

export function Avatar({ seed, feeling = "neutral", archetype = "", age = 30, size = 64, busy = false, model = "" }:
  { seed: number; feeling?: Feeling; archetype?: string; age?: number; size?: number; busy?: boolean; model?: string }) {
  const uid = useId().replace(/[^a-zA-Z0-9]/g, "");
  if (archetype === "AI agent") return <Robot size={size} feeling={feeling} model={model} busy={busy} uid={uid} />;
  const id = (k: string) => `${k}${uid}`;
  const r = rnd(seed);
  const skin = SKIN[Math.floor(r() * SKIN.length)];
  const hair = age >= 58 ? "#d4d4da" : HAIR[Math.floor(r() * HAIR.length)];
  const style = Math.floor(r() * 4);
  const shirt = SHIRT[archetype] ?? "#8a93b8";
  const glasses = archetype === "skeptic" || archetype === "quality-first" || r() > 0.8;
  const ink = shade(skin, -0.72);
  const happy = feeling === "delighted";
  const eyeRy = feeling === "skeptical" ? 2.1 : feeling === "annoyed" ? 2.4 : 3.1;

  const hairTop = [
    "M29 44 Q28.5 21.5 50 21.5 Q71.5 21.5 71 44 Q64 32.5 50 32.5 Q36 32.5 29 44 Z",
    "M28.5 45.5 Q26.5 19.5 50 19.5 Q74 19.5 71.8 45.5 L68 37.5 Q58 27.5 44 30.5 Q33.5 33.5 30.5 42 Z",
    "M28.5 46 Q28.5 20.5 50 20.5 Q71.5 20.5 71.5 46 Q66 29.5 50 29.5 Q34 29.5 28.5 46 Z",
    "M31 38.5 Q35 22.5 50 22.5 Q65 22.5 69 38.5 Q60 31.5 50 31.5 Q40 31.5 31 38.5 Z",
  ][style];

  return (
    <svg width={size} height={size} viewBox="0 0 100 100" className={busy ? "avatar-bob" : ""} aria-hidden>
      <defs>
        <clipPath id={id("clip")}><circle cx="50" cy="50" r="50" /></clipPath>
        <radialGradient id={id("bg")} cx="35%" cy="25%" r="85%"><stop offset="0" stopColor="#fff" stopOpacity=".22" /><stop offset="1" stopColor="#000" stopOpacity=".12" /></radialGradient>
        <radialGradient id={id("skin")} cx="38%" cy="30%" r="75%"><stop offset="0" stopColor={shade(skin, 0.35)} /><stop offset=".55" stopColor={skin} /><stop offset="1" stopColor={shade(skin, -0.28)} /></radialGradient>
        <radialGradient id={id("hair")} cx="35%" cy="20%" r="85%"><stop offset="0" stopColor={shade(hair, 0.3)} /><stop offset=".6" stopColor={hair} /><stop offset="1" stopColor={shade(hair, -0.35)} /></radialGradient>
        <linearGradient id={id("shirt")} x1="0" y1="0" x2=".3" y2="1"><stop offset="0" stopColor={shade(shirt, 0.25)} /><stop offset="1" stopColor={shade(shirt, -0.3)} /></linearGradient>
        <radialGradient id={id("ao")} cx="50%" cy="0%" r="60%"><stop offset="0" stopColor="#000" stopOpacity=".28" /><stop offset="1" stopColor="#000" stopOpacity="0" /></radialGradient>
      </defs>
      <g clipPath={`url(#${id("clip")})`}>
        <rect width="100" height="100" style={{ fill: "var(--avatar-bg)" }} />
        <rect width="100" height="100" fill={`url(#${id("bg")})`} />

        <g transform="translate(-7 -4) scale(1.14)">
        {/* body */}
        <path d="M17 104 Q18 79 50 75.5 Q82 79 83 104 Z" fill={`url(#${id("shirt")})`} />
        <ellipse cx="50" cy="77" rx="20" ry="7" fill={`url(#${id("ao")})`} />
        <path d="M43.5 64 L56.5 64 L57 76 Q50 79 43 76 Z" fill={shade(skin, -0.18)} />

        {/* long hair sits behind the head */}
        {style === 2 && <path d="M27 48 Q24.5 82 36 88 L64 88 Q75.5 82 73 48 Z" fill={`url(#${id("hair")})`} />}

        {/* ears + head */}
        <circle cx="28.8" cy="49" r="4.2" fill={shade(skin, -0.12)} />
        <circle cx="71.2" cy="49" r="4.2" fill={shade(skin, -0.2)} />
        <ellipse cx="50" cy="47" rx="21.5" ry="23.5" fill={`url(#${id("skin")})`} />

        {/* hair + gloss */}
        <path d={hairTop} fill={`url(#${id("hair")})`} />
        {style === 3 && <circle cx="50" cy="19" r="6.5" fill={`url(#${id("hair")})`} />}
        <ellipse cx="41" cy="27.5" rx="8" ry="2.6" fill="#fff" opacity=".22" transform="rotate(-14 41 27.5)" />

        {/* cheeks */}
        <ellipse cx="37.5" cy="54.5" rx="4.2" ry="2.6" fill="#ff7b8f" opacity={happy ? 0.38 : 0.16} />
        <ellipse cx="62.5" cy="54.5" rx="4.2" ry="2.6" fill="#ff7b8f" opacity={happy ? 0.38 : 0.16} />

        {/* brows only when they mean something */}
        {feeling === "annoyed" && <><path d="M37.5 39.5 L45 41.5" stroke={ink} strokeWidth="2" strokeLinecap="round" opacity=".7" /><path d="M55 41.5 L62.5 39.5" stroke={ink} strokeWidth="2" strokeLinecap="round" opacity=".7" /></>}
        {(feeling === "skeptical" || feeling === "confused") && <path d="M55 39.5 Q59 37 63 39" stroke={ink} strokeWidth="2" strokeLinecap="round" fill="none" opacity=".7" />}

        {/* eyes: glossy beads, closed smiles when delighted */}
        <g className="avatar-blink">
          {happy ? <>
            <path d="M39 47 Q42 44 45 47" stroke={ink} strokeWidth="2.2" strokeLinecap="round" fill="none" />
            <path d="M55 47 Q58 44 61 47" stroke={ink} strokeWidth="2.2" strokeLinecap="round" fill="none" />
          </> : <>
            <ellipse cx="42" cy="46.5" rx="2.7" ry={eyeRy} fill="#231b17" />
            <ellipse cx="58" cy="46.5" rx="2.7" ry={eyeRy} fill="#231b17" />
            <circle cx="43" cy={46.5 - eyeRy * 0.45} r=".95" fill="#fff" />
            <circle cx="59" cy={46.5 - eyeRy * 0.45} r=".95" fill="#fff" />
          </>}
        </g>

        {glasses && <g fill="#fff" fillOpacity=".12" stroke="#1d1d22" strokeOpacity=".75" strokeWidth="1.4">
          <circle cx="42" cy="46.5" r="6.4" /><circle cx="58" cy="46.5" r="6.4" /><path d="M48.4 46.5 L51.6 46.5" fill="none" />
        </g>}

        <path d={MOUTH[feeling]} stroke={shade(skin, -0.55)} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill={happy ? shade(skin, -0.6) : "none"} />
        </g>
      </g>
    </svg>
  );
}
