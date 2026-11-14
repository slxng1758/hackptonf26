// Three looks, switchable from the header. The light themes flip Tailwind's "white" to ink, so every translucent
// white-on-dark utility becomes ink-on-light without touching the components.
export type ThemeName = "storefront" | "paper" | "dark";
const THEMES: Record<ThemeName, { bg: string; card: string; ink: string; win: string; loss: string; mid: string; brain: string; avatarBg: string }> = {
  storefront: { bg: "#ffffff", card: "#ffffff", ink: "#111111", win: "#00b386", loss: "#ff2e5b", mid: "#ff9f1c", brain: "#8a4dff", avatarBg: "#fff3c4" },
  paper: { bg: "#f6f1e7", card: "#fffdf8", ink: "#1c1a17", win: "#0f9e86", loss: "#d9223f", mid: "#d98200", brain: "#7a3fd1", avatarBg: "#ece3d3" },
  dark: { bg: "#08080d", card: "#11131c", ink: "#f2efe8", win: "#3ff0d4", loss: "#ff3355", mid: "#ffb547", brain: "#d16bff", avatarBg: "#141623" },
};
function read(): ThemeName {
  try { const t = localStorage.getItem("theme"); if (t && t in THEMES) return t as ThemeName; } catch { /* storage unavailable */ }
  return "storefront";
}
export const THEME = read();
const T = THEMES[THEME];
if (typeof document !== "undefined") {
  const r = document.documentElement;
  r.dataset.theme = THEME;
  for (const [k, v] of Object.entries({ "--bg": T.bg, "--card": T.card, "--ink": T.ink, "--avatar-bg": T.avatarBg })) r.style.setProperty(k, v);
}
export function setTheme(t: ThemeName) {
  try { localStorage.setItem("theme", t); } catch { /* storage unavailable */ }
  location.reload();
}
export const THEME_LIST: { id: ThemeName; label: string; swatch: string[] }[] = [
  { id: "storefront", label: "Storefront", swatch: ["#b8f5e4", "#e7d4ff", "#ffe58a"] },
  { id: "paper", label: "Paper", swatch: ["#f6f1e7", "#1c1a17", "#0f9e86"] },
  { id: "dark", label: "Dark", swatch: ["#08080d", "#3ff0d4", "#d16bff"] },
];

export const C = {
  bg: T.bg, text: T.ink,
  win: T.win,     // bought
  loss: T.loss,   // left
  mid: T.mid,     // maybe later
  brain: T.brain, // the agents' own work
  dim: "rgba(127,127,127,0.6)",
};
export const PANEL = "rounded-2xl border border-white/10 bg-white/[0.035] panel";
export const LABEL = "font-mono text-[10px] uppercase tracking-[0.3em] text-white/40";
export const pct = (x?: number | null) => (x == null ? "–" : `${Math.round(x * 100)}%`);
export const rateColor = (x: number) => (x >= 0.5 ? C.win : x >= 0.2 ? C.mid : C.loss);
