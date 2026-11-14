// What happens after they shop: they post about it (word of mouth), we check the prediction against reality (evals),
// and each persona keeps what it learned. Shapes: sim-extras.ts (Sarah's contract).
import { Avatar, SHIRT } from "./Avatar";
import { C, PANEL } from "./theme";
import type { Persona } from "./Simulate";
import type { EvalScore, PersonaChange, Social } from "./sim-extras";

const sentColor = (s: number) => (s > 0.15 ? C.win : s < -0.15 ? C.loss : C.mid);
const seedOf = (id: string) => [...id].reduce((a, c) => a * 31 + c.charCodeAt(0), 7) % 10000;

function who(personas: Persona[], id: string, label = id) {
  const p = personas.find((x) => x.id === id);
  return p ?? ({ id, name: label, age: 35, archetype: "", avatar: { seed: seedOf(id) } } as unknown as Persona);
}

// ---------- word of mouth ----------
export function WordOfMouth({ social, personas }: { social: Social; personas: Persona[] }) {
  const byId = Object.fromEntries(social.posts.map((p) => [p.id, p]));
  const top = social.top_influencers[0];
  const R = 150, CX = 200, CY = 185;
  const pos = Object.fromEntries(social.nodes.map((n, i) => {
    const a = (i / social.nodes.length) * Math.PI * 2 - Math.PI / 2;
    return [n.id, { x: CX + R * Math.cos(a), y: CY + R * Math.sin(a) }];
  }));
  const maxC = Math.max(...social.nodes.map((n) => n.centrality), 0.01);

  return (
    <section className="mx-auto mt-14 max-w-5xl">
      <h2 className="text-center font-serif text-[30px]">Then they talked about it</h2>
      <p className="mx-auto mt-2 max-w-2xl text-center text-[15px] text-white/60">{social.summary}</p>
      <div className="mt-6 grid gap-5 md:grid-cols-[1fr_400px]">
        <div className={`${PANEL} max-h-[420px] space-y-3 overflow-y-auto p-4`}>
          {social.posts.map((post) => {
            const p = who(personas, post.author, social.nodes.find((n) => n.id === post.author)?.label);
            const t = post.target ? byId[post.target] : null;
            const tp = t ? who(personas, t.author, social.nodes.find((n) => n.id === t.author)?.label) : null;
            return (
              <div key={post.id} className={`rise flex gap-3 ${post.kind !== "post" ? "ml-8" : ""}`}>
                <Avatar seed={p.avatar.seed} archetype={p.archetype} age={p.age} size={36} feeling={post.sentiment > 0.15 ? "interested" : post.sentiment < -0.15 ? "annoyed" : "neutral"} />
                <div className="min-w-0 flex-1 rounded-xl bg-white/[0.04] px-3 py-2">
                  <div className="flex items-center gap-2 text-[12px]">
                    <b>{p.name}</b>
                    {tp && <span className="text-white/40">{post.kind === "repost" ? "🔁 reposted" : "↩ replied to"} {tp.name}</span>}
                    {post.author === top && <span className="rounded-full px-1.5 font-mono text-[9px] font-semibold text-black" style={{ background: C.mid }}>spreads furthest</span>}
                    <span className="ml-auto h-2 w-2 rounded-full" style={{ background: sentColor(post.sentiment) }} />
                  </div>
                  <p className="mt-0.5 text-[14px] leading-snug text-white/85">{post.text}</p>
                </div>
              </div>
            );
          })}
        </div>
        <div className={`${PANEL} relative`}>
          <svg viewBox="0 0 400 370" className="w-full">
            <defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="rgba(255,255,255,0.4)" /></marker></defs>
            {social.edges.map((e, i) => {
              const a = pos[e.source], b = pos[e.target]; if (!a || !b) return null;
              const dx = b.x - a.x, dy = b.y - a.y, L = Math.hypot(dx, dy) || 1, r = 34;
              return <line key={i} x1={a.x + (dx / L) * r} y1={a.y + (dy / L) * r} x2={b.x - (dx / L) * r} y2={b.y - (dy / L) * r}
                stroke={e.kind === "repost" ? C.mid : "rgba(255,255,255,0.35)"} strokeWidth={1 + e.weight} strokeDasharray={e.kind === "repost" ? "0" : "5 4"} markerEnd="url(#arr)" className={e.kind === "reply" ? "flow" : ""} />;
            })}
          </svg>
          {social.nodes.map((n) => {
            const p = who(personas, n.id, n.label), s = 34 + (n.centrality / maxC) * 30, at = pos[n.id];
            return (
              <div key={n.id} className="absolute flex -translate-x-1/2 -translate-y-1/2 flex-col items-center" style={{ left: `${(at.x / 400) * 100}%`, top: `${(at.y / 370) * 100}%` }}>
                {n.id === top && <span className="mb-0.5 text-[14px]">👑</span>}
                <div className="rounded-full" style={{ boxShadow: `0 0 0 3px ${sentColor(n.sentiment)}, 0 0 ${n.id === top ? 30 : 0}px ${sentColor(n.sentiment)}` }}>
                  <Avatar seed={p.avatar.seed} archetype={p.archetype || n.archetype} age={p.age} size={s} />
                </div>
                <span className="mt-1 font-mono text-[10px] text-white/70">{n.label}</span>
              </div>
            );
          })}
          <div className="absolute bottom-2 left-3 font-mono text-[10px] text-white/40">bigger = spreads further · ring = mood · 🔁 repost ⇢ reply</div>
        </div>
      </div>
    </section>
  );
}

// ---------- were we right? ----------
export function Accuracy({ evals }: { evals: EvalScore[] }) {
  const last = evals[evals.length - 1];
  const W = 360, H = 120, maxE = Math.max(...evals.map((e) => e.rating_error), 0.5);
  const pts = evals.map((e, i) => [20 + (i / Math.max(evals.length - 1, 1)) * (W - 40), H - 15 - (e.rating_error / maxE) * (H - 35)]);
  const themes = last.real_themes.length ? last.real_themes.map((t) => t.theme) : [...last.matched_themes, ...last.missed_themes];
  return (
    <section className="mx-auto mt-14 max-w-5xl">
      <h2 className="text-center font-serif text-[30px]">Were we right?</h2>
      <p className="mt-2 text-center text-[15px] text-white/60">We checked the prediction against real public reviews the customers never saw.</p>
      <div className="mt-6 grid gap-5 md:grid-cols-3">
        <div className={`${PANEL} p-5 text-center`}>
          <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-white/40">rating</div>
          <div className="mt-3 flex items-baseline justify-center gap-3 font-mono">
            <span><span className="text-[40px] font-semibold">{last.predicted_rating.toFixed(1)}</span><span className="block text-[11px] text-white/45">we predicted</span></span>
            <span className="text-white/30">vs</span>
            <span><span className="text-[40px] font-semibold" style={{ color: C.win }}>{last.actual_rating.toFixed(1)}</span><span className="block text-[11px] text-white/45">real reviews</span></span>
          </div>
          <div className="mt-2 text-[13px] text-white/60">off by {last.rating_error.toFixed(1)} stars</div>
        </div>
        <div className={`${PANEL} p-5`}>
          <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-white/40">error as personas learn</div>
          <svg viewBox={`0 0 ${W} ${H}`} className="mt-2 w-full">
            <polyline points={pts.map((p) => p.join(",")).join(" ")} fill="none" stroke={C.win} strokeWidth="2.5" />
            {pts.map(([x, y], i) => <g key={i}><circle cx={x} cy={y} r="4" fill={C.win} /><text x={x} y={y - 9} textAnchor="middle" fontSize="11" fill="rgba(255,255,255,.7)">{evals[i].rating_error.toFixed(1)}</text><text x={x} y={H - 1} textAnchor="middle" fontSize="10" fill="rgba(255,255,255,.4)">round {evals[i].iteration}</text></g>)}
          </svg>
        </div>
        <div className={`${PANEL} p-5`}>
          <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-white/40">what real reviewers said · {Math.round(last.theme_recall * 100)}% caught</div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {themes.map((t) => { const hit = last.matched_themes.includes(t); return (
              <span key={t} className="rounded-full px-2.5 py-1 text-[12px]" style={hit ? { background: `${C.win}22`, color: C.win } : { background: "rgba(255,255,255,0.05)", color: "rgba(255,255,255,0.45)", textDecoration: "line-through" }}>{hit ? "✓ " : ""}{t}</span>
            ); })}
          </div>
          {last.notes && <p className="mt-3 text-[12px] text-white/50">{last.notes}</p>}
        </div>
      </div>
    </section>
  );
}

// ---------- what each persona learned ----------
export function Learned({ changes, personas }: { changes: PersonaChange[]; personas: Persona[] }) {
  return (
    <section className="mx-auto mt-14 max-w-3xl">
      <h2 className="text-center font-serif text-[30px]">What they learned for next time</h2>
      <div className="mt-6 space-y-3">
        {changes.map((c, i) => { const p = who(personas, c.persona_id); return (
          <div key={i} className={`${PANEL} flex gap-4 p-4`}>
            <div className="h-fit self-start rounded-full" style={{ boxShadow: `0 0 0 2px ${SHIRT[p.archetype] ?? "#888"}` }}><Avatar seed={p.avatar.seed} archetype={p.archetype} age={p.age} size={44} feeling="interested" /></div>
            <div className="min-w-0 flex-1">
              <div className="text-[14px]"><b>{p.name}</b> <span className="font-mono text-[11px] text-white/40">round {c.iteration}</span></div>
              <p className="text-[14px] text-white/80">{c.lesson}</p>
              <div className="mt-2 grid gap-2 font-mono text-[11.5px] md:grid-cols-2">
                <div className="rounded-lg bg-white/[0.03] p-2 text-white/45"><span className="text-white/30">before </span>{c.before || "(nothing yet)"}</div>
                <div className="rounded-lg p-2" style={{ background: `${C.win}12`, color: C.win }}><span className="opacity-60">after </span>{c.after}</div>
              </div>
            </div>
          </div>
        ); })}
      </div>
    </section>
  );
}
