import { useEffect, useState } from "react";
import type { Job } from "./types";
import { Start } from "./Start";
import { Dashboard } from "./Dashboard";
import { SimView } from "./Simulate";

type View = { kind: "start" } | { kind: "job"; id: string } | { kind: "sim"; id: string };

export function App() {
  const [view, setView] = useState<View>(() => (location.hash.startsWith("#job=") ? { kind: "job", id: location.hash.slice(5).split("&")[0] } : location.hash.startsWith("#sim=") ? { kind: "sim", id: location.hash.slice(5).split("&")[0] } : { kind: "start" }));
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
    else history.replaceState(null, "", location.pathname);
  }, [view]);

  useEffect(() => {
    if (view.kind !== "job") return;
    fetch(`/api/jobs/${view.id}`).then((r) => r.json()).then(setJob).catch(() => {});
  }, [view]);

  async function go(b: { url: string; context: string; world: string }) {
    setErr(null);
    const r = await fetch("/api/sims", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });
    if (!r.ok) { setErr("That doesn't look like a website. Try something like yourbusiness.com"); return; }
    setView({ kind: "sim", id: (await r.json()).id });
  }

  return (
    <div className="min-h-screen">
      <header className="flex h-16 items-center justify-between px-6">
        <button onClick={() => setView({ kind: "start" })} className="font-serif text-[22px]">Agent-ready</button>
        {view.kind !== "start" && <button onClick={() => setView({ kind: "start" })} className="rounded-full border border-white/20 px-4 py-1.5 text-[13px] hover:border-white/50">Try another site</button>}
      </header>
      {err && <div className="mx-auto mt-4 max-w-2xl rounded-xl border border-[#ff3355]/40 bg-[#ff3355]/10 px-4 py-2 text-center text-[13px] text-[#ff8099]">{err}</div>}
      {view.kind === "start" && <Start onGo={go} />}
      {view.kind === "sim" && <SimView key={view.id} id={view.id} />}
      {view.kind === "job" && (job && job.id === view.id ? <Dashboard job={job} /> : <div className="grid h-[60vh] place-items-center font-mono text-white/40">loading…</div>)}
    </div>
  );
}
