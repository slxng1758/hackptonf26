import { useEffect, useState } from "react";
import type { Draft, Job, JobRow } from "./types";
import { Start } from "./Start";
import { Review } from "./Review";
import { Dashboard } from "./Dashboard";
import { SimSetup, SimView, type Sim } from "./Simulate";
import { pct } from "./theme";

type View = { kind: "start" } | { kind: "review"; draft: Draft } | { kind: "job"; id: string } | { kind: "simsetup"; draft: Draft } | { kind: "sim"; id: string };

export function App() {
  const [view, setView] = useState<View>(() => (location.hash.startsWith("#job=") ? { kind: "job", id: location.hash.slice(5) } : location.hash.startsWith("#sim=") ? { kind: "sim", id: location.hash.slice(5) } : { kind: "start" }));
  const [job, setJob] = useState<Job | null>(null);
  const [rows, setRows] = useState<JobRow[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const loadRows = () => fetch("/api/jobs").then((r) => r.json()).then(setRows).catch(() => {});
  useEffect(() => { loadRows(); }, []);
  useEffect(() => {
    if (view.kind === "job") history.replaceState(null, "", `#job=${view.id}`);
    else if (view.kind === "sim") history.replaceState(null, "", `#sim=${view.id}`);
    else history.replaceState(null, "", location.pathname);
  }, [view]);

  async function startSim(b: Sim["input"]) {
    setErr(null);
    const r = await fetch("/api/sims", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });
    if (!r.ok) { setErr("Couldn't start the simulation. Check the website address."); return; }
    const { id } = await r.json();
    setView({ kind: "sim", id });
  }

  useEffect(() => {
    if (view.kind !== "job") return;
    let alive = true;
    const tick = () => fetch(`/api/jobs/${view.id}`).then((r) => r.json()).then((j: Job) => { if (alive) { setJob(j); if (j.status !== "running") loadRows(); } }).catch(() => {});
    tick();
    const t = setInterval(() => { if (!job || job.id !== view.id || job.status === "running") tick(); }, 1500);
    return () => { alive = false; clearInterval(t); };
  }, [view, job?.status]); // eslint-disable-line

  async function run(d: Draft) {
    setErr(null);
    const r = await fetch("/api/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(d) });
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      setErr(Array.isArray(body.detail) ? "Some fields are too short. Check the listing, facts, competitors and customers." : body.detail ?? "Couldn't start the test.");
      return;
    }
    const { id } = await r.json();
    setJob(null); setView({ kind: "job", id }); loadRows();
  }

  return (
    <div className="min-h-screen">
      <header className="flex h-16 items-center justify-between border-b border-white/10 px-6">
        <button onClick={() => { setJob(null); setView({ kind: "start" }); }} className="flex items-baseline gap-3">
          <span className="font-serif text-[22px]">Agent-ready</span>
          <span className="hidden font-mono text-[11px] text-white/40 sm:inline">will AI agents pick your business?</span>
        </button>
        <div className="flex items-center gap-2">
          {rows.length > 0 && (
            <select value={view.kind === "job" ? view.id : ""} onChange={(e) => e.target.value && (setJob(null), setView({ kind: "job", id: e.target.value }))}
              className="max-w-[280px] rounded-full border border-white/15 bg-transparent px-3 py-1.5 font-mono text-[11px] text-white/70">
              <option value="" className="text-black">past tests</option>
              {rows.map((r) => <option key={r.id} value={r.id} className="text-black">{r.name} · {pct(r.first)} → {pct(r.best)}</option>)}
            </select>
          )}
          {view.kind !== "start" && <button onClick={() => { setJob(null); setView({ kind: "start" }); }} className="rounded-full bg-white px-4 py-1.5 text-[13px] font-semibold text-black">New test</button>}
        </div>
      </header>
      {err && <div className="mx-auto mt-4 max-w-6xl rounded-xl border border-[#ff3355]/40 bg-[#ff3355]/10 px-4 py-2 text-[13px] text-[#ff8099]">{err}</div>}
      {view.kind === "start" && <Start onReady={(draft) => setView({ kind: "review", draft })} />}
      {view.kind === "review" && <Review draft={view.draft} onRun={run} onSimulate={(d) => setView({ kind: "simsetup", draft: d })} onBack={() => setView({ kind: "start" })} busy={false} />}
      {view.kind === "simsetup" && <SimSetup draft={view.draft} onStart={startSim} onBack={() => setView({ kind: "review", draft: view.draft })} />}
      {view.kind === "sim" && <SimView key={view.id} id={view.id} />}
      {view.kind === "job" && (job && job.id === view.id ? <Dashboard job={job} /> : <div className="grid h-[60vh] place-items-center font-mono text-white/40">loading…</div>)}
    </div>
  );
}
