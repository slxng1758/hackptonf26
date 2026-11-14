// One palette for every view. The same color always means the same thing.
export const C = {
  bg: "#08080d",
  bg2: "#11121a",
  panel: "rgba(255,255,255,0.04)",
  line: "rgba(255,255,255,0.10)",
  text: "#f2efe8",
  truth: "#3ff0d4",   // knows why
  ritual: "#ffb547",  // still does it, forgot why
  myth: "#d16bff",    // the reason turned sacred
  unsafe: "#7b84a8",  // doesn't act
  none: "#2b2f45",    // hasn't heard
  sick: "#ff3355",
} as const;

export const KIND_COLOR = { truth: C.truth, ritual: C.ritual, myth: C.myth, unsafe: C.unsafe, none: C.none } as const;
