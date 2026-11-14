import { useEffect, useState } from "react";
import type { Job, JobRow, Preset } from "./types";
import { Setup } from "./Setup";
import { Run } from "./Run";
import { LABEL, PANEL, pct, rateColor } from "./theme";

export function App() {
  const [rows, setRows] = useState<JobRow[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [lessons, setLessons] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const refresh = () => {
    fetch("/api/jobs").then((r) => r.json()).then((l: JobRow[]) => { setRows(l); if (!jobId && l[0]) setJobId(l[0].id); }).catch(() => {});
    fetch("/api/lessons").then((r) => r.json()).then(setLessons).catch(() => {});
  };
  useEffect(refresh, []); // eslint-disable-line

  useEffect(() => {
    if (!jobId) return;
    let alive = true;
    const tick = () => fetch(`/api/jobs/${jobId}`).then((r) => r.json()).then((j: Job) => { if (alive) { setJob(j); if (j.status !== "running") refresh(); } }).catch(() => {});
    tick();
    const t = setInterval(() => { if (!job || job.status === "running") tick(); }, 1500);
    return () => { alive = false; clearInterval(t); };
  }, [jobId, job?.status]); // eslint-disable-line

  async function start(p: Preset & { customers_csv: boolean }) {
    setErr(null);
    const r = await fetch("/api/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(p) });
    if (!r.ok) { setErr(await r.text()); return; }
    const { id } = await r.json();
    setJob(null); setJobId(id);
    setRows((x) => [{ id, name: p.name, status: "running", first: null, best: null }, ...x]);
  }

  return (
    <div className="min-h-screen">
      <header className="flex items-center justify-between border-b border-white/10 px-6 py-4">
        <div className="flex items-baseline gap-3">
          <span className="font-serif text-[22px]">Agent-ready</span>
          <span className="hidden font-mono text-[11px] text-white/40 sm:inline">will AI shopping agents pick your business?</span>
        </div>
        {rows.length > 0 && (
          <select value={jobId ?? ""} onChange={(e) => { setJob(null); setJobId(e.target.value); }} className="rounded-full border border-white/15 bg-transparent px-3 py-1.5 font-mono text-[11px] text-white/70">
            {rows.map((r) => <option key={r.id} value={r.id} className="text-black">{r.name} · {r.status} · {pct(r.first)} → {pct(r.best)}</option>)}
          </select>
        )}
      </header>

      <div className="mx-auto grid max-w-[1400px] gap-8 px-6 py-8 lg:grid-cols-[420px_minmax(0,1fr)]">
        <aside className="space-y-6">
          <div>
            <h1 className="font-serif text-[30px] leading-tight">Test your business on the agents that will shop for your customers.</h1>
            <p className="mt-2 text-[13.5px] text-white/55">Real AI models (Claude, GPT) run your customers' requests across your market. You see who they pick and why. Then an agent rewrites your listing from your own facts and tests it again.</p>
          </div>
          <Setup onStart={start} busy={job?.status === "running"} />
          {err && <p className="text-[12px] text-[#ff3355]">{err}</p>}
          {lessons.length > 0 && (
            <div className={`${PANEL} p-4`}>
              <div className={LABEL}>what the agent has learned so far</div>
              <ul className="mt-2 space-y-1.5 text-[12.5px] text-white/70">{lessons.slice(-5).map((l, i) => <li key={i}>· {l}</li>)}</ul>
            </div>
          )}
        </aside>

        <main className="min-w-0">
          {job ? <Run job={job} /> : (
            <div className={`${PANEL} grid h-[420px] place-items-center text-center`}>
              <div>
                <div className="font-serif text-[26px] text-white/80">No test yet.</div>
                <p className="mt-2 text-[13px] text-white/45">Pick an example on the left and send in the shopping agents.</p>
              </div>
            </div>
          )}
          {rows.length > 1 && (
            <div className="mt-6 flex flex-wrap gap-2">
              {rows.slice(0, 8).map((r) => (
                <button key={r.id} onClick={() => { setJob(null); setJobId(r.id); }} className={`rounded-full border px-3 py-1 font-mono text-[11px] ${r.id === jobId ? "border-white/40 text-white" : "border-white/12 text-white/50"}`}>
                  {r.name} <span style={{ color: r.best != null ? rateColor(r.best) : undefined }}>{pct(r.first)} → {pct(r.best)}</span>
                </button>
              ))}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
