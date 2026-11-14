import { useEffect, useMemo, useRef, useState } from "react";
import type { Gen, Run } from "./types";
import { Chart } from "./Chart";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, init);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

const ORIGIN: Record<string, string> = {
  village: "Dirty water made people sick. Boiling it stopped the sickness.",
  village_oral: "Dirty water made people sick. Boiling it stopped the sickness.",
  village_myth: "Dirty water made people sick. Boiling it stopped the sickness.",
  company: "Stale cache from the old schema broke sessions. Flushing it fixed them.",
};

const WORLDS = [
  { id: "village_myth", label: "The Well, as legend" },
  { id: "village_oral", label: "The Well, without healers" },
  { id: "village", label: "The Well" },
  { id: "company", label: "The Runbook" },
];

function saying(run: Run, g?: Gen) {
  if (!g) return "";
  if (g.gen === 0) return run.truth_short ?? ORIGIN[run.preset] ?? run.truth;
  if (!g.score) return "…";
  if (g.score.short) return g.score.short;
  const first = (g.score.rule || "").split(/[.;]/)[0].trim();
  const w = first.split(/\s+/);
  return w.length > 9 ? w.slice(0, 9).join(" ") + "…" : first || "Nothing survived.";
}

// Word-level diff: which words in `now` were not in `before` (LCS on normalized words).
function changedWords(before: string, now: string): boolean[] {
  const norm = (w: string) => w.toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
  const a = before.split(/\s+/).map(norm), b = now.split(/\s+/).map(norm);
  const dp = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--) for (let j = b.length - 1; j >= 0; j--)
    dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const kept = new Array(b.length).fill(false);
  let i = 0, j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { kept[j] = true; i++; j++; } else if (dp[i + 1][j] >= dp[i][j + 1]) i++; else j++;
  }
  return kept.map((k, idx) => !k && b[idx] !== "");
}

function tone(g?: Gen) {
  const s = g?.score;
  if (!s || g!.gen === 0) return "var(--color-belief)";
  if (s.myth >= 0.5) return "var(--color-myth)";
  if (s.belief >= 0.6) return "var(--color-belief)";
  return "var(--color-practice)";
}

function moment(gens: Gen[]): string | null {
  const s = gens.filter((g) => g.score && g.gen > 0 && Object.keys(g.archive).length > 0);
  let g;
  if ((g = s.find((x) => x.score!.belief < 0.4 && x.score!.practice >= 0.6))) return `The ritual survived. The reason died in generation ${g.gen}.`;
  if ((g = s.find((x) => x.score!.myth >= 0.5))) return `By generation ${g.gen}, it was sacred.`;
  if ((g = s.find((x) => x.score!.practice < 0.4 && x.score!.belief >= 0.6))) return `They still knew why, but stopped doing it in generation ${g.gen}.`;
  for (let i = 1; i < s.length; i++) {
    if (s[i - 1].score!.practice - s[i].score!.practice >= 0.25) {
      const back = s.slice(i + 1).find((x) => x.score!.practice >= s[i - 1].score!.practice - 0.05);
      return back ? `It nearly died in generation ${s[i].gen}. A crisis brought it back.` : `It started dying in generation ${s[i].gen}.`;
    }
  }
  return null;
}

export function App() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [sel, setSel] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [tab, setTab] = useState<"archive" | "voices" | "trace">("archive");
  const [showNew, setShowNew] = useState(false);
  const [form, setForm] = useState({ preset: "village_myth", generations: 10, limit: 200 });
  const [err, setErr] = useState<string | null>(null);
  const follow = useRef(true);

  const loadRuns = () => api<Run[]>("/api/runs").then((r) => { setRuns(r); if (!runId && r[0]) setRunId(r[0].id); }).catch((e) => setErr(String(e)));
  useEffect(() => { loadRuns(); }, []); // eslint-disable-line

  useEffect(() => {
    if (!runId) return;
    let alive = true;
    const tick = () => api<Run>(`/api/runs/${runId}`).then((r) => {
      if (!alive) return;
      setRun(r);
      if (follow.current) setSel(Math.max(0, (r.generations?.length ?? 1) - 1));
    }).catch((e) => setErr(String(e)));
    tick();
    const t = setInterval(() => { if (run?.status !== "done") tick(); }, 3000);
    return () => { alive = false; clearInterval(t); };
  }, [runId, run?.status]); // eslint-disable-line

  const gens = run?.generations ?? [];
  const last = gens.length - 1;
  const g = gens.find((x) => x.gen === sel) ?? gens[last];
  const prev = g && g.gen > 0 ? gens.find((x) => x.gen === g.gen - 1) : undefined;
  const headline = useMemo(() => moment(gens), [gens]);
  const pick = (n: number) => { if (n <= last) { follow.current = n === last; setPlaying(false); setSel(n); } };

  // play: walk from the origin to the newest generation
  useEffect(() => {
    if (!playing) return;
    if (sel >= last) { setPlaying(false); follow.current = true; return; }
    const t = setTimeout(() => setSel((s) => s + 1), 2600);
    return () => clearTimeout(t);
  }, [playing, sel, last]);

  const play = () => { follow.current = false; setSel(0); setPlaying(true); };

  async function start(e: React.FormEvent) {
    e.preventDefault();
    try {
      const { id } = await api<{ id: string }>("/api/runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form) });
      follow.current = true; setRunId(id); setRun(null); setSel(0); setShowNew(false); loadRuns();
    } catch (e) { setErr(String(e)); }
  }

  const now = run && g ? saying(run, g) : "";
  const before = run && prev ? saying(run, prev) : "";
  const fresh = prev ? changedWords(before, now) : [];
  const words = now.split(/\s+/);
  const atEnd = !!g && g.gen === last && run?.status === "done";

  return (
    <div className="min-h-screen">
      {/* ---------- the stage ---------- */}
      <section className="relative flex min-h-screen flex-col bg-[#18120e] text-paper">
        <header className="flex items-center justify-between gap-3 px-5 py-4 md:px-10">
          <div className="flex items-baseline gap-3">
            <h1 className="font-serif text-[22px] font-extrabold">Inheritance</h1>
            {run && <span className="hidden font-serif text-[15px] italic text-paper/50 sm:inline">{run.title}</span>}
          </div>
          <div className="flex items-center gap-2">
            {runs.length > 0 && (
              <select value={runId ?? ""} onChange={(e) => { follow.current = true; setPlaying(false); setRunId(e.target.value); setRun(null); }} className="max-w-[200px] rounded-full border border-paper/20 bg-transparent px-3 py-1.5 text-[12px] text-paper/80">
                {runs.map((r) => <option key={r.id} value={r.id} className="text-ink">{r.title} · {r.status}</option>)}
              </select>
            )}
            <button onClick={() => setShowNew(!showNew)} className="rounded-full bg-paper px-4 py-1.5 text-[13px] font-semibold text-ink">New world</button>
          </div>
        </header>
        {showNew && (
          <form onSubmit={start} className="flex flex-wrap items-center gap-3 px-5 pb-2 text-[13px] text-paper/80 md:px-10">
            <select value={form.preset} onChange={(e) => setForm({ ...form, preset: e.target.value })} className="rounded-lg border border-paper/20 bg-transparent px-3 py-2">
              {WORLDS.map((w) => <option key={w.id} value={w.id} className="text-ink">{w.label}</option>)}
            </select>
            <label className="flex items-center gap-2">generations <input type="number" min={1} max={60} value={form.generations} onChange={(e) => setForm({ ...form, generations: +e.target.value })} className="w-16 rounded-lg border border-paper/20 bg-transparent px-2 py-2" /></label>
            <label className="flex items-center gap-2">memory <input type="number" min={100} max={8000} step={50} value={form.limit} onChange={(e) => setForm({ ...form, limit: +e.target.value })} className="w-20 rounded-lg border border-paper/20 bg-transparent px-2 py-2" /> chars</label>
            <button className="rounded-lg bg-seal px-4 py-2 font-semibold text-white">Begin</button>
          </form>
        )}
        {err && <p className="mx-5 rounded-lg bg-seal/30 px-3 py-2 text-[13px] md:mx-10">{err}</p>}

        <div className="flex flex-1 flex-col items-center justify-center px-6 text-center">
          {run && g ? (
            <>
              <div className="font-mono text-[12px] uppercase tracking-[0.3em] text-paper/40">
                {g.gen === 0 ? "what really happened" : `generation ${g.gen}`}
              </div>
              <p key={`${run.id}-${g.gen}`} className="saying mt-6 max-w-4xl font-serif text-[40px] leading-[1.15] md:text-[64px]" style={{ color: g.gen === 0 ? "var(--color-paper)" : undefined }}>
                {words.map((w, i) => (
                  <span key={i} className={fresh[i] ? "fresh" : ""} style={{ animationDelay: `${150 + i * 60}ms`, marginRight: "0.25em", ...(fresh[i] ? { color: tone(g) } : {}) }}>
                    {w}
                  </span>
                ))}
              </p>
              {g.gen > 0 && <p className="mt-6 max-w-xl text-[14px] text-paper/45">{(g.event.split(/[.]/)[0] || g.event).trim()}</p>}
              {atEnd && headline && <p className="mt-10 font-serif text-[22px] italic text-seal">{headline}</p>}
            </>
          ) : (
            <p className="font-serif text-[28px] text-paper/50">{runs.length ? "Loading…" : "Start a new world."}</p>
          )}
        </div>

        {run && (
          <div className="px-5 pb-8 md:px-10">
            <div className="mx-auto flex max-w-4xl items-center gap-4">
              <button onClick={playing ? () => setPlaying(false) : play} className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-paper text-[15px] text-ink" aria-label={playing ? "Pause" : "Play from the origin"}>
                {playing ? "❚❚" : "▶"}
              </button>
              <div className="relative flex flex-1 items-center justify-between">
                <div className="absolute inset-x-0 top-1/2 h-px bg-paper/15" />
                {Array.from({ length: run.generations_planned + 1 }, (_, n) => {
                  const x = gens.find((q) => q.gen === n);
                  const on = !!x && x.gen === g?.gen;
                  return (
                    <button key={n} onClick={() => pick(n)} disabled={!x} className="relative z-10 grid place-items-center" aria-label={`Generation ${n}`}>
                      <span className={`block rounded-full transition-all ${on ? "h-5 w-5 ring-4 ring-paper/20" : "h-3 w-3"} ${x ? "" : "border border-dashed border-paper/30"}`} style={x ? { background: tone(x) } : undefined} />
                      <span className={`absolute top-6 font-mono text-[10px] ${on ? "text-paper" : "text-paper/35"}`}>{n}</span>
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="mx-auto mt-10 flex max-w-4xl justify-center gap-6 font-mono text-[12px] text-paper/60">
              <span><span className="text-belief">●</span> truth kept {g?.score ? Math.round(g.score.belief * 100) : "–"}%</span>
              <span><span className="text-practice">●</span> still done {g?.score ? Math.round(g.score.practice * 100) : "–"}%</span>
              <span><span className="text-myth">●</span> sacred {g?.score ? Math.round(g.score.myth * 100) : "–"}%</span>
              {run.status === "running" && <span className="text-practice">· living gen {gens.length} of {run.generations_planned}</span>}
            </div>
          </div>
        )}
      </section>

      {/* ---------- the records, below the fold ---------- */}
      {run && g && (
        <section className="mx-auto max-w-5xl px-4 py-14 md:px-8">
          <h2 className="font-serif text-[26px] font-semibold">The records</h2>
          <div className="mt-5 rounded-3xl bg-card p-5 shadow-sm ring-1 ring-ink/10">
            <Chart gens={gens} total={run.generations_planned} selected={g.gen} onSelect={pick} />
          </div>
          <div className="mt-6 rounded-3xl bg-card shadow-sm ring-1 ring-ink/10">
            <div className="flex gap-1 border-b border-ink/10 px-4 pt-3">
              {(["archive", "voices", "trace"] as const).map((t) => (
                <button key={t} onClick={() => setTab(t)} className={`rounded-t-lg px-3 py-1.5 text-[13px] font-semibold ${tab === t ? "bg-paper2 text-ink" : "text-ink3 hover:text-ink2"}`}>
                  {t === "archive" ? `What gen ${g.gen} kept` : t === "voices" ? "Who said what" : "Agent trace"}
                </button>
              ))}
            </div>
            <div className="max-h-[480px] overflow-y-auto p-6">
              {tab === "archive" && (Object.keys(g.archive).length ? Object.entries(g.archive).map(([name, body]) => (
                <pre key={name} className="rule-line mb-6 whitespace-pre-wrap font-serif text-[15px] leading-[28px]">{body}</pre>
              )) : <p className="text-ink3">Nothing was saved this generation.</p>)}
              {tab === "voices" && (Object.keys(g.drafts).length ? (
                <div className="grid gap-4 md:grid-cols-2">
                  {Object.entries(g.drafts).map(([name, body]) => (
                    <article key={name} className="rounded-2xl bg-paper p-4">
                      <div className="text-[11px] font-bold uppercase tracking-widest text-practice">{name.replace(".md", "")}</div>
                      <pre className="mt-2 whitespace-pre-wrap font-serif text-[14px] leading-relaxed">{body}</pre>
                    </article>
                  ))}
                </div>
              ) : <p className="text-ink3">The origin. No one has retold it yet.</p>)}
              {tab === "trace" && (g.trace.length ? (
                <ol className="space-y-1.5 font-mono text-[12px]">
                  {g.trace.map((s, i) => (
                    <li key={i} className="flex gap-3"><span className="w-14 shrink-0 text-ink3">{s.tool}</span><span className="w-20 shrink-0 font-semibold">{s.who}</span><span className="truncate text-ink2">{s.note}</span></li>
                  ))}
                </ol>
              ) : <p className="text-ink3">No agents ran for the origin.</p>)}
            </div>
          </div>
          <p className="mt-8 text-center font-mono text-[11px] text-ink3">
            memory {run.limit} chars · villagers {run.models.villagers} · evaluator {run.models.evaluator}
            {run.error && <span className="text-seal"> · stopped: {run.error}</span>}
          </p>
        </section>
      )}
    </div>
  );
}
