import { useState } from "react";
import type { Job, Test } from "./types";
import { C, LABEL, PANEL, pct, rateColor } from "./theme";

const STEP: Record<string, { label: string; color: string }> = {
  segments: { label: "customers", color: C.win }, test: { label: "shopping", color: "#8a93b8" }, result: { label: "result", color: C.mid },
  critic: { label: "critic", color: C.loss }, rewriter: { label: "rewriter", color: C.brain }, answer: { label: "sub-agent", color: C.brain },
  memory: { label: "memory", color: C.win }, matrix: { label: "matrix", color: C.win }, error: { label: "error", color: C.loss },
};

function added(before: string, now: string) {
  const norm = (w: string) => w.toLowerCase().replace(/[^\p{L}\p{N}$%]/gu, "");
  const a = before.split(/\s+/).map(norm), b = now.split(/\s+/);
  const dp = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--) for (let j = b.length - 1; j >= 0; j--) dp[i][j] = a[i] === norm(b[j]) ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const keep = new Array(b.length).fill(false);
  let i = 0, j = 0;
  while (i < a.length && j < b.length) { if (a[i] === norm(b[j])) { keep[j] = true; i++; j++; } else if (dp[i + 1][j] >= dp[i][j + 1]) i++; else j++; }
  return b.map((w, k) => ({ w, isNew: !keep[k] }));
}

function worthAdding(report: string): string[] {
  const m = report.match(/#+\s*Worth adding[^\n]*\n([\s\S]*?)(\n#+\s|$)/i);
  return m ? m[1].split("\n").filter((l) => /^\s*[-*]\s/.test(l)).map((l) => l.replace(/^\s*[-*]\s*/, "").trim()).slice(0, 8) : [];
}

function Kpi({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className={`${PANEL} p-5`}>
      <div className={LABEL}>{label}</div>
      <div className="mt-2 font-mono text-[44px] font-semibold leading-none" style={{ color: color ?? "#fff", textShadow: color ? `0 0 26px ${color}66` : undefined }}>{value}</div>
      {sub && <div className="mt-2 text-[12px] text-white/50">{sub}</div>}
    </div>
  );
}

function Grid({ job }: { job: Job }) {
  const n = job.live[0]?.n ?? job.tests.length;
  const perSeg = 2 * 2 * Math.max(1, job.shoppers.length);
  return (
    <div className="space-y-2.5">
      {job.segments.map((s, si) => {
        const cells = job.live.filter((x) => x.segment === si);
        return (
          <div key={si} className="flex items-center gap-4">
            <div className="w-64 shrink-0 truncate text-[13px] text-white/75" title={s.cares_about}>{s.name}</div>
            <span className="w-10 shrink-0 font-mono text-[11px] text-white/35">{Math.round(s.share * 100)}%</span>
            <div className="flex flex-wrap gap-1">
              {Array.from({ length: perSeg }, (_, k) => {
                const c = cells[k];
                return <span key={`${n}-${k}`} className={`h-[18px] w-[18px] rounded-[5px] ${c ? "cell-in" : ""}`} title={c ? `${c.shopper}: ${c.won ? "picked you" : "picked a competitor"}` : "waiting"}
                  style={{ background: c ? (c.won ? C.win : C.loss) : "rgba(255,255,255,0.06)", boxShadow: c ? `0 0 10px ${c.won ? C.win : C.loss}77` : undefined }} />;
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function Dashboard({ job }: { job: Job }) {
  const [trace, setTrace] = useState(false);
  const [report, setReport] = useState(false);
  const [copied, setCopied] = useState(false);
  const first: Test | undefined = job.tests[0];
  const best: Test | undefined = job.tests.length ? job.tests.reduce((a, b) => (b.pick_rate > a.pick_rate ? b : a)) : undefined;
  const improved = !!best && !!first && best !== first;
  const names = ["You", ...job.input.competitors.map((c, i) => job.input.competitor_meta?.[i]?.name ?? c.split(".")[0])];
  const latest = job.tests[job.tests.length - 1];
  const topComp = latest?.lost_to[0] ?? first?.lost_to[0];
  const running = job.status === "running";
  const testingNow = running && (job.live[0]?.n ?? 0) > job.tests.length;
  const todo = worthAdding(job.report);
  const requests = job.segments.reduce((s, x) => s + x.tasks.length, 0);

  return (
    <div className="mx-auto max-w-[1400px] space-y-5 px-6 py-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className={LABEL}>{job.input.category}</div>
          <h1 className="mt-1 font-serif text-[36px] leading-tight">{job.input.name}</h1>
        </div>
        <span className="rounded-full border px-3 py-1 font-mono text-[11px]" style={{ borderColor: running ? C.mid : job.status === "done" ? C.win : C.loss, color: running ? C.mid : job.status === "done" ? C.win : C.loss }}>
          {running ? (testingNow ? `● agents shopping · test ${job.live[0]?.n}` : "● agent thinking") : job.status === "done" ? "done" : "error"}
        </span>
      </div>

      {/* KPIs */}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Kpi label="picked today" value={first ? pct(first.pick_rate) : "…"} color={first ? rateColor(first.pick_rate) : undefined} sub={first ? `${first.wins} of ${first.total} shopping decisions` : "agents are shopping"} />
        <Kpi label="after the rewrite" value={improved ? pct(best!.pick_rate) : job.tests.length > 1 ? "no gain" : "…"} color={improved ? rateColor(best!.pick_rate) : undefined}
          sub={improved ? `+${Math.round((best!.pick_rate - first!.pick_rate) * 100)} points, using only your facts` : job.tests.length > 1 ? "your facts alone didn't beat the market, see what to add" : "the agent is working on it"} />
        <Kpi label="agents that lost you the most" value={topComp ? names[topComp.competitor + 1] : "–"} sub={topComp ? `won ${topComp.times} decisions${latest?.lost_to[0] ? " in the last test" : " before the rewrite"}` : "nobody, every agent picked you"} />
        <Kpi label="what we tested" value={`${requests || "…"}`} sub={`customer requests × ${job.shoppers.join(", ")} × shuffled orders`} />
      </div>

      {/* who agents picked */}
      {first && (
        <section className={`${PANEL} p-5`}>
          <div className="flex items-center justify-between">
            <span className={LABEL}>who the AI agents picked</span>
            <span className="flex gap-4 font-mono text-[11px] text-white/50"><span><span className="text-white/35">■</span> today</span>{improved && <span><span style={{ color: C.win }}>■</span> with the rewrite</span>}</span>
          </div>
          <div className="mt-4 space-y-2.5">
            {names.map((n, i) => {
              const a = first.share?.[i] ?? 0, b = improved ? best!.share?.[i] ?? 0 : null;
              const max = Math.max(1, ...first.share ?? [1], ...(improved ? best!.share ?? [] : []));
              return (
                <div key={n} className="flex items-center gap-4">
                  <span className={`w-56 shrink-0 truncate text-[13px] ${i === 0 ? "font-semibold text-white" : "text-white/65"}`}>{n}</span>
                  <div className="flex-1 space-y-1">
                    <div className="h-2.5 rounded-full" style={{ width: `${(a / max) * 100}%`, minWidth: a ? 6 : 0, background: i === 0 ? "rgba(255,255,255,0.35)" : "rgba(255,255,255,0.18)" }} />
                    {b !== null && <div className="h-2.5 rounded-full" style={{ width: `${(b / max) * 100}%`, minWidth: b ? 6 : 0, background: i === 0 ? C.win : "rgba(255,51,85,0.55)" }} />}
                  </div>
                  <span className="w-20 text-right font-mono text-[12px] text-white/55">{a}{b !== null && <> → <span style={{ color: i === 0 ? C.win : undefined }}>{b}</span></>}</span>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* live grid */}
      {job.segments.length > 0 && (
        <section className={`${PANEL} p-5`}>
          <div className="flex items-center justify-between">
            <span className={LABEL}>{testingNow ? "live · every square is one real AI shopper deciding" : `test ${job.tests.length} · every square is one real AI shopper's decision`}</span>
            <span className="flex gap-4 font-mono text-[11px] text-white/50"><span><span style={{ color: C.win }}>■</span> picked you</span><span><span style={{ color: C.loss }}>■</span> picked a competitor</span></span>
          </div>
          <div className="mt-4"><Grid job={job} /></div>
        </section>
      )}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        {/* fact matrix */}
        <section className={`${PANEL} overflow-x-auto p-5`}>
          <span className={LABEL}>what each listing tells buyers</span>
          {job.matrix ? (
            <table className="mt-4 w-full text-left text-[12.5px]">
              <thead><tr><th className="pb-2 pr-3 font-mono text-[10px] uppercase tracking-widest text-white/35">buyers ask</th>{job.matrix.names.map((n) => <th key={n} className={`pb-2 pr-3 font-medium ${n.startsWith("You") ? "text-white" : "text-white/55"}`}>{n}</th>)}</tr></thead>
              <tbody>
                {job.matrix.rows.map((r) => (
                  <tr key={r.attribute} className="border-t border-white/[0.07]">
                    <td className="py-2 pr-3 text-white/70">{r.attribute}</td>
                    {r.values.map((v, i) => <td key={i} className="py-2 pr-3" style={{ color: v ? (job.matrix!.names[i].startsWith("You") ? C.win : "rgba(242,239,232,0.75)") : C.loss }}>{v || "— not stated"}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <p className="mt-4 text-[13px] text-white/40">{running ? "Built when the tests finish." : "Not available for this job."}</p>}
        </section>

        {/* best listing + actions */}
        <section className={`${PANEL} p-5`}>
          <div className="flex items-center justify-between">
            <span className={LABEL}>{improved ? "your new listing" : "your listing"}</span>
            {best && <button onClick={() => { navigator.clipboard?.writeText(best.listing); setCopied(true); setTimeout(() => setCopied(false), 1500); }} className="rounded-full border border-white/20 px-3 py-1 font-mono text-[11px] text-white/70 hover:text-white">{copied ? "copied ✓" : "copy"}</button>}
          </div>
          {best ? (
            <p className="mt-3 text-[14.5px] leading-relaxed">
              {(improved ? added(first!.listing, best.listing) : best.listing.split(/\s+/).map((w) => ({ w, isNew: false }))).map((x, i) =>
                <span key={i} style={x.isNew ? { color: C.win, background: "rgba(63,240,212,0.08)" } : undefined}>{x.w} </span>)}
            </p>
          ) : <p className="mt-3 text-white/40">…</p>}
          {todo.length > 0 && (
            <div className="mt-5 border-t border-white/10 pt-4">
              <div className={LABEL}>buyers asked for these · add them if they're true</div>
              <ul className="mt-2 space-y-1.5">{todo.map((t, i) => <li key={i} className="flex gap-2 text-[13px] text-white/75"><span style={{ color: C.mid }}>☐</span>{t}</li>)}</ul>
            </div>
          )}
        </section>
      </div>

      {/* segments */}
      {best && (
        <section className={`${PANEL} p-5`}>
          <span className={LABEL}>by customer segment{improved ? " · today → with the rewrite" : ""}</span>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {best.by_segment.map((s, i) => {
              const before = first!.by_segment[i];
              return (
                <div key={s.segment} className="rounded-xl bg-white/[0.03] p-3">
                  <div className="flex items-baseline justify-between"><span className="text-[13.5px]">{s.segment}</span><span className="font-mono text-[11px] text-white/40">{Math.round(s.share * 100)}% of customers</span></div>
                  <div className="mt-1 text-[12px] text-white/45">{job.segments[i]?.cares_about}</div>
                  <div className="mt-2 font-mono text-[13px]"><span style={{ color: rateColor(before.rate) }}>{pct(before.rate)}</span>{improved && <> → <span style={{ color: rateColor(s.rate) }}>{pct(s.rate)}</span></>}</div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* why they said no */}
      {latest?.losses && latest.losses.length > 0 && (
        <section className={`${PANEL} p-5`}>
          <span className={LABEL}>why agents chose someone else, in their words</span>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            {latest.losses.slice(0, 4).map((l, i) => (
              <div key={i} className="rounded-xl bg-white/[0.03] p-3 text-[13px]">
                <div className="font-mono text-[11px] text-white/40">{l.shopper} · for “{l.request.slice(0, 70)}{l.request.length > 70 ? "…" : ""}”</div>
                <p className="mt-1.5 text-white/80"><span style={{ color: C.loss }}>Chose {l.chose}.</span> {l.reason}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* agent + report */}
      <div className="flex flex-wrap gap-2">
        <button onClick={() => setTrace(!trace)} className="rounded-full border border-white/15 px-4 py-1.5 font-mono text-[11px] text-white/60 hover:text-white">{trace ? "hide" : "show"} what the agent did ({job.steps.length})</button>
        {job.report && <button onClick={() => setReport(!report)} className="rounded-full border border-white/15 px-4 py-1.5 font-mono text-[11px] text-white/60 hover:text-white">{report ? "hide" : "read"} the full report</button>}
      </div>
      {trace && (
        <section className={`${PANEL} max-h-[360px] space-y-1.5 overflow-y-auto p-5 font-mono text-[11.5px]`}>
          {job.steps.slice().reverse().map((s, i) => (
            <div key={i} className="flex gap-3"><span className="w-14 shrink-0 text-white/30">{s.t}</span><span className="w-20 shrink-0 font-semibold uppercase" style={{ color: STEP[s.kind]?.color ?? "#8ab4ff" }}>{STEP[s.kind]?.label ?? s.kind}</span><span className="text-white/75">{s.note}</span></div>
          ))}
        </section>
      )}
      {report && <section className={`${PANEL} p-6`}><pre className="whitespace-pre-wrap font-serif text-[15px] leading-relaxed text-white/85">{job.report}</pre></section>}
    </div>
  );
}
