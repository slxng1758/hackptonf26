import { useEffect, useRef } from "react";
import { Controls } from "./Controls";
import { kind, useEpi, type Kind, type Variant } from "./epi";
import { C, KIND_COLOR } from "./theme";
import { Header, PANEL } from "./ui";

const LETTER: Record<Kind, string> = { truth: "T", ritual: "R", myth: "M", unsafe: "U", none: "?" };
const strain = (v: Variant) => `${LETTER[kind(v)]}-${String(v.id).padStart(2, "0")}`;
const colour = (v: Variant, a = 1) => KIND_COLOR[kind(v)] + Math.round(a * 255).toString(16).padStart(2, "0");

export function Petri() {
  const epi = useEpi(420);
  const { data, day } = epi;
  const canvas = useRef<HTMLCanvasElement>(null);
  const dayRef = useRef(day);
  dayRef.current = day;

  useEffect(() => {
    const c = canvas.current;
    if (!c || !data) return;
    const ctx = c.getContext("2d")!;
    let raf = 0;
    // each person is a cell in the agar; jitter fixed per person so colonies look organic
    const jit = data.people.map((p) => [Math.sin(p.id * 12.9) * 0.05, Math.cos(p.id * 78.2) * 0.05]);
    const draw = (now: number) => {
      const dpr = Math.min(devicePixelRatio, 2), w = c.clientWidth, h = c.clientHeight;
      if (c.width !== w * dpr) { c.width = w * dpr; c.height = h * dpr; }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = C.bg; ctx.fillRect(0, 0, w, h);
      const R = Math.min(w, h) * 0.4, cx = w / 2, cy = h / 2;
      const f = data.frames[dayRef.current];

      // dish: glass rim and agar
      const agar = ctx.createRadialGradient(cx - R * 0.3, cy - R * 0.3, R * 0.1, cx, cy, R);
      agar.addColorStop(0, "#1a2230"); agar.addColorStop(1, "#0e121b");
      ctx.fillStyle = agar; ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.fill();
      ctx.save(); ctx.beginPath(); ctx.arc(cx, cy, R - 2, 0, Math.PI * 2); ctx.clip();

      // colonies: blurred cells blend into blobs
      ctx.filter = "blur(5px)";
      ctx.globalCompositeOperation = "lighter";
      data.people.forEach((p, i) => {
        const v = f.b[i];
        if (v === null) return;
        const x = cx + (p.x + jit[i][0]) * R * 0.92, y = cy + (p.y + jit[i][1]) * R * 0.92;
        const breathe = 1 + Math.sin(now / 900 + i) * 0.06;
        ctx.fillStyle = colour(data.variants[v], 0.55);
        ctx.beginPath(); ctx.arc(x, y, 15 * breathe, 0, Math.PI * 2); ctx.fill();
      });
      ctx.filter = "none";
      ctx.globalCompositeOperation = "source-over";
      // crisp cell cores, infected cells speckled red
      data.people.forEach((p, i) => {
        const x = cx + (p.x + jit[i][0]) * R * 0.92, y = cy + (p.y + jit[i][1]) * R * 0.92;
        const v = f.b[i];
        ctx.fillStyle = v === null ? "rgba(255,255,255,0.12)" : colour(data.variants[v], 1);
        ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2); ctx.fill();
        if (f.h[i] === "I") {
          for (let k = 0; k < 5; k++) {
            const a = k * 1.3 + now / 600, r = 6 + (k % 2) * 3;
            ctx.fillStyle = C.sick; ctx.beginPath(); ctx.arc(x + Math.cos(a) * r, y + Math.sin(a) * r, 1.6, 0, Math.PI * 2); ctx.fill();
          }
        }
      });
      ctx.restore();

      // glass rim + light reflection
      ctx.strokeStyle = "rgba(255,255,255,0.5)"; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.stroke();
      ctx.strokeStyle = "rgba(255,255,255,0.12)"; ctx.lineWidth = 14; ctx.beginPath(); ctx.arc(cx, cy, R + 9, 0, Math.PI * 2); ctx.stroke();
      ctx.strokeStyle = "rgba(255,255,255,0.35)"; ctx.lineWidth = 4; ctx.beginPath(); ctx.arc(cx, cy, R - 12, Math.PI * 1.1, Math.PI * 1.4); ctx.stroke();

      // rim ticks, like a measuring reticle
      ctx.strokeStyle = "rgba(255,255,255,0.25)"; ctx.lineWidth = 1;
      for (let k = 0; k < 120; k++) {
        const a = (k / 120) * Math.PI * 2, l = k % 10 === 0 ? 12 : 5;
        ctx.beginPath(); ctx.moveTo(cx + Math.cos(a) * (R + 20), cy + Math.sin(a) * (R + 20)); ctx.lineTo(cx + Math.cos(a) * (R + 20 + l), cy + Math.sin(a) * (R + 20 + l)); ctx.stroke();
      }

      // strain labels at colony centroids
      const groups = new Map<number, [number, number, number]>();
      data.people.forEach((p, i) => {
        const v = f.b[i];
        if (v === null) return;
        const g = groups.get(v) ?? [0, 0, 0];
        groups.set(v, [g[0] + p.x, g[1] + p.y, g[2] + 1]);
      });
      ctx.font = "600 11px 'JetBrains Mono', monospace"; ctx.textAlign = "left";
      groups.forEach(([sx, sy, n], v) => {
        if (n < 3) return;
        const x = cx + (sx / n) * R * 0.92, y = cy + (sy / n) * R * 0.92;
        const label = `${strain(data.variants[v])}  n=${n}`;
        const tw = ctx.measureText(label).width;
        ctx.fillStyle = "rgba(10,10,12,0.78)"; ctx.beginPath(); ctx.roundRect(x + 10, y - 22, tw + 12, 18, 4); ctx.fill();
        ctx.strokeStyle = colour(data.variants[v]); ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + 10, y - 13); ctx.stroke();
        ctx.fillStyle = "#fff"; ctx.fillText(label, x + 16, y - 9);
      });

      // vignette
      const vg = ctx.createRadialGradient(cx, cy, R * 0.8, cx, cy, Math.max(w, h) * 0.75);
      vg.addColorStop(0, "rgba(0,0,0,0)"); vg.addColorStop(1, "rgba(0,0,0,0.7)");
      ctx.fillStyle = vg; ctx.fillRect(0, 0, w, h);
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [data]);

  if (!data) return <div className="grid h-screen place-items-center bg-[#08080d] font-mono text-white/40">preparing specimen…</div>;
  const f = data.frames[day];
  const share = new Map<number, number>();
  f.b.forEach((v) => v !== null && share.set(v, (share.get(v) ?? 0) + 1));
  const live = [...share.entries()].sort((a, b) => b[1] - a[1]).map(([v, n]) => ({ v: data.variants[v], n }));

  return (
    <div className="relative h-screen overflow-hidden bg-[#08080d] font-mono text-white">
      <canvas ref={canvas} className="absolute inset-0 h-full w-full" />
      <Header eyebrow="petri dish view" title={`Day ${day} of ${data.days}`} sub={<>{f.sick_total} fell sick · {live.length} live strains · {data.villages.length} groups</>} />
      <div className={`absolute right-6 top-16 max-h-[65vh] w-[320px] overflow-y-auto p-4 ${PANEL}`}>
        <div className="text-[10px] uppercase tracking-[0.3em] text-white/40">strain register</div>
        {live.map(({ v, n }) => (
          <div key={v.id} className="mt-2 border-t border-white/5 pt-2">
            <div className="flex items-center justify-between text-[11px]">
              <span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full" style={{ background: colour(v) }} />{strain(v)}{v.parent !== null && <span className="text-white/30">← {strain(data.variants[v.parent])}</span>}</span>
              <span className="text-white/50">n={n}</span>
            </div>
            <div className="mt-1 font-serif text-[13px] leading-snug text-white/85">“{v.short}”</div>
          </div>
        ))}
        <div className="mt-3 border-t border-white/10 pt-2 text-[10px] text-white/40">T true cause · R ritual · M myth · U unsafe</div>
      </div>
      <div className="absolute inset-x-0 bottom-0 p-6"><Controls {...epi} data={data} /></div>
    </div>
  );
}
