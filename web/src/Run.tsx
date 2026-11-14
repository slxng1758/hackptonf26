import type { Job, Test } from "./types";
import { C, LABEL, PANEL, pct, rateColor } from "./theme";

const STEP: Record<string, { label: string; color: string }> = {
  segments: { label: "customers", color: C.win }, test: { label: "shopping", color: "#8a93b8" }, result: { label: "result", color: C.mid },
  critic: { label: "critic", color: C.loss }, rewriter: { label: "rewriter", color: C.brain }, answer: { label: "sub-agent", color: C.brain },
  memory: { label: "memory", color: C.win }, error: { label: "error", color: C.loss },
};

// Word-level diff: words in `now` that were not in `before`.
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

function Grid({ job }: { job: Job }) {
  const n = job.live[0]?.n ?? job.tests.length;
  const perSeg = 2 * 2 * Math.max(1, job.shoppers.length);
  return (
    <div className="space-y-2.5">
      {job.segments.map((s, si) => {
        const cells = job.live.filter((x) => x.segment === si);
        return (
          <div key={si} className="flex items-center gap-3">
            <div className="w-56 shrink-0 truncate text-[12.5px] text-white/70" title={s.cares_about}>{s.name} <span className="font-mono text-white/35">{Math.round(s.share * 100)}%</span></div>
            <div className="flex flex-wrap gap-1">
              {Array.from({ length: perSeg }, (_, k) => {
                const c = cells[k];
                return <span key={`${n}-${k}`} className={`h-4 w-4 rounded-[4px] ${c ? "cell-in" : ""}`} title={c ? `${c.shopper}: ${c.won ? "picked you" : "picked a competitor"}` : "waiting"}
                  style={{ background: c ? (c.won ? C.win : C.loss) : "rgba(255,255,255,0.06)", boxShadow: c ? `0 0 10px ${c.won ? C.win : C.loss}88` : undefined }} />;
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function TestCard({ t, prev, competitors }: { t: Test; prev?: Test; competitors: string[] }) {
  const words = prev ? added(prev.listing, t.listing) : t.listing.split(/\s+/).map((w) => ({ w, isNew: false }));
  return (
    <div className={`${PANEL} rise p-5`}>
      <div className="flex items-baseline justify-between">
        <span className={LABEL}>test {t.n}{t.n === 1 ? " · your listing" : " · rewrite"}</span>
        <span className="font-mono text-[28px] font-semibold" style={{ color: rateColor(t.pick_rate) }}>{pct(t.pick_rate)}</span>
      </div>
      <p className="mt-2 text-[14px] leading-relaxed">
        {words.map((x, i) => <span key={i} style={x.isNew ? { color: C.win, background: "rgba(63,240,212,0.08)" } : undefined}>{x.w} </span>)}
      </p>
      <div className="mt-3 flex flex-wrap gap-2 font-mono text-[11px]">
        {Object.entries(t.by_shopper).map(([s, d]) => <span key={s} className="rounded-full border border-white/15 px-2 py-0.5 text-white/70">{s} picked you {d.wins}/{d.total}</span>)}
        {t.lost_to[0] && <span className="rounded-full border border-white/15 px-2 py-0.5 text-white/50">lost most to {competitors[t.lost_to[0].competitor]?.split(".")[0]}</span>}
      </div>
      <div className="mt-3 space-y-1.5">
        {t.by_segment.map((s) => (
          <div key={s.segment} className="flex items-center gap-3 text-[12px]">
            <span className="w-52 shrink-0 truncate text-white/60">{s.segment}</span>
            <div className="h-1.5 flex-1 rounded-full bg-white/[0.06]"><div className="h-1.5 rounded-full" style={{ width: `${s.rate * 100}%`, background: rateColor(s.rate) }} /></div>
            <span className="w-12 text-right font-mono text-white/50">{s.wins}/{s.total}</span>
          </div>
        ))}
      </div>
      {t.losses?.[0] && (
        <p className="mt-3 border-t border-white/10 pt-3 text-[12.5px] leading-snug text-white/60">
          <span style={{ color: C.loss }}>{t.losses[0].shopper} chose {t.losses[0].chose}:</span> “{t.losses[0].reason}”
        </p>
      )}
    </div>
  );
}

export function Run({ job }: { job: Job }) {
  const first = job.tests[0];
  const best = job.tests.length ? job.tests.reduce((a, b) => (b.pick_rate > a.pick_rate ? b : a)) : undefined;
  const plan = [...job.steps].reverse().find((s) => s.kind === "plan" && s.note.includes("→"));
  const testing = job.status === "running" && job.live.length > 0 && (job.tests.length < (job.live[0]?.n ?? 0));

  return (
    <div className="space-y-5">
      {/* the number */}
      <section className={`${PANEL} p-6`}>
        <div className={LABEL}>how often AI shopping agents pick {job.input.name}</div>
        <div className="mt-3 flex flex-wrap items-end gap-8">
          <div>
            <div className="font-mono text-[72px] font-semibold leading-none" style={{ color: first ? rateColor(first.pick_rate) : C.dim, textShadow: first ? `0 0 34px ${rateColor(first.pick_rate)}88` : undefined }}>{first ? pct(first.pick_rate) : "…"}</div>
            <div className="mt-1 font-mono text-[11px] uppercase tracking-widest text-white/45">today</div>
          </div>
          {best && best !== first && (
            <>
              <div className="pb-7 font-serif text-[40px] text-white/25">→</div>
              <div>
                <div className="font-mono text-[72px] font-semibold leading-none" style={{ color: rateColor(best.pick_rate), textShadow: `0 0 34px ${rateColor(best.pick_rate)}88` }}>{pct(best.pick_rate)}</div>
                <div className="mt-1 font-mono text-[11px] uppercase tracking-widest text-white/45">after the agent's rewrite</div>
              </div>
            </>
          )}
          <div className="ml-auto text-right font-mono text-[11px] text-white/45">
            shoppers: {job.shoppers.join(" · ")}<br />weighted by your customer mix
          </div>
        </div>
      </section>

      {/* live grid */}
      {job.segments.length > 0 && (
        <section className={`${PANEL} p-5`}>
          <div className="flex items-center justify-between">
            <span className={LABEL}>{testing ? `test ${job.live[0]?.n} · agents shopping now` : "last test · every square is one AI shopper's decision"}</span>
            <span className="flex gap-3 font-mono text-[11px] text-white/50"><span><span style={{ color: C.win }}>■</span> picked you</span><span><span style={{ color: C.loss }}>■</span> picked a competitor</span></span>
          </div>
          <div className="mt-4"><Grid job={job} /></div>
        </section>
      )}

      {/* tests */}
      <section className="grid gap-4 xl:grid-cols-2">
        {job.tests.map((t, i) => <TestCard key={t.n} t={t} prev={job.tests[i - 1]} competitors={job.input.competitors} />)}
      </section>

      {/* agent */}
      <section className={`${PANEL} p-5`}>
        <div className="flex items-center justify-between">
          <span className={LABEL}>the agent</span>
          <span className="font-mono text-[11px]" style={{ color: job.status === "running" ? C.mid : job.status === "done" ? C.win : C.loss }}>{job.status === "running" ? "● working" : job.status}</span>
        </div>
        {plan && (
          <ol className="mt-3 grid gap-1 sm:grid-cols-2">
            {plan.note.split(" → ").map((p, i) => <li key={i} className={`text-[12.5px] ${p.startsWith("✓") ? "text-white/35 line-through" : "text-white/85"}`}>{p.startsWith("✓") ? "☑" : "☐"} {p.replace(/^✓ /, "")}</li>)}
          </ol>
        )}
        <div className="mt-4 max-h-[300px] space-y-1.5 overflow-y-auto font-mono text-[11.5px]">
          {job.steps.filter((s) => s.kind !== "plan").slice().reverse().map((s, i) => (
            <div key={i} className="flex gap-3"><span className="w-14 shrink-0 text-white/30">{s.t}</span><span className="w-20 shrink-0 font-semibold uppercase" style={{ color: STEP[s.kind]?.color ?? "#fff" }}>{STEP[s.kind]?.label ?? s.kind}</span><span className="text-white/75">{s.note}</span></div>
          ))}
        </div>
      </section>

      {job.report && (
        <section className={`${PANEL} rise p-6`}>
          <div className={LABEL}>the agent's report</div>
          <pre className="mt-3 whitespace-pre-wrap font-serif text-[15px] leading-relaxed text-white/85">{job.report}</pre>
        </section>
      )}
    </div>
  );
}
