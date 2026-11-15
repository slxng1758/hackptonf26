// Three looks, switchable from the header. The light themes flip Tailwind's "white" to ink, so every translucent
// white-on-dark utility becomes ink-on-light without touching the components.
export type ThemeName = "receipt" | "storefront" | "paper" | "dark";
const THEMES: Record<ThemeName, { bg: string; card: string; ink: string; win: string; loss: string; mid: string; brain: string; avatarBg: string }> = {
  // Receipt (default): warm paper, ink, one tomato accent. The brand color is ink itself, so buttons read like print.
  receipt: { bg: "#f3ede2", card: "#fbf7ef", ink: "#1b1813", win: "#2f7a4a", loss: "#c8402a", mid: "#b8801c", brain: "#1b1813", avatarBg: "#e9e1d2" },
  storefront: { bg: "#f7f8fa", card: "#ffffff", ink: "#101828", win: "#00a37a", loss: "#e5384f", mid: "#f08c00", brain: "#6d4aff", avatarBg: "#eef1f5" },
  paper: { bg: "#f6f1e7", card: "#fffdf8", ink: "#1c1a17", win: "#0f9e86", loss: "#d9223f", mid: "#d98200", brain: "#7a3fd1", avatarBg: "#ece3d3" },
  dark: { bg: "#08080d", card: "#11131c", ink: "#f2efe8", win: "#3ff0d4", loss: "#ff3355", mid: "#ffb547", brain: "#d16bff", avatarBg: "#141623" },
};
function read(): ThemeName {
  if (typeof location !== "undefined" && location.hash.startsWith("#print=")) return "storefront"; // the PDF is always light
  try { const t = localStorage.getItem("theme2"); if (t === "dark" || t === "receipt") return t; } catch { /* storage unavailable */ }
  return "receipt";
}
export const THEME = read();
const T = THEMES[THEME];
if (typeof document !== "undefined") {
  const r = document.documentElement;
  r.dataset.theme = THEME;
  for (const [k, v] of Object.entries({ "--bg": T.bg, "--card": T.card, "--ink": T.ink, "--avatar-bg": T.avatarBg })) r.style.setProperty(k, v);
}
export function setTheme(t: ThemeName) {
  try { localStorage.setItem("theme2", t); } catch { /* storage unavailable */ }
  location.reload();
}
export const THEME_LIST: { id: ThemeName; label: string; swatch: string[] }[] = [
  { id: "receipt", label: "Paper", swatch: ["#f3ede2", "#1b1813", "#c8402a"] },
  { id: "dark", label: "Dark", swatch: ["#08080d", "#3ff0d4", "#d16bff"] },
];

export const C = {
  bg: T.bg, text: T.ink,
  win: T.win,     // bought
  loss: T.loss,   // left
  mid: T.mid,     // maybe later
  brain: T.brain, // the agents' own work
  accent: THEME === "receipt" ? "#c8402a" : T.brain, // the one highlight color (tomato on paper)
  dim: "rgba(127,127,127,0.6)",
};
export const PANEL = "rounded-2xl border border-white/10 bg-white/[0.035] panel";
export const LABEL = "font-mono text-[10px] uppercase tracking-[0.3em] text-white/40";
export const pct = (x?: number | null) => (x == null ? "–" : `${Math.round(x * 100)}%`);
export const rateColor = (x: number) => (x >= 0.5 ? C.win : x >= 0.2 ? C.mid : C.loss);
