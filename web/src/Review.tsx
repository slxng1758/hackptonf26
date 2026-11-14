import { useState } from "react";
import type { Draft } from "./types";
import { C, LABEL, PANEL } from "./theme";

export function Review({ draft, onRun, onBack, busy }: { draft: Draft; onRun: (d: Draft) => void; onBack: () => void; busy: boolean }) {
  const [d, setD] = useState<Draft>(draft);
  const [newFact, setNewFact] = useState("");
  const [editListing, setEditListing] = useState(false);
  const set = (patch: Partial<Draft>) => setD({ ...d, ...patch });
  const ready = d.listing.trim().length > 4 && d.facts.length > 0 && d.competitors.length > 0 && d.customers.trim().length > 4;

  const compName = (i: number) => d.competitor_meta?.[i]?.name ?? d.competitors[i].split(".")[0];

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <button onClick={onBack} className="font-mono text-[11px] text-white/45 hover:text-white">← start over</button>
      <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className={LABEL}>{d.source === "scan" ? "here's what we found · fix anything that's wrong" : "demo business"}</div>
          <h1 className="mt-1 font-serif text-[40px] leading-tight">{d.name}</h1>
          <div className="font-mono text-[13px] text-white/50">{d.category}</div>
        </div>
        <button disabled={!ready || busy} onClick={() => onRun(d)} className="rounded-xl px-7 py-3.5 text-[15px] font-semibold text-black disabled:opacity-40"
          style={{ background: C.win, boxShadow: `0 0 40px ${C.win}55` }}>
          {busy ? "Running…" : "Send in the shopping agents →"}
        </button>
      </div>
      {!ready && <p className="mt-2 text-[12px]" style={{ color: C.mid }}>Needs a listing, at least one fact, one competitor and a line about your customers.</p>}

      <div className="mt-8 grid gap-5 lg:grid-cols-2">
        {/* listing */}
        <section className={`${PANEL} p-5`}>
          <div className="flex items-center justify-between">
            <span className={LABEL}>how you describe yourself today</span>
            <button onClick={() => setEditListing(!editListing)} className="font-mono text-[11px] text-white/45 hover:text-white">{editListing ? "done" : "edit"}</button>
          </div>
          {editListing
            ? <textarea autoFocus rows={4} value={d.listing} onChange={(e) => set({ listing: e.target.value })} className="mt-3 w-full rounded-xl border border-white/15 bg-white/[0.04] p-3 font-serif text-[16px] outline-none" />
            : <p className="mt-3 font-serif text-[18px] leading-snug text-white/90">“{d.listing}”</p>}
        </section>

        {/* customers */}
        <section className={`${PANEL} p-5`}>
          <div className="flex items-center justify-between">
            <span className={LABEL}>your customers</span>
            <label className="cursor-pointer font-mono text-[11px]" style={{ color: C.win }}>
              upload CSV instead<input type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => e.target.files?.[0]?.text().then((t) => set({ customers: t, customers_csv: true }))} />
            </label>
          </div>
          {d.customers_csv
            ? <p className="mt-3 text-[14px] text-white/70">CSV with {d.customers.split("\n").length - 1} rows loaded. Names, emails, phones, addresses and IDs are dropped before anything is sent to a model. <button onClick={() => set({ customers: draft.customers, customers_csv: false })} className="underline">undo</button></p>
            : <textarea rows={4} value={d.customers} onChange={(e) => set({ customers: e.target.value })} className="mt-3 w-full resize-none bg-transparent text-[14px] leading-relaxed text-white/80 outline-none" />}
        </section>

        {/* facts */}
        <section className={`${PANEL} p-5 lg:col-span-2`}>
          <span className={LABEL}>your facts · the rewrite will only use these · remove anything untrue</span>
          <div className="mt-3 flex flex-wrap gap-2">
            {d.facts.map((f, i) => (
              <span key={i} className="group flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.04] py-1.5 pl-3 pr-2 text-[13px]">
                {f}
                <button onClick={() => set({ facts: d.facts.filter((_, k) => k !== i) })} className="grid h-5 w-5 place-items-center rounded-full text-white/40 hover:bg-white/10 hover:text-white" aria-label="remove">×</button>
              </span>
            ))}
            <form onSubmit={(e) => { e.preventDefault(); if (newFact.trim()) { set({ facts: [...d.facts, newFact.trim()] }); setNewFact(""); } }}>
              <input value={newFact} onChange={(e) => setNewFact(e.target.value)} placeholder="+ add a fact" className="rounded-full border border-dashed border-white/20 bg-transparent px-3 py-1.5 text-[13px] outline-none placeholder:text-white/35 focus:border-[#3ff0d4]" />
            </form>
          </div>
        </section>

        {/* competitors */}
        <section className="lg:col-span-2">
          <div className={LABEL}>your competitors{d.source === "scan" ? " · found on the web" : ""}</div>
          <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {d.competitors.map((c, i) => (
              <div key={i} className={`${PANEL} relative p-4`}>
                <button onClick={() => set({ competitors: d.competitors.filter((_, k) => k !== i), competitor_meta: d.competitor_meta?.filter((_, k) => k !== i) })}
                  className="absolute right-2 top-2 grid h-6 w-6 place-items-center rounded-full text-white/35 hover:bg-white/10 hover:text-white" aria-label="remove">×</button>
                <div className="pr-6 text-[14px] font-semibold">{compName(i)}</div>
                {d.competitor_meta?.[i]?.url && <a href={d.competitor_meta[i].url} target="_blank" rel="noreferrer" className="block truncate font-mono text-[10.5px] text-white/40 hover:text-white">{d.competitor_meta[i].url.replace(/^https?:\/\//, "")}</a>}
                <p className="mt-2 text-[12.5px] leading-snug text-white/60">{c}</p>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
