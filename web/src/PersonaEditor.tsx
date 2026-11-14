// Edit a customer before the test, or add your own: who they are, which model plays them, how much of the customer
// base they stand for, and a persona prompt that goes into every prompt that plays them.
import { useEffect, useRef, useState } from "react";
import { Avatar, MODEL_GLOW, SHIRT } from "./Avatar";
import { C, LABEL } from "./theme";
import type { Persona } from "./Simulate";

const TYPES = ["price-sensitive", "quality-first", "brand-loyal", "function-first", "first-time user", "skeptic", "enthusiast"];
const FIELD = "w-full rounded-xl border border-white/10 bg-white/[0.04] px-3.5 py-2.5 text-[14px] outline-none transition placeholder:text-white/30 focus:border-[#3ff0d4] focus:bg-white/[0.06]";

export function blankPersona(): Persona {
  return { id: `new-${Date.now().toString(36)}`, name: "", age: 30, occupation: "", archetype: "first-time user", segment: "", share: 0.15,
    goal: "", budget: "", voice: "", instructions: "", avatar: { seed: Math.floor(Math.random() * 10000) }, model: "", custom: true };
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-white/10 px-7 py-6">
      <div className="flex items-baseline justify-between gap-4">
        <h3 className={LABEL}>{title}</h3>
        {hint && <span className="text-right text-[12px] text-white/40">{hint}</span>}
      </div>
      <div className="mt-4 space-y-3">{children}</div>
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[12px] font-medium text-white/55">{label}</span>
      {children}
    </label>
  );
}

export function PersonaEditor({ initial, isNew, models, simId, onSave, onRemove, onClose }: {
  initial: Persona; isNew: boolean; models: string[]; simId: string;
  onSave: (p: Persona) => void; onRemove?: () => void; onClose: () => void;
}) {
  const [p, setP] = useState<Persona>(initial);
  const [brief, setBrief] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const first = useRef<HTMLInputElement>(null);
  const set = <K extends keyof Persona>(k: K, v: Persona[K]) => setP((x) => ({ ...x, [k]: v }));
  const color = SHIRT[p.archetype] ?? "#8a93b8";
  const valid = p.name.trim().length > 0 && p.goal.trim().length > 0;

  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    if (!isNew) first.current?.focus();
    return () => window.removeEventListener("keydown", esc);
  }, [isNew, onClose]);

  async function draft() {
    if (brief.trim().length < 3) return;
    setDrafting(true); setErr(null);
    try {
      const r = await fetch("/api/personas/draft", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: brief.trim(), sim_id: simId }) });
      if (!r.ok) throw new Error((await r.json()).detail ?? "Couldn't draft that customer.");
      const d = await r.json();
      setP((x) => ({ ...x, ...d, id: x.id, model: x.model, share: x.share, custom: true }));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't draft that customer.");
    } finally {
      setDrafting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="scrim absolute inset-0 bg-black/60 backdrop-blur-[2px]" onClick={onClose} />
      <aside role="dialog" aria-label={isNew ? "New customer" : `Edit ${p.name}`}
        className="drawer relative flex h-full w-full max-w-[560px] flex-col text-left border-l border-white/10 bg-[var(--card)] shadow-[0_0_80px_rgba(0,0,0,.45)]">

        {/* header */}
        <header className="flex items-center justify-between px-7 pb-5 pt-6">
          <div>
            <div className={LABEL}>{isNew ? "New customer" : "Edit customer"}</div>
            <div className="mt-1 font-serif text-[26px] leading-tight">{p.name.trim() || "Untitled customer"}</div>
          </div>
          <button onClick={onClose} aria-label="close" className="grid h-9 w-9 place-items-center rounded-full text-[20px] text-white/50 transition hover:bg-white/10 hover:text-white">×</button>
        </header>

        <div className="flex-1 overflow-y-auto">
          {/* preview */}
          <div className="mx-7 mb-6 flex items-center gap-5 rounded-2xl border border-white/10 bg-white/[0.03] p-5">
            <div className="relative shrink-0">
              <div className="rounded-full transition-shadow" style={{ boxShadow: `0 0 0 3px ${color}` }}>
                <Avatar seed={p.avatar.seed} archetype={p.archetype} model={p.model} age={p.age} size={84} feeling="interested" />
              </div>
              <button onClick={() => set("avatar", { seed: Math.floor(Math.random() * 10000) })} title="New look"
                className="absolute -bottom-1 -right-1 grid h-7 w-7 place-items-center rounded-full border border-white/15 bg-[var(--card)] text-[13px] text-white/70 transition hover:text-white">↻</button>
            </div>
            <div className="min-w-0">
              <div className="truncate text-[16px] font-semibold">{p.name.trim() || "Name"}{p.age ? `, ${p.age}` : ""}</div>
              <div className="truncate text-[13px] text-white/50">{p.occupation.trim() || "Occupation"}</div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <span className="rounded-full px-2 py-0.5 font-mono text-[10px]" style={{ background: `${color}22`, color }}>{p.archetype}</span>
                <span className="rounded-full border border-white/15 px-2 py-0.5 font-mono text-[10px] text-white/60">
                  {p.model ? <>played by <span style={{ color: MODEL_GLOW[p.model] }}>{p.model}</span></> : "model: auto"}
                </span>
                <span className="rounded-full border border-white/15 px-2 py-0.5 font-mono text-[10px] text-white/60">{Math.round(p.share * 100)}% of customers</span>
              </div>
            </div>
          </div>

          {/* draft with AI */}
          {isNew && (
            <div className="mx-7 mb-6 rounded-2xl border p-4" style={{ borderColor: `${C.brain}55`, background: `${C.brain}0d` }}>
              <div className="flex items-center justify-between">
                <span className="text-[13px] font-semibold" style={{ color: C.brain }}>Draft with AI</span>
                <span className="text-[12px] text-white/40">then fine-tune below</span>
              </div>
              <div className="mt-3 flex gap-2">
                <input value={brief} onChange={(e) => setBrief(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); draft(); } }}
                  placeholder="e.g. a retired nurse on a fixed income who distrusts subscriptions" className={FIELD} />
                <button onClick={draft} disabled={drafting || brief.trim().length < 3}
                  className="shrink-0 rounded-xl px-4 text-[13px] font-semibold text-white transition disabled:opacity-40" style={{ background: C.brain }}>
                  {drafting ? "Drafting…" : "Draft"}
                </button>
              </div>
              {err && <p className="mt-2 text-[12px]" style={{ color: C.loss }}>{err}</p>}
            </div>
          )}

          <Section title="Identity">
            <div className="grid grid-cols-[1fr_96px] gap-3">
              <Field label="Name"><input ref={first} value={p.name} onChange={(e) => set("name", e.target.value)} placeholder="Maya" className={FIELD} maxLength={40} /></Field>
              <Field label="Age"><input type="number" min={16} max={90} value={p.age} onChange={(e) => set("age", Number(e.target.value))} className={FIELD} /></Field>
            </div>
            <Field label="Occupation"><input value={p.occupation} onChange={(e) => set("occupation", e.target.value)} placeholder="Graduate student" className={FIELD} maxLength={80} /></Field>
            <Field label="Segment"><input value={p.segment} onChange={(e) => set("segment", e.target.value)} placeholder="Students near campus" className={FIELD} maxLength={120} /></Field>
          </Section>

          <Section title="Customer type">
            <div className="flex flex-wrap gap-2">
              {TYPES.map((t) => {
                const on = p.archetype === t;
                return (
                  <button key={t} onClick={() => set("archetype", t)}
                    className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-[13px] transition ${on ? "" : "border-white/12 text-white/60 hover:border-white/30 hover:text-white"}`}
                    style={on ? { borderColor: SHIRT[t], color: SHIRT[t], background: `${SHIRT[t]}14` } : undefined}>
                    <span className="h-2 w-2 rounded-full" style={{ background: SHIRT[t] }} />{t}
                  </button>
                );
              })}
            </div>
          </Section>

          <Section title="Played by" hint="the model that thinks as this customer">
            <div className="flex flex-wrap gap-2">
              {["", ...models].map((m) => {
                const on = (p.model ?? "") === m;
                const glow = m ? MODEL_GLOW[m] ?? C.win : "var(--ink)";
                return (
                  <button key={m || "auto"} onClick={() => set("model", m)}
                    className={`flex items-center gap-2 rounded-xl border px-3.5 py-2 text-[13px] font-medium transition ${on ? "bg-white/[0.06]" : "border-white/12 text-white/60 hover:border-white/30 hover:text-white"}`}
                    style={on ? { borderColor: glow, color: m ? glow : undefined } : undefined}>
                    <span className="h-2 w-2 rounded-full" style={{ background: glow, boxShadow: m ? `0 0 8px ${glow}` : undefined, opacity: m ? 1 : 0.4 }} />
                    {m || "Auto"}
                  </button>
                );
              })}
            </div>
            {!models.length && <p className="text-[12px] text-white/40">No model keys found on the server; customers will use the default.</p>}
          </Section>

          <Section title="Share of customers" hint="rebalanced to 100% at start">
            <div className="flex items-center gap-4">
              <input type="range" min={1} max={60} value={Math.max(1, Math.round(p.share * 100))} onChange={(e) => set("share", Number(e.target.value) / 100)} className="range-ink h-1 flex-1 cursor-pointer" />
              <span className="w-12 text-right font-mono text-[14px] tabular-nums">{Math.round(p.share * 100)}%</span>
            </div>
          </Section>

          <Section title="What they want">
            <Field label="Goal, in their words"><textarea value={p.goal} onChange={(e) => set("goal", e.target.value)} rows={2} placeholder="A cheap coffee I can grab before my 9am" className={`${FIELD} resize-none`} maxLength={300} /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Budget"><input value={p.budget} onChange={(e) => set("budget", e.target.value)} placeholder="about $5" className={FIELD} maxLength={120} /></Field>
              <Field label="Voice"><input value={p.voice} onChange={(e) => set("voice", e.target.value)} placeholder="Blunt, in a hurry" className={FIELD} maxLength={300} /></Field>
            </div>
          </Section>

          <Section title="Persona prompt" hint="added to every prompt that plays this customer">
            <textarea value={p.instructions ?? ""} onChange={(e) => set("instructions", e.target.value)} rows={5} maxLength={1000}
              placeholder={"e.g. Reads every review before buying. Leaves if shipping isn't shown on the product page.\nNever pays for a subscription."}
              className={`${FIELD} resize-y font-mono text-[13px] leading-relaxed`} />
            <div className="text-right font-mono text-[11px] text-white/35">{(p.instructions ?? "").length}/1000</div>
          </Section>
        </div>

        {/* footer */}
        <footer className="flex items-center gap-3 border-t border-white/10 px-7 py-4">
          {onRemove && !isNew && (
            <button onClick={onRemove} className="rounded-xl px-3 py-2 text-[13px] font-medium transition hover:bg-white/5" style={{ color: C.loss }}>Remove</button>
          )}
          <div className="flex-1" />
          <button onClick={onClose} className="rounded-xl border border-white/15 px-4 py-2.5 text-[14px] text-white/70 transition hover:border-white/40 hover:text-white">Cancel</button>
          <button onClick={() => valid && onSave({ ...p, name: p.name.trim(), custom: true })} disabled={!valid}
            className="rounded-xl px-5 py-2.5 text-[14px] font-semibold text-black transition disabled:opacity-40" style={{ background: C.win, boxShadow: valid ? `0 0 24px ${C.win}44` : undefined }}>
            {isNew ? "Add customer" : "Save changes"}
          </button>
        </footer>
      </aside>
    </div>
  );
}
