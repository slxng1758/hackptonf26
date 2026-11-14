import { useEffect, useState } from "react";
import type { Job } from "./types";
import { Start, type StartInput } from "./Start";
import { Dashboard } from "./Dashboard";
import { SimView } from "./Simulate";
import { Sidebar } from "./Sidebar";
import { Memory } from "./Memory";
import { PrintReport } from "./Print";
import { PersonaPage } from "./PersonaPage";

type View = { kind: "start" } | { kind: "job"; id: string } | { kind: "sim"; id: string } | { kind: "memory" } | { kind: "print"; id: string } | { kind: "persona"; id: string; pid: string };

function fromHash(): View {
  const h = location.hash;
  if (h.startsWith("#print=")) return { kind: "print", id: h.slice(7) };
  if (h === "#memory") return { kind: "memory" };
  if (h.startsWith("#job=")) return { kind: "job", id: h.slice(5).split("&")[0] };
  if (h.startsWith("#sim=")) {
    const [id, ...rest] = h.slice(5).split("&");
    const pid = rest.find((x) => x.startsWith("p="))?.slice(2);
    return pid ? { kind: "persona", id, pid } : { kind: "sim", id };
  }
  return { kind: "start" };
}

export function App() {
  const [view, setView] = useState<View>(fromHash);
  const [job, setJob] = useState<Job | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const on = () => { const v = fromHash(); if (v.kind !== "start" || !location.hash) setView(v); };
    addEventListener("hashchange", on);
    return () => removeEventListener("hashchange", on);
  }, []);
  useEffect(() => {
    if (view.kind === "job") history.replaceState(null, "", `#job=${view.id}`);
    else if (view.kind === "sim") history.replaceState(null, "", `#sim=${view.id}`);
    else if (view.kind === "memory") history.replaceState(null, "", "#memory");
    else if (view.kind === "print") return;
    else if (view.kind === "persona") { if (location.hash !== `#sim=${view.id}&p=${view.pid}`) history.replaceState(null, "", `#sim=${view.id}&p=${view.pid}`); }
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
      <Sidebar current={view.kind === "sim" || view.kind === "persona" ? view.id : undefined} view={view.kind} go={(v) => setView(v)} />
      <main className="min-w-0 flex-1">
        {/* phones and tablets: the sidebar is hidden below lg, so keep a way home and to memory (found by /qa) */}
        <nav className="sticky top-0 z-30 flex items-center gap-4 border-b border-white/10 bg-[var(--card)] px-4 py-2.5 text-[14px] lg:hidden">
          <a href="#" onClick={(e) => { e.preventDefault(); setView({ kind: "start" }); }} className="flex items-center gap-2 font-semibold"><img src="/icon.svg" alt="" className="h-7 w-7" />Agent-ready</a>
          <a href="#memory" onClick={(e) => { e.preventDefault(); setView({ kind: "memory" }); }} className="ml-auto text-white/70">Panel memory</a>
        </nav>
        {err && <div className="mx-auto mt-4 max-w-2xl rounded-xl border border-[#ff3355]/40 bg-[#ff3355]/10 px-4 py-2 text-center text-[13px] text-[#ff8099]">{err}</div>}
        {view.kind === "start" && <Start onGo={go} onOpen={(id) => setView({ kind: "sim", id })} />}
        {view.kind === "sim" && <SimView key={view.id} id={view.id} />}
        {view.kind === "memory" && <Memory />}
        {view.kind === "persona" && <PersonaPage key={view.id + view.pid} simId={view.id} pid={view.pid} />}
        {view.kind === "job" && (job && job.id === view.id ? <Dashboard job={job} /> : <div className="grid h-[60vh] place-items-center font-mono text-white/40">loading…</div>)}
      </main>
    </div>
  );
}
