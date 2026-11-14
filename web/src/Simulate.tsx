import { useEffect, useState } from "react";
import { Avatar, SHIRT, type Feeling } from "./Avatar";
import { C, LABEL, PANEL, pct } from "./theme";

export interface Persona { id: string; name: string; age: number; occupation: string; archetype: string; segment: string; share: number; goal: string; budget: string; voice: string; avatar: { seed: number } }
interface SimStep { n: number; url: string; title: string; shot: string | null; blocked?: boolean; thought: string; feeling: Feeling; action: string; target: string }
interface Decision { decision: string; rating: number; feeling: Feeling; quote: string; reasons: string[]; missing: string }
export interface Sim {
  id: string; input: { url: string; name: string; category: string; context: string; world: string; customers: string };
  status: "casting" | "awaiting_approval" | "browsing" | "analyzing" | "done" | "error"; error: string | null;
  personas: Persona[]; live: Record<string, SimStep[]>; decisions: Record<string, Decision>;
  summary: { buy_rate: number; rating: number; decisions: Record<string, number>; missing: { persona: string; text: string }[] } | null;
  report: string; steps: { t: string; kind: string; note: string }[]; memory: Record<string, string>;
}

export const WORLDS = ["Today, normal times", "During COVID-19 (spring 2020)", "A recession: budgets are tight", "Holiday season rush", "Back-to-school week"];
const DEC_COLOR: Record<string, string> = { buy: C.win, "would recommend": C.win, "maybe later": C.mid, "not buy": C.loss, "would complain": C.loss };
const shot = (simId: string, f: string | null) => (f ? `/api/shots/${simId}/shots/${f}` : "");

// ---------- setup: what changed + which world ----------
export function SimSetup({ draft, onStart, onBack }: { draft: { name: string; category: string; customers: string; url?: string }; onStart: (b: Sim["input"]) => void; onBack: () => void }) {
  const [url, setUrl] = useState(draft.url ?? "");
  const [context, setContext] = useState("");
  const [world, setWorld] = useState(WORLDS[0]);
  const [custom, setCustom] = useState("");
  return (
    <div className="mx-auto max-w-3xl px-6 py-12">
      <button onClick={onBack} className="font-mono text-[11px] text-white/45 hover:text-white">← back</button>
      <div className={`${LABEL} mt-4`}>simulate your customers</div>
      <h1 className="mt-1 font-serif text-[40px] leading-tight">{draft.name}</h1>
      <p className="mt-2 text-[15px] text-white/55">Your customers become personas. Each one opens your real website in a browser, clicks around, thinks out loud, and decides. You approve who's in the room first.</p>

      <label className="mt-8 block"><span className={LABEL}>the page they'll land on</span>
        <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://yourbusiness.com" className="mt-2 w-full rounded-xl border border-white/15 bg-white/[0.04] px-4 py-3 font-mono text-[14px] outline-none focus:border-[#3ff0d4]" />
      </label>

      <label className="mt-6 block"><span className={LABEL}>what changed? (optional)</span>
        <textarea rows={2} value={context} onChange={(e) => setContext(e.target.value)} placeholder="e.g. we just added online ordering for catering, or we raised prices 10%"
          className="mt-2 w-full rounded-xl border border-white/15 bg-white/[0.04] p-3 text-[14px] outline-none focus:border-[#3ff0d4]" />
      </label>

      <div className="mt-6"><span className={LABEL}>the world they live in</span>
        <div className="mt-2 flex flex-wrap gap-2">
          {WORLDS.map((w) => <button key={w} onClick={() => setWorld(w)} className={`rounded-full border px-3 py-1.5 text-[13px] ${world === w ? "border-[#3ff0d4] text-[#3ff0d4]" : "border-white/15 text-white/65 hover:text-white"}`}>{w}</button>)}
          <input value={custom} onChange={(e) => { setCustom(e.target.value); if (e.target.value) setWorld(e.target.value); }} placeholder="or your own…" className="rounded-full border border-dashed border-white/20 bg-transparent px-3 py-1.5 text-[13px] outline-none" />
        </div>
      </div>

      <button disabled={url.trim().length < 4} onClick={() => onStart({ url: url.trim(), name: draft.name, category: draft.category, customers: draft.customers, context, world })}
        className="mt-10 w-full rounded-xl py-4 text-[16px] font-semibold text-black disabled:opacity-40" style={{ background: C.win, boxShadow: `0 0 40px ${C.win}55` }}>
        Meet your customers →
      </button>
    </div>
  );
}

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

function Tile({ sim, p, onOpen }: { sim: Sim; p: Persona; onOpen: () => void }) {
  const steps = sim.live[p.id] ?? [];
  const last = steps[steps.length - 1];
  const d = sim.decisions[p.id];
  const feeling: Feeling = d?.feeling ?? last?.feeling ?? "neutral";
  return (
    <button onClick={onOpen} className={`${PANEL} group relative overflow-hidden text-left transition hover:border-white/30`}>
      <div className="relative aspect-[16/10] bg-black/40">
        {last?.shot ? <img src={shot(sim.id, last.shot)} alt="" className="h-full w-full object-cover object-top opacity-90" /> :
          <div className="grid h-full place-items-center font-mono text-[11px] text-white/30">{sim.status === "browsing" ? "opening the site…" : "waiting"}</div>}
        {last && !d && <div className="absolute left-2 top-2 max-w-[85%] truncate rounded-md bg-black/70 px-2 py-0.5 font-mono text-[10px] text-white/70">{last.url.replace(/^https?:\/\//, "")}</div>}
        {d && <div className="absolute right-2 top-2 rounded-full px-2.5 py-1 font-mono text-[11px] font-semibold text-black" style={{ background: DEC_COLOR[d.decision] ?? C.mid }}>{d.decision} · {d.rating}/5</div>}
        <div className="absolute bottom-2 left-2 flex items-end gap-2">
          <div className="rounded-full ring-2" style={{ boxShadow: `0 0 0 2px ${SHIRT[p.archetype]}` }}><Avatar seed={p.avatar.seed} archetype={p.archetype} age={p.age} size={58} feeling={feeling} busy={sim.status === "browsing" && !d} /></div>
          {(d || last) && (
            <div className="bubble mb-6 max-w-[230px] rounded-xl rounded-bl-none bg-white px-3 py-2 text-[12px] leading-snug text-black shadow-lg">
              {d ? d.quote : last!.thought}
            </div>
          )}
        </div>
      </div>
      <div className="flex items-center justify-between px-3 py-2">
        <span className="text-[13px]"><b>{p.name}</b> <span className="text-white/45">· {p.archetype}</span></span>
        <span className="flex gap-1">{Array.from({ length: 5 }, (_, k) => <span key={k} className="h-1.5 w-1.5 rounded-full" style={{ background: k < steps.length ? SHIRT[p.archetype] : "rgba(255,255,255,0.12)" }} />)}</span>
      </div>
    </button>
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
                <div className="font-mono text-[11px] text-white/40">step {s.n} · {s.url.replace(/^https?:\/\//, "")}{s.blocked && <span className="ml-2 rounded-full bg-white/10 px-2 py-0.5 text-white/60">blocked by a bot check · not a customer issue</span>}</div>
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

  const s = sim.summary;
  return (
    <div className="mx-auto max-w-[1400px] px-6 py-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className={LABEL}>{sim.input.world || "today"}{sim.input.context ? ` · changed: ${sim.input.context}` : ""}</div>
          <h1 className="mt-1 font-serif text-[34px] leading-tight">{sim.input.name}</h1>
          <a href={sim.input.url} target="_blank" rel="noreferrer" className="font-mono text-[12px] text-white/45 hover:text-white">{sim.input.url}</a>
        </div>
        <span className="rounded-full border px-3 py-1 font-mono text-[11px]" style={{ borderColor: sim.status === "done" ? C.win : sim.status === "error" ? C.loss : C.mid, color: sim.status === "done" ? C.win : sim.status === "error" ? C.loss : C.mid }}>
          {{ casting: "● meeting your customers", awaiting_approval: "waiting for you", browsing: "● customers are browsing your site", analyzing: "● agent analyzing and evolving personas", done: "done", error: "error" }[sim.status]}
        </span>
      </div>
      {sim.error && <p className="mt-3 text-[13px]" style={{ color: C.loss }}>{sim.error}</p>}

      {sim.status === "casting" && <div className={`${PANEL} mt-6 grid h-64 place-items-center font-mono text-white/45`}>casting customers from your market…</div>}

      {sim.status === "awaiting_approval" && cast && (
        <div className="mt-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-[15px] text-white/70">These are the customers who'll test your site. Remove anyone who doesn't fit, then let them in.</p>
            <button disabled={!cast.length} onClick={approve} className="rounded-xl px-6 py-3 font-semibold text-black" style={{ background: C.win, boxShadow: `0 0 30px ${C.win}55` }}>Approve and let them in →</button>
          </div>
          <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">{cast.map((p) => <PersonaCard key={p.id} p={p} onRemove={() => setCast(cast.filter((x) => x.id !== p.id))} />)}</div>
        </div>
      )}

      {["browsing", "analyzing", "done"].includes(sim.status) && (
        <>
          {s && (
            <div className="mt-6 grid gap-4 md:grid-cols-4">
              <div className={`${PANEL} p-5`}><div className={LABEL}>would buy</div><div className="mt-2 font-mono text-[44px] font-semibold" style={{ color: s.buy_rate >= 0.5 ? C.win : s.buy_rate >= 0.25 ? C.mid : C.loss }}>{pct(s.buy_rate)}</div><div className="text-[12px] text-white/45">weighted by your customer mix</div></div>
              <div className={`${PANEL} p-5`}><div className={LABEL}>average rating</div><div className="mt-2 font-mono text-[44px] font-semibold">{s.rating.toFixed(1)}<span className="text-[20px] text-white/40">/5</span></div></div>
              <div className={`${PANEL} p-5 md:col-span-2`}><div className={LABEL}>what they decided</div>
                <div className="mt-3 flex flex-wrap gap-2">{Object.entries(s.decisions).map(([k, v]) => <span key={k} className="rounded-full px-3 py-1 font-mono text-[12px] font-semibold text-black" style={{ background: DEC_COLOR[k] ?? C.mid }}>{v} × {k}</span>)}</div>
              </div>
            </div>
          )}
          <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{sim.personas.map((p) => <Tile key={p.id} sim={sim} p={p} onOpen={() => setOpen(p)} />)}</div>
          {s && s.missing.length > 0 && (
            <section className={`${PANEL} mt-6 p-5`}>
              <div className={LABEL}>what would have changed their minds</div>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                {s.missing.map((m) => { const p = sim.personas.find((x) => x.id === m.persona)!; return (
                  <div key={m.persona} className="flex items-start gap-3 rounded-xl bg-white/[0.03] p-3"><Avatar seed={p.avatar.seed} archetype={p.archetype} age={p.age} size={36} feeling={sim.decisions[p.id]?.feeling ?? "neutral"} /><p className="text-[13px] text-white/80"><b>{p.name}:</b> {m.text}</p></div>
                ); })}
              </div>
            </section>
          )}
          {sim.report && (
            <div className="mt-6"><button onClick={() => setReport(!report)} className="rounded-full border border-white/15 px-4 py-1.5 font-mono text-[11px] text-white/60 hover:text-white">{report ? "hide" : "read"} the agent's report</button>
              {report && <pre className={`${PANEL} mt-3 whitespace-pre-wrap p-6 font-serif text-[15px] leading-relaxed text-white/85`}>{sim.report}</pre>}</div>
          )}
        </>
      )}
      {open && <Replay sim={sim} p={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
