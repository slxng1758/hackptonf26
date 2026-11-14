import { useEffect, useMemo, useRef, useState } from "react";
import { C, KIND_COLOR } from "./theme";
import { Header, Legend, PANEL } from "./ui";

interface Person { id: number; village: number; role: string; x: number; y: number }
interface Variant { id: number; parent: number | null; text: string; short: string; day: number; person: number; role: string; belief: number; practice: number; myth: number }
interface Frame { day: number; b: (number | null)[]; h: string; sick_total: number }
interface Epi {
  id: string; scenario: string; days: number; population: number; ever_sick: number;
  villages: { name: string; water: string }[]; contaminated: Record<string, number>;
  people: Person[]; edges: [number, number][]; variants: Variant[]; frames: Frame[];
}

// What a variant does to people, in four colors.
function kind(v?: Variant) {
  if (!v) return "none";
  if (v.practice < 0.4) return "unsafe";
  if (v.myth >= 0.5) return "myth";
  if (v.belief >= 0.55) return "truth";
  return "ritual";
}
const COLOR: Record<string, string> = KIND_COLOR;
const LABEL: Record<string, string> = { truth: "knows why", ritual: "boils, forgot why", myth: "sacred myth", unsafe: "doesn't boil" };
const SICK = C.sick;

interface Sweep { seeds: number; scenarios: Record<string, { sick: number[]; mean: number; sd: number; population: number }> }
const SC_LABEL: Record<string, string> = { baseline: "one healer", healers_everywhere: "healers everywhere", priests_everywhere: "priests everywhere" };

interface Particle { from: number; to: number; t: number; color: string }

export function Infodemic() {
  const [list, setList] = useState<{ id: string; scenario: string; ever_sick: number; population: number }[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [data, setData] = useState<Epi | null>(null);
  const [day, setDay] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [toast, setToast] = useState<Variant | null>(null);
  const [sweep, setSweep] = useState<Sweep | null>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const particles = useRef<Particle[]>([]);
  const dayRef = useRef(0);
  dayRef.current = day;

  useEffect(() => {
    fetch("/api/epi").then((r) => r.json()).then((l) => { setList(l); if (l[0]) setRunId(l[0].id); }).catch(() => {});
  }, []);
  useEffect(() => {
    fetch("/api/epi/sweep").then((r) => (r.ok ? r.json() : null)).then(setSweep).catch(() => {});
  }, []);
  useEffect(() => {
    if (!runId) return;
    fetch(`/api/epi/${runId}`).then((r) => r.json()).then((d: Epi) => { setData(d); setDay(0); particles.current = []; }).catch(() => {});
  }, [runId]);

  const nbrs = useMemo(() => {
    const m = new Map<number, number[]>();
    data?.edges.forEach(([a, b]) => { m.set(a, [...(m.get(a) ?? []), b]); m.set(b, [...(m.get(b) ?? []), a]); });
    return m;
  }, [data]);

  // advance a day while playing
  useEffect(() => {
    if (!playing || !data) return;
    if (day >= data.days) { setPlaying(false); return; }
    const t = setTimeout(() => setDay((d) => d + 1), 420);
    return () => clearTimeout(t);
  }, [playing, day, data]);

  // when the day changes: launch a light particle for every saying that changed hands, flash new variants
  useEffect(() => {
    if (!data || day === 0) return;
    const prev = data.frames[day - 1], cur = data.frames[day];
    cur.b.forEach((v, i) => {
      if (v === null || v === prev.b[i]) return;
      const src = (nbrs.get(i) ?? []).find((n) => prev.b[n] === v) ?? (nbrs.get(i) ?? []).find((n) => prev.b[n] !== null);
      if (src !== undefined) particles.current.push({ from: src, to: i, t: 0, color: COLOR[kind(data.variants[v])] });
    });
    const born = data.variants.filter((v) => v.day === day && v.parent !== null);
    if (born.length) { setToast(born[born.length - 1]); const t = setTimeout(() => setToast(null), 2200); return () => clearTimeout(t); }
  }, [day, data, nbrs]);

  // render loop
  useEffect(() => {
    const c = canvas.current;
    if (!c || !data) return;
    const ctx = c.getContext("2d")!;
    let raf = 0;
    const draw = (now: number) => {
      const dpr = Math.min(window.devicePixelRatio, 2);
      const w = c.clientWidth, h = c.clientHeight;
      if (c.width !== w * dpr) { c.width = w * dpr; c.height = h * dpr; }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const S = Math.min(w, h) * 0.46, cx = w / 2, cy = h / 2;
      const P = (p: Person) => [cx + p.x * S, cy + p.y * S] as const;
      const f = data.frames[dayRef.current];

      // villages: soft halos, red when their water is bad
      const centers = data.villages.map((_, vi) => {
        const ms = data.people.filter((p) => p.village === vi);
        return [ms.reduce((s, p) => s + p.x, 0) / ms.length, ms.reduce((s, p) => s + p.y, 0) / ms.length];
      });
      centers.forEach(([x, y], vi) => {
        const bad = data.contaminated[vi] !== undefined && dayRef.current >= data.contaminated[vi];
        const g = ctx.createRadialGradient(cx + x * S, cy + y * S, 0, cx + x * S, cy + y * S, S * 0.32);
        g.addColorStop(0, bad ? "rgba(255,51,85,0.13)" : "rgba(63,240,212,0.05)");
        g.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(cx + x * S, cy + y * S, S * 0.32, 0, Math.PI * 2); ctx.fill();
        ctx.font = "600 11px 'JetBrains Mono', monospace"; ctx.textAlign = "center";
        ctx.fillStyle = bad ? C.sick : "rgba(242,239,232,0.55)";
        const ly = cy + y * S + (y > 0 ? S * 0.3 : -S * 0.3);
        ctx.fillText(`${data.villages[vi].name}${bad ? ((data as { message?: string }).message ? " · exposed" : " · well gone bad") : ""}`, cx + x * S, ly);
      });

      // edges
      ctx.lineWidth = 0.6;
      ctx.strokeStyle = "rgba(140,150,220,0.07)";
      ctx.beginPath();
      data.edges.forEach(([a, b]) => { const [x1, y1] = P(data.people[a]); const [x2, y2] = P(data.people[b]); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); });
      ctx.stroke();

      // people
      ctx.globalCompositeOperation = "lighter";
      data.people.forEach((p, i) => {
        const [x, y] = P(p);
        const v = f.b[i];
        const col = COLOR[kind(v === null ? undefined : data.variants[v])];
        const hub = p.village === -1;
        const r = p.role === "priest" || p.role === "healer" || hub ? 5.5 : 3.8;
        const glow = ctx.createRadialGradient(x, y, 0, x, y, r * 4);
        glow.addColorStop(0, col + "aa"); glow.addColorStop(1, col + "00");
        ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(x, y, r * 4, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = col; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
        if (f.h[i] === "I") {
          const pulse = 0.5 + 0.5 * Math.sin(now / 160 + i);
          ctx.strokeStyle = SICK; ctx.lineWidth = 2;
          ctx.globalAlpha = 0.5 + 0.5 * pulse;
          ctx.beginPath(); ctx.arc(x, y, r + 4 + pulse * 5, 0, Math.PI * 2); ctx.stroke();
          ctx.globalAlpha = 1;
        }
      });

      // particles: a saying flying along a friendship
      particles.current = particles.current.filter((pt) => pt.t < 1);
      particles.current.forEach((pt) => {
        pt.t += 0.035;
        const [x1, y1] = P(data.people[pt.from]); const [x2, y2] = P(data.people[pt.to]);
        for (let k = 0; k < 6; k++) {
          const tt = Math.max(0, pt.t - k * 0.03);
          const x = x1 + (x2 - x1) * tt, y = y1 + (y2 - y1) * tt;
          ctx.fillStyle = pt.color; ctx.globalAlpha = (1 - k / 6) * 0.9;
          ctx.beginPath(); ctx.arc(x, y, 2.6 - k * 0.3, 0, Math.PI * 2); ctx.fill();
        }
        ctx.globalAlpha = 1;
      });
      ctx.globalCompositeOperation = "source-over";
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [data]);

  if (!data) {
    return <div className="grid min-h-screen place-items-center bg-[#08080d] font-mono text-[13px] text-white/40">{list.length ? "loading the outbreak…" : "no infodemic runs yet · python -m sim.epidemic"}</div>;
  }

  const f = data.frames[day];
  const counts: Record<string, number> = { truth: 0, ritual: 0, myth: 0, unsafe: 0, none: 0 };
  f.b.forEach((v) => { counts[kind(v === null ? undefined : data.variants[v])]++; });
  const sickNow = [...f.h].filter((c) => c === "I").length;
  const share = new Map<number, number>();
  f.b.forEach((v) => v !== null && share.set(v, (share.get(v) ?? 0) + 1));
  const alive = data.variants.filter((v) => v.day <= day);
  const depth = (v: Variant): number => (v.parent === null ? 0 : 1 + depth(data.variants[v.parent]));
  const sickSeries = data.frames.map((fr) => fr.sick_total);
  const maxSick = Math.max(1, ...sickSeries);

  return (
    <div className="relative h-screen overflow-hidden bg-[#08080d] text-white">
      <canvas ref={canvas} className="absolute inset-0 h-full w-full" />

      {/* top: title + counters */}
      <Header eyebrow="network view" title={`Day ${day} of ${data.days}`} sub={`${data.population} people · ${data.villages.length} groups`} />
      <div className="pointer-events-none absolute right-6 top-16 flex items-start justify-end">
        <div className="flex gap-6 text-right">
          <div>
            <div className="font-mono text-[44px] font-semibold leading-none" style={{ color: SICK, textShadow: `0 0 24px ${SICK}` }}>{f.sick_total}</div>
            <div className="mt-1 font-mono text-[11px] uppercase tracking-widest text-white/50">fell sick</div>
          </div>
          <div>
            <div className="font-mono text-[44px] font-semibold leading-none text-white/90">{sickNow}</div>
            <div className="mt-1 font-mono text-[11px] uppercase tracking-widest text-white/50">sick now</div>
          </div>
          <div>
            <div className="font-mono text-[44px] font-semibold leading-none" style={{ color: COLOR.myth, textShadow: `0 0 24px ${COLOR.myth}` }}>{alive.length}</div>
            <div className="mt-1 font-mono text-[11px] uppercase tracking-widest text-white/50">variants</div>
          </div>
        </div>
      </div>

      {/* across many worlds: the honest comparison */}
      {sweep && (
        <div className={`absolute left-6 top-40 w-72 p-4 ${PANEL}`}>
          <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-white/40">across {sweep.seeds} random worlds</div>
          <div className="mt-3 space-y-2.5">
            {Object.entries(sweep.scenarios).map(([k, v]) => (
              <div key={k}>
                <div className="flex justify-between font-mono text-[11px] text-white/70"><span>{SC_LABEL[k] ?? k}</span><span>{v.mean.toFixed(1)} ± {v.sd.toFixed(1)} sick</span></div>
                <div className="relative mt-1 h-1.5 rounded-full bg-white/5">
                  <div className="h-1.5 rounded-full" style={{ width: `${(v.mean / v.population) * 100}%`, background: SICK, boxShadow: `0 0 8px ${SICK}` }} />
                  <div className="absolute top-[-2px] h-2.5 bg-white/40" style={{ left: `${((v.mean - v.sd) / v.population) * 100}%`, width: `${((2 * v.sd) / v.population) * 100}%`, opacity: 0.35 }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* new variant toast */}
      {toast && (
        <div key={toast.id} className="toast pointer-events-none absolute left-1/2 top-[18%] -translate-x-1/2 rounded-2xl border px-6 py-4 text-center backdrop-blur" style={{ borderColor: COLOR[kind(toast)], boxShadow: `0 0 40px ${COLOR[kind(toast)]}55`, background: "rgba(10,10,20,0.75)" }}>
          <div className="font-mono text-[10px] uppercase tracking-[0.3em]" style={{ color: COLOR[kind(toast)] }}>new variant · a {toast.role} retold it</div>
          <div className="mt-1 max-w-xl font-serif text-[22px] leading-snug">“{toast.text}”</div>
        </div>
      )}

      {/* left: what people believe */}
      <Legend counts={counts} className="absolute bottom-28 left-6" />

      {/* right: family tree of sayings */}
      <div className={`absolute bottom-28 right-6 top-40 w-[340px] overflow-y-auto p-4 ${PANEL}`}>
        <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-white/40">family tree of the saying</div>
        <div className="mt-3 space-y-2">
          {alive.map((v) => {
            const n = share.get(v.id) ?? 0;
            return (
              <div key={v.id} style={{ paddingLeft: Math.min(depth(v), 6) * 12 }} className={n === 0 ? "opacity-35" : ""}>
                <div className="flex items-start gap-2">
                  <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full" style={{ background: COLOR[kind(v)], boxShadow: `0 0 8px ${COLOR[kind(v)]}` }} />
                  <div className="min-w-0 flex-1">
                    <div className="text-[13px] leading-snug text-white/90">{v.short}</div>
                    <div className="mt-0.5 flex items-center gap-2 font-mono text-[10px] text-white/40">
                      <span>{v.role} · day {v.day}</span>
                      <span className="h-1 flex-1 rounded-full bg-white/5"><span className="block h-1 rounded-full" style={{ width: `${(n / data.population) * 100}%`, background: COLOR[kind(v)] }} /></span>
                      <span>{n}</span>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* bottom: controls + sickness curve */}
      <div className="absolute inset-x-0 bottom-0 p-6">
        <div className="flex items-center gap-4">
          <button onClick={() => { if (day >= data.days) setDay(0); setPlaying(!playing); }} className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-white text-[16px] text-black shadow-[0_0_30px_rgba(255,255,255,0.35)]" aria-label={playing ? "Pause" : "Play"}>
            {playing ? "❚❚" : "▶"}
          </button>
          <div className="relative flex-1">
            <svg viewBox={`0 0 ${data.days} 30`} preserveAspectRatio="none" className="h-10 w-full">
              <polyline points={sickSeries.map((s, i) => `${i},${30 - (s / maxSick) * 28}`).join(" ")} fill="none" stroke={SICK} strokeWidth="0.6" vectorEffect="non-scaling-stroke" opacity="0.35" />
              <polyline points={sickSeries.slice(0, day + 1).map((s, i) => `${i},${30 - (s / maxSick) * 28}`).join(" ")} fill="none" stroke={SICK} strokeWidth="2" vectorEffect="non-scaling-stroke" />
            </svg>
            <input type="range" min={0} max={data.days} value={day} onChange={(e) => { setPlaying(false); setDay(+e.target.value); }} className="epi-range w-full" aria-label="Day" />
          </div>
          {list.length > 1 && (
            <select value={runId ?? ""} onChange={(e) => setRunId(e.target.value)} className="rounded-full border border-white/20 bg-transparent px-3 py-2 font-mono text-[12px] text-white/80">
              {list.map((r) => <option key={r.id} value={r.id} className="text-black">{r.scenario} · {r.ever_sick}/{r.population} sick</option>)}
            </select>
          )}
        </div>
      </div>
    </div>
  );
}
