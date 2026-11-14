// Shared pieces so every view has the same header, panels and legend.
import type { ReactNode } from "react";
import { KIND_COLOR, C } from "./theme";
import { LABEL, type Kind } from "./epi";

export const PANEL = "rounded-2xl border border-white/10 bg-white/[0.04] backdrop-blur";

export function Header({ eyebrow, title, sub }: { eyebrow: string; title: ReactNode; sub?: ReactNode }) {
  return (
    <div className="pointer-events-none absolute left-6 top-16 z-10 max-w-[420px]">
      <div className="font-mono text-[10px] uppercase tracking-[0.35em] text-white/40">{eyebrow}</div>
      <div className="mt-1 font-serif text-[28px] leading-tight text-white">{title}</div>
      {sub && <div className="mt-1.5 font-mono text-[12px] text-white/45">{sub}</div>}
    </div>
  );
}

export function Legend({ counts, className = "" }: { counts?: Partial<Record<Kind, number>>; className?: string }) {
  return (
    <div className={`${PANEL} p-4 font-mono ${className}`}>
      {(["truth", "ritual", "myth", "unsafe"] as const).map((k) => (
        <div key={k} className="flex items-center gap-3 py-0.5 text-[12px]">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: KIND_COLOR[k], boxShadow: `0 0 8px ${KIND_COLOR[k]}` }} />
          <span className="w-36 text-white/65">{LABEL[k]}</span>
          {counts && <span className="text-white">{counts[k] ?? 0}</span>}
        </div>
      ))}
      <div className="mt-2 flex items-center gap-3 border-t border-white/10 pt-2 text-[12px] text-white/65">
        <span className="h-2.5 w-2.5 rounded-full border-2" style={{ borderColor: C.sick }} /> sick
      </div>
    </div>
  );
}
