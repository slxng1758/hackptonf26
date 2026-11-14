// Panel memory: what each kind of customer has learned across every business tested. Lives in the Deep Agents
// long-term store (/memories/<type>.md) and seeds every new test panel.
import { useEffect, useState } from "react";
import { Avatar, SHIRT } from "./Avatar";
import { C, PANEL } from "./theme";

const SEEDS: Record<string, { seed: number; age: number; label: string }> = {
  "price-sensitive": { seed: 11, age: 24, label: "Price-sensitive" }, "quality-first": { seed: 913, age: 46, label: "Quality-first" },
  "brand-loyal": { seed: 402, age: 38, label: "Brand-loyal" }, "function-first": { seed: 77, age: 52, label: "Function-first" },
  "first-time": { seed: 250, age: 19, label: "First-time user" }, skeptic: { seed: 640, age: 61, label: "Skeptic" },
  enthusiast: { seed: 333, age: 29, label: "Enthusiast" }, "AI-agent": { seed: 901, age: 30, label: "AI shopping agent" },
};
const keyOf = (k: string) => Object.keys(SEEDS).find((s) => k.toLowerCase().startsWith(s.toLowerCase().split("-")[0])) ?? k;
const archetypeOf = (k: string) => (k === "AI-agent" ? "AI agent" : k === "first-time" ? "first-time user" : k);

export function Memory() {
  const [mem, setMem] = useState<Record<string, string> | null>(null);
  useEffect(() => { fetch("/api/memory").then((r) => r.json()).then(setMem).catch(() => setMem({})); }, []);
  const entries = Object.entries(mem ?? {});
  return (
    <div className="mx-auto max-w-6xl px-8 py-10">
      <div className="text-[13px] font-semibold" style={{ color: C.brain }}>Workspace</div>
      <h1 className="mt-1 text-[32px] font-bold tracking-tight">Panel memory</h1>
      <p className="mt-2 max-w-2xl text-[15px] text-white/60">What each kind of customer has learned from every business you've tested. Every new test panel starts from this, so the tenth business gets smarter customers than the first.</p>
      {mem === null && <p className="mt-8 text-white/50">Loading…</p>}
      {mem && !entries.length && <p className={`${PANEL} mt-8 p-6 text-white/60`}>Nothing yet. Memory fills in after your first finished test.</p>}
      <div className="mt-8 grid gap-4 md:grid-cols-2">
        {entries.map(([k, text]) => {
          const meta = SEEDS[keyOf(k)] ?? { seed: 5, age: 30, label: k };
          const a = archetypeOf(keyOf(k));
          const lessons = text.split("\n").map((l) => l.replace(/^[-*•]\s*/, "").trim()).filter(Boolean);
          return (
            <div key={k} className={`${PANEL} p-5`}>
              <div className="flex items-center gap-3">
                <div className="rounded-full" style={{ boxShadow: `0 0 0 2px ${SHIRT[a] ?? C.brain}` }}><Avatar seed={meta.seed} archetype={a} model="Gemini" age={meta.age} size={48} feeling="interested" /></div>
                <div><div className="text-[16px] font-semibold">{meta.label}</div><div className="text-[12px] text-white/50">{lessons.length} lesson{lessons.length === 1 ? "" : "s"} learned</div></div>
              </div>
              <ul className="mt-4 space-y-2">
                {lessons.map((l, i) => <li key={i} className="flex gap-2 text-[14px] leading-snug text-white/80"><span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: SHIRT[a] ?? C.brain }} />{l}</li>)}
              </ul>
            </div>
          );
        })}
      </div>
    </div>
  );
}
