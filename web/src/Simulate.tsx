import { useEffect, useState } from "react";
import { marked } from "marked";
import { Avatar, SHIRT, type Feeling } from "./Avatar";
import { C, PANEL } from "./theme";
import { SiteMap, ThoughtStream, outcome, outcomeDetail, outcomeColor, OUTCOME_LABEL } from "./SiteMap";
import { Timeline } from "./Timeline";
import { Lens } from "./Lens";
import { PersonaEditor, blankPersona } from "./PersonaEditor";
import { CastingLive, ThinkingFeed, type ThinkEvent } from "./CastingLive";
import { Accuracy, Learned, WordOfMouth } from "./Extras";
import type { SimExtras } from "./sim-extras";

export interface Persona { id: string; name: string; age: number; occupation: string; archetype: string; segment: string; share: number; goal: string; budget: string; voice: string; avatar: { seed: number }; model?: string; memory?: string; inherited?: boolean; kind?: "agent"; played_by?: string; model_note?: string; instructions?: string; custom?: boolean; why?: string }
interface SimStep { n: number; url: string; title: string; shot: string | null; blocked?: boolean; cart?: boolean; ordered?: boolean; thought: string; feeling: Feeling; action: string; target: string }
interface Suggestion { change: string; why: string; where: string; impact: "would make me buy" | "nice to have" }
interface Decision {
  decision: string; rating: number; feeling: Feeling; quote: string; reasons: string[]; missing: string;
  // newer fields (older sims don't have them)
  confidence?: number; first_impression?: string; review?: string; liked?: string[]; disliked?: string[]; would_pay?: string;
  suggestions?: Suggestion[]; stars_after_use?: number | null; memory_version?: number;
  deciding_moment?: string; deciding_step?: number; reconsidered?: string;
  outcome?: "bought" | "bought_unhappy" | "abandoned_cart" | "maybe" | "left"; ordered_step?: number; order_possible?: boolean;
}
export interface Sim extends Partial<SimExtras> {
  id: string; input: { url: string; name: string; category: string; context: string; world: string; customers: string; director?: boolean };
  thinking?: ThinkEvent[];
  status: "casting" | "awaiting_approval" | "browsing" | "talking" | "analyzing" | "done" | "error"
    | "briefing" | "resuming" | "approved" | "base_models" | "scoring" | "evolving" | "social" | "summarizing"; error: string | null;  // second row: director statuses
  personas: Persona[]; live: Record<string, SimStep[]>; decisions: Record<string, Decision>;
  summary: { agents?: { persona: string; model: string; bought: boolean; decision: string; missing: string; quote: string }[]; buy_rate: number; by_model?: Record<string, { bought: number; of: number }>; rating: number; decisions: Record<string, number>; missing: { persona: string; text: string }[] } | null;
  report: string; steps: { t: string; kind: string; note: string }[]; memory: Record<string, string>; round?: number; parent?: string | null;
  director?: { t: string; tool: string; reason: string; result: string }[]; todos?: { content: string; status: string }[];
  actions?: { fix: string; why: string; audience: "people" | "AI agents" | "both"; who: string[]; page: string; effort: "small" | "medium" | "big" }[];
}

const DEC_COLOR: Record<string, string> = { buy: C.win, "would recommend": C.win, "maybe later": C.mid, "not buy": C.loss, "would complain": C.loss };
const shot = (simId: string, f: string | null) => (f ? `/api/shots/${simId}/shots/${f}` : "");

// ---------- the simulation itself ----------
function PersonaCard({ p, onRemove }: { p: Persona; onRemove?: () => void }) {
  return (
    <div className={`${PANEL} rise relative p-4`}>
      {onRemove && <button onClick={onRemove} className="absolute right-2 top-2 grid h-6 w-6 place-items-center rounded-full text-white/35 hover:bg-white/10 hover:text-white" aria-label="remove">×</button>}
      <div className="flex items-center gap-3">
        <Avatar seed={p.avatar.seed} archetype={p.archetype} model={p.model} age={p.age} size={56} feeling="neutral" />
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

const MOOD: Record<string, number> = { delighted: 2, interested: 1, neutral: 0, confused: -1, skeptical: -1, annoyed: -2 };
const H = "font-mono text-[11px] font-semibold uppercase tracking-[0.2em] text-white/45";

// One persona, top to bottom: why they decided, what they came in with, every step, their review, what they learned.
function Replay({ sim, p, onClose }: { sim: Sim; p: Persona; onClose: () => void }) {
  const steps = sim.live[p.id] ?? [];
  const d = sim.decisions[p.id];
  const od = outcomeDetail(sim, p.id);
  const color = outcomeColor(od);
  const ordered = steps.find((s) => s.ordered);
  const learned = (sim.persona_changes ?? []).filter((c) => c.persona_id === p.id);
  const carted = steps.find((s) => s.cart);
  const pages = new Set(steps.map((s) => s.url)).size;
  // p.memory is replaced with the new lessons once the run ends, so what they started with is the first change's "before"
  const startedWith = learned.length ? learned[0].before : p.memory;
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/80 p-6 backdrop-blur" onClick={onClose}>
      <div className={`${PANEL} mx-auto max-w-5xl bg-[var(--card)] p-6`} onClick={(e) => e.stopPropagation()}>
        {/* who */}
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-4"><Avatar seed={p.avatar.seed} archetype={p.archetype} model={p.model} age={p.age} size={64} feeling={d?.feeling ?? "neutral"} />
            <div>
              <div className="flex flex-wrap items-center gap-2"><span className="font-serif text-[26px]">{p.name}</span>
                {od && <span className="rounded-full px-2.5 py-0.5 font-mono text-[11px] font-semibold uppercase text-black" style={{ background: color }}>{OUTCOME_LABEL[od]}</span>}</div>
              <div className="text-[13px] text-white/50">{p.kind === "agent" ? "AI shopping agent acting for a user" : `${p.age} · ${p.occupation} · ${p.archetype} · ${Math.round(p.share * 100)}% of customers`}
                {p.model ? ` · played by ${p.played_by ? `${p.played_by} (${p.model} unavailable)` : p.model}` : ""}</div>
            </div></div>
          <button onClick={onClose} className="text-[22px] text-white/50 hover:text-white" aria-label="close">×</button>
        </div>

        {/* why */}
        {d ? (
          <section className="mt-6 rounded-xl border-2 p-5" style={{ borderColor: color }}>
            <div className={H}>Why {p.name} {od === "bought" ? "bought" : od === "bought_unhappy" ? "bought but isn't happy" : od === "abandoned_cart" ? "left the cart" : od === "maybe" ? "said maybe later" : "didn't buy"}</div>
            <p className="mt-2 font-serif text-[20px] leading-snug">“{d.quote}”</p>
            {d.deciding_moment && (
              <p className="mt-3 text-[14px]"><span className="font-semibold" style={{ color }}>What made up their mind{d.deciding_step ? ` (step ${d.deciding_step})` : ""}: </span>{d.deciding_moment}</p>
            )}
            <p className="mt-2 text-[13px] text-white/60">
              {ordered ? `Placed the order at step ${ordered.n}${od === "bought_unhappy" ? `, then said “${d.decision}”` : ""}.`
                : carted ? `Added to cart at step ${carted.n} but didn't place the order${d.order_possible ? " (checkout needed no payment)" : ""}. Said “${d.decision}”.`
                : d.order_possible ? `Never added it to the cart. Said “${d.decision}”.` : `Said “${d.decision}”.`}
            </p>
            {d.reconsidered && (
              <p className="mt-2 text-[12px] text-white/45">First answer didn't match the visit ({d.reconsidered}), so they reconsidered.</p>
            )}
            <div className="mt-4 grid gap-3 sm:grid-cols-4">
              <Fact label="Rating" value={`${d.rating}/5`} sub={d.stars_after_use ? `${d.stars_after_use}/5 after using it` : `felt ${d.feeling}`} />
              <Fact label="How sure" value={d.confidence != null ? `${Math.round(d.confidence * 100)}%` : "–"} sub={d.confidence != null ? (d.confidence < 0.5 ? "unsure" : d.confidence < 0.75 ? "fairly sure" : "sure") : ""} />
              <Fact label="Would pay" value={d.would_pay || "–"} />
              <Fact label="Journey" value={`${steps.length} steps`} sub={`${pages} page${pages === 1 ? "" : "s"}${ordered ? ` · ordered at step ${ordered.n}` : carted ? ` · cart at step ${carted.n}` : ""}`} />
            </div>
            {d.reasons.length > 0 && <div className="mt-4"><div className="text-[13px] text-white/45">Because</div>
              <ul className="mt-1 space-y-1 text-[14px]">{d.reasons.map((r, i) => <li key={i}>· {r}</li>)}</ul></div>}
            {d.missing && <p className="mt-4 rounded-lg bg-white/[0.05] p-3 text-[14px]"><span className="text-white/45">What would have changed their mind: </span>{d.missing}</p>}
          </section>
        ) : <p className="mt-6 rounded-xl bg-white/[0.05] p-4 text-[14px] text-white/60">{p.name} hasn't decided yet: still browsing.</p>}

        {/* came in with */}
        <section className="mt-6 grid gap-4 md:grid-cols-2">
          <div className="rounded-xl bg-white/[0.04] p-4"><div className={H}>Came in wanting</div>
            <p className="mt-2 text-[14px]">“{p.goal}”</p><p className="mt-1 font-mono text-[12px] text-white/45">budget: {p.budget}</p>
            {d?.first_impression && <p className="mt-3 text-[14px]"><span className="text-white/45">First impression: </span>{d.first_impression}</p>}</div>
          <div className="rounded-xl bg-white/[0.04] p-4"><div className={H}>Memory they started with{d?.memory_version ? ` · v${d.memory_version}` : ""}</div>
            {startedWith ? <p className="mt-2 whitespace-pre-line text-[13px] text-white/75">{startedWith}</p> : <p className="mt-2 text-[13px] text-white/45">{p.kind === "agent" ? "None: AI agents start fresh every time." : "Nothing yet: first visit."}</p>}
            {p.inherited && <p className="mt-2 font-mono text-[11px]" style={{ color: C.win }}>includes lessons from customers like them on other sites</p>}</div>
        </section>

        {/* journey */}
        <section className="mt-8"><div className={H}>The journey, step by step</div>
          <ol className="mt-4 space-y-5">
            {steps.map((s, i) => {
              const prev = steps[i - 1];
              const turn = prev && Math.abs((MOOD[s.feeling] ?? 0) - (MOOD[prev.feeling] ?? 0)) >= 2;
              const deciding = !!d?.deciding_step && d.deciding_step === s.n;
              return (
                <li key={s.n} className={`grid gap-4 md:grid-cols-[360px_1fr] ${deciding ? "-mx-3 rounded-xl p-3" : ""}`} style={deciding ? { outline: `2px solid ${color}` } : undefined}>
                  {s.shot ? <img src={shot(sim.id, s.shot)} alt={`step ${s.n}`} className="w-full rounded-lg border border-white/10" /> : <div className="min-h-16 rounded-lg bg-white/5" />}
                  <div>
                    <div className="font-mono text-[11px] text-white/40">step {s.n} · {s.url.replace(/^https?:\/\//, "")}
                      {s.blocked && <span className="ml-2 rounded-full bg-white/10 px-2 py-0.5 text-white/60">blocked by a bot check · not a customer issue</span>}
                      {s.cart && <span className="ml-2 rounded-full px-2 py-0.5 font-semibold" style={{ background: `${C.win}33`, color: C.win }}>clicked “{s.target}”</span>}
                      {s.ordered && <span className="ml-2 rounded-full px-2 py-0.5 font-semibold text-black" style={{ background: C.win }}>order placed</span>}
                      {deciding && <span className="ml-2 rounded-full px-2 py-0.5 font-semibold text-black" style={{ background: color }}>made up their mind here</span>}
                      {turn && <span className="ml-2 rounded-full px-2 py-0.5 font-semibold" style={{ background: `${(MOOD[s.feeling] ?? 0) < (MOOD[prev.feeling] ?? 0) ? C.loss : C.win}33`, color: (MOOD[s.feeling] ?? 0) < (MOOD[prev.feeling] ?? 0) ? C.loss : C.win }}>turning point: {prev.feeling} → {s.feeling}</span>}</div>
                    <div className="mt-2 flex items-start gap-3"><Avatar seed={p.avatar.seed} archetype={p.archetype} model={p.model} age={p.age} size={40} feeling={s.feeling} /><p className="rounded-xl rounded-tl-none bg-white/[0.06] px-3 py-2 text-[14px] leading-snug">“{s.thought}”</p></div>
                    <div className="mt-2 font-mono text-[12px]" style={{ color: SHIRT[p.archetype] ?? C.brain }}>→ {s.action === "click" ? `clicked “${s.target}”` : s.action === "decide" ? "ready to decide" : s.action}  <span className="text-white/40">· felt {s.feeling}</span></div>
                  </div>
                </li>
              );
            })}
            {!steps.length && <li className="text-[13px] text-white/45">No steps recorded yet.</li>}
          </ol>
        </section>

        {/* review */}
        {d && (d.review || d.liked?.length || d.disliked?.length) && (
          <section className="mt-8"><div className={H}>{p.name}'s review</div>
            {d.review && <p className="mt-2 text-[15px] leading-relaxed text-white/85">{d.review}</p>}
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <List title="Liked" items={d.liked} color={C.win} /><List title="Disliked" items={d.disliked} color={C.loss} />
            </div>
          </section>
        )}

        {/* suggestions */}
        {d?.suggestions?.length ? (
          <section className="mt-8"><div className={H}>What {p.name} would change</div>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              {d.suggestions.map((sg, i) => (
                <div key={i} className="rounded-xl border border-white/10 p-4">
                  <span className="rounded-full px-2 py-0.5 font-mono text-[10px] font-semibold uppercase" style={{ background: `${sg.impact === "would make me buy" ? C.win : C.mid}26`, color: sg.impact === "would make me buy" ? C.win : C.mid }}>{sg.impact}</span>
                  <p className="mt-2 text-[14px] font-semibold">{sg.change}</p>
                  <p className="mt-1 text-[13px] text-white/65">{sg.why}</p>
                  {sg.where && <p className="mt-2 truncate font-mono text-[11px] text-white/40">on: {sg.where.replace(/^https?:\/\//, "")}</p>}
                </div>
              ))}
            </div>
          </section>
        ) : null}

        {/* learned */}
        {(learned.length > 0 || sim.memory[p.id]) && (
          <section className="mt-8 border-t border-white/10 pt-5"><div className={H} style={{ color: C.win }}>What {p.name} learned for next time</div>
            {learned.length ? (
              <ul className="mt-2 space-y-2 text-[14px]">{learned.map((c, i) => (
                <li key={i}>· {c.lesson} <span className="font-mono text-[11px] text-white/40">({c.source === "human" ? "from the owner" : "from this visit"}{"memory_version" in c ? `, memory v${(c as { memory_version?: number }).memory_version}` : ""})</span></li>))}</ul>
            ) : <p className="mt-2 whitespace-pre-line text-[14px] text-white/75">{sim.memory[p.id]}</p>}
          </section>
        )}
      </div>
    </div>
  );
}

function Fact({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg bg-white/[0.05] p-3">
      <div className="text-[11px] text-white/45">{label}</div>
      <div className={`mt-0.5 font-semibold leading-tight ${value.length > 24 ? "text-[13px]" : "text-[18px]"}`}>{value}</div>
      {sub && <div className="mt-0.5 text-[11px] text-white/45">{sub}</div>}
    </div>
  );
}

function List({ title, items, color }: { title: string; items?: string[]; color: string }) {
  if (!items?.length) return null;
  return (
    <div className="rounded-xl bg-white/[0.04] p-4">
      <div className="font-mono text-[11px] font-semibold uppercase" style={{ color }}>{title}</div>
      <ul className="mt-2 space-y-1 text-[14px] text-white/80">{items.map((x, i) => <li key={i}>· {x}</li>)}</ul>
    </div>
  );
}

const host = (u: string) => u.replace(/^https?:\/\//, "").replace(/\/.*$/, "");

export function SimView({ id }: { id: string }) {
  const [sim, setSim] = useState<Sim | null>(null);
  const [cast, setCast] = useState<Persona[] | null>(null);
  const [editing, setEditing] = useState<{ p: Persona; isNew: boolean } | null>(null);
  const [showWhy, setShowWhy] = useState(false);
  useEffect(() => { if (sim?.status === "awaiting_approval") window.scrollTo({ top: 0, behavior: "smooth" }); }, [sim?.status]);  // the live feed scrolled down
  const [models, setModels] = useState<string[]>([]);
  useEffect(() => { fetch("/api/models").then((r) => r.json()).then(setModels).catch(() => {}); }, []);
  const saveEdit = (p: Persona) => {
    setCast((c) => (c ?? []).some((x) => x.id === p.id) ? (c ?? []).map((x) => (x.id === p.id ? p : x)) : [...(c ?? []), p]);
    setEditing(null);
  };
  const [open, setOpen] = useState<Persona | null>(null);
  const openPersona = (p: Persona) => { location.hash = `#sim=${id}&p=${p.id}`; };
  const [fix, setFix] = useState("");
  const [tab, setTab] = useState("map");
  const [truth, setTruth] = useState("");
  const [change, setChange] = useState("");
  const [teaching, setTeaching] = useState(false);
  const [taught, setTaught] = useState<number | null>(null);
  const [demo, setDemo] = useState<SimExtras | null>(null);
  useEffect(() => { if (location.hash.includes("demo")) fetch("/api/fixtures/extras").then((r) => r.json()).then(setDemo).catch(() => {}); }, []);

  useEffect(() => {
    let alive = true;
    const tick = () => fetch(`/api/sims/${id}`).then((r) => r.json()).then((s: Sim) => { if (alive) { setSim(s); if (s.status === "awaiting_approval" && !cast) setCast(s.personas); } }).catch(() => {});
    tick();
    const building = !sim || ["casting", "briefing", "resuming"].includes(sim.status);  // stream the agent's reasoning smoothly
    const t = setInterval(() => { if (!sim || !["done", "error"].includes(sim.status)) tick(); }, building ? 600 : 1500);
    return () => { alive = false; clearInterval(t); };
  }, [id, sim?.status]); // eslint-disable-line

  if (!sim) return <div className="grid h-[60vh] place-items-center font-mono text-white/40">loading…</div>;

  async function recast() {
    await fetch(`/api/sims/${id}/recast`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ feedback: fix.trim() }) });
    setFix(""); setCast(null); setSim({ ...sim!, status: "casting" });
  }
  async function teach() {
    setTeaching(true);
    try {
      const r = await fetch(`/api/sims/${id}/teach`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ truth: truth.trim() }) });
      const { changes } = await r.json();
      setTaught(changes.length); setTruth("");
      setSim({ ...sim!, persona_changes: [...(sim!.persona_changes ?? []), ...changes] });
    } finally { setTeaching(false); }
  }
  async function rerun() {
    const r = await fetch(`/api/sims/${id}/rerun`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ change: change.trim() }) });
    if (r.ok) location.hash = `#sim=${(await r.json()).id}`;
  }

  async function approve() {
    await fetch(`/api/sims/${id}/approve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ personas: cast }) });
    setSim({ ...sim!, status: "browsing", personas: cast ?? sim!.personas });
  }

  const name = sim.input.name || host(sim.input.url);
  const humans = sim.personas.filter((p) => p.kind !== "agent");
  const bots = sim.personas.filter((p) => p.kind === "agent");
  const decided = humans.filter((p) => sim.decisions[p.id]).length;
  const buyers = humans.filter((p) => outcome(sim, p.id) === "bought").length;
  const botsDone = bots.filter((p) => sim.decisions[p.id]).length;
  const botsBought = bots.filter((p) => outcome(sim, p.id) === "bought").length;
  const live = ["browsing", "talking", "analyzing", "done"].includes(sim.status);
  const x = { ...demo, ...Object.fromEntries(Object.entries({ social: sim.social, evals: sim.evals, persona_changes: sim.persona_changes }).filter(([, v]) => v && (!Array.isArray(v) || v.length))) } as Partial<SimExtras>;
  const unconvinced = humans.filter((p) => sim.decisions[p.id] && outcome(sim, p.id) !== "bought" && sim.decisions[p.id].missing);

  return (
    <div className="mx-auto max-w-[1400px] px-6 pb-16">
      {/* one headline that always says what is happening */}
      <div className="pt-6 text-center">
        <div className="font-mono text-[12px] text-white/40">{sim.round ? <span className="mr-2 rounded-full px-2 py-0.5 font-semibold text-black" style={{ background: C.brain }}>round {sim.round + 1} · they remember round {sim.round}</span> : null}{host(sim.input.url)}{sim.input.context ? ` · ${sim.input.context}` : ""}{sim.input.world ? ` · ${sim.input.world}` : ""}</div>
        <h1 className="mt-2 font-serif text-[40px] leading-tight">
          {["casting", "briefing"].includes(sim.status) && <>Casting customers for {name}<span className="animate-pulse">…</span></>}
          {sim.status === "awaiting_approval" && <>Review your test panel</>}
          {sim.status === "browsing" && <>{decided + botsDone} of {sim.personas.length} have decided<span className="animate-pulse">…</span></>}
          {sim.status === "talking" && <><span style={{ color: buyers ? C.win : C.loss }}>{buyers} of {decided}</span> would buy · <span className="text-white/50">now they're posting about it<span className="animate-pulse">…</span></span></>}
          {sim.status === "analyzing" && <><span style={{ color: buyers ? C.win : C.loss }}>{buyers} of {decided}</span> would buy · <span className="text-white/50">writing up why<span className="animate-pulse">…</span></span></>}
          {sim.status === "done" && <><span style={{ color: buyers / Math.max(decided, 1) >= 0.5 ? C.win : buyers ? C.mid : C.loss }}>{buyers} of {decided}</span> customers would buy from {name}</>}
          {sim.status === "error" && <span style={{ color: C.loss }}>Something broke</span>}
        </h1>
        {bots.length > 0 && botsDone > 0 && ["talking", "analyzing", "done"].includes(sim.status) && (
          <div className="mt-2 text-[17px]">
            <span className="font-semibold" style={{ color: botsBought / botsDone >= 0.5 ? C.win : botsBought ? C.mid : C.loss }}>{botsBought} of {botsDone} AI shopping agents</span>
            <span className="text-white/60"> could complete the purchase for their user</span>
          </div>
        )}
        {sim.summary?.by_model && Object.keys(sim.summary.by_model).length > 1 && (
          <div className="mt-3 flex justify-center gap-2 font-mono text-[12px]">
            {Object.entries(sim.summary.by_model).map(([m, v]) => <span key={m} className="rounded-full border border-white/15 px-3 py-1 text-white/70">{m} customers: <b className="text-white">{v.bought}/{v.of}</b> bought</span>)}
          </div>
        )}
        {sim.error && <p className="mt-2 text-[13px]" style={{ color: C.loss }}>{sim.error}</p>}
        <Timeline url={sim.input.url} current={sim.id} />
      </div>

      {(["casting", "briefing"].includes(sim.status) || (sim.status === "resuming" && !sim.steps.some((x) => x.kind === "approved"))) && (
        <CastingLive events={sim.thinking ?? []} personas={sim.personas} director={!!sim.input.director} />
      )}

      {sim.status === "awaiting_approval" && cast && (
        <div className="mt-10 text-center">
          {!!sim.thinking?.length && (
            <div className="mx-auto mb-8 max-w-3xl text-left">
              <button onClick={() => setShowWhy(!showWhy)} className="flex w-full items-center justify-between rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-[14px] transition hover:border-white/25">
                <span><span className="font-semibold">How these customers were chosen</span><span className="ml-2 text-white/45">the agent's reasoning, step by step</span></span>
                <span className="font-mono text-[12px] text-white/50">{showWhy ? "hide" : "show"}</span>
              </button>
              {showWhy && <div className="rise mt-5"><ThinkingFeed events={sim.thinking} personas={sim.personas} follow={false} /></div>}
            </div>
          )}
          <div className="flex flex-wrap justify-center gap-6">
            {cast.filter((p) => p.kind !== "agent").map((p, i) => (
              <div key={p.id} className="rise group relative w-[164px]" style={{ animationDelay: `${i * 0.06}s` }}>
                <div className="absolute right-2 top-0 z-10 hidden gap-1 group-hover:flex">
                  <button onClick={() => setEditing({ p, isNew: false })} aria-label={`edit ${p.name}`} title="Edit"
                    className="grid h-7 w-7 place-items-center rounded-full border border-white/15 bg-[var(--card)] text-[12px] text-white/70 shadow transition hover:text-white">✎</button>
                  <button onClick={() => setCast(cast.filter((x) => x.id !== p.id))} aria-label={`remove ${p.name}`} title="Remove"
                    className="grid h-7 w-7 place-items-center rounded-full border border-white/15 bg-[var(--card)] text-[14px] text-white/70 shadow transition hover:border-[#ff3355] hover:bg-[#ff3355] hover:text-white">×</button>
                </div>
                <button onClick={() => setEditing({ p, isNew: false })} className="block w-full rounded-2xl px-2 pb-3 pt-1 transition hover:bg-white/[0.04]">
                  <div className="mx-auto w-fit rounded-full transition group-hover:scale-[1.03]" style={{ boxShadow: `0 0 0 3px ${SHIRT[p.archetype] ?? "#8a93b8"}` }}><Avatar seed={p.avatar.seed} archetype={p.archetype} model={p.model} age={p.age} size={96} /></div>
                  <div className="mt-3 text-[15px] font-semibold">{p.name}, {p.age}</div>
                  <div className="font-mono text-[11px]" style={{ color: SHIRT[p.archetype] }}>{p.archetype} · {Math.round(p.share * 100)}%</div>
                  <div className="mt-1 flex flex-wrap justify-center gap-1">
                    {p.model && <span className="rounded-full border border-white/15 px-2 py-0.5 font-mono text-[10px] text-white/60">played by {p.model}</span>}
                    {p.custom && <span className="rounded-full px-2 py-0.5 font-mono text-[10px] font-semibold" style={{ background: `${C.win}22`, color: C.win }}>{p.instructions ? "custom prompt" : "edited"}</span>}
                  </div>
                  {p.inherited && <div title={p.memory} className="mt-1 inline-block cursor-help rounded-full px-2 py-0.5 font-mono text-[10px] font-semibold text-black" style={{ background: C.brain }}>prior memory</div>}
                  <p className="mt-1 line-clamp-3 text-[12px] leading-snug text-white/50">{p.goal}</p>
                </button>
              </div>
            ))}
            <div className="rise w-[164px]" style={{ animationDelay: `${cast.length * 0.06}s` }}>
              <button onClick={() => setEditing({ p: blankPersona(), isNew: true })}
                className="group block w-full rounded-2xl px-2 pb-3 pt-1 transition hover:bg-white/[0.04]">
                <div className="mx-auto grid h-[96px] w-[96px] place-items-center rounded-full border-2 border-dashed border-white/20 text-[34px] font-light text-white/40 transition group-hover:border-[#3ff0d4] group-hover:text-[#3ff0d4]">+</div>
                <div className="mt-3 text-[15px] font-semibold text-white/80">Add customer</div>
                <div className="font-mono text-[11px] text-white/40">your own persona</div>
              </button>
            </div>
          </div>
          {cast.some((p) => p.kind === "agent") && (
            <div className="mx-auto mt-10 max-w-3xl">
              <div className="font-mono text-[11px] uppercase tracking-[0.25em] text-white/45">plus AI shopping agents, sent by a user</div>
              <p className="mt-1 text-[14px] text-white/70">{cast.find((p) => p.kind === "agent")!.goal}</p>
              <div className="mt-4 flex flex-wrap justify-center gap-6">
                {cast.filter((p) => p.kind === "agent").map((p) => (
                  <div key={p.id} className="group relative w-[120px]">
                    <button onClick={() => setCast(cast.filter((x) => x.id !== p.id))} className="absolute right-2 top-0 z-10 hidden h-6 w-6 place-items-center rounded-full bg-white/15 text-white/70 hover:bg-[#ff3355] hover:text-white group-hover:grid" aria-label={`remove ${p.name}`}>×</button>
                    <div className="mx-auto w-fit"><Avatar seed={p.avatar.seed} archetype={p.archetype} model={p.model} size={76} feeling="neutral" /></div>
                    <div className="mt-2 text-[14px] font-semibold">{p.name}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
          <button disabled={!cast.length} onClick={approve} className="mt-10 rounded-2xl px-10 py-4 text-[17px] font-semibold text-black disabled:opacity-40" style={{ background: C.win, boxShadow: `0 0 40px ${C.win}66` }}>Start the test →</button>
          <p className="mt-3 text-[12px] text-white/35">click anyone to edit their profile, model or persona prompt · shares rebalance to 100% when the test starts</p>
          <form onSubmit={(e) => { e.preventDefault(); if (fix.trim().length > 1) recast(); }} className="mx-auto mt-6 flex max-w-xl gap-2">
            <input value={fix} onChange={(e) => setFix(e.target.value)} placeholder="Anything off? e.g. my customers are older than that"
              className="min-w-0 flex-1 rounded-xl border border-white/15 bg-white/[0.04] px-4 py-2.5 text-[14px] outline-none focus:border-[#3ff0d4]" />
            <button className="rounded-xl border border-white/20 px-4 text-[14px] hover:border-white/50">Recast</button>
          </form>
          {editing && (
            <PersonaEditor key={editing.p.id} initial={editing.p} isNew={editing.isNew} models={models} simId={id}
              onSave={saveEdit} onClose={() => setEditing(null)}
              onRemove={() => { setCast(cast.filter((x) => x.id !== editing.p.id)); setEditing(null); }} />
          )}
        </div>
      )}

      {live && (
        <>
          {sim.status === "done" && <Bento sim={sim} buyers={buyers} decided={decided} botsBought={botsBought} botsDone={botsDone} goto={setTab} />}
          <Tabs tab={tab} setTab={setTab} items={[
            { id: "map", label: "Sessions", show: true },
            { id: "fixes", label: "Recommendations", show: !!sim.actions?.length },
            { id: "agents", label: "Agent checkout", show: sim.status === "done" && !!sim.summary?.agents?.length },
            { id: "lens", label: "Friction hotspots", show: sim.status === "done" },
            { id: "talk", label: "Word of mouth", show: !!x.social },
            { id: "director", label: "Director", show: !!sim.director?.length },
            { id: "voices", label: "Objections", show: sim.status === "done" && unconvinced.length > 0 },
            { id: "learned", label: "Panel memory", show: !!x.persona_changes?.length },
            { id: "accuracy", label: "Accuracy", show: !!x.evals?.length },
            { id: "next", label: "Re-test", show: sim.status === "done" },
            { id: "report", label: "Report", show: !!sim.report },
          ]} />
          {tab === "map" && <>
            <ThoughtStream sim={sim} onOpen={openPersona} />
            <SiteMap sim={sim} onOpen={openPersona} />
            <p className="mt-3 text-center text-[12px] text-white/35">click anyone to open their full profile: every step, the prompts behind it, their decision and suggestions</p>
          </>}
          {tab === "fixes" && sim.actions && sim.actions.length > 0 && <DoThese actions={sim.actions} />}
          {tab === "agents" && sim.summary?.agents && sim.summary.agents.length > 0 && <AgentsPanel sim={sim} />}

          {tab === "lens" && <Lens simId={sim.id} />}
          {tab === "director" && sim.director && <DirectorLog sim={sim} />}
          {tab === "talk" && x.social && <WordOfMouth social={x.social} personas={sim.personas} />}
          {tab === "accuracy" && x.evals && x.evals.length > 0 && <Accuracy evals={x.evals} />}
          {tab === "learned" && x.persona_changes && x.persona_changes.length > 0 && <Learned changes={x.persona_changes} personas={sim.personas} />}

          {tab === "voices" && sim.status === "done" && unconvinced.length > 0 && (
            <section className="mx-auto mt-10 max-w-6xl">
              <Eyebrow n="05" label="objections" color={C.mid} />
              <h2 className="text-center font-serif text-[30px]">What would have converted them</h2>
              <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {unconvinced.map((p, i) => { const d = sim.decisions[p.id]; return (
                  <div key={p.id} onClick={() => openPersona(p)} className={`${PANEL} rise relative cursor-pointer p-5 transition hover:-translate-y-0.5`} style={{ animationDelay: `${i * 0.06}s` }}>
                    <div className="flex items-center gap-3">
                      <div className="rounded-full" style={{ boxShadow: `0 0 0 3px ${SHIRT[p.archetype] ?? C.brain}` }}><Avatar seed={p.avatar.seed} archetype={p.archetype} model={p.model} age={p.age} size={56} feeling={d.feeling} /></div>
                      <div><div className="text-[16px] font-semibold">{p.name}{p.kind !== "agent" && `, ${p.age}`}</div>
                        <div className="font-mono text-[11px]" style={{ color: SHIRT[p.archetype] }}>{p.kind === "agent" ? `${p.model} agent` : p.archetype} · <span style={{ color: DEC_COLOR[d.decision] ?? C.mid }}>{d.decision}</span> · {"★".repeat(d.rating)}<span className="opacity-30">{"★".repeat(5 - d.rating)}</span></div></div>
                    </div>
                    <p className="mt-4 font-serif text-[18px] leading-snug">“{d.missing}”</p>
                  </div>
                ); })}
              </div>
            </section>
          )}

          {tab === "next" && sim.status === "done" && (
            <section className="relative mx-auto mt-10 max-w-6xl overflow-hidden rounded-[28px] p-8 text-left" style={{ background: `linear-gradient(135deg, ${C.brain}26, ${C.win}1f)`, border: `1px solid ${C.brain}55` }}>
              <Eyebrow n="06" label="iterate" color={C.brain} />
              <h2 className="text-center font-serif text-[30px]">Re-test</h2>
              <div className="mt-6 grid gap-5 md:grid-cols-2">
              <div className={`${PANEL} p-5 text-left`}>
                <div className="font-serif text-[22px]">Teach them what real customers do</div>
                <p className="mt-1 text-[13px] text-white/50">Real people beat our guesses. Tell them what actually happens and every persona it applies to updates its memory before the next round.</p>
                <form onSubmit={(e) => { e.preventDefault(); teach(); }} className="mt-3 flex gap-2">
                  <input value={truth} onChange={(e) => setTruth(e.target.value)} disabled={teaching} placeholder="e.g. most of our buyers are over 50 and call to order, nobody reads the science page"
                    className="min-w-0 flex-1 rounded-xl border border-white/15 bg-white/[0.04] px-4 py-2.5 text-[14px] outline-none focus:border-[#d16bff]" />
                  <button disabled={teaching || truth.trim().length < 3} className="rounded-xl px-4 text-[14px] font-semibold text-black disabled:opacity-40" style={{ background: C.brain }}>{teaching ? "Teaching…" : "Teach"}</button>
                </form>
                {taught != null && <p className="mt-2 text-[13px]" style={{ color: C.brain }}>{taught === 0 ? "That didn't change anyone's memory." : `${taught} persona${taught > 1 ? "s" : ""} updated their memory. See "What they learned" above.`}</p>}
              </div>
              <div className={`${PANEL} flex flex-col p-5 text-left`}>
                <div className="font-serif text-[22px]">Changed your site? Test it</div>
                <p className="mt-1 text-[13px] text-white/50">The same customers come back with their memory, so before and after is a fair comparison.</p>
                <input value={change} onChange={(e) => setChange(e.target.value)} placeholder="What did you change? e.g. added prices to the Nocturne page (optional)"
                  className="mt-3 w-full rounded-xl border border-white/15 bg-white/[0.04] px-4 py-2.5 text-[14px] outline-none focus:border-[#d16bff]" />
                <button onClick={rerun} className="mt-4 rounded-2xl px-6 py-3.5 text-[16px] font-semibold text-black" style={{ background: C.brain, boxShadow: `0 0 40px ${C.brain}66` }}>{change.trim() ? "Test the change →" : `Run round ${(sim.round ?? 0) + 2} →`}</button>
              </div>
              </div>
            </section>
          )}

          {tab === "report" && sim.report && (
            <div className="mt-8 text-center">
              {<article className={`${PANEL} report mx-auto mt-4 max-w-4xl p-8 text-left`} dangerouslySetInnerHTML={{ __html: marked.parse(sim.report, { async: false }) as string }} />}
            </div>
          )}
        </>
      )}
      {open && <Replay sim={sim} p={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

// ---------- the owner's to-do list ----------
const AUD: Record<string, string> = { people: "for people", "AI agents": "for AI agents", both: "for people + agents" };
function DoThese({ actions }: { actions: NonNullable<Sim["actions"]> }) {
  return (
    <section className="mx-auto mt-12 max-w-4xl">
      <Eyebrow n="02" label="prioritized by impact" color={C.win} />
      <h2 className="text-center font-serif text-[30px]">Recommendations</h2>
      <div className="mt-6 space-y-3">
        {actions.map((a, i) => (
          <div key={i} className={`${PANEL} rise flex gap-4 p-5`} style={{ animationDelay: `${i * 0.08}s` }}>
            <div className="grid h-10 w-10 shrink-0 place-items-center rounded-full font-mono text-[18px] font-bold text-black" style={{ background: i === 0 ? C.win : i === 1 ? C.mid : C.brain }}>{i + 1}</div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[17px] font-semibold">{a.fix}</span>
                <span className="rounded-full px-2 py-0.5 font-mono text-[10px] font-semibold text-black" style={{ background: a.audience === "AI agents" ? "#9aa4b8" : a.audience === "both" ? C.brain : C.win }}>{AUD[a.audience]}</span>
                <span className="rounded-full border border-white/15 px-2 py-0.5 font-mono text-[10px] text-white/60">{a.effort} fix</span>
              </div>
              <p className="mt-1 text-[14px] text-white/70">{a.why}</p>
              <p className="mt-1 font-mono text-[11px] text-white/40">wins back: {a.who.join(", ")}{a.page ? ` · on ${a.page}` : ""}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

// ---------- layer 1: can AI shopping agents buy here? ----------
function AgentsPanel({ sim }: { sim: Sim }) {
  const rows = sim.summary!.agents!;
  return (
    <section className="mx-auto mt-12 max-w-4xl">
      <Eyebrow n="03" label="agent readiness" color="#9aa4b8" />
      <h2 className="text-center font-serif text-[30px]">Can AI agents check out?</h2>
      <p className="mt-2 text-center text-[14px] text-white/55">Shoppers now send ChatGPT, Gemini and Claude to buy for them. Agents need facts: exact product, price, terms, a path to checkout.</p>
      <div className="mt-6 grid gap-3 md:grid-cols-3">
        {rows.map((r) => { const p = sim.personas.find((x) => x.id === r.persona)!; return (
          <div key={r.persona} onClick={() => { location.hash = `#sim=${sim.id}&p=${r.persona}`; }} className={`${PANEL} cursor-pointer p-4 transition hover:-translate-y-0.5`}>
            <div className="flex items-center gap-3">
              <Avatar seed={p.avatar.seed} archetype={p.archetype} model={p.model} size={48} feeling={sim.decisions[p.id]?.feeling ?? "neutral"} />
              <div><div className="text-[15px] font-semibold">{p.name}</div>
                <div className="font-mono text-[12px] font-semibold" style={{ color: r.bought ? C.win : C.loss }}>{r.bought ? "✓ could buy" : "✗ couldn't buy"}</div></div>
            </div>
            <p className="mt-3 text-[13px] text-white/75">“{r.quote}”</p>
            {!r.bought && r.missing && <p className="mt-2 text-[12px] text-white/50"><span className="text-white/70">Needed:</span> {r.missing}</p>}
          </div>
        ); })}
      </div>
    </section>
  );
}

function Eyebrow({ n, label, color }: { n: string; label: string; color: string }) {
  return (
    <div className="mb-2 flex items-center justify-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-[0.3em]" style={{ color }}>
      <span className="h-2 w-2 rounded-full" style={{ background: color }} data-n={n} />{label}
    </div>
  );
}
export { Eyebrow };

// ---------- the one-screen summary ----------
function Ring({ value, of, color, size = 132 }: { value: number; of: number; color: string; size?: number }) {
  const r = 52, c = 2 * Math.PI * r, f = of ? value / of : 0;
  return (
    <svg width={size} height={size} viewBox="0 0 120 120" className="shrink-0">
      <circle cx="60" cy="60" r={r} fill="none" stroke="currentColor" strokeOpacity=".1" strokeWidth="12" />
      <circle cx="60" cy="60" r={r} fill="none" stroke={color} strokeWidth="12" strokeLinecap="round" strokeDasharray={`${c * f} ${c}`} transform="rotate(-90 60 60)" className="ring-in" />
      <text x="60" y="58" textAnchor="middle" fontSize="30" fontWeight="800" fill={color} fontFamily="Inter, system-ui">{value}/{of}</text>
      <text x="60" y="78" textAnchor="middle" fontSize="11" fill="currentColor" opacity=".55" fontFamily="JetBrains Mono, monospace">{Math.round(f * 100)}%</text>
    </svg>
  );
}

function Kpi({ label, value, sub, color, onClick, delay = 0 }: { label: string; value: string; sub: string; color?: string; onClick?: () => void; delay?: number }) {
  return (
    <button onClick={onClick} className={`${PANEL} rise p-5 text-left transition hover:-translate-y-0.5`} style={{ animationDelay: `${delay}s` }}>
      <div className="text-[12px] font-medium text-white/55">{label}</div>
      <div className="mt-1 text-[34px] font-bold leading-none tracking-tight" style={{ color }}>{value}</div>
      <div className="mt-2 text-[12.5px] leading-snug text-white/55">{sub}</div>
    </button>
  );
}

function funnel(sim: Sim) {
  const people = sim.personas.filter((p) => p.kind !== "agent");
  const steps = (id: string) => sim.live[id] ?? [];
  const landed = people.filter((p) => steps(p.id).length > 0);
  const explored = landed.filter((p) => new Set(steps(p.id).map((x) => x.url.split("#")[0])).size > 1);
  const bought = landed.filter((p) => outcome(sim, p.id) === "bought");
  const acted = landed.filter((p) => steps(p.id).some((x) => x.cart) || outcome(sim, p.id) === "bought");
  const ordered = landed.filter((p) => steps(p.id).some((x) => x.ordered));
  const canOrder = landed.some((p) => sim.decisions[p.id]?.order_possible);
  return [
    { label: "Landed on the site", n: landed.length },
    { label: "Explored past the first page", n: explored.length },
    { label: "Added to cart (or clicked buy)", n: acted.length },
    ...(canOrder ? [{ label: "Placed the order", n: ordered.length }] : []),
    { label: canOrder ? "Converted (ordered and happy or not)" : "Converted (decided to buy)", n: bought.length },
  ];
}

function downloadReport(sim: Sim) {
  const name = sim.input.name || sim.input.url;
  const lines = [`# Customer test: ${name}`, `${sim.input.url} · test ${sim.id}${sim.input.context ? ` · change tested: ${sim.input.context}` : ""}`, ""];
  if (sim.actions?.length) {
    lines.push("## Recommendations", "");
    sim.actions.forEach((a, i) => lines.push(`${i + 1}. **${a.fix}** (${a.audience}, ${a.effort} effort). ${a.why} Wins back: ${a.who.join(", ")}.`));
    lines.push("");
  }
  lines.push("## Panel", "", "| Panelist | Type | Model | Decision | Rating | Would have converted them |", "|---|---|---|---|---|---|");
  for (const p of sim.personas) {
    const d = sim.decisions[p.id];
    if (d) lines.push(`| ${p.name} | ${p.kind === "agent" ? "AI agent" : p.archetype} | ${p.model ?? ""} | ${outcome(sim, p.id) === "bought" ? "bought" : d.decision} | ${d.rating}/5 | ${(d.missing || "").replace(/\|/g, "/")} |`);
  }
  if (sim.report) lines.push("", "## Analyst report", "", sim.report);
  lines.push("", "_Simulated customers, a fast first pass before testing with real people._");
  const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/markdown" }));
  const a = document.createElement("a");
  a.href = url; a.download = `customer-test-${(sim.input.name || "site").replace(/[^a-z0-9]+/gi, "-").toLowerCase()}-${sim.id}.md`; a.click();
  URL.revokeObjectURL(url);
}

function Bento({ sim, buyers, decided, botsBought, botsDone, goto }: { sim: Sim; buyers: number; decided: number; botsBought: number; botsDone: number; goto: (t: string) => void }) {
  const top = sim.social?.top_influencers?.[0];
  const star = top ? sim.personas.find((p) => p.id === top) : undefined;
  const spread = sim.social?.summary?.replace(/\*\*/g, "").split(/(?<=\.)\s/)[0];
  const tone = (v: number, n: number) => (n && v / n >= 0.5 ? C.win : v ? C.mid : C.loss);
  const pct = (v: number, n: number) => (n ? `${Math.round((v / n) * 100)}%` : "–");
  const f = funnel(sim);
  const sessions = Object.values(sim.live);
  const avgSteps = sessions.length ? (sessions.reduce((t, x) => t + x.length, 0) / sessions.length).toFixed(1) : "–";
  return (
    <div className="mx-auto mt-8 max-w-6xl">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-[13px] font-semibold text-white/60">Summary</div>
        <div className="flex gap-2">
          <a href={`/api/sims/${sim.id}/report.pdf`} className="rounded-lg px-3 py-1.5 text-[13px] font-semibold text-[#ffffff]" style={{ background: C.brain }}>Download PDF report</a>
          <button onClick={() => downloadReport(sim)} className="rounded-lg border border-white/15 px-3 py-1.5 text-[13px] font-semibold hover:border-white/40">Markdown</button>
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Kpi label="Simulated conversion" value={pct(buyers, decided)} sub={`${buyers} of ${decided} panelists bought`} color={tone(buyers, decided)} onClick={() => goto("map")} />
        <Kpi label="AI agent checkout" value={pct(botsBought, botsDone)} sub={`${botsBought} of ${botsDone} agents completed their user's errand`} color={tone(botsBought, botsDone)} onClick={() => goto("agents")} delay={0.05} />
        <Kpi label="Top blocker" value={sim.actions?.[0] ? `${sim.actions[0].who.length} hit it` : "–"} sub={sim.actions?.[0]?.fix ?? "Writing recommendations…"} color={C.loss} onClick={() => goto("fixes")} delay={0.1} />
        <Kpi label="Avg. steps per session" value={avgSteps} sub={`${sessions.length} sessions on the real site`} onClick={() => goto("map")} delay={0.15} />
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-[1.25fr_1fr]">
        <div className={`${PANEL} rise p-5`} style={{ animationDelay: ".2s" }}>
          <div className="text-[13px] font-semibold">Conversion funnel <span className="font-normal text-white/50">· people panel</span></div>
          <div className="mt-4 space-y-3">
            {f.map((s, i) => { const w = f[0].n ? (s.n / f[0].n) * 100 : 0; const drop = i ? f[i - 1].n - s.n : 0; return (
              <div key={s.label}>
                <div className="flex justify-between text-[12.5px]"><span className="text-white/70">{s.label}</span><span className="font-mono">{s.n}{i > 0 && drop > 0 && <span style={{ color: C.loss }}> · −{drop}</span>}</span></div>
                <div className="mt-1 h-3 w-full overflow-hidden rounded-full bg-white/[0.06]"><div className="h-full rounded-full transition-all duration-700" style={{ width: `${w}%`, background: i === f.length - 1 ? C.win : C.brain, opacity: 1 - i * 0.12 }} /></div>
              </div>
            ); })}
          </div>
        </div>
        <button onClick={() => goto("fixes")} className={`${PANEL} rise p-5 text-left transition hover:-translate-y-0.5`} style={{ animationDelay: ".25s" }}>
          <div className="text-[13px] font-semibold">Top recommendations</div>
          <ol className="mt-3 space-y-3">
            {(sim.actions ?? []).slice(0, 3).map((a, i) => (
              <li key={i} className="flex gap-3"><span className="grid h-6 w-6 shrink-0 place-items-center rounded-md font-mono text-[12px] font-bold text-white" style={{ background: C.brain }}>{i + 1}</span>
                <span className="text-[14px] leading-snug"><span className="font-semibold">{a.fix}</span><span className="ml-2 rounded px-1.5 py-0.5 font-mono text-[10px] text-white/60 ring-1 ring-white/15">{a.audience === "AI agents" ? "agents" : a.audience === "both" ? "both" : "people"} · {a.effort}</span></span></li>
            ))}
            {!sim.actions?.length && <li className="text-[14px] text-white/50">Writing recommendations…</li>}
          </ol>
        </button>
      </div>
      {spread && star && (
        <button onClick={() => goto("talk")} className={`${PANEL} rise mt-4 flex w-full items-center gap-4 p-4 text-left transition hover:-translate-y-0.5`} style={{ animationDelay: ".3s" }}>
          <Avatar seed={star.avatar.seed} archetype={star.archetype} model={star.model} age={star.age} size={44} feeling={sim.decisions[star.id]?.feeling ?? "neutral"} />
          <div><div className="text-[12px] font-medium" style={{ color: C.mid }}>Most-shared complaint · started by {star.name}</div>
            <p className="mt-0.5 text-[14px] leading-snug">{spread}</p></div>
        </button>
      )}
    </div>
  );
}

function Tabs({ tab, setTab, items }: { tab: string; setTab: (t: string) => void; items: { id: string; label: string; show: boolean }[] }) {
  return (
    <nav className="sticky top-2 z-30 mx-auto mt-8 flex w-fit max-w-full gap-1 overflow-x-auto rounded-full border border-white/15 bg-[var(--card)] p-1 shadow-xl panel">
      {items.filter((t) => t.show).map((t) => (
        <button key={t.id} onClick={() => setTab(t.id)} className={`whitespace-nowrap rounded-full px-4 py-2 text-[13px] font-semibold transition ${tab === t.id ? "text-white" : "text-white/60 hover:text-white"}`}
          style={tab === t.id ? { background: C.brain, color: "#fff" } : undefined}>{t.label}</button>
      ))}
    </nav>
  );
}

// Jayden's director agent (b2a/director.py): its live plan and the reason behind every decision it made.
function DirectorLog({ sim }: { sim: Sim }) {
  return (
    <section className="mx-auto mt-10 grid max-w-6xl gap-5 lg:grid-cols-[320px_1fr]">
      <div className={`${PANEL} h-fit p-5`}>
        <div className="text-[13px] font-semibold">The director's plan</div>
        <ol className="mt-3 space-y-2">
          {(sim.todos ?? []).map((t, i) => (
            <li key={i} className="flex gap-2 text-[13.5px]"><span className="mt-0.5 font-mono text-[12px]" style={{ color: t.status === "completed" ? C.win : t.status === "in_progress" ? C.mid : "rgba(127,127,127,.7)" }}>{t.status === "completed" ? "✓" : t.status === "in_progress" ? "●" : "○"}</span><span className={t.status === "completed" ? "text-white/55 line-through" : ""}>{t.content}</span></li>
          ))}
          {!sim.todos?.length && <li className="text-[13px] text-white/50">No plan recorded.</li>}
        </ol>
      </div>
      <div className={`${PANEL} p-5`}>
        <div className="text-[13px] font-semibold">Every decision, with its reason</div>
        <ol className="mt-3 space-y-3">
          {(sim.director ?? []).map((d, i) => (
            <li key={i} className="border-l-2 pl-3" style={{ borderColor: C.brain }}>
              <div className="font-mono text-[11px] text-white/45">{d.t} · {d.tool}</div>
              <div className="text-[14px]">{d.reason}</div>
              {d.result && <div className="mt-0.5 line-clamp-2 text-[12.5px] text-white/50">{d.result}</div>}
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
