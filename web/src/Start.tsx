import { useState } from "react";
import { Avatar } from "./Avatar";
import { C } from "./theme";
import { YourSites } from "./Timeline";

const WORLDS = ["Normal times", "COVID-19 (2020)", "A recession", "Holiday rush"];
const CROWD = [
  { seed: 11, a: "price-sensitive", age: 24, f: "interested" },
  { seed: 402, a: "skeptic", age: 51, f: "skeptical" },
  { seed: 77, a: "enthusiast", age: 29, f: "delighted" },
  { seed: 913, a: "quality-first", age: 63, f: "neutral" },
  { seed: 250, a: "first-time user", age: 19, f: "confused" },
] as const;


// The store floor behind the hero: a website as a map of pages, with customers walking it and thinking out loud.
const PAGES = [
  { x: 70, y: 90, label: "Home" }, { x: 330, y: 610, label: "Menu" }, { x: 1180, y: 110, label: "Product" },
  { x: 1210, y: 560, label: "Cart" }, { x: 80, y: 520, label: "FAQ" }, { x: 900, y: 690, label: "Checkout" },
];
const ROUTES = [
  { path: "M190 160 C 420 120, 900 60, 1180 170", dur: 11, seed: 11, a: "price-sensitive", age: 24, f: "interested", say: "$24? pricey…" },
  { path: "M1300 250 C 1360 380, 1330 470, 1320 560", dur: 8, seed: 77, a: "enthusiast", age: 29, f: "delighted", say: "added to cart!" },
  { path: "M190 230 C 160 330, 150 420, 180 520", dur: 9, seed: 402, a: "skeptic", age: 51, f: "skeptical", say: "any reviews?" },
  { path: "M260 160 C 380 300, 400 470, 430 610", dur: 12, seed: 250, a: "first-time user", age: 19, f: "confused", say: "where's the price?" },
  { path: "M1210 660 C 1120 720, 1060 740, 1020 740", dur: 7, seed: 913, a: "quality-first", age: 63, f: "interested", say: "50 washes, ok" },
] as const;

function Scene() {
  return (
    <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 1440 860" preserveAspectRatio="xMidYMid slice" aria-hidden
      style={{ maskImage: "radial-gradient(ellipse 38% 46% at 50% 50%, transparent 55%, black 100%)", WebkitMaskImage: "radial-gradient(ellipse 38% 46% at 50% 50%, transparent 55%, black 100%)" }}>
      <defs><linearGradient id="trail" x1="0" x2="1"><stop offset="0" stopColor="#3ff0d4" /><stop offset="1" stopColor="#d16bff" /></linearGradient></defs>
      {ROUTES.map((r, i) => <path key={i} d={r.path} fill="none" stroke="url(#trail)" strokeOpacity=".35" strokeWidth="1.5" strokeDasharray="6 7" className="flow" />)}
      {PAGES.map((p) => (
        <g key={p.label} transform={`translate(${p.x} ${p.y})`} opacity=".55">
          <rect width="230" height="140" rx="14" fill="#10121b" stroke="#3ff0d4" strokeOpacity=".25" />
          <rect x="0" y="0" width="230" height="26" rx="14" fill="#ffffff" fillOpacity=".04" />
          <circle cx="14" cy="13" r="3" fill="#ff3355" opacity=".6" /><circle cx="26" cy="13" r="3" fill="#ffb547" opacity=".6" /><circle cx="38" cy="13" r="3" fill="#3ff0d4" opacity=".6" />
          <text x="54" y="17" fontSize="11" fill="#f2efe8" opacity=".6" fontFamily="JetBrains Mono, monospace">{p.label.toLowerCase()}</text>
          <rect x="16" y="42" width="120" height="10" rx="5" fill="#f2efe8" opacity=".14" />
          <rect x="16" y="62" width="190" height="7" rx="3.5" fill="#f2efe8" opacity=".08" />
          <rect x="16" y="76" width="160" height="7" rx="3.5" fill="#f2efe8" opacity=".08" />
          <rect x="16" y="100" width="70" height="22" rx="11" fill="#3ff0d4" opacity=".25" />
        </g>
      ))}
      {ROUTES.map((r, i) => (
        <g key={i}>
          <animateMotion dur={`${r.dur}s`} repeatCount="indefinite" path={r.path} keyPoints="0;1;1" keyTimes="0;0.8;1" calcMode="linear" />
          <g transform="translate(-20 -20)">
            <Avatar seed={r.seed} archetype={r.a} age={r.age} feeling={r.f} size={40} />
          </g>
          <g transform="translate(-6 -58)">
            <rect width={r.say.length * 7.2 + 18} height="26" rx="13" fill="#fff" />
            <text x="9" y="17" fontSize="12" fill="#000" fontFamily="Inter, system-ui, sans-serif">{r.say}</text>
            <animate attributeName="opacity" values="0;0;1;1;0" keyTimes="0;0.35;0.45;0.8;1" dur={`${r.dur}s`} repeatCount="indefinite" />
          </g>
        </g>
      ))}
    </svg>
  );
}

export interface StartInput { description: string; name: string; price: string; context: string; world: string }

const EXAMPLE = {
  name: "Oat milk latte",
  price: "$5.50",
  description: "Our house oat milk latte: a double shot of espresso with steamed oat milk, made to order. Available hot or iced, " +
    "in 12 oz or 16 oz. Add a flavor shot (vanilla, caramel or lavender) for 75 cents. Order at the counter or ahead online for pickup.",
};

export function Start({ onGo, onOpen }: { onGo: (b: StartInput) => void; onOpen: (id: string) => void }) {
  const [description, setDescription] = useState("");
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");
  const [more, setMore] = useState(false);
  const [context, setContext] = useState("");
  const [world, setWorld] = useState(WORLDS[0]);
  const ready = description.trim().length >= 10;
  const go = (b?: { description: string; name: string; price: string }) => {
    const x = b ?? { description, name, price };
    if (x.description.trim().length >= 10) onGo({ ...x, description: x.description.trim(), context, world: world === WORLDS[0] ? "" : world });
  };

  return (
    <div className="relative overflow-hidden">
    <Scene />
    <div className="relative mx-auto flex min-h-[calc(100vh-64px)] max-w-2xl flex-col items-center justify-center px-6 text-center">
      <div className="flex -space-x-3">
        {CROWD.map((c, i) => <div key={i} className="rounded-full ring-4 ring-[#08080d]" style={{ animationDelay: `${i * 0.2}s` }}><Avatar seed={c.seed} archetype={c.a} age={c.age} feeling={c.f} size={64} busy /></div>)}
      </div>
      <h1 className="mt-8 font-serif text-[56px] leading-[1.02]">Watch your customers<br /><span className="shimmer">try your product.</span></h1>
      <p className="mt-3 text-[16px] text-white/55">Describe it. AI customers look it over, think out loud, and decide if they'd buy.</p>

      <form onSubmit={(e) => { e.preventDefault(); go(); }} className="mt-10 w-full space-y-2 rounded-2xl border border-white/15 bg-white/[0.04] p-3 text-left focus-within:border-[#3ff0d4]">
        <textarea autoFocus value={description} onChange={(e) => setDescription(e.target.value)} rows={5}
          placeholder="Describe your product the way you'd explain it to a customer: what it is, what's in it, options, price, how to get it."
          className="w-full resize-none bg-transparent px-3 py-2 text-[16px] leading-relaxed outline-none placeholder:text-white/30" />
        <div className="flex gap-2">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Product name (optional)"
            className="min-w-0 flex-1 rounded-xl border border-white/10 bg-transparent px-3 py-2 text-[14px] outline-none placeholder:text-white/30 focus:border-white/30" />
          <input value={price} onChange={(e) => setPrice(e.target.value)} placeholder="Price (optional)"
            className="w-36 rounded-xl border border-white/10 bg-transparent px-3 py-2 text-[14px] outline-none placeholder:text-white/30 focus:border-white/30" />
          <button disabled={!ready} className="rounded-xl px-7 text-[16px] font-semibold text-black disabled:opacity-40" style={{ background: C.win, boxShadow: `0 0 30px ${C.win}55` }}>Go</button>
        </div>
      </form>

      <div className="mt-4 flex flex-wrap justify-center gap-2 text-[13px]">
        <span className="text-white/35">try:</span>
        <button onClick={() => { setDescription(EXAMPLE.description); setName(EXAMPLE.name); setPrice(EXAMPLE.price); go(EXAMPLE); }}
          className="text-white/60 underline decoration-white/20 hover:text-white">an oat milk latte</button>
        <span className="text-white/20">·</span>
        <button onClick={() => setMore(!more)} className="text-white/45 hover:text-white">{more ? "− less" : "+ what changed?"}</button>
      </div>

      {more && (
        <div className="rise mt-5 w-full space-y-3 text-left">
          <input value={context} onChange={(e) => setContext(e.target.value)} placeholder="e.g. we raised prices 10%, or we added online ordering"
            className="w-full rounded-xl border border-white/15 bg-white/[0.04] px-4 py-2.5 text-[14px] outline-none focus:border-[#3ff0d4]" />
          <div className="flex flex-wrap gap-2">
            {WORLDS.map((w) => <button key={w} onClick={() => setWorld(w)} className={`rounded-full border px-3 py-1 text-[13px] ${world === w ? "border-[#3ff0d4] text-[#3ff0d4]" : "border-white/15 text-white/55"}`}>{w}</button>)}
          </div>
        </div>
      )}
      <YourSites onOpen={onOpen} />
    </div>
    </div>
  );
}
