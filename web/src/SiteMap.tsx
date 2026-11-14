// The website drawn as a map of the pages customers actually visited. Avatars walk between pages as they click,
// then leave through the exits on the right: bought, maybe later, or left.
import { useEffect, useMemo, useRef, useState } from "react";
import { Avatar, SHIRT, type Feeling } from "./Avatar";
import { C } from "./theme";
import type { Persona, Sim } from "./Simulate";

const COL = 250, ROW = 170, NODE_W = 190, NODE_H = 120, EXIT_H = 165, PAD = 40;
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
    const height = Math.max(PAD * 2 + Math.max(...cols.map((c) => c.length), 3) * ROW, 3 * (EXIT_H + 20) + PAD * 2);
    return { nodes, edges, width: exitX + NODE_W + PAD, height, exitX };
  }, [sim, rootHost]);

  const exits = [
    { id: "bought", label: "Bought", color: C.win },
    { id: "maybe", label: "Maybe later", color: C.mid },
    { id: "left", label: "Left", color: C.loss },
  ];
  const exitY = (i: number) => PAD + i * Math.max(EXIT_H + 20, (height - PAD * 2 - EXIT_H) / 2);

  const maxVisits = Math.max(1, ...[...nodes.values()].map((n) => n.visits));
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
    <Fit width={width} height={height + 60}>
        <svg className="absolute inset-0" width={width} height={height + 60}>
          {[...edges.values()].map((e) => {
            const a = nodes.get(e.a)!, b = nodes.get(e.b)!;
            const x1 = a.x + NODE_W, y1 = a.y + NODE_H / 2, x2 = b.x, y2 = b.y + NODE_H / 2;
            const back = x2 <= x1;
            const d = back ? `M${a.x + NODE_W / 2} ${a.y + NODE_H} C ${a.x + NODE_W / 2} ${a.y + NODE_H + 50}, ${b.x + NODE_W / 2} ${b.y + NODE_H + 50}, ${b.x + NODE_W / 2} ${b.y + NODE_H}` : `M${x1} ${y1} C ${x1 + 50} ${y1}, ${x2 - 50} ${y2}, ${x2} ${y2}`;
            return <path key={e.a + e.b} d={d} fill="none" stroke="rgba(63,240,212,0.35)" strokeWidth={1 + e.n} strokeDasharray="6 6" className="flow" />;
          })}
        </svg>

        {[...nodes.values()].map((n) => { const here = crowd.get(n.key) ?? 0; const heat = Math.min(n.visits / maxVisits, 1); return (
          <div key={n.key} onMouseEnter={() => setHover(n.key)} onMouseLeave={() => setHover(null)}
            className={`absolute overflow-hidden rounded-2xl border bg-[var(--card)] transition-all duration-700 hover:z-20 hover:scale-[1.6] ${here ? "heat" : ""}`}
            style={{ left: n.x, top: n.y, width: NODE_W, height: NODE_H, transformOrigin: "top left",
              borderColor: n.blocked ? "rgba(255,255,255,0.15)" : hover === n.key || here ? C.win : `rgba(63,240,212,${0.12 + heat * 0.4})`,
              boxShadow: here ? `0 0 ${18 + here * 16}px ${C.win}${here > 2 ? "aa" : "66"}, inset 0 0 30px ${C.win}22` : `0 10px 30px rgba(0,0,0,.5), 0 0 ${heat * 24}px ${C.win}33` }}>
            {n.shot ? <img src={`/api/shots/${sim.id}/shots/${n.shot}`} alt="" className="h-full w-full object-cover object-top opacity-60" /> : <div className="h-full w-full bg-white/[0.03]" />}
            <div className="absolute inset-x-0 top-0 flex items-center justify-between px-2.5 pb-4 pt-1.5" style={{ background: "linear-gradient(var(--card) 55%, transparent)" }}>
              <span className="truncate text-[12px] font-semibold">{n.label}</span>
              {n.blocked ? <span className="font-mono text-[9px] text-white/50">bot check</span> : here > 0 ? <span className="rounded-full px-1.5 font-mono text-[10px] font-semibold text-black" style={{ background: C.win }}>{here} here</span> : n.visits > 0 && <span className="font-mono text-[10px] text-white/50">{n.visits}×</span>}
            </div>
            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-1" style={{ background: `linear-gradient(90deg, ${C.win}, ${C.brain})`, opacity: heat }} />
          </div>
        ); })}

        {exits.map((e, i) => {
          const n = sim.personas.filter((p) => outcome(sim, p.id) === e.id).length;
          return (
            <div key={e.id} className={`absolute rounded-2xl border-2 ${e.id === "bought" && n ? "border-solid" : "border-dashed"}`} style={{ left: exitX, top: exitY(i), width: NODE_W, height: EXIT_H, borderColor: `${e.color}${n ? "cc" : "55"}`, background: `${e.color}${n ? "1a" : "0a"}`, boxShadow: e.id === "bought" && n ? `0 0 ${20 + n * 12}px ${e.color}66` : "none" }}>
              <div className="flex items-center justify-between px-3 pt-2"><span className="text-[13px] font-semibold" style={{ color: e.color }}>{e.label}</span><span key={n} className="cell-in font-mono text-[22px] font-semibold" style={{ color: e.color }}>{n}</span></div>
              {e.id === "bought" && n > 0 && (
                <div key={`burst${n}`} className="pointer-events-none absolute right-6 top-4">
                  {Array.from({ length: 12 }, (_, k) => <span key={k} className="spark" style={{ ["--a" as string]: `${k * 30}deg`, background: k % 2 ? C.win : C.mid }} />)}
                  <span className="plus-one font-mono text-[14px] font-bold" style={{ color: C.win }}>+1 sale</span>
                </div>
              )}
            </div>
          );
        })}

        {spots.map(({ p, first, x, y, feeling, thought, d, moving }) => (
          <button key={p.id} onClick={() => onOpen(p)} className="group absolute z-10 transition-all duration-[1200ms] ease-in-out" style={{ left: x, top: y }} title={`${p.name} · ${p.archetype}${p.model ? ` · ${p.model}` : ""}`}>
            <div className="rounded-full" style={{ boxShadow: `0 0 0 2.5px ${SHIRT[p.archetype]}, 0 6px 20px rgba(0,0,0,.6)` }}>
              <Avatar seed={p.avatar.seed} archetype={p.archetype} model={p.model} age={p.age} size={40} feeling={feeling} busy={moving} />
            </div>
            {(sim.live[p.id] ?? []).some((x) => x.cart) && <span className="absolute -right-1 -top-1 grid h-4 w-4 place-items-center rounded-full text-[9px] font-bold text-black" style={{ background: C.win }}>✓</span>}
            <div className="mx-auto mt-0.5 w-[44px] truncate text-center font-mono text-[9px] text-white/70">{p.name}{p.model && <span className="block text-white/35" title={p.model_note}>{p.played_by ? `${p.model}→${p.played_by}` : p.model}</span>}</div>
            {thought && (
              <div key={thought} className={`bubble pointer-events-none absolute bottom-full left-1/2 mb-1 w-[200px] -translate-x-1/2 rounded-xl px-2.5 py-1.5 text-left text-[11px] leading-snug shadow-lg ${moving && first ? "block" : "hidden group-hover:block"}`}
                style={{ background: d ? ({ bought: C.win, maybe: C.mid, left: "#fff" }[outcome(sim, p.id) ?? "left"]) : "#fff", color: "#000" }}>
                {thought.length > 110 ? thought.slice(0, 110) + "…" : thought}
              </div>
            )}
          </button>
        ))}
    </Fit>
  );
}

// Scale the map down to the screen so the exits on the right are never cut off.
function Fit({ width, height, children }: { width: number; height: number; children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [k, setK] = useState(1);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const ro = new ResizeObserver(() => setK(Math.min(1, (el.clientWidth - 16) / width)));
    ro.observe(el); return () => ro.disconnect();
  }, [width]);
  return (
    <div ref={ref} className="relative mt-6 overflow-hidden rounded-3xl border border-white/10 panel" style={{ height: height * k + 16, backgroundImage: "radial-gradient(rgba(127,127,127,0.18) 1px, transparent 1px)", backgroundSize: "22px 22px" }}>
      <div className="absolute left-1/2 top-2" style={{ width, height, transform: `translateX(-50%) scale(${k})`, transformOrigin: "top center" }}>{children}</div>
    </div>
  );
}

// What everyone is thinking right now: big speech cards drifting past, above the map.
export function ThoughtStream({ sim }: { sim: Sim }) {
  const items = sim.personas.flatMap((p) => {
    const d = sim.decisions[p.id], steps = sim.live[p.id] ?? [];
    const last = steps[steps.length - 1];
    const text = d ? d.quote : last?.thought;
    if (!text) return [];
    const o = outcome(sim, p.id);
    return [{ p, text, o, feeling: (d?.feeling ?? last?.feeling ?? "neutral") as Feeling }];
  });
  if (!items.length) return null;
  const live = sim.status === "browsing";
  const card = (it: (typeof items)[number], i: number) => (
    <div key={i} className="mx-2 inline-flex w-[360px] shrink-0 items-start gap-3 whitespace-normal rounded-2xl border border-white/15 bg-[var(--card)] p-3 align-top shadow-lg panel"
      style={{ borderLeft: `5px solid ${it.o === "bought" ? C.win : it.o === "maybe" ? C.mid : it.o === "left" ? C.loss : SHIRT[it.p.archetype] ?? C.brain}` }}>
      <div className="shrink-0"><Avatar seed={it.p.avatar.seed} archetype={it.p.archetype} model={it.p.model} age={it.p.age} size={44} feeling={it.feeling} /></div>
      <div className="min-w-0">
        <div className="text-[13px]"><b>{it.p.name}</b> <span className="text-white/45">· {it.p.kind === "agent" ? "AI agent" : it.p.archetype}</span>
          {it.o && <span className="ml-1 font-mono text-[10px] font-semibold uppercase" style={{ color: it.o === "bought" ? C.win : it.o === "maybe" ? C.mid : C.loss }}>{it.o === "bought" ? "bought" : it.o === "maybe" ? "maybe later" : "left"}</span>}</div>
        <p className="mt-0.5 line-clamp-3 text-[14px] leading-snug text-white/85">“{it.text}”</p>
      </div>
    </div>
  );
  return (
    <section className="mt-6">
      <div className="mb-2 flex items-center justify-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-[0.25em]" style={{ color: live ? C.loss : "rgba(127,127,127,0.9)" }}>
        {live && <span className="h-2 w-2 animate-pulse rounded-full" style={{ background: C.loss }} />}{live ? "live · what they're thinking" : "what they said"}
      </div>
      <div className="relative overflow-hidden py-1" style={{ maskImage: "linear-gradient(90deg, transparent, black 6%, black 94%, transparent)", WebkitMaskImage: "linear-gradient(90deg, transparent, black 6%, black 94%, transparent)" }}>
        <div className="ticker flex w-max" style={{ animationDuration: `${Math.max(40, items.length * 7)}s` }}>{items.map(card)}{items.map((it, i) => card(it, i + 100))}</div>
      </div>
    </section>
  );
}
