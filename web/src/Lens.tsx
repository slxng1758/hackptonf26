// Friction hotspots (b2a/gemini.py): Gemini looks at the screenshots where customers got stuck and boxes the exact spot.
import { useEffect, useState } from "react";
import { C, PANEL } from "./theme";

interface Box { box_2d: number[]; label: string; issue: string; fix: string; severity: number }
interface Shot { persona_id: string; persona: string; archetype: string; model: string; step: number; url: string; shot: string; feeling: string; thought: string; why: string; boxes: Box[]; error: string }
interface Hotspot { page: string; label: string; issue: string; fix: string; severity: number; count: number; personas: string[] }
interface LensData { model: string; shots: Shot[]; hotspots: Hotspot[]; summary: string }

const sev = (s: number) => (s >= 2.5 ? C.loss : s >= 1.5 ? C.mid : C.brain);

export function Lens({ simId }: { simId: string }) {
  const [lens, setLens] = useState<LensData | null>(null);
  const [state, setState] = useState<"loading" | "none" | "running" | "ready" | "error">("loading");
  const [err, setErr] = useState("");
  useEffect(() => {
    fetch(`/api/sims/${simId}/lens`).then(async (r) => { if (r.ok) { setLens(await r.json()); setState("ready"); } else setState("none"); }).catch(() => setState("none"));
  }, [simId]);
  async function run() {
    setState("running");
    const r = await fetch(`/api/sims/${simId}/lens`, { method: "POST" });
    if (r.ok) { setLens(await r.json()); setState("ready"); } else { setErr((await r.json().catch(() => ({}))).detail ?? "Lens failed"); setState("error"); }
  }
  const shots = (lens?.shots ?? []).filter((s) => s.boxes.length);
  return (
    <section className="mx-auto mt-10 max-w-6xl">
      <h2 className="text-center font-serif text-[30px]">Friction hotspots</h2>
      <p className="mx-auto mt-2 max-w-2xl text-center text-[14px] text-white/55">Gemini looks at the exact screens where customers got confused, went back or left, and boxes the part of the page that caused it.</p>
      {state === "loading" && <p className="mt-8 text-center text-white/50">Loading…</p>}
      {(state === "none" || state === "error") && (
        <div className="mt-8 text-center">
          <button onClick={run} className="rounded-xl px-6 py-3 text-[15px] font-semibold text-[#ffffff]" style={{ background: C.brain }}>Run the Gemini lens</button>
          <p className="mt-2 text-[12px] text-white/45">Takes about 30 to 60 seconds.{err && <span style={{ color: C.loss }}> {err}</span>}</p>
        </div>
      )}
      {state === "running" && <p className="mt-8 text-center text-white/60">Gemini is reading the screenshots<span className="animate-pulse">…</span></p>}
      {state === "ready" && lens && (
        <>
          {lens.summary && <p className={`${PANEL} mx-auto mt-6 max-w-4xl p-4 text-[15px] leading-relaxed`}>{lens.summary}</p>}
          <div className="mt-6 grid gap-3 md:grid-cols-2">
            {lens.hotspots.map((h, i) => (
              <div key={i} className={`${PANEL} p-4`} style={{ borderLeft: `4px solid ${sev(h.severity)}` }}>
                <div className="flex items-baseline justify-between gap-2"><span className="text-[15px] font-semibold">{h.label}</span><span className="font-mono text-[11px] text-white/50">{h.count} customer{h.count > 1 ? "s" : ""} · {h.page}</span></div>
                <p className="mt-1 text-[13.5px] text-white/75">{h.issue}</p>
                <p className="mt-1 text-[13px]"><span className="font-semibold" style={{ color: C.win }}>Fix:</span> <span className="text-white/75">{h.fix}</span></p>
              </div>
            ))}
          </div>
          <div className="mt-8 grid gap-5 lg:grid-cols-2">
            {shots.map((s, i) => (
              <figure key={i} className={`${PANEL} overflow-hidden`}>
                <div className="relative">
                  <img src={`/api/shots/${simId}/shots/${s.shot}`} alt="" className="block w-full" />
                  {s.boxes.map((b, k) => { const [y0, x0, y1, x1] = b.box_2d; return (
                    <div key={k} className="absolute rounded-md" title={`${b.label}: ${b.issue}`}
                      style={{ top: `${y0 / 10}%`, left: `${x0 / 10}%`, height: `${(y1 - y0) / 10}%`, width: `${(x1 - x0) / 10}%`, border: `3px solid ${sev(b.severity)}`, boxShadow: `0 0 0 9999px rgba(0,0,0,${k === 0 ? 0.18 : 0})` }}>
                      <span className="absolute -top-6 left-0 whitespace-nowrap rounded px-1.5 py-0.5 text-[11px] font-semibold text-[#ffffff]" style={{ background: sev(b.severity) }}>{b.label}</span>
                    </div>
                  ); })}
                </div>
                <figcaption className="p-3 text-[13px]"><b>{s.persona}</b> <span className="text-white/50">· {s.archetype}{s.model ? ` · ${s.model}` : ""} · {s.why}</span><p className="mt-1 text-white/70">“{s.thought}”</p></figcaption>
              </figure>
            ))}
          </div>
          <p className="mt-4 text-center font-mono text-[11px] text-white/40">boxes by {lens.model}</p>
        </>
      )}
    </section>
  );
}
