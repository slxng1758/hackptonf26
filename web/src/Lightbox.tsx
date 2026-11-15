// A screenshot, big. Esc or a click outside closes it.
// <ZoomRoot/> (mounted once in App) makes every screenshot in the app clickable: any <img> served from /api/shots/,
// or any element marked data-zoom="<src>" (for thumbnails with overlays on top), opens here.
import { useEffect, useState } from "react";

export function Lightbox({ src, title, sub, onClose, side }: { src: string | null; title: string; sub?: string; onClose: () => void; side?: React.ReactNode }) {
  useEffect(() => {
    // capture + stopImmediatePropagation: Esc closes only this, not a popup underneath it
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopImmediatePropagation(); onClose(); } };
    addEventListener("keydown", k, true);
    const was = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { removeEventListener("keydown", k, true); document.body.style.overflow = was; };
  }, [onClose]);
  return (
    <div data-lightbox className="scrim fixed inset-0 z-[70] flex items-center justify-center bg-black/80 p-4 md:p-8" onClick={onClose}>
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

export function ZoomRoot() {
  const [z, setZ] = useState<{ src: string; title: string; sub?: string } | null>(null);
  useEffect(() => {
    // capture phase, so a parent's onClick (stopPropagation in a popup, an avatar button) can't swallow the click
    const click = (e: MouseEvent) => {
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey) return;
      const t = e.target as HTMLElement | null;
      if (!t || t.closest("[data-lightbox], [data-nozoom], a, button:not([data-zoom])")) return;
      const box = t.closest<HTMLElement>("[data-zoom]");
      const img = box ? null : t.closest("img");
      const src = box?.dataset.zoom || (img && img.getAttribute("src")?.startsWith("/api/shots/") ? img.getAttribute("src") : null);
      if (!src) return;
      e.preventDefault(); e.stopPropagation();
      const el = box ?? img!;
      setZ({ src, title: el.dataset.title || img?.alt || "Screenshot", sub: el.dataset.sub });
    };
    document.addEventListener("click", click, true);
    return () => document.removeEventListener("click", click, true);
  }, []);
  return z ? <Lightbox src={z.src} title={z.title} sub={z.sub} onClose={() => setZ(null)} /> : null;
}
