import { Controls } from "./Controls";
import { dominant, kind, useEpi, villageCenters } from "./epi";

const ROLE_NAME: Record<string, string> = { villager: "a villager", child: "a child", priest: "the priest", healer: "the healer", merchant: "a merchant", traveler: "a traveler" };

export function Paper() {
  const epi = useEpi(1600);
  const { data, day } = epi;
  if (!data) return <div className="grid h-screen place-items-center bg-[#efe6cf] font-serif text-ink2">the press is warming up…</div>;

  const f = data.frames[day];
  const top = dominant(data, day);
  const bornToday = data.variants.filter((v) => v.day === day && v.parent !== null);
  const badToday = Object.entries(data.contaminated).filter(([, d]) => d === day).map(([vi]) => data.villages[+vi].name);
  const weekAgo = data.frames[Math.max(0, day - 7)].sick_total;
  const share = new Map<number, number>();
  f.b.forEach((v) => v !== null && share.set(v, (share.get(v) ?? 0) + 1));
  const overheard = [...share.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3).map(([v, n]) => ({ v: data.variants[v], n }));
  const truthShare = f.b.filter((v) => v !== null && kind(data.variants[v]) === "truth").length;
  const series = data.frames.slice(0, day + 1).map((fr) => fr.sick_total);
  const max = Math.max(1, data.frames[data.days].sick_total);
  const centers = villageCenters(data);

  const sub = badToday.length
    ? `${badToday.join(" and ")} well turns foul; villagers warned`
    : bornToday.length
      ? `New account of the old saying spreads, told by ${ROLE_NAME[bornToday[0].role] ?? "a stranger"}`
      : `${f.sick_total - weekAgo} taken ill this past week`;

  return (
    <div className="min-h-screen bg-[#2a2520] px-4 pb-32 pt-16">
      <article key={day} className="paper-in mx-auto max-w-5xl bg-[#f4ecd6] px-8 pb-10 pt-6 text-[#1d1a15] shadow-2xl" style={{ backgroundImage: "radial-gradient(rgba(120,90,40,.08) 1px, transparent 1px)", backgroundSize: "4px 4px" }}>
        <div className="flex items-end justify-between border-b border-[#1d1a15] pb-1 font-serif text-[12px] italic">
          <span>Vol. I · No. {day + 1}</span><span>Price, one copper</span><span>Day {day} of the sickness</span>
        </div>
        <h1 className="masthead py-2 text-center text-[64px] leading-none md:text-[84px]">The Valley Crier</h1>
        <div className="border-y-[3px] border-double border-[#1d1a15] py-1 text-center font-serif text-[12px] uppercase tracking-[0.3em]">
          {data.villages.map((v) => v.name).join(" · ")}
        </div>

        <h2 className="mt-6 text-center font-serif text-[40px] font-extrabold uppercase leading-[1.05] md:text-[52px]">
          “{top ? top.v.text.replace(/[.]$/, "") : "No word yet"}”
        </h2>
        <p className="mt-3 text-center font-serif text-[19px] italic">{top ? `Saying now repeated by ${top.n} of ${data.population} souls. ` : ""}{sub}.</p>

        <div className="mt-6 grid gap-6 border-t border-[#1d1a15] pt-5 md:grid-cols-[1fr_1.3fr_1fr]">
          <section className="md:border-r md:border-[#1d1a15]/30 md:pr-6">
            <h3 className="font-serif text-[15px] font-extrabold uppercase tracking-widest">Taken Ill</h3>
            <div className="mt-1 font-serif text-[72px] font-extrabold leading-none">{f.sick_total}</div>
            <p className="font-serif text-[14px] italic">souls since the sickness came. {[...f.h].filter((c) => c === "I").length} lie abed today.</p>
            <svg viewBox={`0 0 ${data.days} 40`} className="mt-3 h-16 w-full" preserveAspectRatio="none">
              {series.map((s, i) => <rect key={i} x={i} y={40 - (s / max) * 40} width={0.8} height={(s / max) * 40} fill="#1d1a15" />)}
            </svg>
            <div className="mt-4 border border-[#1d1a15] p-3">
              <h4 className="font-serif text-[13px] font-extrabold uppercase tracking-widest">The Healer's Notice</h4>
              <p className="mt-1 font-serif text-[14px] leading-snug">Of all who speak the saying, <b>{truthShare}</b> still know <i>why</i> one boils the water. The rest keep the custom by habit, or by faith.</p>
            </div>
          </section>

          <section>
            <h3 className="font-serif text-[15px] font-extrabold uppercase tracking-widest">Overheard at the Market</h3>
            {overheard.map(({ v, n }) => (
              <blockquote key={v.id} className="mt-3 border-l-2 border-[#1d1a15] pl-3">
                <p className="font-serif text-[20px] leading-snug">“{v.text}”</p>
                <footer className="mt-1 font-serif text-[13px] italic">first said by {ROLE_NAME[v.role] ?? "someone"}, day {v.day} · believed by {n} · {kind(v) === "myth" ? "a matter of faith" : kind(v) === "truth" ? "the healer's own words" : kind(v) === "unsafe" ? "the healer disapproves" : "custom"}</footer>
              </blockquote>
            ))}
          </section>

          <section className="md:border-l md:border-[#1d1a15]/30 md:pl-6">
            <h3 className="font-serif text-[15px] font-extrabold uppercase tracking-widest">Map of the Valley</h3>
            <svg viewBox="-1.1 -1.1 2.2 2.2" className="mt-2 w-full">
              <circle cx="0" cy="0" r="1.05" fill="none" stroke="#1d1a15" strokeWidth="0.01" strokeDasharray="0.03 0.02" />
              {centers.map(([x, y], vi) => {
                const bad = data.contaminated[vi] !== undefined && day >= data.contaminated[vi];
                return (
                  <g key={vi}>
                    <line x1={0} y1={0} x2={x} y2={y} stroke="#1d1a15" strokeWidth="0.012" strokeDasharray="0.04 0.03" />
                    <circle cx={x} cy={y} r={0.16} fill="none" stroke="#1d1a15" strokeWidth="0.015" />
                    {bad && <path d={`M${x - 0.08} ${y - 0.08} L${x + 0.08} ${y + 0.08} M${x + 0.08} ${y - 0.08} L${x - 0.08} ${y + 0.08}`} stroke="#9b1c1c" strokeWidth="0.03" />}
                    <text x={x} y={y + (y > 0 ? 0.3 : -0.22)} textAnchor="middle" fontSize="0.13" fontFamily="Fraunces, serif" fontStyle="italic" fill="#1d1a15">{data.villages[vi].name}</text>
                  </g>
                );
              })}
              <rect x={-0.07} y={-0.07} width={0.14} height={0.14} fill="#1d1a15" />
              <text x={0} y={0.24} textAnchor="middle" fontSize="0.1" fontFamily="Fraunces, serif" fill="#1d1a15">Market</text>
            </svg>
            <p className="font-serif text-[12px] italic">✕ marks a well gone foul.</p>
          </section>
        </div>
      </article>
      <div className="fixed inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent p-6"><Controls {...epi} data={data} /></div>
    </div>
  );
}
