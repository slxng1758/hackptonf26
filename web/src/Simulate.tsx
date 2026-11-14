import { useEffect, useState } from "react";
import { Avatar, SHIRT, type Feeling } from "./Avatar";
import { C, PANEL } from "./theme";
import { SiteMap } from "./SiteMap";

export interface Persona { id: string; name: string; age: number; occupation: string; archetype: string; segment: string; share: number; goal: string; budget: string; voice: string; avatar: { seed: number } }
interface SimStep { n: number; url: string; title: string; shot: string | null; blocked?: boolean; cart?: boolean; thought: string; feeling: Feeling; action: string; target: string }
interface Decision { decision: string; rating: number; feeling: Feeling; quote: string; reasons: string[]; missing: string }
export interface Sim {
  id: string; input: { url: string; name: string; category: string; context: string; world: string; customers: string };
  status: "casting" | "awaiting_approval" | "browsing" | "analyzing" | "done" | "error"; error: string | null;
  personas: Persona[]; live: Record<string, SimStep[]>; decisions: Record<string, Decision>;
  summary: { buy_rate: number; rating: number; decisions: Record<string, number>; missing: { persona: string; text: string }[] } | null;
  report: string; steps: { t: string; kind: string; note: string }[]; memory: Record<string, string>;
}

const DEC_COLOR: Record<string, string> = { buy: C.win, "would recommend": C.win, "maybe later": C.mid, "not buy": C.loss, "would complain": C.loss };
const shot = (simId: string, f: string | null) => (f ? `/api/shots/${simId}/shots/${f}` : "");

// ---------- the simulation itself ----------
function PersonaCard({ p, onRemove }: { p: Persona; onRemove?: () => void }) {
  return (
    <div className={`${PANEL} rise relative p-4`}>
      {onRemove && <button onClick={onRemove} className="absolute right-2 top-2 grid h-6 w-6 place-items-center rounded-full text-white/35 hover:bg-white/10 hover:text-white" aria-label="remove">×</button>}
      <div className="flex items-center gap-3">
        <Avatar seed={p.avatar.seed} archetype={p.archetype} age={p.age} size={56} feeling="neutral" />
        <div>
          <div className="text-[15px] font-semibold">{p.name}, {p.age}</div>
          <div className="text-[12px] text-white/50">{p.occupation}</div>
          <span className="mt-1 inline-block rounded-full px-2 py-0.5 font-mono text-[10px]" style={{ background: `${SHIRT[p.archetype]}22`, color: SHIRT[p.archetype] }}>{p.archetype} · {Math.round(p.share * 100)}%</span>
        </div>
      </div>
      <p className="mt-3 text-[13px] leading-snug text-white/75">“{p.goal}”</p>
      <p className="mt-1 font-mono text-[11px] text-white/40">budget: {p.budget}</p>
    </div>
  );
}

function Replay({ sim, p, onClose }: { sim: Sim; p: Persona; onClose: () => void }) {
  const steps = sim.live[p.id] ?? [];
  const d = sim.decisions[p.id];
  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/80 p-6 backdrop-blur" onClick={onClose}>
      <div className={`${PANEL} mx-auto max-w-5xl bg-[#0d0e15] p-6`} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4"><Avatar seed={p.avatar.seed} archetype={p.archetype} age={p.age} size={64} feeling={d?.feeling ?? "neutral"} />
            <div><div className="font-serif text-[26px]">{p.name}'s session</div><div className="text-[13px] text-white/50">{p.age} · {p.occupation} · {p.archetype} · wants: {p.goal}</div></div></div>
          <button onClick={onClose} className="text-[22px] text-white/50 hover:text-white">×</button>
        </div>
        <ol className="mt-6 space-y-5">
          {steps.map((s) => (
            <li key={s.n} className="grid gap-4 md:grid-cols-[360px_1fr]">
              {s.shot ? <img src={shot(sim.id, s.shot)} alt="" className="w-full rounded-lg border border-white/10" /> : <div className="rounded-lg bg-white/5" />}
              <div>
                <div className="font-mono text-[11px] text-white/40">step {s.n} · {s.url.replace(/^https?:\/\//, "")}{s.blocked && <span className="ml-2 rounded-full bg-white/10 px-2 py-0.5 text-white/60">blocked by a bot check · not a customer issue</span>}{s.cart && <span className="ml-2 rounded-full px-2 py-0.5 font-semibold text-black" style={{ background: C.win }}>🛒 chose to buy</span>}</div>
                <div className="mt-2 flex items-start gap-3"><Avatar seed={p.avatar.seed} archetype={p.archetype} age={p.age} size={40} feeling={s.feeling} /><p className="rounded-xl rounded-tl-none bg-white/[0.06] px-3 py-2 text-[14px] leading-snug">“{s.thought}”</p></div>
                <div className="mt-2 font-mono text-[12px]" style={{ color: SHIRT[p.archetype] }}>→ {s.action === "click" ? `clicked “${s.target}”` : s.action === "decide" ? "ready to decide" : s.action}  <span className="text-white/40">· felt {s.feeling}</span></div>
              </div>
            </li>
          ))}
        </ol>
        {d && (
          <div className="mt-6 rounded-xl border p-5" style={{ borderColor: DEC_COLOR[d.decision] ?? C.mid }}>
            <div className="flex items-baseline justify-between"><span className="font-mono text-[13px] font-semibold uppercase" style={{ color: DEC_COLOR[d.decision] }}>{d.decision} · {d.rating}/5 · {d.feeling}</span></div>
            <p className="mt-2 font-serif text-[18px]">“{d.quote}”</p>
            <ul className="mt-3 space-y-1 text-[13px] text-white/70">{d.reasons.map((r, i) => <li key={i}>· {r}</li>)}</ul>
            <p className="mt-3 text-[13px]"><span className="text-white/45">Would have changed their mind:</span> {d.missing}</p>
            {sim.memory[p.id] && <p className="mt-3 border-t border-white/10 pt-3 text-[13px] text-white/70"><span style={{ color: C.win }}>What {p.name} learned (kept for next time):</span> {sim.memory[p.id]}</p>}
          </div>
        )}
      </div>
    </div>
  );
}

const BUY = new Set(["buy", "would recommend"]);
const host = (u: string) => u.replace(/^https?:\/\//, "").replace(/\/.*$/, "");

export function SimView({ id }: { id: string }) {
  const [sim, setSim] = useState<Sim | null>(null);
  const [cast, setCast] = useState<Persona[] | null>(null);
  const [open, setOpen] = useState<Persona | null>(null);
  const [report, setReport] = useState(false);

  useEffect(() => {
    let alive = true;
    const tick = () => fetch(`/api/sims/${id}`).then((r) => r.json()).then((s: Sim) => { if (alive) { setSim(s); if (s.status === "awaiting_approval" && !cast) setCast(s.personas); } }).catch(() => {});
    tick();
    const t = setInterval(() => { if (!sim || !["done", "error"].includes(sim.status)) tick(); }, 1500);
    return () => { alive = false; clearInterval(t); };
  }, [id, sim?.status]); // eslint-disable-line

  if (!sim) return <div className="grid h-[60vh] place-items-center font-mono text-white/40">loading…</div>;

  async function approve() {
    await fetch(`/api/sims/${id}/approve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ personas: cast }) });
    setSim({ ...sim!, status: "browsing", personas: cast ?? sim!.personas });
  }

  const name = sim.input.name || host(sim.input.url);
  const decided = Object.keys(sim.decisions).length;
  const buyers = Object.values(sim.decisions).filter((d) => BUY.has(d.decision)).length;
  const live = ["browsing", "analyzing", "done"].includes(sim.status);
  const unconvinced = sim.personas.filter((p) => sim.decisions[p.id] && !BUY.has(sim.decisions[p.id].decision) && sim.decisions[p.id].missing);

  return (
    <div className="mx-auto max-w-[1400px] px-6 pb-16">
      {/* one headline that always says what is happening */}
      <div className="pt-6 text-center">
        <div className="font-mono text-[12px] text-white/40">{host(sim.input.url)}{sim.input.context ? ` · ${sim.input.context}` : ""}{sim.input.world ? ` · ${sim.input.world}` : ""}</div>
        <h1 className="mt-2 font-serif text-[40px] leading-tight">
          {sim.status === "casting" && <>Reading {name}<span className="animate-pulse">…</span></>}
          {sim.status === "awaiting_approval" && <>Meet your customers</>}
          {sim.status === "browsing" && <>{decided} of {sim.personas.length} have decided<span className="animate-pulse">…</span></>}
          {sim.status === "analyzing" && <><span style={{ color: buyers ? C.win : C.loss }}>{buyers} of {decided}</span> would buy · <span className="text-white/50">writing up why<span className="animate-pulse">…</span></span></>}
          {sim.status === "done" && <><span style={{ color: buyers / Math.max(decided, 1) >= 0.5 ? C.win : buyers ? C.mid : C.loss }}>{buyers} of {decided}</span> customers would buy from {name}</>}
          {sim.status === "error" && <span style={{ color: C.loss }}>Something broke</span>}
        </h1>
        {sim.error && <p className="mt-2 text-[13px]" style={{ color: C.loss }}>{sim.error}</p>}
      </div>

      {sim.status === "casting" && (
        <div className="mt-12 flex justify-center gap-5">
          {[0, 1, 2, 3, 4].map((i) => <div key={i} className="h-20 w-20 animate-pulse rounded-full bg-white/[0.06]" style={{ animationDelay: `${i * 0.15}s` }} />)}
        </div>
      )}

      {sim.status === "awaiting_approval" && cast && (
        <div className="mt-10 text-center">
          <div className="flex flex-wrap justify-center gap-6">
            {cast.map((p, i) => (
              <div key={p.id} className="rise group relative w-[150px]" style={{ animationDelay: `${i * 0.08}s` }}>
                <button onClick={() => setCast(cast.filter((x) => x.id !== p.id))} className="absolute right-3 top-0 z-10 hidden h-6 w-6 place-items-center rounded-full bg-white/15 text-white/70 hover:bg-[#ff3355] hover:text-white group-hover:grid" aria-label={`remove ${p.name}`}>×</button>
                <div className="mx-auto w-fit rounded-full" style={{ boxShadow: `0 0 0 3px ${SHIRT[p.archetype]}` }}><Avatar seed={p.avatar.seed} archetype={p.archetype} age={p.age} size={96} /></div>
                <div className="mt-3 text-[15px] font-semibold">{p.name}, {p.age}</div>
                <div className="font-mono text-[11px]" style={{ color: SHIRT[p.archetype] }}>{p.archetype}</div>
                <p className="mt-1 text-[12px] leading-snug text-white/50">{p.goal}</p>
              </div>
            ))}
          </div>
          <button disabled={!cast.length} onClick={approve} className="mt-10 rounded-2xl px-10 py-4 text-[17px] font-semibold text-black disabled:opacity-40" style={{ background: C.win, boxShadow: `0 0 40px ${C.win}66` }}>Let them in →</button>
          <p className="mt-3 text-[12px] text-white/35">hover anyone to remove them</p>
        </div>
      )}

      {live && (
        <>
          <SiteMap sim={sim} onOpen={setOpen} />
          <p className="mt-3 text-center text-[12px] text-white/35">click anyone to replay their visit · hover a page to see it</p>

          {sim.status === "done" && unconvinced.length > 0 && (
            <section className="mx-auto mt-10 max-w-3xl">
              <h2 className="text-center font-serif text-[26px]">What would win the rest over</h2>
              <div className="mt-5 space-y-3">
                {unconvinced.map((p) => (
                  <div key={p.id} className={`${PANEL} flex items-center gap-4 p-4`}>
                    <Avatar seed={p.avatar.seed} archetype={p.archetype} age={p.age} size={48} feeling={sim.decisions[p.id].feeling} />
                    <p className="text-[15px] leading-snug text-white/85"><b>{p.name}:</b> {sim.decisions[p.id].missing}</p>
                  </div>
                ))}
              </div>
            </section>
          )}

          {sim.report && (
            <div className="mt-8 text-center">
              <button onClick={() => setReport(!report)} className="text-[13px] text-white/45 underline decoration-white/20 hover:text-white">{report ? "hide" : "read"} the full report</button>
              {report && <pre className={`${PANEL} mx-auto mt-4 max-w-3xl whitespace-pre-wrap p-6 text-left font-serif text-[15px] leading-relaxed text-white/85`}>{sim.report}</pre>}
            </div>
          )}
        </>
      )}
      {open && <Replay sim={sim} p={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
