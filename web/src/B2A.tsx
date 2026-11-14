import { useEffect, useState } from "react";
import { C } from "./theme";
import { PANEL } from "./ui";

interface Test {
  listing: string; to_confirm?: string[]; pick_rate: number; wins: number; total: number; errors: number;
  by_shopper: Record<string, { wins: number; total: number }>;
  by_task: { task: string; wins: number; total: number }[];
  lost_to: { competitor: number; times: number }[];
  losses: { shopper: string; task: string; reason: string; missing: string }[];
  wins_why: { shopper: string; task: string; reason: string }[];
}
interface Market { name: string; ours: string; competitors: string[]; tasks: string[] }
interface Job { id: string; ours: string; market: Market; status: string; error: string | null; steps: { t: string; kind: string; note: string }[]; tests: Test[]; report: string; shoppers: string[] }

const KIND: Record<string, string> = { plan: "#8ab4ff", test: "#7b84a8", result: C.ritual, critic: C.sick, rewriter: C.myth, answer: C.myth, memory: C.truth, error: C.sick };
const pct = (x: number) => `${Math.round(x * 100)}%`;
const name = (c: string) => c.split(".")[0];

export function B2A() {
  const [demo, setDemo] = useState<Market | null>(null);
  const [ours, setOurs] = useState("");
  const [jobs, setJobs] = useState<{ id: string; ours: string; status: string; tests: number }[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [showMarket, setShowMarket] = useState(false);

  useEffect(() => {
    fetch("/api/b2a/demo").then((r) => r.json()).then((d: Market) => { setDemo(d); setOurs(d.ours); }).catch(() => {});
    fetch("/api/b2a").then((r) => r.json()).then((l) => { setJobs(l); if (l[0]) setJobId(l[0].id); }).catch(() => {});
  }, []);
  useEffect(() => {
    if (!jobId) return;
    let alive = true;
    const tick = () => fetch(`/api/b2a/${jobId}`).then((r) => r.json()).then((j: Job) => alive && setJob(j)).catch(() => {});
    tick();
    const t = setInterval(() => { if (job?.status !== "done" && job?.status !== "error") tick(); }, 2000);
    return () => { alive = false; clearInterval(t); };
  }, [jobId, job?.status]); // eslint-disable-line

  async function run() {
    const r = await fetch("/api/b2a", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ours }) });
    const { id } = await r.json();
    setJob(null); setJobId(id);
    setJobs((j) => [{ id, ours, status: "running", tests: 0 }, ...j]);
  }

  const market = job?.market ?? demo;
  const first = job?.tests[0], best = job?.tests.length ? job.tests.reduce((a, b) => (b.pick_rate > a.pick_rate ? b : a)) : null;
  const plan = [...(job?.steps ?? [])].reverse().find((s) => s.kind === "plan" && s.note.includes("→"));

  return (
    <div className="min-h-screen px-6 pb-16 pt-16">
      <div className="mx-auto grid max-w-7xl gap-6 lg:grid-cols-[400px_minmax(0,1fr)]">
        <aside className="space-y-4">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.35em] text-white/40">b2a test</div>
            <h1 className="mt-1 font-serif text-[28px] leading-tight">Will an AI shopping agent pick you?</h1>
            <p className="mt-2 text-[13px] text-white/55">Real models shop for real buyer tasks across your market. You see who they pick and why, then an agent rewrites your listing and re-tests it.</p>
          </div>
          <label className="block">
            <span className="font-mono text-[10px] uppercase tracking-widest text-white/40">Your listing · {market?.name}</span>
            <textarea value={ours} onChange={(e) => setOurs(e.target.value)} rows={6} className="mt-1 w-full rounded-xl border border-white/15 bg-white/[0.04] p-3 text-[14px] leading-snug outline-none focus:border-[#3ff0d4]" />
          </label>
          <button onClick={run} className="w-full rounded-xl bg-[#3ff0d4] py-3 font-semibold text-black shadow-[0_0_40px_rgba(63,240,212,0.35)] hover:brightness-110">Send in the shopping agents</button>
          <button onClick={() => setShowMarket(!showMarket)} className="w-full rounded-xl border border-white/15 py-2 font-mono text-[11px] uppercase tracking-widest text-white/60 hover:text-white">{showMarket ? "hide" : "show"} the market ({market?.competitors.length ?? 0} competitors, {market?.tasks.length ?? 0} buyer tasks)</button>
          {showMarket && market && (
            <div className={`${PANEL} space-y-3 p-4 text-[12.5px]`}>
              {market.competitors.map((c, i) => <p key={i} className="text-white/70"><b className="text-white">{name(c)}</b>{c.slice(name(c).length)}</p>)}
              <div className="border-t border-white/10 pt-2 font-mono text-[10px] uppercase tracking-widest text-white/40">buyer tasks</div>
              {market.tasks.map((t, i) => <p key={i} className="text-white/60">“{t}”</p>)}
            </div>
          )}
          {jobs.length > 0 && (
            <select value={jobId ?? ""} onChange={(e) => { setJob(null); setJobId(e.target.value); }} className="w-full rounded-xl border border-white/15 bg-transparent px-3 py-2 font-mono text-[11px] text-white/70">
              {jobs.map((j) => <option key={j.id} value={j.id} className="text-black">{j.status} · {j.tests} tests · {j.ours.slice(0, 40)}</option>)}
            </select>
          )}
        </aside>

        <main className="min-w-0 space-y-6">
          {first && best && (
            <section className={`${PANEL} p-6`}>
              <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-white/40">picked by AI shopping agents</div>
              <div className="mt-3 flex flex-wrap items-end gap-10">
                <div>
                  <div className="font-mono text-[64px] font-semibold leading-none" style={{ color: C.sick, textShadow: `0 0 30px ${C.sick}` }}>{pct(first.pick_rate)}</div>
                  <div className="mt-1 font-mono text-[11px] uppercase tracking-widest text-white/50">your listing · {first.wins}/{first.total}</div>
                </div>
                {best !== first && (
                  <>
                    <div className="pb-6 font-serif text-[36px] text-white/30">→</div>
                    <div>
                      <div className="font-mono text-[64px] font-semibold leading-none" style={{ color: C.truth, textShadow: `0 0 30px ${C.truth}` }}>{pct(best.pick_rate)}</div>
                      <div className="mt-1 font-mono text-[11px] uppercase tracking-widest text-white/50">after rewrite · {best.wins}/{best.total}</div>
                    </div>
                  </>
                )}
              </div>
            </section>
          )}

          {job && job.tests.length > 0 && (
            <section className="grid gap-4 xl:grid-cols-2">
              {job.tests.map((t, i) => (
                <div key={i} className={`${PANEL} p-4 ${t === best && i > 0 ? "ring-1 ring-[#3ff0d4]/50" : ""}`}>
                  <div className="flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.3em] text-white/40">
                    <span>test {i + 1}{i === 0 ? " · original" : ""}</span>
                    <span style={{ color: t.pick_rate >= 0.5 ? C.truth : t.pick_rate > 0 ? C.ritual : C.sick }}>{pct(t.pick_rate)} picked</span>
                  </div>
                  <p className="mt-2 text-[13px] leading-snug text-white/85">{t.listing}</p>
                  {!!t.to_confirm?.length && (
                    <div className="mt-2 rounded-lg border border-[#ffb547]/40 bg-[#ffb547]/[0.06] p-2 text-[11.5px] text-[#ffb547]">
                      Needs your confirmation before you publish: {t.to_confirm.join(" · ")}
                    </div>
                  )}
                  <div className="mt-3 flex flex-wrap gap-3 font-mono text-[11px]">
                    {Object.entries(t.by_shopper).map(([s, d]) => <span key={s} className="rounded-full border border-white/15 px-2 py-0.5 text-white/70">{s} {d.wins}/{d.total}</span>)}
                  </div>
                  <div className="mt-3 space-y-1">
                    {t.by_task.map((b, k) => (
                      <div key={k} className="flex items-center gap-2 text-[11.5px]">
                        <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: b.wins === 0 ? C.sick : b.wins === b.total ? C.truth : C.ritual }} />
                        <span className="truncate text-white/60">{b.task}</span>
                        <span className="ml-auto shrink-0 font-mono text-white/40">{b.wins}/{b.total}</span>
                      </div>
                    ))}
                  </div>
                  {t.losses.slice(0, 2).map((l, k) => (
                    <p key={k} className="mt-2 text-[12px] leading-snug text-white/55"><span style={{ color: C.sick }}>{l.shopper} chose another:</span> {l.reason}</p>
                  ))}
                </div>
              ))}
            </section>
          )}

          <section className={`${PANEL} p-5`}>
            <div className="flex items-center justify-between">
              <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-white/40">the agent, live</div>
              {job && <span className="font-mono text-[11px]" style={{ color: job.status === "running" ? C.ritual : job.status === "done" ? C.truth : C.sick }}>{job.status === "running" ? "● working" : job.status}</span>}
            </div>
            {plan && (
              <ol className="mt-3 space-y-1">
                {plan.note.split(" → ").map((p, i) => <li key={i} className={`text-[13px] ${p.startsWith("✓") ? "text-white/40 line-through" : "text-white/85"}`}>{p.startsWith("✓") ? "☑" : "☐"} {p.replace(/^✓ /, "")}</li>)}
              </ol>
            )}
            <div className="mt-4 max-h-[320px] space-y-1.5 overflow-y-auto font-mono text-[11.5px]">
              {(job?.steps ?? []).filter((s) => s.kind !== "plan").slice().reverse().map((s, i) => (
                <div key={i} className="flex gap-3"><span className="w-14 shrink-0 text-white/30">{s.t}</span><span className="w-20 shrink-0 font-semibold uppercase" style={{ color: KIND[s.kind] ?? "#fff" }}>{s.kind}</span><span className="text-white/75">{s.note}</span></div>
              ))}
              {!job && <p className="text-white/40">Press “Send in the shopping agents”.</p>}
            </div>
          </section>

          {job?.report && (
            <section className={`${PANEL} p-6`}>
              <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-white/40">the agent's report</div>
              <pre className="mt-3 whitespace-pre-wrap font-serif text-[15px] leading-relaxed text-white/85">{job.report}</pre>
            </section>
          )}
        </main>
      </div>
    </div>
  );
}
