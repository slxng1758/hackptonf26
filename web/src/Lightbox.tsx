// A screenshot, big: click any page thumbnail to open it. Esc or a click outside closes it.
import { useEffect } from "react";

export function Lightbox({ src, title, sub, onClose, side }: { src: string | null; title: string; sub?: string; onClose: () => void; side?: React.ReactNode }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    addEventListener("keydown", k);
    const was = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { removeEventListener("keydown", k); document.body.style.overflow = was; };
  }, [onClose]);
  return (
    <div className="scrim fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 md:p-8" onClick={onClose}>
      <div className="flex max-h-full w-full max-w-[1500px] flex-col overflow-hidden rounded-xl border border-white/15 bg-[var(--card)] shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-3 border-b border-white/10 px-4 py-2.5">
          <div className="min-w-0 flex-1"><div className="truncate text-[14px] font-semibold">{title}</div>{sub && <div className="truncate font-mono text-[11px] text-white/45">{sub}</div>}</div>
          {src && <a href={src} target="_blank" rel="noreferrer" className="font-mono text-[11px] text-white/50 hover:text-white">open full size ↗</a>}
          <button onClick={onClose} aria-label="close" className="grid h-8 w-8 place-items-center rounded-full text-[18px] text-white/60 hover:bg-white/10 hover:text-white">×</button>
        </div>
        <div className={`grid min-h-0 flex-1 ${side ? "md:grid-cols-[1fr_340px]" : ""}`}>
          <div className="min-h-0 overflow-auto bg-black/30">
            {src ? <img src={src} alt={title} className="block w-full" /> : <div className="grid h-64 place-items-center text-[13px] text-white/45">No screenshot for this step.</div>}
          </div>
          {side && <div className="min-h-0 overflow-auto border-l border-white/10">{side}</div>}
        </div>
      </div>
    </div>
  );
}
