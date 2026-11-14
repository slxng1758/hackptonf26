import { useEffect, useState } from "react";
import type { Preset } from "./types";
import { LABEL, PANEL } from "./theme";

const field = "w-full rounded-xl border border-white/12 bg-white/[0.04] p-3 text-[14px] leading-snug outline-none focus:border-[#3ff0d4]";
const lines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);

export function Setup({ onStart, busy }: { onStart: (p: Preset & { customers_csv: boolean }) => void; busy: boolean }) {
  const [presets, setPresets] = useState<Record<string, Preset>>({});
  const [p, setP] = useState<Preset | null>(null);
  const [facts, setFacts] = useState("");
  const [comps, setComps] = useState("");
  const [csv, setCsv] = useState(false);
  const [open, setOpen] = useState(false);

  const load = (x: Preset) => { setP(x); setFacts(x.facts.join("\n")); setComps(x.competitors.join("\n\n")); setCsv(false); };
  useEffect(() => { fetch("/api/presets").then((r) => r.json()).then((d) => { setPresets(d); load(d.catering ?? Object.values(d)[0]); }).catch(() => {}); }, []);
  if (!p) return <div className="text-white/40">loading…</div>;

  function upload(f: File) { f.text().then((t) => { setP({ ...p!, customers: t }); setCsv(true); }); }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1.5">
        {Object.entries(presets).map(([k, x]) => (
          <button key={k} onClick={() => load(x)} className={`rounded-full border px-3 py-1 font-mono text-[11px] ${p.name === x.name ? "border-[#3ff0d4] text-[#3ff0d4]" : "border-white/15 text-white/60 hover:text-white"}`}>{x.category}</button>
        ))}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <label><span className={LABEL}>Business</span><input className={`${field} mt-1`} value={p.name} onChange={(e) => setP({ ...p, name: e.target.value })} /></label>
        <label><span className={LABEL}>What you sell</span><input className={`${field} mt-1`} value={p.category} onChange={(e) => setP({ ...p, category: e.target.value })} /></label>
      </div>

      <label className="block"><span className={LABEL}>Your listing, as agents see it today</span>
        <textarea rows={3} className={`${field} mt-1 font-serif text-[16px]`} value={p.listing} onChange={(e) => setP({ ...p, listing: e.target.value })} />
      </label>

      <label className="block"><span className={LABEL}>Your real facts · one per line · the rewrite can only use these</span>
        <textarea rows={6} className={`${field} mt-1 font-mono text-[12px]`} value={facts} onChange={(e) => setFacts(e.target.value)} />
      </label>

      <div className="block">
        <div className="flex items-center justify-between">
          <span className={LABEL}>Your customers</span>
          <label className="cursor-pointer font-mono text-[10.5px] text-[#3ff0d4] hover:underline">
            upload CSV<input type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          </label>
        </div>
        <textarea rows={3} className={`${field} mt-1`} value={p.customers} onChange={(e) => { setP({ ...p, customers: e.target.value }); setCsv(false); }} />
        {csv && <p className="mt-1 font-mono text-[10.5px] text-white/40">CSV loaded. Name, email, phone, address and ID columns are dropped before anything is sent to a model.</p>}
      </div>

      <button onClick={() => setOpen(!open)} className={`w-full ${PANEL} px-3 py-2 text-left font-mono text-[11px] text-white/60 hover:text-white`}>
        {open ? "▾" : "▸"} Competitors ({lines(comps.replace(/\n\n+/g, "\n")).length})
      </button>
      {open && <textarea rows={8} className={`${field} text-[12.5px]`} value={comps} onChange={(e) => setComps(e.target.value)} />}

      <button disabled={busy} onClick={() => onStart({ ...p, facts: lines(facts), competitors: comps.split(/\n\s*\n/).map((x) => x.trim()).filter(Boolean), customers_csv: csv })}
        className="w-full rounded-xl bg-[#3ff0d4] py-3.5 text-[15px] font-semibold text-black shadow-[0_0_40px_rgba(63,240,212,0.3)] hover:brightness-110 disabled:opacity-50">
        {busy ? "Agents are shopping…" : "Send in the shopping agents"}
      </button>
    </div>
  );
}
