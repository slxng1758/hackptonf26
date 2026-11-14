import { useEffect, useState } from "react";
import type { Job } from "./types";
import { Start, type StartInput } from "./Start";
import { Dashboard } from "./Dashboard";
import { SimView } from "./Simulate";
import { Sidebar } from "./Sidebar";
import { Memory } from "./Memory";
import { PrintReport } from "./Print";

type View = { kind: "start" } | { kind: "job"; id: string } | { kind: "sim"; id: string } | { kind: "memory" } | { kind: "print"; id: string };

export function App() {
  const [view, setView] = useState<View>(() => location.hash.startsWith("#print=") ? { kind: "print", id: location.hash.slice(7) } : location.hash === "#memory" ? { kind: "memory" } : (location.hash.startsWith("#job=") ? { kind: "job", id: location.hash.slice(5).split("&")[0] } : location.hash.startsWith("#sim=") ? { kind: "sim", id: location.hash.slice(5).split("&")[0] } : { kind: "start" }));
  const [job, setJob] = useState<Job | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const on = () => { const h = location.hash; if (h.startsWith("#sim=")) setView({ kind: "sim", id: h.slice(5).split("&")[0] }); else if (h.startsWith("#job=")) setView({ kind: "job", id: h.slice(5).split("&")[0] }); };
    addEventListener("hashchange", on);
    return () => removeEventListener("hashchange", on);
  }, []);
  useEffect(() => {
    if (view.kind === "job") history.replaceState(null, "", `#job=${view.id}`);
    else if (view.kind === "sim") history.replaceState(null, "", `#sim=${view.id}`);
    else if (view.kind === "memory") history.replaceState(null, "", "#memory");
    else if (view.kind === "print") return;
    else history.replaceState(null, "", location.pathname);
  }, [view]);

  useEffect(() => {
    if (view.kind !== "job") return;
    fetch(`/api/jobs/${view.id}`).then((r) => r.json()).then(setJob).catch(() => {});
  }, [view]);

  async function go(b: StartInput) {
    setErr(null);
    const r = await fetch("/api/sims", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });
    if (!r.ok) { setErr("Describe your product in a sentence or two (at least 10 characters)."); return; }
    setView({ kind: "sim", id: (await r.json()).id });
  }

  if (view.kind === "print") return <PrintReport id={view.id} />;

  return (
    <div className="flex min-h-screen">
      <Sidebar current={view.kind === "sim" ? view.id : undefined} view={view.kind} go={(v) => setView(v)} />
      <main className="min-w-0 flex-1">
        {err && <div className="mx-auto mt-4 max-w-2xl rounded-xl border border-[#ff3355]/40 bg-[#ff3355]/10 px-4 py-2 text-center text-[13px] text-[#ff8099]">{err}</div>}
        {view.kind === "start" && <Start onGo={go} onOpen={(id) => setView({ kind: "sim", id })} />}
        {view.kind === "sim" && <SimView key={view.id} id={view.id} />}
        {view.kind === "memory" && <Memory />}
        {view.kind === "job" && (job && job.id === view.id ? <Dashboard job={job} /> : <div className="grid h-[60vh] place-items-center font-mono text-white/40">loading…</div>)}
      </main>
    </div>
  );
}
