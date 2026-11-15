// One customer, all the way down: who they are and the prompt that created them, every step they took (screenshot,
// thought, the exact prompt), their decision and review, their suggestions, what they posted and what they learned.
import { useEffect, useState } from "react";
import { pretty, isOwnPage } from "./pretty";
import { Avatar, SHIRT, type Feeling } from "./Avatar";
import { C, PANEL } from "./theme";
import type { Persona } from "./Simulate";
import { OUTCOME_LABEL, outcomeColor, type Outcome } from "./SiteMap";

interface Step { n: number; url: string; title?: string; shot: string | null; blocked?: boolean; cart?: boolean; ordered?: boolean; point?: [number, number]; clicked?: string; thought: string; feeling: Feeling; action: string; target: string }
interface Suggestion { change: string; why: string; where: string; impact: string }
interface Decision {
  decision: string; rating: number; feeling: Feeling; confidence?: number; quote: string; reasons: string[]; missing: string; stars_after_use?: number | null;
  first_impression?: string; review?: string; liked?: string[]; disliked?: string[]; would_pay?: string; suggestions?: Suggestion[];
  // how the decision was reached (newer tests): the step that settled it, and a note if a contradictory first answer was reconsidered
  deciding_moment?: string; deciding_step?: number; reconsidered?: string; ordered_step?: number; order_possible?: boolean;
}
interface Box { box_2d: number[]; label: string; issue: string; fix: string; severity: number }
interface Detail {
  persona: Persona & { segment?: string; share?: number; goal?: string; budget?: string; voice?: string; occupation?: string; played_by?: string; model_note?: string; memory?: string; inherited?: boolean };
  persona_file: string; cast_prompt: string; prompts_rebuilt: boolean; persona_prompt: string; step_prompts: { n: number; prompt: string; with_screenshot: boolean }[];
  decide_prompt: string; steps: Step[]; decision: Decision | null; outcome: Outcome | null; fallbacks: number; fallback_reason: string;
  posts: { id: string; round: number; kind: string; target: string | null; text: string; sentiment: number }[];
  changes: { iteration: number; lesson: string; before: string; after: string; source?: string }[];
  lens: { step: number; boxes: Box[]; why: string }[];
  sim: { id: string; url: string; name: string | null; status: string };
}

const q = (t?: string) => (t ?? "").trim().replace(/^["“”']+|["“”']+$/g, "");
// how their mood moved: a swing of 2+ between steps is a turning point
const MOOD: Record<string, number> = { delighted: 2, interested: 1, neutral: 0, confused: -1, skeptical: -1, annoyed: -2 };
const WHY: Record<Outcome, string> = { bought: "bought", bought_unhappy: "bought but isn't happy", abandoned_cart: "left the cart", maybe: "said maybe later", left: "didn't buy" };
const sev = (s: number) => (s >= 2.5 ? C.loss : s >= 1.5 ? C.mid : C.brain);

function Code({ title, text, note }: { title: string; text: string; note?: string }) {
  const [open, setOpen] = useState(false);
  if (!text) return null;
  return (
    <div className={`${PANEL} overflow-hidden`}>
      <button onClick={() => setOpen(!open)} className="flex w-full items-center justify-between px-4 py-3 text-left">
        <span className="text-[14px] font-semibold">{title}{note && <span className="ml-2 font-mono text-[11px] font-normal text-white/45">{note}</span>}</span>
        <span className="font-mono text-[12px] text-white/50">{open ? "hide" : "show"} · {text.length.toLocaleString()} chars</span>
      </button>
      {open && <pre className="max-h-[480px] overflow-auto whitespace-pre-wrap border-t border-white/10 bg-black/20 p-4 font-mono text-[12px] leading-relaxed text-white/80">{text}</pre>}
    </div>
  );
}

export function PersonaPage({ simId, pid }: { simId: string; pid: string }) {
  const [d, setD] = useState<Detail | null>(null);
  const [err, setErr] = useState("");
  const [tab, setTab] = useState("decision");
  useEffect(() => {
    fetch(`/api/sims/${simId}/persona/${pid}`).then(async (r) => { if (r.ok) setD(await r.json()); else setErr((await r.json().catch(() => ({}))).detail ?? "Couldn't load this customer."); }).catch(() => setErr("Couldn't load this customer."));
  }, [simId, pid]);
  if (err) return <div className="p-10 text-white/60">{err}</div>;
  if (!d) return <div className="grid h-[60vh] place-items-center font-mono text-white/40">loading…</div>;
  const p = d.persona, dec = d.decision;
  const agent = p.kind === "agent";
  const oc = d.outcome;
  const bought = oc === "bought" || oc === "bought_unhappy";
  const label = oc ? OUTCOME_LABEL[oc] : "No decision";
  const color = oc ? outcomeColor(oc) : "#888";
  const ordered = d.steps.find((s) => s.ordered), carted = d.steps.find((s) => s.cart);
  const did = !dec ? "" : ordered ? `Placed the order at step ${ordered.n}${oc === "bought_unhappy" ? `, then said “${dec.decision}”` : ""}.`
    : carted ? `Added to cart at step ${carted.n} but didn't place the order${dec.order_possible ? " (checkout needed no payment)" : ""}. Said “${dec.decision}”.`
    : dec.order_possible ? `Never added it to the cart. Said “${dec.decision}”.` : `Said “${dec.decision}”.`;
  // the memory they really started with: once the run ends p.memory holds the new lessons, so use the first change's "before"
  const memoryIn = d.changes.length ? d.changes[0].before : p.memory;
  const goStep = (n: number) => { setTab("journey"); setTimeout(() => document.getElementById(`step-${n}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 60); };
  const lensFor = (n: number) => d.lens.find((l) => l.step === n)?.boxes ?? [];
  const promptFor = (n: number) => d.step_prompts.find((x) => x.n === n);
  const tabs = [["decision", "Decision"], ["journey", `Journey · ${d.steps.length} steps`], ["prompts", "Prompts"], ["learning", "Learning"], ["posts", `Posts · ${d.posts.length}`]];

  return (
    <div className="mx-auto max-w-6xl px-8 py-8">
      <a href={`#sim=${simId}`} className="text-[13px] text-white/55 hover:text-white">← Back to the test of {d.sim.name || d.sim.url}</a>

      {/* hero */}
      <div className={`${PANEL} mt-4 flex flex-wrap items-center gap-6 p-6`}>
        <div className="rounded-full" style={{ boxShadow: `0 0 0 4px ${SHIRT[p.archetype] ?? C.brain}` }}><Avatar seed={p.avatar.seed} archetype={p.archetype} model={p.model} age={p.age} size={112} feeling={dec?.feeling ?? "neutral"} /></div>
        <div className="min-w-0 flex-1">
          <div className="text-[12px] font-semibold uppercase tracking-wider" style={{ color: SHIRT[p.archetype] ?? C.brain }}>{agent ? "AI shopping agent" : p.archetype}{p.segment && !agent ? ` · ${p.segment}` : ""}</div>
          <h1 className="mt-1 text-[32px] font-bold tracking-tight">{p.name}{!agent && `, ${p.age}`}</h1>
          <div className="text-[14px] text-white/60">{agent ? `Acting for a user · ${p.goal}` : p.occupation}{!agent && p.share != null && ` · ${Math.round(p.share * 100)}% of customers`}</div>
          <div className="mt-2 flex flex-wrap gap-2 text-[12px]">
            <span className="rounded-full border border-white/15 px-2.5 py-0.5">played by {p.played_by ? `${p.played_by} (${p.model} unavailable)` : p.model}</span>
            {p.inherited && <span className="on-brain rounded-full px-2.5 py-0.5 font-semibold text-[#ffffff]" style={{ background: C.brain }}>carries memory from other businesses</span>}
            {d.fallbacks > 0 && <span className="rounded-full border px-2.5 py-0.5" style={{ borderColor: C.mid, color: C.mid }} title={d.fallback_reason}>Claude stood in for {d.fallbacks} step(s)</span>}
          </div>
        </div>
        {dec && (
          <div className="text-right">
            <div className="text-[26px] font-bold capitalize" style={{ color }}>{label}</div>
            <div className="text-[14px] text-white/70">{"★".repeat(dec.rating)}<span className="opacity-30">{"★".repeat(5 - dec.rating)}</span> on the page{dec.stars_after_use ? ` · ${dec.stars_after_use}★ after use` : ""}</div>
            {dec.confidence != null && <div className="text-[12px] text-white/50">confidence {Math.round(dec.confidence * 100)}%</div>}
          </div>
        )}
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[280px_1fr]">
        {/* profile */}
        <aside className={`${PANEL} h-fit space-y-4 p-5 text-[13.5px] lg:sticky lg:top-4`}>
          {[["Goal", p.goal], ["Budget", p.budget], ["How they think", agent ? "Literal and logical: needs the exact product, full price, terms and a path to buy. Marketing doesn't move it." : p.voice]].map(([k, v]) => v && (
            <div key={k}><div className="text-[11px] font-semibold uppercase tracking-wider text-white/45">{k}</div><div className="mt-0.5 text-white/85">{v}</div></div>
          ))}
          <div><div className="text-[11px] font-semibold uppercase tracking-wider text-white/45">Memory going in</div><div className="mt-0.5 whitespace-pre-wrap text-white/70">{memoryIn || (agent ? "None: AI agents start fresh every time." : "Nothing yet. First visit to this kind of product.")}</div></div>
        </aside>

        <div className="min-w-0">
          <nav className="flex flex-wrap gap-1 rounded-xl border border-white/10 p-1">
            {tabs.map(([id, l]) => <button key={id} onClick={() => setTab(id)} className={`rounded-lg px-3.5 py-1.5 text-[13px] font-semibold ${tab === id ? "text-[#ffffff]" : "text-white/60 hover:text-white"}`} style={tab === id ? { background: C.brain } : undefined}>{l}</button>)}
          </nav>

          {tab === "decision" && dec && (
            <div className="mt-5 space-y-4">
              <div className="rounded-2xl border-2 p-5" style={{ borderColor: color }}>
                <div className="text-[12px] font-semibold uppercase tracking-wider" style={{ color }}>Why {p.name} {oc ? WHY[oc] : "decided this"}</div>
                {dec.deciding_moment && (
                  <p className="mt-2 text-[16px] leading-snug">{dec.deciding_moment}
                    {!!dec.deciding_step && <button onClick={() => goStep(dec.deciding_step!)} className="ml-2 whitespace-nowrap rounded-full border px-2 py-0.5 align-middle font-mono text-[11px] hover:bg-white/10" style={{ borderColor: color, color }}>step {dec.deciding_step} →</button>}</p>
                )}
                <p className="mt-2 text-[13.5px] text-white/65">{did}</p>
                {dec.reasons?.length > 0 && <ul className="mt-3 space-y-1 text-[14px]">{dec.reasons.map((r, i) => <li key={i}>· {r}</li>)}</ul>}
                {dec.reconsidered && <p className="mt-3 text-[12px] text-white/45">Their first answer didn't match the visit ({dec.reconsidered}), so they reconsidered.</p>}
              </div>
              {dec.first_impression && <div className={`${PANEL} p-5`}><div className="text-[12px] font-semibold text-white/50">First impression</div><p className="mt-1 text-[16px]">“{q(dec.first_impression)}”</p></div>}
              <div className={`${PANEL} p-5`}>
                <div className="text-[12px] font-semibold text-white/50">What they'd tell a friend</div>
                <p className="mt-1 font-serif text-[20px] leading-snug">“{q(dec.quote)}”</p>
                {dec.review && <p className="mt-3 text-[14px] leading-relaxed text-white/75">{dec.review}</p>}
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div className={`${PANEL} p-5`}><div className="text-[12px] font-semibold" style={{ color: C.win }}>Liked</div><ul className="mt-2 space-y-1.5 text-[14px]">{(dec.liked?.length ? dec.liked : bought ? dec.reasons : []).map((x, i) => <li key={i}>+ {x}</li>)}{!dec.liked?.length && !bought && <li className="text-white/45">Nothing stood out.</li>}</ul></div>
                <div className={`${PANEL} p-5`}><div className="text-[12px] font-semibold" style={{ color: C.loss }}>Disliked</div><ul className="mt-2 space-y-1.5 text-[14px]">{(dec.disliked?.length ? dec.disliked : !bought ? dec.reasons : []).map((x, i) => <li key={i}>− {x}</li>)}</ul></div>
              </div>
              {(dec.missing || dec.would_pay) && (
                <div className={`${PANEL} p-5`}>
                  {dec.missing && <><div className="text-[12px] font-semibold text-white/50">What would have changed their mind</div><p className="mt-1 text-[15px]">{dec.missing}</p></>}
                  {dec.would_pay && <p className="mt-3 text-[14px]"><span className="font-semibold">Would pay:</span> {dec.would_pay}</p>}
                </div>
              )}
              {dec.suggestions && dec.suggestions.length > 0 && (
                <div className={`${PANEL} p-5`}>
                  <div className="text-[13px] font-semibold">How they'd improve the product</div>
                  <ol className="mt-3 space-y-3">
                    {dec.suggestions.map((s, i) => (
                      <li key={i} className="flex gap-3"><span className="grid h-6 w-6 shrink-0 place-items-center rounded-md text-[12px] font-bold text-[#ffffff]" style={{ background: s.impact === "would make me buy" ? C.win : C.brain }}>{i + 1}</span>
                        <div><div className="text-[14.5px] font-semibold">{pretty(s.change)} <span className="ml-1 rounded border border-white/15 px-1.5 text-[10.5px] font-normal text-white/60">{s.impact}</span></div>
                          <div className="break-words text-[13px] text-white/65">{pretty(s.why)}{s.where && <span className="text-white/45"> · {pretty(s.where)}</span>}</div></div></li>
                    ))}
                  </ol>
                </div>
              )}
            </div>
          )}

          {tab === "journey" && (
            <ol className="mt-5 space-y-5">
              {d.steps.map((s, i) => {
                const boxes = lensFor(s.n), pr = promptFor(s.n), prev = d.steps[i - 1];
                const swing = prev ? (MOOD[s.feeling] ?? 0) - (MOOD[prev.feeling] ?? 0) : 0;
                const deciding = !!dec?.deciding_step && dec.deciding_step === s.n;
                return (
                <li key={s.n} id={`step-${s.n}`} className={`${PANEL} grid gap-4 p-4 md:grid-cols-[360px_1fr]`} style={deciding ? { outline: `2px solid ${color}` } : undefined}>
                  <div className="relative overflow-hidden rounded-lg border border-white/10">
                    {s.shot ? <img src={`/api/shots/${simId}/shots/${s.shot}`} alt="" className="block w-full" /> : <div className="aspect-[16/10] bg-white/5" />}
                    {boxes.map((b, k) => { const [y0, x0, y1, x1] = b.box_2d; return <div key={k} className="absolute rounded" title={`${b.label}: ${b.issue}`} style={{ top: `${y0 / 10}%`, left: `${x0 / 10}%`, height: `${(y1 - y0) / 10}%`, width: `${(x1 - x0) / 10}%`, border: `3px solid ${sev(b.severity)}` }} />; })}
                    {s.point && <div className="pointer-events-none absolute h-5 w-5 -translate-x-1/2 -translate-y-1/2 rounded-full" title={`clicked here: ${s.target || s.clicked || ""}`} style={{ top: `${s.point[1] / 10}%`, left: `${s.point[0] / 10}%`, border: `3px solid ${C.brain}`, boxShadow: "0 0 0 2px rgba(0,0,0,.6)" }} />}
                  </div>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2 font-mono text-[11px] text-white/50">
                      <span>step {s.n}</span><span className="truncate">{isOwnPage(s.url) ? "the product page" : s.url.replace(/^https?:\/\//, "")}</span>
                      {s.blocked && <span className="rounded-full bg-white/10 px-2 text-white/70">bot check · not counted</span>}
                      {s.cart && <span className="rounded-full px-2 font-semibold" style={{ background: `${C.win}33`, color: C.win }}>clicked “{s.target}”</span>}
                      {s.ordered && <span className="on-brain rounded-full px-2 font-semibold text-black" style={{ background: C.win }}>order placed</span>}
                      {Math.abs(swing) >= 2 && <span className="rounded-full px-2 font-semibold" style={{ background: `${swing < 0 ? C.loss : C.win}33`, color: swing < 0 ? C.loss : C.win }}>turning point: {prev.feeling} → {s.feeling}</span>}
                      {deciding && <span className="rounded-full px-2 font-semibold text-black" style={{ background: color }}>made up their mind here</span>}
                    </div>
                    <div className="mt-2 flex items-start gap-2">
                      <div className="shrink-0"><Avatar seed={p.avatar.seed} archetype={p.archetype} model={p.model} age={p.age} size={36} feeling={s.feeling} /></div>
                      <p className="rounded-xl rounded-tl-none bg-white/[0.06] px-3 py-2 text-[14.5px] leading-snug">“{q(s.thought)}”</p>
                    </div>
                    <div className="mt-2 text-[13px]"><span className="font-semibold" style={{ color: C.brain }}>→ {s.action === "click" ? `clicked “${s.target}”` : s.action === "click_at" ? `clicked “${s.target || s.clicked || "a spot"}” on the screen` : s.action === "decide" ? "ready to decide" : s.action}</span> <span className="text-white/45">· felt {s.feeling}</span></div>
                    {boxes.map((b, k) => <div key={k} className="mt-2 rounded-lg border-l-4 bg-white/[0.03] px-3 py-1.5 text-[12.5px]" style={{ borderColor: sev(b.severity) }}><b>{b.label}:</b> {b.issue} <span className="text-white/60">Fix: {b.fix}</span></div>)}
                    {pr && <details className="mt-3"><summary className="cursor-pointer font-mono text-[11.5px] text-white/50 hover:text-white">the exact prompt at this step{pr.with_screenshot ? " (+ screenshot)" : ""}</summary><pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-black/25 p-3 font-mono text-[11.5px] text-white/75">{pr.prompt}</pre></details>}
                  </div>
                </li>
              ); })}
              {!d.steps.length && <p className="text-white/50">No steps recorded.</p>}
            </ol>
          )}

          {tab === "prompts" && (
            <div className="mt-5 space-y-3">
              {d.prompts_rebuilt && <p className="text-[12.5px] text-white/50">This test ran before exact prompts were saved, so these are rebuilt from the same templates and this customer's data.</p>}
              <Code title="1. Casting: how this panel was created" text={d.cast_prompt} note="one prompt casts the whole panel" />
              <Code title="2. Who they are: the persona prompt" text={d.persona_prompt} note={d.prompts_rebuilt ? "rebuilt" : "step 1, as sent"} />
              {d.step_prompts.length > 0 && d.step_prompts.slice(1).map((x) => <Code key={x.n} title={`Step ${x.n} prompt`} text={x.prompt} note={x.with_screenshot ? "+ screenshot" : ""} />)}
              <Code title="3. The decision prompt" text={d.decide_prompt} note={d.prompts_rebuilt ? "rebuilt" : "as sent"} />
              <Code title="4. Their persona file (Deep Agents filesystem)" text={d.persona_file} note={`personas/${p.id}.md`} />
            </div>
          )}

          {tab === "learning" && (
            <div className="mt-5 space-y-3">
              {d.changes.map((c, i) => (
                <div key={i} className={`${PANEL} p-5`}>
                  <div className="text-[12px] font-semibold" style={{ color: C.brain }}>round {c.iteration}{c.source === "human" ? " · from real people" : " · from their own visit"}</div>
                  <p className="mt-1 text-[15px]">{c.lesson}</p>
                  <div className="mt-3 grid gap-2 font-mono text-[12px] md:grid-cols-2">
                    <pre className="whitespace-pre-wrap rounded-lg bg-white/[0.03] p-3 text-white/50">{c.before || "(nothing yet)"}</pre>
                    <pre className="whitespace-pre-wrap rounded-lg p-3" style={{ background: `${C.win}14`, color: C.win }}>{c.after}</pre>
                  </div>
                </div>
              ))}
              {!d.changes.length && <p className="text-white/50">No learning recorded yet for this customer in this test.</p>}
            </div>
          )}

          {tab === "posts" && (
            <div className="mt-5 space-y-3">
              {d.posts.map((x) => (
                <div key={x.id} className={`${PANEL} flex gap-3 p-4`}>
                  <div className="shrink-0"><Avatar seed={p.avatar.seed} archetype={p.archetype} model={p.model} age={p.age} size={36} feeling={x.sentiment > 0.15 ? "interested" : x.sentiment < -0.15 ? "annoyed" : "neutral"} /></div>
                  <div><div className="font-mono text-[11px] text-white/45">round {x.round} · {x.kind}{x.target ? ` → ${x.target}` : ""}</div><p className="text-[14.5px]">{x.text}</p></div>
                </div>
              ))}
              {!d.posts.length && <p className="text-white/50">{agent ? "AI shopping agents don't post." : "They didn't post."}</p>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
