// What the agent is doing while it builds the test panel: reading the product, reasoning about who buys it (streamed as
// it's written), writing each persona and why it's there, and in director mode the deep agent's plan, subagents and
// decisions. Fed by sim.thinking (b2a/sim.py think / think_more / think_done).
import { useEffect, useRef, useState } from "react";
import { Avatar, MODEL_GLOW, SHIRT } from "./Avatar";
import { C, LABEL, PANEL } from "./theme";
import type { Persona } from "./Simulate";

export interface ThinkEvent {
  t: string; kind: "step" | "reason" | "persona" | "plan" | "subagent" | "decision" | "owner"; title: string; text: string;
  status: "running" | "done" | "error"; facts?: Record<string, string>; persona_id?: string; memory?: string;
  todos?: { content: string; status: string }[]; answer?: string; result?: string;
}

const TINT: Record<ThinkEvent["kind"], string> = {
  step: C.win, reason: C.brain, persona: C.win, plan: C.mid, subagent: C.brain, decision: C.win, owner: C.mid,
};
const KIND_LABEL: Partial<Record<ThinkEvent["kind"], string>> = { reason: "thinking", plan: "plan", subagent: "subagent", decision: "decision", owner: "you" };

function Dot({ ev, color }: { ev: ThinkEvent; color: string }) {
  if (ev.status === "running")
    return <span className="grid h-7 w-7 place-items-center rounded-full border border-white/10 bg-[var(--card)]"><span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/15" style={{ borderTopColor: color }} /></span>;
  if (ev.status === "error")
    return <span className="on-brain grid h-7 w-7 place-items-center rounded-full text-[13px] font-bold text-black" style={{ background: C.loss }}>!</span>;
  return <span className="grid h-7 w-7 place-items-center rounded-full border text-[12px]" style={{ borderColor: `${color}66`, background: `${color}1a`, color }}>✓</span>;
}

function More({ text, n = 280 }: { text: string; n?: number }) {
  const [open, setOpen] = useState(false);
  if (text.length <= n) return <p className="whitespace-pre-wrap">{text}</p>;
  return (
    <p className="whitespace-pre-wrap">
      {open ? text : text.slice(0, n).trimEnd() + "…"}{" "}
      <button onClick={() => setOpen(!open)} className="font-mono text-[11px] text-white/45 underline decoration-white/20 hover:text-white">{open ? "less" : "more"}</button>
    </p>
  );
}

function Body({ ev, persona }: { ev: ThinkEvent; persona?: Persona }) {
  switch (ev.kind) {
    case "reason":
      return (
        <div className={`${PANEL} mt-2 px-5 py-4`} style={{ borderColor: `${C.brain}33` }}>
          <p className={`whitespace-pre-wrap text-[15px] leading-relaxed text-white/85 ${ev.status === "running" ? "caret" : ""}`}>
            {ev.text || (ev.status === "running" ? "" : "…")}
          </p>
        </div>
      );
    case "persona": {
      const color = SHIRT[persona?.archetype ?? ""] ?? "#8a93b8";
      return (
        <div className="rise mt-2 flex items-start gap-4 rounded-2xl border border-white/10 bg-white/[0.03] p-4">
          {persona && <div className="shrink-0 rounded-full" style={{ boxShadow: `0 0 0 2px ${color}` }}><Avatar seed={persona.avatar.seed} archetype={persona.archetype} model={persona.model} age={persona.age} size={52} feeling="interested" /></div>}
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-1.5">
              {persona && <span className="rounded-full px-2 py-0.5 font-mono text-[10px]" style={{ background: `${color}22`, color }}>{persona.archetype} · {Math.round(persona.share * 100)}%</span>}
              {persona?.model && <span className="rounded-full border border-white/15 px-2 py-0.5 font-mono text-[10px] text-white/60">played by <span style={{ color: MODEL_GLOW[persona.model] }}>{persona.model}</span></span>}
            </div>
            {persona && <p className="mt-1.5 text-[13px] text-white/55">{persona.occupation} · “{persona.goal}”</p>}
            {ev.text && <p className="mt-1.5 text-[14px] leading-snug text-white/85"><span className="text-white/45">Why: </span>{ev.text}</p>}
            {ev.memory && <p className="mt-1.5 font-mono text-[11px]" style={{ color: C.brain }}>{ev.memory}</p>}
          </div>
        </div>
      );
    }
    case "plan":
      return (
        <ul className="mt-2 space-y-1.5">
          {(ev.todos ?? []).map((t, i) => (
            <li key={i} className="flex items-start gap-2 text-[13px]">
              <span className="mt-[3px] h-3 w-3 shrink-0 rounded-[4px] border" style={{ borderColor: t.status === "completed" ? C.win : "rgba(127,127,127,.5)", background: t.status === "completed" ? C.win : t.status === "in_progress" ? `${C.mid}55` : "transparent" }} />
              <span className={t.status === "completed" ? "text-white/45 line-through" : t.status === "in_progress" ? "text-white" : "text-white/65"}>{t.content}</span>
            </li>
          ))}
        </ul>
      );
    case "subagent":
      return (
        <div className="mt-1 text-[13px] leading-relaxed text-white/65">
          <More text={ev.text} />
          {ev.answer && <div className={`${PANEL} mt-2 px-4 py-3 text-white/80`}><div className={`${LABEL} mb-1`}>answer</div><More text={ev.answer} n={420} /></div>}
        </div>
      );
    case "decision":
      return (
        <div className="mt-1 text-[14px] leading-relaxed text-white/80">
          <More text={ev.text} />
          {ev.result && <p className="mt-1 font-mono text-[11px] text-white/40">{ev.result.split("\n")[0].slice(0, 200)}</p>}
        </div>
      );
    default:
      return (
        <div className="mt-1 text-[13px] leading-relaxed text-white/60">
          {ev.text && <More text={ev.text} />}
          {ev.facts && (
            <dl className="mt-2 grid grid-cols-[110px_1fr] gap-x-4 gap-y-1.5">
              {Object.entries(ev.facts).filter(([, v]) => v).map(([k, v]) => (
                <div key={k} className="contents"><dt className="font-mono text-[11px] uppercase tracking-wider text-white/40">{k}</dt><dd className="text-white/80"><More text={v} n={200} /></dd></div>
              ))}
            </dl>
          )}
        </div>
      );
  }
}

export function ThinkingFeed({ events, personas, follow = true }: { events: ThinkEvent[]; personas: Persona[]; follow?: boolean }) {
  const end = useRef<HTMLDivElement>(null);
  const last = events[events.length - 1];
  useEffect(() => {
    if (!follow || !end.current) return;
    const r = end.current.getBoundingClientRect();
    if (r.top < window.innerHeight + 400) end.current.scrollIntoView({ behavior: "smooth", block: "end" });  // only when you're near the bottom
  }, [events.length, last?.text?.length, follow]);
  return (
    <ol className="relative">
      <span className="absolute bottom-3 left-[13px] top-3 w-px bg-white/10" aria-hidden />
      {events.map((ev, i) => {
        const persona = ev.persona_id ? personas.find((p) => p.id === ev.persona_id) : undefined;
        const color = ev.kind === "persona" ? SHIRT[persona?.archetype ?? ""] ?? C.win : TINT[ev.kind];
        return (
          <li key={i} className="rise relative flex gap-4 pb-5 last:pb-0">
            <div className="relative z-[1] shrink-0"><Dot ev={ev} color={color} /></div>
            <div className="min-w-0 flex-1 pt-[3px]">
              <div className="flex items-baseline gap-2">
                <span className="text-[14px] font-semibold">{ev.kind === "subagent" ? <>Asked the <span style={{ color }}>{ev.title}</span> subagent</> : ev.title}</span>
                {KIND_LABEL[ev.kind] && <span className="rounded-full px-1.5 py-px font-mono text-[9px] uppercase tracking-wider" style={{ background: `${color}1f`, color }}>{KIND_LABEL[ev.kind]}</span>}
                <span className="ml-auto font-mono text-[11px] text-white/30">{ev.t}</span>
              </div>
              <Body ev={ev} persona={persona} />
            </div>
          </li>
        );
      })}
      <div ref={end} />
    </ol>
  );
}

export function CastingLive({ events, personas, director }: { events: ThinkEvent[]; personas: Persona[]; director?: boolean }) {
  return (
    <div className="mx-auto mt-10 max-w-3xl text-left">
      <div className="mb-6 flex items-center gap-3">
        <span className="relative flex h-2.5 w-2.5"><span className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-60" style={{ background: C.brain }} /><span className="relative inline-flex h-2.5 w-2.5 rounded-full" style={{ background: C.brain }} /></span>
        <span className={LABEL}>{director ? "The director agent is building your test panel" : "Building your test panel"}</span>
      </div>
      {events.length ? <ThinkingFeed events={events} personas={personas} /> : (
        <div className="flex items-center gap-3 text-[14px] text-white/50"><span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/15" style={{ borderTopColor: C.brain }} />Starting…</div>
      )}
    </div>
  );
}
