// The website drawn as a map of the pages customers actually visited. Avatars walk between pages as they click,
// then leave through the exits on the right: bought, maybe later, or left.
import { useMemo, useState } from "react";
import { Avatar, SHIRT, type Feeling } from "./Avatar";
import { C } from "./theme";
import type { Persona, Sim } from "./Simulate";

const COL = 250, ROW = 170, NODE_W = 190, NODE_H = 120, PAD = 40;
const BOUGHT = new Set(["buy", "would recommend"]);
const MAYBE = new Set(["maybe later"]);

// What they did, not what they said: clicking "Add to cart" / "Download" counts as buying.
export function outcome(sim: Sim, pid: string): "bought" | "maybe" | "left" | null {
  const d = sim.decisions[pid];
  if (!d) return null;
  if (BOUGHT.has(d.decision) || (sim.live[pid] ?? []).some((x) => x.cart)) return "bought";
  return MAYBE.has(d.decision) ? "maybe" : "left";
}

function keyOf(u: string, rootHost: string) {
  try {
    const x = new URL(u);
    const path = x.pathname.replace(/\/+$/, "") || "/";
    const host = x.host.replace(/^www\./, "");
    const label = host !== rootHost ? host + (path === "/" ? "" : " · " + decodeURIComponent(path.split("/").filter(Boolean).pop() ?? "").replace(/[-_]+/g, " ")) : path === "/" ? "Home" : decodeURIComponent(path.split("/").filter(Boolean).pop() ?? "").replace(/[-_]+/g, " ").replace(/\.\w+$/, "");
    return { key: host + path, label: label.charAt(0).toUpperCase() + label.slice(1) };
  } catch { return { key: u, label: u }; }
}

export function SiteMap({ sim, onOpen }: { sim: Sim; onOpen: (p: Persona) => void }) {
  const [hover, setHover] = useState<string | null>(null);
  const rootHost = keyOf(sim.input.url.startsWith("http") ? sim.input.url : `https://${sim.input.url}`, "").label.toLowerCase();

  const { nodes, edges, width, height, exitX } = useMemo(() => {
    const nodes = new Map<string, { key: string; label: string; shot: string | null; blocked: boolean; visits: number; depth: number; x: number; y: number }>();
    const edges = new Map<string, { a: string; b: string; n: number }>();
    const root = keyOf(sim.input.url.startsWith("http") ? sim.input.url : `https://${sim.input.url}`, rootHost);
    nodes.set(root.key, { ...root, shot: null, blocked: false, visits: 0, depth: 0, x: 0, y: 0 });
    for (const p of sim.personas) {
      let prev = root.key;
      for (const s of sim.live[p.id] ?? []) {
        const k = keyOf(s.url, rootHost);
        const n = nodes.get(k.key) ?? { ...k, shot: null, blocked: false, visits: 0, depth: (nodes.get(prev)?.depth ?? 0) + 1, x: 0, y: 0 };
        n.visits++; if (s.shot) n.shot = s.shot; if (s.blocked) n.blocked = true;
        nodes.set(k.key, n);
        if (k.key !== prev) { const ek = `${prev}→${k.key}`; const e = edges.get(ek) ?? { a: prev, b: k.key, n: 0 }; e.n++; edges.set(ek, e); }
        prev = k.key;
      }
    }
    const cols: string[][] = [];
    for (const n of nodes.values()) (cols[n.depth] ??= []).push(n.key);
    cols.forEach((keys, d) => keys.forEach((k, i) => { const n = nodes.get(k)!; n.x = PAD + d * COL; n.y = PAD + i * ROW; }));
    const exitX = PAD + Math.max(cols.length, 1) * COL + 30;
    const height = Math.max(PAD * 2 + Math.max(...cols.map((c) => c.length), 3) * ROW, 3 * ROW + PAD * 2);
    return { nodes, edges, width: exitX + NODE_W + PAD, height, exitX };
  }, [sim, rootHost]);

  const exits = [
    { id: "bought", label: "Bought", color: C.win },
    { id: "maybe", label: "Maybe later", color: C.mid },
    { id: "left", label: "Left", color: C.loss },
  ];
  const exitY = (i: number) => PAD + i * ((height - PAD * 2 - NODE_H) / 2);

  // where each avatar stands right now
  const crowd = new Map<string, number>();
  const spots = sim.personas.map((p) => {
    const steps = sim.live[p.id] ?? [];
    const last = steps[steps.length - 1];
    const d = sim.decisions[p.id];
    let x: number, y: number, at: string;
    if (d) { const i = exits.findIndex((e) => e.id === outcome(sim, p.id)); at = exits[i].id; x = exitX; y = exitY(i); }
    else { const n = nodes.get(keyOf(last?.url ?? `https://${rootHost}`, rootHost).key) ?? [...nodes.values()][0]; at = n.key; x = n.x; y = n.y; }
    const k = crowd.get(at) ?? 0; crowd.set(at, k + 1);
    const feeling: Feeling = d?.feeling ?? last?.feeling ?? "neutral";
    return { p, first: k === 0, x: x + 8 + (k % 4) * 44, y: (d ? y + 40 : y + NODE_H - 30) + Math.floor(k / 4) * 44, feeling, thought: d ? d.quote : last?.thought, d, moving: !d && sim.status === "browsing" };
  });

  return (
    <div className="relative mt-8 overflow-x-auto rounded-3xl border border-white/10 bg-[radial-gradient(ellipse_at_top,rgba(63,240,212,0.06),transparent_60%)]" style={{ backgroundImage: "radial-gradient(rgba(255,255,255,0.06) 1px, transparent 1px)", backgroundSize: "22px 22px" }}>
      <div className="relative mx-auto" style={{ width, height: height + 60 }}>
        <svg className="absolute inset-0" width={width} height={height + 60}>
          {[...edges.values()].map((e) => {
            const a = nodes.get(e.a)!, b = nodes.get(e.b)!;
            const x1 = a.x + NODE_W, y1 = a.y + NODE_H / 2, x2 = b.x, y2 = b.y + NODE_H / 2;
            const back = x2 <= x1;
            const d = back ? `M${a.x + NODE_W / 2} ${a.y + NODE_H} C ${a.x + NODE_W / 2} ${a.y + NODE_H + 50}, ${b.x + NODE_W / 2} ${b.y + NODE_H + 50}, ${b.x + NODE_W / 2} ${b.y + NODE_H}` : `M${x1} ${y1} C ${x1 + 50} ${y1}, ${x2 - 50} ${y2}, ${x2} ${y2}`;
            return <path key={e.a + e.b} d={d} fill="none" stroke="rgba(63,240,212,0.35)" strokeWidth={1 + e.n} strokeDasharray="6 6" className="flow" />;
          })}
        </svg>

        {[...nodes.values()].map((n) => (
          <div key={n.key} onMouseEnter={() => setHover(n.key)} onMouseLeave={() => setHover(null)}
            className="absolute overflow-hidden rounded-2xl border bg-[#11131c] shadow-xl transition-transform hover:z-20 hover:scale-[1.6]"
            style={{ left: n.x, top: n.y, width: NODE_W, height: NODE_H, borderColor: n.blocked ? "rgba(255,255,255,0.15)" : hover === n.key ? C.win : "rgba(255,255,255,0.14)", transformOrigin: "top left" }}>
            {n.shot ? <img src={`/api/shots/${sim.id}/shots/${n.shot}`} alt="" className="h-full w-full object-cover object-top opacity-60" /> : <div className="h-full w-full bg-white/[0.03]" />}
            <div className="absolute inset-x-0 top-0 flex items-center justify-between bg-gradient-to-b from-black/90 to-transparent px-2.5 pb-4 pt-1.5">
              <span className="truncate text-[12px] font-semibold">{n.label}</span>
              {n.blocked ? <span className="font-mono text-[9px] text-white/50">bot check</span> : n.visits > 0 && <span className="font-mono text-[10px] text-white/50">{n.visits}×</span>}
            </div>
          </div>
        ))}

        {exits.map((e, i) => {
          const n = sim.personas.filter((p) => outcome(sim, p.id) === e.id).length;
          return (
            <div key={e.id} className="absolute rounded-2xl border-2 border-dashed" style={{ left: exitX, top: exitY(i), width: NODE_W, height: NODE_H, borderColor: `${e.color}66`, background: `${e.color}0d` }}>
              <div className="flex items-center justify-between px-3 pt-2"><span className="text-[13px] font-semibold" style={{ color: e.color }}>{e.label}</span><span className="font-mono text-[18px] font-semibold" style={{ color: e.color }}>{n}</span></div>
            </div>
          );
        })}

        {spots.map(({ p, first, x, y, feeling, thought, d, moving }) => (
          <button key={p.id} onClick={() => onOpen(p)} className="group absolute z-10 transition-all duration-[1200ms] ease-in-out" style={{ left: x, top: y }} title={`${p.name} · ${p.archetype}`}>
            <div className="rounded-full" style={{ boxShadow: `0 0 0 2.5px ${SHIRT[p.archetype]}, 0 6px 20px rgba(0,0,0,.6)` }}>
              <Avatar seed={p.avatar.seed} archetype={p.archetype} age={p.age} size={40} feeling={feeling} busy={moving} />
            </div>
            {(sim.live[p.id] ?? []).some((x) => x.cart) && <span className="absolute -right-1.5 -top-1.5 grid h-5 w-5 place-items-center rounded-full text-[11px]" style={{ background: C.win }}>🛒</span>}
            <div className="mt-0.5 text-center font-mono text-[9px] text-white/70">{p.name}</div>
            {thought && (
              <div key={thought} className={`bubble pointer-events-none absolute bottom-full left-1/2 mb-1 w-[200px] -translate-x-1/2 rounded-xl px-2.5 py-1.5 text-left text-[11px] leading-snug shadow-lg ${moving && first ? "block" : "hidden group-hover:block"}`}
                style={{ background: d ? ({ bought: C.win, maybe: C.mid, left: "#fff" }[outcome(sim, p.id) ?? "left"]) : "#fff", color: "#000" }}>
                {thought.length > 110 ? thought.slice(0, 110) + "…" : thought}
              </div>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
