import { SCENARIO, type Epi } from "./epi";

export function Controls({ data, day, setDay, playing, toggle, setPlaying, list, runId, setRunId, dark = true }: {
  data: Epi; day: number; setDay: (d: number) => void; playing: boolean; toggle: () => void; setPlaying: (p: boolean) => void;
  list: { id: string; scenario: string; ever_sick: number; population: number }[]; runId: string | null; setRunId: (id: string) => void; dark?: boolean;
}) {
  const fg = dark ? "text-white/80 border-white/20" : "text-ink border-ink/20";
  return (
    <div className="flex items-center gap-4">
      <button onClick={toggle} className={`grid h-12 w-12 shrink-0 place-items-center rounded-full text-[16px] ${dark ? "bg-white text-black shadow-[0_0_30px_rgba(255,255,255,0.3)]" : "bg-ink text-paper"}`} aria-label={playing ? "Pause" : "Play"}>
        {playing ? "❚❚" : "▶"}
      </button>
      <input type="range" min={0} max={data.days} value={day} onChange={(e) => { setPlaying(false); setDay(+e.target.value); }} className="epi-range flex-1" aria-label="Day" />
      <span className={`w-20 font-mono text-[12px] ${dark ? "text-white/60" : "text-ink2"}`}>day {day}/{data.days}</span>
      {list.length > 1 && (
        <select value={runId ?? ""} onChange={(e) => setRunId(e.target.value)} className={`rounded-full border bg-transparent px-3 py-2 font-mono text-[12px] ${fg}`}>
          {list.map((r) => <option key={r.id} value={r.id} className="text-black">{SCENARIO[r.scenario] ?? r.scenario} · {r.ever_sick}/{r.population} sick</option>)}
        </select>
      )}
    </div>
  );
}
