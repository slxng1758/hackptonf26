import { useEffect, useState } from "react";

interface Step { t: string; kind: string; note: string }
interface Trial {
  message: string; brief: string[]; worlds: number; sick_mean: number; sick_sd: number; acting_mean: number; population: number;
  distorters: [string, number][]; top_variants: { text: string; practice: number; myth: number; role: string }[]; replay_id: string;
}
interface Job {
  id: string; message: string; description: string; status: string; error: string | null; steps: Step[]; report: string;
  community: { name: string; groups: { name: string }[]; messengers: { role: string; voice: string }[]; hubs: { role: string }[]; hazard: string; action: string; why: string } | null;
  trials: Trial[];
}

const EXAMPLES = [
  { label: "Heat wave · Chinatown", message: "During the heat wave, drink water every hour and spend afternoons in a cooling center.", community: "Manhattan Chinatown: elderly Cantonese speakers, churches and temples, WeChat groups, family association halls, corner herbal shops" },
  { label: "Boil-water notice · rural town", message: "Boil tap water for one minute before drinking until further notice.", community: "A rural farming town: churches, a feed store, high school sports parents, a Facebook community page, older residents on well water" },
  { label: "Measles · suburb", message: "Measles is spreading. Check that your children have had two MMR doses and call your clinic if not.", community: "A suburban district: parent group chats, a homeschool co-op, pediatric clinics, wellness influencers, school nurses" },
];

const KIND: Record<string, { label: string; color: string }> = {
  plan: { label: "PLAN", color: "#8ab4ff" }, community: { label: "COMMUNITY", color: "#3ff0d4" }, trial: { label: "SIM", color: "#7b84a8" },
  result: { label: "RESULT", color: "#ffb547" }, critic: { label: "CRITIC", color: "#ff6b8a" }, rewriter: { label: "REWRITER", color: "#d16bff" },
  answer: { label: "SUB-AGENT", color: "#d16bff" }, file: { label: "FILE", color: "#7b84a8" }, error: { label: "ERROR", color: "#ff3355" },
};

export function Lab() {
  const [message, setMessage] = useState(EXAMPLES[0].message);
  const [community, setCommunity] = useState(EXAMPLES[0].community);
  const [jobs, setJobs] = useState<{ id: string; message: string; status: string; trials: number }[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/lab").then((r) => r.json()).then((l) => { setJobs(l); if (l[0]) setJobId(l[0].id); }).catch(() => {});
  }, []);
  useEffect(() => {
    if (!jobId) return;
    let alive = true;
    const tick = () => fetch(`/api/lab/${jobId}`).then((r) => r.json()).then((j: Job) => alive && setJob(j)).catch(() => {});
    tick();
    const t = setInterval(() => { if (job?.status !== "done" && job?.status !== "error") tick(); }, 2000);
    return () => { alive = false; clearInterval(t); };
  }, [jobId, job?.status]); // eslint-disable-line

  async function run() {
    setErr(null);
    try {
      const r = await fetch("/api/lab", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message, community }) });
      if (!r.ok) throw new Error(await r.text());
      const { id } = await r.json();
      setJob(null); setJobId(id);
      setJobs((j) => [{ id, message, status: "running", trials: 0 }, ...j]);
    } catch (e) { setErr(String(e)); }
  }

  const plan = [...(job?.steps ?? [])].reverse().find((s) => s.kind === "plan" && s.note.includes("→"));
  const best = job?.trials.length ? job.trials.reduce((a, b) => (b.acting_mean > a.acting_mean ? b : a)) : null;
  const base = job?.trials[0];

  return (
    <div className="min-h-screen bg-[#07070c] px-6 pb-16 pt-16 text-white">
      <div className="mx-auto grid max-w-7xl gap-6 lg:grid-cols-[380px_minmax(0,1fr)]">
        {/* input */}
        <aside className="space-y-4">
          <div>
            <div className="font-mono text-[11px] uppercase tracking-[0.35em] text-white/40">Message Lab</div>
            <h1 className="mt-1 font-serif text-[30px] leading-tight">Will your health message survive being retold?</h1>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {EXAMPLES.map((e) => (
              <button key={e.label} onClick={() => { setMessage(e.message); setCommunity(e.community); }} className="rounded-full border border-white/15 px-3 py-1 font-mono text-[10.5px] text-white/60 hover:border-white/40 hover:text-white">{e.label}</button>
            ))}
          </div>
          <label className="block">
            <span className="font-mono text-[10px] uppercase tracking-widest text-white/40">Your message</span>
            <textarea value={message} onChange={(e) => setMessage(e.target.value)} rows={3} className="mt-1 w-full rounded-xl border border-white/15 bg-white/[0.04] p-3 font-serif text-[17px] leading-snug outline-none focus:border-[#3ff0d4]" />
          </label>
          <label className="block">
            <span className="font-mono text-[10px] uppercase tracking-widest text-white/40">The community, in your words</span>
            <textarea value={community} onChange={(e) => setCommunity(e.target.value)} rows={4} className="mt-1 w-full rounded-xl border border-white/15 bg-white/[0.04] p-3 text-[14px] leading-snug text-white/85 outline-none focus:border-[#3ff0d4]" />
          </label>
          <button onClick={run} className="w-full rounded-xl bg-[#3ff0d4] py-3 font-semibold text-black shadow-[0_0_40px_rgba(63,240,212,0.35)] hover:brightness-110">Stress-test it</button>
          {err && <p className="text-[12px] text-[#ff3355]">{err}</p>}
          {jobs.length > 0 && (
            <select value={jobId ?? ""} onChange={(e) => { setJob(null); setJobId(e.target.value); }} className="w-full rounded-xl border border-white/15 bg-transparent px-3 py-2 font-mono text-[11px] text-white/70">
              {jobs.map((j) => <option key={j.id} value={j.id} className="text-black">{j.status} · {j.message.slice(0, 50)}</option>)}
            </select>
          )}

          {job?.community && (
            <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
              <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-white/40">community the agent built</div>
              <div className="mt-2 text-[14px] font-semibold">{job.community.name}</div>
              <div className="mt-1 text-[12px] text-white/60">{job.community.groups.map((g) => g.name).join(" · ")}</div>
              <div className="mt-3 space-y-1.5">
                {job.community.messengers.map((m) => <div key={m.role} className="text-[12px]"><span className="font-semibold text-[#3ff0d4]">{m.role}</span> <span className="text-white/55">· {m.voice}</span></div>)}
                <div className="text-[12px] text-white/55">connected by {job.community.hubs.map((h) => h.role).join(", ")}</div>
              </div>
              <div className="mt-3 border-t border-white/10 pt-2 text-[12px] text-white/60"><b className="text-white/85">Action:</b> {job.community.action}. <b className="text-white/85">Why:</b> {job.community.why}</div>
            </div>
          )}
        </aside>

        <main className="min-w-0 space-y-6">
          {/* headline result */}
          {best && base && (
            <section className="rounded-3xl border border-white/10 bg-gradient-to-br from-white/[0.06] to-transparent p-6">
              <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-white/40">{job?.status === "done" ? "result" : "so far"}</div>
              <div className="mt-2 flex flex-wrap items-end gap-8">
                <div>
                  <div className="font-mono text-[56px] font-semibold leading-none text-[#3ff0d4]" style={{ textShadow: "0 0 30px #3ff0d4" }}>{Math.round(best.acting_mean * 100)}%</div>
                  <div className="mt-1 font-mono text-[11px] uppercase tracking-widest text-white/50">still take the action{best !== base && <> · was {Math.round(base.acting_mean * 100)}%</>}</div>
                </div>
                <div>
                  <div className="font-mono text-[56px] font-semibold leading-none text-[#ff3355]" style={{ textShadow: "0 0 30px #ff3355" }}>{best.sick_mean.toFixed(1)}</div>
                  <div className="mt-1 font-mono text-[11px] uppercase tracking-widest text-white/50">fell sick, of {best.population}{best !== base && <> · was {base.sick_mean.toFixed(1)}</>}</div>
                </div>
              </div>
              {best !== base && <p className="mt-4 font-serif text-[22px] leading-snug">Best version: “{best.message}”{best.brief.length > 0 && <span className="text-white/60"> · brief {best.brief.join(", ")} first</span>}</p>}
            </section>
          )}

          {/* trials */}
          {job && job.trials.length > 0 && (
            <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {job.trials.map((t, i) => (
                <div key={i} className={`rounded-2xl border p-4 ${t === best ? "border-[#3ff0d4]/60 bg-[#3ff0d4]/[0.05]" : "border-white/10 bg-white/[0.03]"}`}>
                  <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-white/40">trial {i + 1}{i === 0 ? " · original" : ""}{t === best && i > 0 ? " · best" : ""}</div>
                  <p className="mt-2 font-serif text-[16px] leading-snug">“{t.message}”</p>
                  {t.brief.length > 0 && <p className="mt-1 font-mono text-[10.5px] text-[#d16bff]">briefed: {t.brief.join(", ")}</p>}
                  <div className="mt-3 flex gap-5 font-mono text-[12px]">
                    <span className="text-[#3ff0d4]">{Math.round(t.acting_mean * 100)}% act</span>
                    <span className="text-[#ff3355]">{t.sick_mean.toFixed(1)} ± {t.sick_sd.toFixed(1)} sick</span>
                    <span className="text-white/40">{t.worlds} worlds</span>
                  </div>
                  <div className="mt-3 space-y-1.5">
                    {t.top_variants.slice(1, 4).map((v, k) => (
                      <p key={k} className="text-[12px] leading-snug text-white/70"><span className={v.practice < 0.5 ? "text-[#ff6b8a]" : "text-white/40"}>{v.role}:</span> “{v.text}”</p>
                    ))}
                  </div>
                  {t.distorters.length > 0 && <p className="mt-2 font-mono text-[10.5px] text-[#ff6b8a]">distorted most: {t.distorters.map((d) => d[0]).join(", ")}</p>}
                  <div className="mt-3 flex gap-2">
                    <a href={`#/village?run=${t.replay_id}`} className="rounded-full border border-white/20 px-3 py-1 font-mono text-[10.5px] text-white/70 hover:text-white">watch it spread →</a>
                    <a href={`#/paper?run=${t.replay_id}`} className="rounded-full border border-white/20 px-3 py-1 font-mono text-[10.5px] text-white/70 hover:text-white">front page →</a>
                  </div>
                </div>
              ))}
            </section>
          )}

          {/* the agent, live */}
          <section className="rounded-3xl border border-white/10 bg-white/[0.02] p-5">
            <div className="flex items-center justify-between">
              <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-white/40">the agent, live</div>
              {job && <span className={`font-mono text-[11px] ${job.status === "running" ? "text-[#ffb547]" : job.status === "done" ? "text-[#3ff0d4]" : "text-[#ff3355]"}`}>{job.status === "running" ? "● working" : job.status}</span>}
            </div>
            {plan && (
              <ol className="mt-3 space-y-1">
                {plan.note.split(" → ").map((p, i) => (
                  <li key={i} className={`text-[13px] ${p.startsWith("✓") ? "text-white/40 line-through" : "text-white/85"}`}>{p.startsWith("✓") ? "☑" : "☐"} {p.replace(/^✓ /, "")}</li>
                ))}
              </ol>
            )}
            <div className="mt-4 max-h-[360px] space-y-1.5 overflow-y-auto font-mono text-[11.5px]">
              {(job?.steps ?? []).filter((s) => s.kind !== "plan").slice().reverse().map((s, i) => (
                <div key={i} className="flex gap-3">
                  <span className="w-14 shrink-0 text-white/30">{s.t}</span>
                  <span className="w-20 shrink-0 font-semibold" style={{ color: KIND[s.kind]?.color ?? "#fff" }}>{KIND[s.kind]?.label ?? s.kind}</span>
                  <span className="text-white/75">{s.note}</span>
                </div>
              ))}
              {!job && <p className="text-white/40">Write a message, describe the community, and press Stress-test it.</p>}
            </div>
          </section>

          {job?.report && (
            <section className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
              <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-white/40">the agent's report</div>
              <pre className="mt-3 whitespace-pre-wrap font-serif text-[15px] leading-relaxed text-white/85">{job.report}</pre>
            </section>
          )}
        </main>
      </div>
    </div>
  );
}
