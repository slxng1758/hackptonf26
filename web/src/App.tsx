import { useEffect, useState } from "react";
import type { Job } from "./types";
import { Start, type StartInput } from "./Start";
import { Dashboard } from "./Dashboard";
import { SimView } from "./Simulate";
import { THEME, THEME_LIST, setTheme } from "./theme";

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

  async function go(b: StartInput) {
    setErr(null);
    const r = await fetch("/api/sims", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });
    if (!r.ok) { setErr("Describe your product in a sentence or two (at least 10 characters)."); return; }
    setView({ kind: "sim", id: (await r.json()).id });
  }

  return (
    <div className="min-h-screen">
      <header className="flex h-16 items-center justify-between px-6">
        <button onClick={() => setView({ kind: "start" })} className="font-serif text-[22px]">Agent-ready</button>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1 rounded-full border border-white/15 p-1" title="Theme">
            {THEME_LIST.map((t) => (
              <button key={t.id} onClick={() => t.id !== THEME && setTheme(t.id)} title={t.label}
                className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] ${t.id === THEME ? "bg-white/10 font-semibold" : "text-white/50 hover:text-white"}`}>
                <span className="flex -space-x-1">{t.swatch.map((c) => <span key={c} className="h-3 w-3 rounded-full ring-1 ring-black/20" style={{ background: c }} />)}</span>{t.label}
              </button>
            ))}
          </div>
          {view.kind !== "start" && <button onClick={() => setView({ kind: "start" })} className="rounded-full border border-white/20 px-4 py-1.5 text-[13px] hover:border-white/50">Try another site</button>}
        </div>
      </header>
      {err && <div className="mx-auto mt-4 max-w-2xl rounded-xl border border-[#ff3355]/40 bg-[#ff3355]/10 px-4 py-2 text-center text-[13px] text-[#ff8099]">{err}</div>}
      {view.kind === "start" && <Start onGo={go} onOpen={(id) => setView({ kind: "sim", id })} />}
      {view.kind === "sim" && <SimView key={view.id} id={view.id} />}
      {view.kind === "job" && (job && job.id === view.id ? <Dashboard job={job} /> : <div className="grid h-[60vh] place-items-center font-mono text-white/40">loading…</div>)}
    </div>
  );
}
