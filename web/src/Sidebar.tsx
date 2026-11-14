// The app shell: new test, every site you've tested, panel memory, the iMessage line, theme.
import { useEffect, useState } from "react";
import { C, THEME, THEME_LIST, setTheme } from "./theme";

const readCollapsed = () => { try { return localStorage.getItem("sidebar") === "collapsed"; } catch { return false; } };

interface Row { id: string; name: string; host: string; status: string; round: number; bought: number; of: number }

export function Sidebar({ current, view, go }: { current?: string; view: string; go: (v: { kind: "start" } | { kind: "sim"; id: string } | { kind: "memory" }) => void }) {
  const [rows, setRows] = useState<Row[]>([]);
  const [small, setSmall] = useState(readCollapsed);
  const toggle = () => { const v = !small; setSmall(v); try { localStorage.setItem("sidebar", v ? "collapsed" : "open"); } catch { /* storage unavailable */ } };
  useEffect(() => {
    const load = () => fetch("/api/sims").then((r) => r.json()).then(setRows).catch(() => {});
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, []);
  // one row per site: the latest finished result, "running" only if its newest test is actually in progress
  const label = (r: Row) => (/^(127\.0\.0\.1|localhost)/.test(r.host) ? r.name.slice(0, 28) : r.host);
  const sites = new Map<string, { latest: Row; tests: number; running: boolean }>();
  for (const r of rows) {
    const key = label(r);
    const s = sites.get(key);
    const live = ["browsing", "talking", "analyzing"].includes(r.status);
    if (!s) sites.set(key, { latest: r, tests: 1, running: live });
    else { s.tests++; if (s.latest.status !== "done" && r.status === "done") s.latest = r; }
  }
  for (const [k, s] of sites) if (s.latest.status !== "done" && !s.running) sites.delete(k);
  const cur = rows.find((r) => r.id === current);
  const currentHost = cur ? label(cur) : undefined;

  const item = (active: boolean) => `flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[13.5px] transition ${active ? "bg-white/10 font-semibold" : "text-white/70 hover:bg-white/[0.06] hover:text-white"}`;

  if (small) return (
    <aside className="sticky top-0 hidden h-screen w-[64px] shrink-0 flex-col items-center gap-2 border-r border-white/10 bg-[var(--card)] py-4 lg:flex">
      <button onClick={() => go({ kind: "start" })} title="Agent-ready" className="grid h-9 w-9 place-items-center rounded-lg text-[15px] font-black text-[#ffffff]" style={{ background: `linear-gradient(135deg, ${C.win}, ${C.brain})` }}>A</button>
      <button onClick={() => go({ kind: "start" })} title="New test" className="grid h-9 w-9 place-items-center rounded-lg text-[20px] font-semibold text-[#ffffff]" style={{ background: C.brain }}>+</button>
      <div className="mt-2 flex min-h-0 flex-1 flex-col items-center gap-1.5 overflow-y-auto">
        {[...sites.entries()].map(([host, s]) => (
          <button key={host} onClick={() => go({ kind: "sim", id: s.latest.id })} title={`${host} · ${s.running ? "running" : `${s.latest.bought}/${s.latest.of}`}`}
            className={`grid h-9 w-9 place-items-center rounded-lg text-[13px] font-bold uppercase ${host === currentHost && view === "sim" ? "bg-white/15" : "bg-white/[0.05] hover:bg-white/10"}`}
            style={{ boxShadow: `inset 0 -3px 0 ${s.running ? C.mid : s.latest.of && s.latest.bought / s.latest.of >= 0.5 ? C.win : s.latest.bought ? C.mid : C.loss}` }}>{host[0]}</button>
        ))}
      </div>
      <button onClick={() => go({ kind: "memory" })} title="Panel memory" className={`grid h-9 w-9 place-items-center rounded-lg text-[11px] font-bold ${view === "memory" ? "bg-white/15" : "hover:bg-white/10"}`}>MEM</button>
      <button onClick={toggle} title="Expand sidebar" className="grid h-9 w-9 place-items-center rounded-lg text-[16px] text-white/60 hover:bg-white/10 hover:text-white">»</button>
    </aside>
  );

  return (
    <aside className="sticky top-0 hidden h-screen w-[260px] shrink-0 flex-col border-r border-white/10 bg-[var(--card)] px-3 py-4 lg:flex">
      <button onClick={() => go({ kind: "start" })} className="flex items-center gap-2 px-2 pb-4">
        <span className="grid h-8 w-8 place-items-center rounded-lg text-[15px] font-black text-[#ffffff]" style={{ background: `linear-gradient(135deg, ${C.win}, ${C.brain})` }}>A</span>
        <span className="flex-1 text-left text-[17px] font-bold tracking-tight">Agent-ready</span>
      </button>
      <button onClick={() => go({ kind: "start" })} className="mb-4 rounded-lg px-3 py-2.5 text-[14px] font-semibold text-[#ffffff]" style={{ background: C.brain }}>+ New test</button>

      <div className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-white/40">Sites</div>
      <nav className="min-h-0 flex-1 space-y-0.5 overflow-y-auto">
        {[...sites.entries()].map(([host, s]) => (
          <button key={host} onClick={() => go({ kind: "sim", id: s.latest.id })} className={item(host === currentHost && view === "sim")}>
            <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: s.running ? C.mid : s.latest.of && s.latest.bought / s.latest.of >= 0.5 ? C.win : s.latest.bought ? C.mid : C.loss }} />
            <span className="min-w-0 flex-1 truncate">{host}</span>
            <span className="font-mono text-[11px] text-white/45">{s.running ? "running" : `${s.latest.bought}/${s.latest.of}`}</span>
          </button>
        ))}
        {!sites.size && <div className="px-3 py-2 text-[13px] text-white/40">No tests yet</div>}
      </nav>

      <div className="mt-3 space-y-0.5 border-t border-white/10 pt-3">
        <div className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-white/40">Workspace</div>
        <button onClick={() => go({ kind: "memory" })} className={item(view === "memory")}>Panel memory</button>
        <div className="rounded-lg px-3 py-2 text-[12.5px] text-white/60">
          <div className="font-semibold text-white/80">Test by text</div>
          iMessage <span className="font-mono">+1 628-502-4649</span>
        </div>
      </div>

      <button onClick={toggle} className="mt-3 rounded-lg px-3 py-1.5 text-left text-[12.5px] text-white/50 hover:bg-white/[0.06] hover:text-white">« Collapse sidebar</button>
      <div className="mt-2 flex gap-1 rounded-lg border border-white/10 p-1">
        {THEME_LIST.map((t) => (
          <button key={t.id} onClick={() => t.id !== THEME && setTheme(t.id)} className={`flex-1 rounded-md py-1.5 text-[12px] ${t.id === THEME ? "bg-white/10 font-semibold" : "text-white/50 hover:text-white"}`}>{t.label}</button>
        ))}
      </div>
    </aside>
  );
}
