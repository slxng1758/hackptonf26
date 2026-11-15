// The website drawn as a map of the pages customers actually visited. Avatars walk between pages as they click,
// then leave through the exits on the right: bought, maybe later, or left.
import { useEffect, useMemo, useRef, useState } from "react";
import { Avatar, SHIRT, type Feeling } from "./Avatar";
import { C, THEME } from "./theme";
const PAPER = true;  // flat look in every theme: thin lines, no glows
const INK = THEME === "receipt" ? "27,24,19" : "255,255,255";
import type { Persona, Sim } from "./Simulate";

const COL = 250, ROW = 170, NODE_W = 190, NODE_H = 120, EXIT_H = 165, PAD = 40;
const BOUGHT = new Set(["buy", "would recommend"]);
const MAYBE = new Set(["maybe later"]);

// What each customer did (b2a/outcome.py): placing an order is buying. Stored per decision; older sims fall back to the decision.
export type Outcome = "bought" | "bought_unhappy" | "abandoned_cart" | "maybe" | "left";
export const OUTCOME_LABEL: Record<Outcome, string> = { bought: "bought", bought_unhappy: "bought, unhappy", abandoned_cart: "left the cart", maybe: "maybe later", left: "didn't buy" };
export function outcomeDetail(sim: Sim, pid: string): Outcome | null {
  const d = sim.decisions[pid] as (Sim["decisions"][string] & { outcome?: Outcome }) | undefined;
  if (!d) return null;
  if (d.outcome) return d.outcome;
  if (BOUGHT.has(d.decision)) return "bought";
  if (MAYBE.has(d.decision)) return "maybe";
  return (sim.live[pid] ?? []).some((x) => x.cart) ? "abandoned_cart" : "left";
}
export const outcomeColor = (o: Outcome | null) =>
  o === "bought" ? C.win : o === "bought_unhappy" || o === "maybe" ? C.mid : o ? C.loss : C.brain;

// The three-way view used for colors and counts: a sale (happy or not), maybe later, or lost.
export function outcome(sim: Sim, pid: string): "bought" | "maybe" | "left" | null {
  const o = outcomeDetail(sim, pid);
  return o === null ? null : o === "bought" || o === "bought_unhappy" ? "bought" : o === "maybe" ? "maybe" : "left";
}

function keyOf(u: string, rootHost: string) {
  try {
    const x = new URL(u);
    const path = x.pathname.replace(/\/+$/, "") || "/";
    const host = x.host.replace(/^www\./, "");
    if (path.startsWith("/api/product/")) return { key: host + path, label: path.endsWith("-cart.html") ? "Cart" : path.endsWith("-checkout.html") ? "Checkout" : "Product page" };  // the rebuilt Amazon listing
    const label = host !== rootHost ? host + (path === "/" ? "" : " · " + decodeURIComponent(path.split("/").filter(Boolean).pop() ?? "").replace(/[-_]+/g, " ")) : path === "/" ? "Home" : decodeURIComponent(path.split("/").filter(Boolean).pop() ?? "").replace(/[-_]+/g, " ").replace(/\.\w+$/, "");
    return { key: host + path, label: label.charAt(0).toUpperCase() + label.slice(1) };
  } catch { return { key: u, label: u }; }
}

export function SiteMap({ sim, onOpen, onThought }: { sim: Sim; onOpen: (p: Persona) => void; onThought?: (p: Persona) => void }) {
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
            return <path key={e.a + e.b} d={d} fill="none" stroke={PAPER ? `rgba(${INK},0.35)` : "rgba(74,222,154,0.35)"} strokeWidth={PAPER ? 1 + e.n * 0.6 : 1 + e.n} strokeDasharray={PAPER ? "2 5" : "6 6"} strokeLinecap="round" className="flow" />;
          })}
        </svg>

        {[...nodes.values()].map((n) => { const here = crowd.get(n.key) ?? 0; const heat = Math.min(n.visits / maxVisits, 1); return (
          <div key={n.key} onMouseEnter={() => setHover(n.key)} onMouseLeave={() => setHover(null)}
            data-zoom={n.shot ? `/api/shots/${sim.id}/shots/${n.shot}` : undefined} data-title={n.label} data-sub={`${n.visits} visit${n.visits === 1 ? "" : "s"}`}
            className={`absolute overflow-hidden border bg-[var(--card)] transition-all duration-700 hover:z-20 hover:scale-[1.6] ${PAPER ? "rounded-[3px]" : "rounded-2xl"} ${here ? "heat" : ""}`}
            style={{ left: n.x, top: n.y, width: NODE_W, height: NODE_H, transformOrigin: "top left",
              borderColor: PAPER ? (hover === n.key || here ? C.text : `rgba(${INK},${0.14 + heat * 0.4})`) : n.blocked ? "rgba(255,255,255,0.15)" : hover === n.key || here ? C.win : `rgba(74,222,154,${0.12 + heat * 0.4})`,
              boxShadow: PAPER ? (THEME === "receipt" ? (here ? `4px 4px 0 ${C.text}` : `3px 3px 0 rgba(27,24,19,${0.08 + heat * 0.25})`) : `0 12px 28px rgba(0,0,0,.45)`) : here ? `0 0 ${18 + here * 16}px ${C.win}${here > 2 ? "aa" : "66"}, inset 0 0 30px ${C.win}22` : `0 10px 30px rgba(0,0,0,.5), 0 0 ${heat * 24}px ${C.win}33` }}>
            {n.shot ? <img src={`/api/shots/${sim.id}/shots/${n.shot}`} alt="" className={`h-full w-full object-cover object-top ${THEME === "receipt" ? "opacity-90 grayscale-[35%]" : "opacity-75"}`} /> : <div className="h-full w-full bg-white/[0.03]" />}
            <div className="absolute inset-x-0 top-0 flex items-center justify-between px-2.5 pb-4 pt-1.5" style={{ background: "linear-gradient(var(--card) 55%, transparent)" }}>
              <span className="truncate text-[12px] font-semibold">{n.label}</span>
              {n.blocked ? <span className="on-brain font-mono text-[9px] text-white/50">bot check</span> : here > 0 ? <span className="rounded-full px-1.5 font-mono text-[10px] font-semibold text-black" style={{ background: C.win }}>{here} here</span> : n.visits > 0 && <span className="font-mono text-[10px] text-white/50">{n.visits}×</span>}
            </div>
            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-1" style={{ background: PAPER ? C.accent : `linear-gradient(90deg, ${C.win}, ${C.brain})`, opacity: heat }} />
          </div>
        ); })}

        {exits.map((e, i) => {
          const n = sim.personas.filter((p) => outcome(sim, p.id) === e.id).length;
          return (
            <div key={e.id} className={PAPER ? "panel absolute" : `absolute rounded-2xl border-2 ${e.id === "bought" && n ? "border-solid" : "border-dashed"}`} style={PAPER ? { left: exitX, top: exitY(i), width: NODE_W, height: EXIT_H, borderTop: `4px solid ${e.color}` } : { left: exitX, top: exitY(i), width: NODE_W, height: EXIT_H, borderColor: `${e.color}${n ? "cc" : "55"}`, background: `${e.color}${n ? "1a" : "0a"}`, boxShadow: e.id === "bought" && n ? `0 0 ${20 + n * 12}px ${e.color}66` : "none" }}>
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
            <div className="rounded-full" style={{ boxShadow: PAPER ? THEME === "receipt" ? `0 0 0 2px ${C.text}` : `0 0 0 2px ${SHIRT[p.archetype] ?? C.brain}` : `0 0 0 2.5px ${SHIRT[p.archetype]}, 0 6px 20px rgba(0,0,0,.6)` }}>
              <Avatar seed={p.avatar.seed} archetype={p.archetype} model={p.model} age={p.age} size={40} feeling={feeling} busy={moving} />
            </div>
            {outcome(sim, p.id) === "bought" && <span className="on-brain absolute -right-1 -top-1 grid h-4 w-4 place-items-center rounded-full text-[9px] font-bold text-black" style={{ background: C.win }}>✓</span>}
            <div className="mx-auto mt-0.5 w-[44px] truncate text-center font-mono text-[9px] text-white/70">{p.name}{p.model && <span className="block text-white/35" title={p.model_note}>{p.played_by ? `${p.model}→${p.played_by}` : p.model}</span>}</div>
            {thought && (
              // the transparent pb-1 bridges the gap to the avatar so hover holds while the mouse moves up to click it
              <div key={thought} role="button" title="Click to read it all" onClick={(e) => { e.stopPropagation(); (onThought ?? onOpen)(p); }}
                className={`absolute bottom-full left-1/2 z-30 w-[200px] -translate-x-1/2 cursor-pointer pb-1 ${moving && first ? "block" : "hidden group-hover:block"}`}>
                <div className="bubble rounded-xl px-2.5 py-1.5 text-left text-[11px] leading-snug shadow-lg transition hover:brightness-95"
                  style={{ background: d ? ({ bought: C.win, maybe: C.mid, left: "#fff" }[outcome(sim, p.id) ?? "left"]) : "#fff", color: "#000" }}>
                  {thought.length > 110 ? thought.slice(0, 110) + "…" : thought}
                  <span className="mt-0.5 block font-mono text-[9px] uppercase tracking-wider text-black/45">click to read more</span>
                </div>
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
    <div ref={ref} className="relative mt-6 overflow-hidden rounded-3xl border border-white/10 panel" style={PAPER
      ? { height: height * k + 16, backgroundImage: `linear-gradient(rgba(${INK},0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(${INK},0.05) 1px, transparent 1px)`, backgroundSize: "32px 32px" }  // a store floor plan
      : { height: height * k + 16, backgroundImage: "radial-gradient(rgba(127,127,127,0.18) 1px, transparent 1px)", backgroundSize: "22px 22px" }}>
      <div className="absolute left-1/2 top-2" style={{ width, height, transform: `translateX(-50%) scale(${k})`, transformOrigin: "top center" }}>{children}</div>
    </div>
  );
}

// What everyone is thinking right now: big speech cards drifting past, above the map.
export function ThoughtStream({ sim, onOpen }: { sim: Sim; onOpen?: (p: Persona) => void }) {  // onOpen: show this card in full (ThoughtCard)
  const items = sim.personas.flatMap((p) => {
    const d = sim.decisions[p.id], steps = sim.live[p.id] ?? [];
    const last = steps[steps.length - 1];
    const text = d ? d.quote : last?.thought;
    if (!text) return [];
    const o = outcome(sim, p.id), od = outcomeDetail(sim, p.id);
    return [{ p, text, o, od, feeling: (d?.feeling ?? last?.feeling ?? "neutral") as Feeling }];
  });
  if (!items.length) return null;
  const live = sim.status === "browsing";
  const card = (it: (typeof items)[number], i: number) => (
    <button key={i} type="button" onClick={() => onOpen?.(it.p)} title={`Read what ${it.p.name} is thinking`}
      className="mx-2 inline-flex w-[360px] shrink-0 cursor-pointer items-start gap-3 whitespace-normal rounded-2xl border border-white/15 bg-[var(--card)] p-3 text-left align-top shadow-lg transition hover:-translate-y-0.5 hover:border-white/40 panel"
      style={{ borderLeft: `5px solid ${it.od ? outcomeColor(it.od) : SHIRT[it.p.archetype] ?? C.brain}` }}>
      <div className="shrink-0"><Avatar seed={it.p.avatar.seed} archetype={it.p.archetype} model={it.p.model} age={it.p.age} size={44} feeling={it.feeling} /></div>
      <div className="min-w-0">
        <div className="text-[13px]"><b>{it.p.name}</b> <span className="text-white/45">· {it.p.kind === "agent" ? "AI agent" : it.p.archetype}</span>
          {it.od && <span className="ml-1 font-mono text-[10px] font-semibold uppercase" style={{ color: outcomeColor(it.od) }}>{OUTCOME_LABEL[it.od]}</span>}</div>
        <p className="mt-0.5 line-clamp-3 text-[14px] leading-snug text-white/85">“{it.text}”</p>
        {onOpen && <span className="mt-1 inline-block font-mono text-[10px] uppercase tracking-wider text-white/35">read more →</span>}
      </div>
    </button>
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

// One customer's thought in full: what they're thinking now (or their final word), the page they're on,
// and every thought so far. Opened from a ticker card or a map bubble; updates live while they shop.
export function ThoughtCard({ sim, pid, onClose, onOpen }: { sim: Sim; pid: string; onClose: () => void; onOpen: (p: Persona) => void }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    addEventListener("keydown", k);
    const was = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { removeEventListener("keydown", k); document.body.style.overflow = was; };
  }, [onClose]);
  const p = sim.personas.find((x) => x.id === pid);
  if (!p) return null;
  const steps = sim.live[pid] ?? [], last = steps[steps.length - 1], d = sim.decisions[pid];
  const od = outcomeDetail(sim, pid), color = od ? outcomeColor(od) : SHIRT[p.archetype] ?? C.brain;
  const host = (u: string) => u.replace(/^https?:\/\/(www\.)?/, "");
  const shotOf = (f: string | null) => (f ? `/api/shots/${sim.id}/shots/${f}` : null);
  const doing = (s: (typeof steps)[number]) => s.action === "click" || s.action === "click_at" ? `clicked “${s.target || s.clicked || "a spot"}”` : s.action === "decide" ? "ready to decide" : [s.action, s.target].filter(Boolean).join(" ");
  return (
    <div className="scrim fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 md:p-8" onClick={onClose}>
      <div className="flex max-h-full w-full max-w-[860px] flex-col overflow-hidden rounded-2xl border border-white/15 bg-[var(--card)] shadow-2xl" style={{ borderTop: `5px solid ${color}` }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-3 border-b border-white/10 px-5 py-3">
          <Avatar seed={p.avatar.seed} archetype={p.archetype} model={p.model} age={p.age} size={48} feeling={d?.feeling ?? last?.feeling ?? "neutral"} busy={!d && sim.status === "browsing"} />
          <div className="min-w-0 flex-1">
            <div className="text-[16px]"><b>{p.name}</b> <span className="text-white/50">· {p.kind === "agent" ? "AI agent" : `${p.age}, ${p.occupation}`}</span>
              {od && <span className="ml-2 font-mono text-[11px] font-semibold uppercase" style={{ color }}>{OUTCOME_LABEL[od]}</span>}</div>
            <div className="truncate font-mono text-[11px] text-white/45">{p.archetype}{p.model ? ` · ${p.model}` : ""}{p.goal ? ` · wants: ${p.goal}` : ""}{p.budget ? ` · budget ${p.budget}` : ""}</div>
          </div>
          <button onClick={onClose} aria-label="close" className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-[18px] text-white/60 hover:bg-white/10 hover:text-white">×</button>
        </div>

        <div className="min-h-0 flex-1 overflow-auto p-5">
          {d ? (
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.25em] text-white/40">their final word · {d.decision}{d.rating ? ` · ${d.rating}/5` : ""}</div>
              <p className="mt-1 font-serif text-[20px] leading-snug">“{d.quote}”</p>
              {d.reasons?.length > 0 && <ul className="mt-3 list-disc space-y-1 pl-5 text-[14px] text-white/80">{d.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>}
              {d.missing && <p className="mt-3 text-[14px]"><span className="font-semibold" style={{ color: C.loss }}>What was missing:</span> <span className="text-white/80">{d.missing}</span></p>}
            </div>
          ) : last ? (
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.25em] text-white/40">thinking right now · step {last.n} · felt {last.feeling}</div>
              <p className="mt-1 font-serif text-[20px] leading-snug">“{last.thought}”</p>
              <p className="mt-2 text-[13px]"><span className="font-semibold" style={{ color: C.brain }}>→ {doing(last)}</span> <span className="text-white/45">on {host(last.url)}</span></p>
            </div>
          ) : <p className="text-white/50">Hasn't started yet.</p>}

          {last?.shot && (
            <figure className="mt-4 overflow-hidden rounded-lg border border-white/10" data-zoom={shotOf(last.shot)!} data-title={`${p.name} · step ${last.n}`} data-sub={last.url}>
              <img src={shotOf(last.shot)!} alt="" className="block max-h-[320px] w-full object-cover object-top" />
              <figcaption className="truncate px-3 py-1.5 font-mono text-[11px] text-white/45">{d ? "last page they saw" : "where they are"} · {host(last.url)} · click to enlarge</figcaption>
            </figure>
          )}

          {steps.length > 0 && (
            <div className="mt-5">
              <div className="font-mono text-[10px] uppercase tracking-[0.25em] text-white/40">every thought so far</div>
              <ol className="mt-2 space-y-2">
                {[...steps].reverse().map((s) => (
                  <li key={s.n} className="flex gap-3 rounded-lg bg-white/[0.04] p-2.5">
                    {s.shot ? <img src={shotOf(s.shot)!} alt={`${p.name} · step ${s.n}`} className="h-14 w-20 shrink-0 rounded border border-white/10 object-cover object-top" /> : <div className="h-14 w-20 shrink-0 rounded bg-white/5" />}
                    <div className="min-w-0 text-[13px]">
                      <div className="truncate font-mono text-[10.5px] text-white/45">step {s.n} · {host(s.url)} · felt {s.feeling}{s.blocked ? " · bot check" : ""}</div>
                      <p className="leading-snug text-white/85">“{s.thought}”</p>
                      <div className="text-[12px]" style={{ color: C.brain }}>→ {doing(s)}</div>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>

        <div className="flex justify-end border-t border-white/10 px-5 py-3">
          <button onClick={() => onOpen(p)} className="on-brain rounded-xl px-4 py-2 text-[14px] font-semibold text-[#ffffff]" style={{ background: C.brain }}>Open full profile: prompts, decision, suggestions →</button>
        </div>
      </div>
    </div>
  );
}
