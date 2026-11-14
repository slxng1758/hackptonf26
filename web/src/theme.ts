export const C = {
  bg: "#08080d", text: "#f2efe8",
  win: "#3ff0d4",     // an AI shopper picked you
  loss: "#ff3355",    // it picked a competitor
  mid: "#ffb547",     // partly
  brain: "#d16bff",   // the agent's own steps
  dim: "rgba(242,239,232,0.5)",
} as const;
export const PANEL = "rounded-2xl border border-white/10 bg-white/[0.035]";
export const LABEL = "font-mono text-[10px] uppercase tracking-[0.3em] text-white/40";
export const pct = (x?: number | null) => (x == null ? "–" : `${Math.round(x * 100)}%`);
export const rateColor = (x: number) => (x >= 0.5 ? C.win : x >= 0.2 ? C.mid : C.loss);
