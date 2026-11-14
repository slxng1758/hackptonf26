// The PDF report. The server opens #print=<id> in its own browser and saves it with page.pdf(), so this page is laid
// out for paper: light, letter width, page breaks between sections.
import { useEffect, useState } from "react";
import { marked } from "marked";
import { Avatar } from "./Avatar";
import { C } from "./theme";
import type { Sim } from "./Simulate";
import { outcome } from "./SiteMap";

export function PrintReport({ id }: { id: string }) {
  const [sim, setSim] = useState<Sim | null>(null);
  useEffect(() => { fetch(`/api/sims/${id}`).then((r) => r.json()).then(setSim); }, [id]);
  if (!sim) return null;
  const people = sim.personas.filter((p) => p.kind !== "agent" && sim.decisions[p.id]);
  const agents = sim.personas.filter((p) => p.kind === "agent" && sim.decisions[p.id]);
  const bought = people.filter((p) => outcome(sim, p.id) === "bought").length;
  const agentsOk = agents.filter((p) => outcome(sim, p.id) === "bought").length;
  const pct = (a: number, b: number) => (b ? `${Math.round((a / b) * 100)}%` : "–");
  const name = sim.input.name || sim.input.url;
  const date = new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
  const steps = (pid: string) => sim.live[pid] ?? [];
  const explored = people.filter((p) => steps(p.id).length > 1 || steps(p.id).some((x) => x.cart) || outcome(sim, p.id) === "bought").length;
  const acted = people.filter((p) => steps(p.id).some((x) => x.cart) || outcome(sim, p.id) === "bought").length;
  const funnel = [["Landed on the site", people.length], ["Kept looking past the first screen", explored], ["Reached a buy decision", acted], ["Converted", bought]] as const;

  return (
    <div id="print-ready" className="print-doc mx-auto max-w-[780px] bg-[#ffffff] px-10 py-10 text-[#101828]">
      <div className="flex items-center justify-between border-b border-[#e4e7ec] pb-4">
        <div className="flex items-center gap-2"><img src="/icon.svg" alt="" className="h-7 w-7" /><b>Agent-ready</b><span className="text-[#667085]">· customer test report</span></div>
        <span className="text-[12px] text-[#667085]">{date}</span>
      </div>

      <h1 className="mt-6 text-[28px] font-bold leading-tight tracking-tight">{name}</h1>
      <div className="mt-1 text-[13px] text-[#667085]">{/\/api\/product\//.test(sim.input.url) ? "Amazon listing, rebuilt from the public Amazon Reviews 2023 dataset" : sim.input.url}{sim.input.context ? ` · change tested: ${sim.input.context}` : ""}{sim.round ? ` · round ${sim.round + 1}` : ""}</div>

      <div className="mt-6 grid grid-cols-4 gap-3">
        {[["Simulated conversion", pct(bought, people.length), `${bought} of ${people.length} panelists`],
          ["AI agent checkout", pct(agentsOk, agents.length), `${agentsOk} of ${agents.length} agents`],
          ["Sessions", String(Object.keys(sim.live).length), "on the real site"],
          ["Top blocker", sim.actions?.[0] ? `${sim.actions[0].who.length} hit it` : "–", "see recommendation 1"]].map(([l, v, s]) => (
          <div key={l} className="rounded-lg border border-[#e4e7ec] p-3"><div className="text-[11px] text-[#667085]">{l}</div><div className="text-[24px] font-bold">{v}</div><div className="text-[11px] text-[#667085]">{s}</div></div>
        ))}
      </div>

      <h2 className="mt-8 text-[17px] font-bold">Conversion funnel</h2>
      <div className="mt-3 space-y-2">
        {funnel.map(([l, n], i) => (
          <div key={l} className="flex items-center gap-3 text-[12.5px]">
            <span className="w-[200px] shrink-0">{l}</span>
            <div className="h-3 flex-1 overflow-hidden rounded-full bg-[#f2f4f7]"><div className="h-full rounded-full" style={{ width: `${people.length ? (n / people.length) * 100 : 0}%`, background: i === 3 ? C.win : C.brain }} /></div>
            <span className="w-6 text-right font-mono">{n}</span>
          </div>
        ))}
      </div>

      {sim.actions && sim.actions.length > 0 && <>
        <h2 className="mt-8 text-[17px] font-bold">Recommendations</h2>
        <ol className="mt-3 space-y-3">
          {sim.actions.map((a, i) => (
            <li key={i} className="flex gap-3 break-inside-avoid"><span className="grid h-6 w-6 shrink-0 place-items-center rounded-md text-[12px] font-bold text-[#ffffff]" style={{ background: C.brain }}>{i + 1}</span>
              <div><div className="text-[14px] font-semibold">{a.fix} <span className="ml-1 rounded border border-[#e4e7ec] px-1.5 text-[10px] font-normal text-[#667085]">{a.audience} · {a.effort} effort</span></div>
                <div className="mt-0.5 text-[12.5px] text-[#475467]">{a.why}</div>
                <div className="mt-0.5 text-[11.5px] text-[#667085]">Wins back: {a.who.join(", ")}{a.page ? ` · ${a.page}` : ""}</div></div></li>
          ))}
        </ol>
      </>}

      <h2 className="mt-8 break-before-page text-[17px] font-bold">The panel</h2>
      <table className="mt-3 w-full text-left text-[12px]">
        <thead><tr className="border-b border-[#e4e7ec] text-[10.5px] uppercase tracking-wider text-[#667085]"><th className="py-2"></th><th>Panelist</th><th>Model</th><th>Outcome</th><th>Rating</th><th className="w-[45%]">What would have converted them</th></tr></thead>
        <tbody>
          {[...people, ...agents].map((p) => { const d = sim.decisions[p.id]; const o = outcome(sim, p.id); return (
            <tr key={p.id} className="break-inside-avoid border-b border-[#f2f4f7] align-top">
              <td className="py-2 pr-2"><Avatar seed={p.avatar.seed} archetype={p.archetype} model={p.model} age={p.age} size={30} feeling={d.feeling} /></td>
              <td className="py-2"><b>{p.name}</b><div className="text-[11px] text-[#667085]">{p.kind === "agent" ? "AI shopping agent" : `${p.age} · ${p.archetype}`}</div></td>
              <td className="py-2">{p.model}</td>
              <td className="py-2 font-semibold" style={{ color: o === "bought" ? C.win : o === "maybe" ? C.mid : C.loss }}>{o === "bought" ? "Bought" : o === "maybe" ? "Maybe later" : "Left"}</td>
              <td className="py-2">{d.rating}/5</td>
              <td className="py-2 text-[#475467]">{o === "bought" ? `“${d.quote}”` : d.missing}</td>
            </tr>
          ); })}
        </tbody>
      </table>

      {sim.social?.summary && <>
        <h2 className="mt-8 text-[17px] font-bold">Word of mouth</h2>
        <p className="mt-2 text-[13px] leading-relaxed text-[#344054]">{sim.social.summary.replace(/\*\*/g, "")}</p>
      </>}

      {sim.report && <>
        <h2 className="mt-8 break-before-page text-[17px] font-bold">Analyst report</h2>
        <article className="report print-report mt-2" dangerouslySetInnerHTML={{ __html: marked.parse(sim.report, { async: false }) as string }} />
      </>}

      <p className="mt-10 border-t border-[#e4e7ec] pt-3 text-[11px] text-[#667085]">Simulated customers browsing the real website: a fast first pass before testing with real people. Personas played by {[...new Set(sim.personas.map((p) => p.model).filter(Boolean))].join(", ")}.</p>
    </div>
  );
}
