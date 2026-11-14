import { useEffect, useRef } from "react";
import { Controls } from "./Controls";
import { kind, useEpi, villageCenters, LABEL, type Kind } from "./epi";
import { C, KIND_COLOR } from "./theme";
import { Header, Legend } from "./ui";

const SHIRT: Record<Kind, string> = { ...KIND_COLOR, none: "#5b6075" };
interface Bubble { person: number; from: number; text: string; k: Kind; born: number }

function wrap(ctx: CanvasRenderingContext2D, text: string, max: number) {
  const words = text.split(" "), lines: string[] = [];
  let line = "";
  for (const w of words) {
    const t = line ? line + " " + w : w;
    if (ctx.measureText(t).width > max && line) { lines.push(line); line = w; } else line = t;
  }
  if (line) lines.push(line);
  return lines.slice(0, 3);
}

export function Village() {
  const epi = useEpi(650);
  const { data, day } = epi;
  const canvas = useRef<HTMLCanvasElement>(null);
  const bubbles = useRef<Bubble[]>([]);
  const dayRef = useRef(day);
  dayRef.current = day;

  // new conversations become speech bubbles (a few at a time, new variants first)
  useEffect(() => {
    if (!data) return;
    const ts = epi.transfers(day);
    const fresh = ts.filter((t) => data.variants[t.variant].day === day && data.variants[t.variant].parent !== null);
    const rest = ts.filter((t) => !fresh.includes(t)).sort(() => Math.random() - 0.5);
    const now = performance.now();
    const live = bubbles.current.filter((b) => now - b.born < 3600);
    const near = (a: number, b: number) => Math.hypot(data.people[a].x - data.people[b].x, data.people[a].y - data.people[b].y) < 0.32;
    let added = 0;
    for (const t of [...fresh, ...rest]) {
      if (live.length + added >= 2) break;
      if ([...live, ...bubbles.current.slice(-added || bubbles.current.length)].some((b) => near(b.person, t.to))) continue;
      const v = data.variants[t.variant];
      bubbles.current.push({ person: t.to, from: t.from, text: v.text, k: kind(v), born: now + added * 300 });
      added++;
    }
  }, [day, data]); // eslint-disable-line

  useEffect(() => {
    const c = canvas.current;
    if (!c || !data) return;
    const ctx = c.getContext("2d")!;
    const centers = villageCenters(data);
    let raf = 0;
    const draw = (now: number) => {
      const dpr = Math.min(devicePixelRatio, 2), w = c.clientWidth, h = c.clientHeight;
      if (c.width !== w * dpr) { c.width = w * dpr; c.height = h * dpr; }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const S = Math.min(w, h) * 0.47, cx = w / 2, cy = h / 2 + 10;
      const X = (x: number) => cx + x * S, Y = (y: number) => cy + y * S;
      const f = data.frames[dayRef.current];

      // ground
      const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.max(w, h) * 0.7);
      g.addColorStop(0, "#161b26"); g.addColorStop(1, C.bg);
      ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);

      // dirt roads from each village to the market
      ctx.strokeStyle = "rgba(255,255,255,0.06)"; ctx.lineWidth = 14; ctx.lineCap = "round";
      centers.forEach(([x, y]) => { ctx.beginPath(); ctx.moveTo(X(x), Y(y)); ctx.lineTo(cx, cy); ctx.stroke(); });

      // market stalls
      ["#3a3550", "#2f3a4a", "#3a3550", "#2f3a4a"].forEach((col, i) => {
        const a = (i / 4) * Math.PI * 2 + 0.4, x = cx + Math.cos(a) * 30, y = cy + Math.sin(a) * 30;
        ctx.fillStyle = "#1c2030"; ctx.fillRect(x - 11, y - 2, 22, 12);
        ctx.fillStyle = "rgba(255,210,122,0.8)"; ctx.fillRect(x - 3, y + 2, 6, 4);
        ctx.fillStyle = col; ctx.beginPath(); ctx.moveTo(x - 14, y); ctx.lineTo(x + 14, y); ctx.lineTo(x + 10, y - 10); ctx.lineTo(x - 10, y - 10); ctx.fill();
      });
      ctx.font = "600 10px 'JetBrains Mono', monospace"; ctx.textAlign = "center"; ctx.fillStyle = "rgba(242,239,232,0.4)"; ctx.fillText("MARKET", cx, cy + 48);

      // villages: houses around a well, a shrine if the myth has taken hold
      centers.forEach(([vx, vy], vi) => {
        const bx = X(vx), by = Y(vy);
        for (let k = 0; k < 9; k++) {
          const a = (k / 9) * Math.PI * 2 + vi, r = S * 0.2 + (k % 2) * 10;
          const hx = bx + Math.cos(a) * r, hy = by + Math.sin(a) * r;
          ctx.fillStyle = "#1b1f2c"; ctx.fillRect(hx - 10, hy - 6, 20, 13);
          ctx.fillStyle = (k + vi) % 3 ? "rgba(255,210,122,0.85)" : "rgba(255,210,122,0.25)"; ctx.fillRect(hx - 6, hy - 3, 4, 4); ctx.fillRect(hx + 2, hy - 3, 4, 4);
          ctx.fillStyle = "#2a2f42";
          ctx.beginPath(); ctx.moveTo(hx - 13, hy - 6); ctx.lineTo(hx, hy - 17); ctx.lineTo(hx + 13, hy - 6); ctx.fill();
        }
        const bad = data.contaminated[vi] !== undefined && dayRef.current >= data.contaminated[vi];
        ctx.fillStyle = "#2a2f42"; ctx.beginPath(); ctx.arc(bx, by, 13, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = bad ? C.sick : "#4aa3d8"; ctx.beginPath(); ctx.arc(bx, by, 8.5, 0, Math.PI * 2); ctx.fill();
        if (bad) {
          ctx.fillStyle = C.bg; ctx.font = "800 13px Inter"; ctx.fillText("!", bx, by + 4.5);
        }
        const members = data.people.filter((p) => p.village === vi).map((p) => p.id);
        const mythShare = members.filter((id) => f.b[id] !== null && kind(data.variants[f.b[id]!]) === "myth").length / members.length;
        if (mythShare >= 0.2) {
          const sx = bx + 30, sy = by - 26;
          ctx.fillStyle = "#3a2552"; ctx.fillRect(sx - 9, sy - 2, 18, 14);
          ctx.fillStyle = C.myth; ctx.beginPath(); ctx.moveTo(sx - 12, sy - 2); ctx.lineTo(sx, sy - 13); ctx.lineTo(sx + 12, sy - 2); ctx.fill();
          const fl = 5 + Math.sin(now / 90) * 1.5;
          ctx.fillStyle = "#ff9d2e"; ctx.beginPath(); ctx.ellipse(sx, sy - 18, 3.5, fl, 0, 0, Math.PI * 2); ctx.fill();
        }
        ctx.font = "600 11px 'JetBrains Mono', monospace"; ctx.fillStyle = bad ? C.sick : "rgba(242,239,232,0.55)";
        ctx.fillText(`${data.villages[vi].name}${bad ? ((data as { message?: string }).message ? " · exposed" : " · well gone bad") : ""}`, bx, by + (vy > 0 ? S * 0.3 : -S * 0.28));
      });

      // people, wandering a little around home
      const pos = data.people.map((p) => {
        const ph = p.id * 1.7;
        return [X(p.x) + Math.sin(now / 1400 + ph) * 6, Y(p.y) + Math.cos(now / 1700 + ph) * 4] as const;
      });
      data.people.forEach((p, i) => {
        const [x, y] = pos[i];
        const v = f.b[i];
        const k = kind(v === null ? undefined : data.variants[v]);
        const sick = f.h[i] === "I";
        const wob = sick ? Math.sin(now / 120 + i) * 1.2 : 0;
        ctx.fillStyle = SHIRT[k] + "33"; ctx.beginPath(); ctx.arc(x, y + 2, 11, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = SHIRT[k]; ctx.beginPath(); ctx.roundRect(x - 4.5 + wob, y - 2, 9, 10, 3); ctx.fill();
        ctx.fillStyle = "#e8d5c0"; ctx.beginPath(); ctx.arc(x + wob, y - 6, 4.2, 0, Math.PI * 2); ctx.fill();
        if (sick) { ctx.strokeStyle = C.sick; ctx.lineWidth = 2; ctx.globalAlpha = 0.6 + 0.4 * Math.sin(now / 160 + i); ctx.beginPath(); ctx.arc(x, y, 12, 0, Math.PI * 2); ctx.stroke(); ctx.globalAlpha = 1; }
        if (p.role === "priest") { ctx.fillStyle = C.myth; ctx.fillRect(x - 3, y - 12, 6, 2.5); }
        if (p.role === "healer") { ctx.fillStyle = C.truth; ctx.fillRect(x - 1, y + 0, 2, 6); ctx.fillRect(x - 3, y + 2, 6, 2); }
      });

      // speech bubbles
      bubbles.current = bubbles.current.filter((b) => now - b.born < 3600);
      bubbles.current.forEach((b) => {
        const age = now - b.born;
        if (age < 0) return;
        const a = Math.min(1, age / 250) * Math.min(1, (3600 - age) / 400);
        const [x, y] = pos[b.person], [fx, fy] = pos[b.from];
        ctx.globalAlpha = a * 0.6; ctx.setLineDash([3, 4]); ctx.strokeStyle = SHIRT[b.k]; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(fx, fy - 6); ctx.lineTo(x, y - 6); ctx.stroke(); ctx.setLineDash([]);
        ctx.globalAlpha = a;
        ctx.font = "400 14px Fraunces, Georgia, serif";
        const lines = wrap(ctx, `“${b.text}”`, 210);
        const bw = Math.max(...lines.map((l) => ctx.measureText(l).width)) + 22, bh = lines.length * 18 + 14;
        const lift = Math.min(1, age / 300) * 6;
        const bx = Math.min(Math.max(x - bw / 2, 8), w - bw - 8), by = y - 22 - bh - lift;
        ctx.shadowColor = SHIRT[b.k]; ctx.shadowBlur = 24;
        ctx.fillStyle = "rgba(14,15,24,0.94)"; ctx.beginPath(); ctx.roundRect(bx, by, bw, bh, 12); ctx.fill();
        ctx.shadowBlur = 0;
        ctx.strokeStyle = SHIRT[b.k]; ctx.lineWidth = 1.2; ctx.beginPath(); ctx.roundRect(bx, by, bw, bh, 12); ctx.stroke();
        ctx.fillStyle = "rgba(14,15,24,0.94)"; ctx.beginPath(); ctx.moveTo(x - 6, by + bh - 1); ctx.lineTo(x, by + bh + 8); ctx.lineTo(x + 6, by + bh - 1); ctx.fill();
        ctx.fillStyle = C.text; ctx.textAlign = "left";
        lines.forEach((l, i) => ctx.fillText(l, bx + 12, by + 22 + i * 18));
        ctx.textAlign = "center";
      });
      ctx.globalAlpha = 1;
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [data]);

  if (!data) return <div className="grid h-screen place-items-center bg-[#08080d] font-mono text-white/40">loading the valley…</div>;
  const f = data.frames[day];
  const counts: Record<Kind, number> = { truth: 0, ritual: 0, myth: 0, unsafe: 0, none: 0 };
  f.b.forEach((v) => counts[kind(v === null ? undefined : data.variants[v])]++);

  return (
    <div className="relative h-screen overflow-hidden">
      <canvas ref={canvas} className="absolute inset-0 h-full w-full" />
      <Header eyebrow="village view" title={`${(data as { message?: string }).message ? "The neighborhood" : "The valley"}, day ${day}`} sub={`${f.sick_total} fell sick · ${data.population} people · ${data.villages.length} groups`} />
      <Legend counts={counts} className="absolute right-6 top-16" />
      <div className="absolute inset-x-0 bottom-0 p-6">
        <Controls {...epi} data={data} />
      </div>
    </div>
  );
}
