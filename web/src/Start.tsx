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

export function Start({ onGo, onOpen }: { onGo: (b: { url: string; context: string; world: string }) => void; onOpen: (id: string) => void }) {
  const [url, setUrl] = useState("");
  const [more, setMore] = useState(false);
  const [context, setContext] = useState("");
  const [world, setWorld] = useState(WORLDS[0]);
  const go = (u = url) => u.trim().length > 3 && onGo({ url: u.trim(), context, world: world === WORLDS[0] ? "" : world });

  return (
    <div className="mx-auto flex min-h-[calc(100vh-64px)] max-w-2xl flex-col items-center justify-center px-6 text-center">
      <div className="flex -space-x-3">
        {CROWD.map((c, i) => <div key={i} className="rounded-full ring-4 ring-[#08080d]" style={{ animationDelay: `${i * 0.2}s` }}><Avatar seed={c.seed} archetype={c.a} age={c.age} feeling={c.f} size={64} busy /></div>)}
      </div>
      <h1 className="mt-8 font-serif text-[48px] leading-[1.05]">Watch your customers<br />try your website.</h1>
      <p className="mt-3 text-[16px] text-white/55">AI customers open it, click around, think out loud, and decide if they'd buy.</p>

      <form onSubmit={(e) => { e.preventDefault(); go(); }} className="mt-10 flex w-full gap-2 rounded-2xl border border-white/15 bg-white/[0.04] p-2 focus-within:border-[#3ff0d4]">
        <input autoFocus value={url} onChange={(e) => setUrl(e.target.value)} placeholder="yourwebsite.com"
          className="min-w-0 flex-1 bg-transparent px-4 py-3 text-[18px] outline-none placeholder:text-white/30" />
        <button className="rounded-xl px-7 text-[16px] font-semibold text-black" style={{ background: C.win, boxShadow: `0 0 30px ${C.win}55` }}>Go</button>
      </form>

      <div className="mt-4 flex flex-wrap justify-center gap-2 text-[13px]">
        <span className="text-white/35">try:</span>
        {["olivesprinceton.com"].map((u) => <button key={u} onClick={() => { setUrl(u); go(u); }} className="text-white/60 underline decoration-white/20 hover:text-white">{u}</button>)}
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
  );
}
