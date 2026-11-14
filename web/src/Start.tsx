import { useEffect, useState } from "react";
import type { Draft, Preset } from "./types";
import { C } from "./theme";

const STEPS = ["Reading your website", "Searching the web for your competitors", "Reading their sites", "Drafting your customers"];

export function Start({ onReady }: { onReady: (d: Draft) => void }) {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const [presets, setPresets] = useState<Record<string, Preset>>({});

  useEffect(() => { fetch("/api/presets").then((r) => r.json()).then(setPresets).catch(() => {}); }, []);
  useEffect(() => {
    if (!busy) return;
    setStep(0);
    const t = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 1800);
    return () => clearInterval(t);
  }, [busy]);

  async function scan(e?: React.FormEvent) {
    e?.preventDefault();
    if (q.trim().length < 3) { setErr("Type your website or your business name and town."); return; }
    setErr(null); setBusy(true);
    try {
      const r = await fetch("/api/scan", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: q.trim() }) });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail ?? "Something went wrong.");
      onReady({ ...d, customers_csv: false, source: "scan" });
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  }

  return (
    <div className="mx-auto flex min-h-[calc(100vh-64px)] max-w-3xl flex-col justify-center px-6 py-16">
      <div className="font-mono text-[11px] uppercase tracking-[0.35em]" style={{ color: C.win }}>for the businesses AI agents shop from</div>
      <h1 className="mt-4 font-serif text-[52px] leading-[1.05]">Will an AI agent pick your business?</h1>
      <p className="mt-4 max-w-xl text-[16px] leading-relaxed text-white/60">
        People now ask ChatGPT and Claude to find them a caterer, an insurer, a plumber. Paste your website. We find your real competitors,
        send real AI shopping agents through your customers' requests, and show you who they pick and why.
      </p>

      <form onSubmit={scan} className="mt-10 flex gap-2 rounded-2xl border border-white/15 bg-white/[0.04] p-2 focus-within:border-[#3ff0d4]">
        <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} disabled={busy} placeholder="yourbusiness.com, or “Olives catering Princeton”"
          className="min-w-0 flex-1 bg-transparent px-4 py-3 text-[17px] outline-none placeholder:text-white/30" />
        <button disabled={busy} className="rounded-xl px-6 font-semibold text-black disabled:opacity-60" style={{ background: C.win, boxShadow: `0 0 30px ${C.win}55` }}>
          {busy ? "Scanning…" : "Scan"}
        </button>
      </form>
      {err && <p className="mt-3 text-[13px]" style={{ color: C.loss }}>{err}</p>}

      {busy && (
        <ol className="mt-6 space-y-2 font-mono text-[13px]">
          {STEPS.map((s, i) => (
            <li key={s} className="flex items-center gap-3" style={{ color: i < step ? C.win : i === step ? "#fff" : "rgba(255,255,255,0.3)" }}>
              <span>{i < step ? "✓" : i === step ? "●" : "○"}</span>{s}{i === step && <span className="animate-pulse">…</span>}
            </li>
          ))}
        </ol>
      )}

      {!busy && Object.keys(presets).length > 0 && (
        <div className="mt-8">
          <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-white/35">or try a demo business</div>
          <div className="mt-3 flex flex-wrap gap-2">
            {Object.values(presets).map((p) => (
              <button key={p.name} onClick={() => onReady({ ...p, customers_csv: false, source: "demo" })}
                className="rounded-xl border border-white/15 px-4 py-2.5 text-left hover:border-white/40">
                <div className="text-[14px]">{p.name}</div>
                <div className="font-mono text-[11px] text-white/45">{p.category}</div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
