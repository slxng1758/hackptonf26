// Every test this business has run, oldest to newest: what changed and how many bought. The reason to come back.
import { useEffect, useState } from "react";
import { C } from "./theme";

export interface Run { id: string; name: string; host: string; status: string; round: number; context: string; world: string; bought: number; of: number }
const when = (id: string) => `${id.slice(0, 2)}/${id.slice(2, 4)} ${id.slice(5, 7)}:${id.slice(7, 9)}`;

export function Timeline({ url, current }: { url: string; current: string }) {
  const [runs, setRuns] = useState<Run[]>([]);
  useEffect(() => { fetch(`/api/sims?host=${encodeURIComponent(url)}`).then((r) => r.json()).then((rs: Run[]) => setRuns(rs.filter((r) => r.status === "done" || r.id === current).reverse())).catch(() => {}); }, [url, current]);
  if (runs.length < 2) return null;
  return (
    <div className="mx-auto mt-5 flex max-w-5xl items-end justify-center gap-2 overflow-x-auto pb-1">
      {runs.map((r, i) => {
        const prev = runs[i - 1], up = prev && r.of && prev.of ? r.bought / r.of - prev.bought / prev.of : 0;
        const on = r.id === current;
        return (
          <a key={r.id} href={`#sim=${r.id}`} className={`min-w-[120px] rounded-xl border px-3 py-2 text-left transition ${on ? "border-white/50 bg-white/[0.07]" : "border-white/10 hover:border-white/30"}`}>
            <div className="flex items-baseline justify-between font-mono text-[10px] text-white/40"><span>{when(r.id)}</span>{r.round > 0 && <span style={{ color: C.brain }}>round {r.round + 1}</span>}</div>
            <div className="mt-1 flex items-baseline gap-1.5">
              <span className="font-mono text-[20px] font-semibold" style={{ color: r.of && r.bought / r.of >= 0.5 ? C.win : r.bought ? C.mid : C.loss }}>{r.status === "done" ? `${r.bought}/${r.of}` : "…"}</span>
              {prev && r.status === "done" && up !== 0 && <span className="font-mono text-[11px]" style={{ color: up > 0 ? C.win : C.loss }}>{up > 0 ? "▲" : "▼"}</span>}
            </div>
            <div className="mt-0.5 h-1 w-full overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full" style={{ width: `${r.of ? (r.bought / r.of) * 100 : 0}%`, background: C.win }} /></div>
            <div className="mt-1 max-w-[150px] truncate text-[11px] text-white/50">{r.context || (r.round ? "after learning" : "first test")}</div>
          </a>
        );
      })}
    </div>
  );
}

export function YourSites({ onOpen }: { onOpen: (id: string) => void }) {
  const [rows, setRows] = useState<Run[]>([]);
  useEffect(() => { fetch("/api/sims").then((r) => r.json()).then(setRows).catch(() => {}); }, []);
  const latest = new Map<string, Run & { tests: number }>();
  for (const r of rows) {
    if (r.status !== "done") continue;
    const cur = latest.get(r.host);
    if (!cur) latest.set(r.host, { ...r, tests: 1 }); else cur.tests++;
  }
  if (!latest.size) return null;
  return (
    <div className="mt-12 w-full">
      <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-white/35">your sites</div>
      <div className="mt-3 flex flex-wrap justify-center gap-2">
        {[...latest.values()].slice(0, 6).map((r) => (
          <button key={r.host} onClick={() => onOpen(r.id)} className="rounded-xl border border-white/15 px-4 py-2 text-left hover:border-white/40">
            <div className="text-[14px]">{r.host}</div>
            <div className="font-mono text-[11px] text-white/45">{r.bought}/{r.of} bought · {r.tests} test{r.tests > 1 ? "s" : ""}</div>
          </button>
        ))}
      </div>
    </div>
  );
}
