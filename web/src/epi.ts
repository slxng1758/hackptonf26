// Shared data + playback for every infodemic view.
import { useEffect, useMemo, useState } from "react";

export interface Person { id: number; village: number; role: string; x: number; y: number }
export interface Variant { id: number; parent: number | null; text: string; short: string; day: number; person: number; role: string; belief: number; practice: number; myth: number }
export interface Frame { day: number; b: (number | null)[]; h: string; sick_total: number }
export interface Epi {
  id: string; scenario: string; days: number; population: number; ever_sick: number;
  villages: { name: string; water: string }[]; contaminated: Record<string, number>;
  people: Person[]; edges: [number, number][]; variants: Variant[]; frames: Frame[];
}
export interface Transfer { from: number; to: number; variant: number }

export type Kind = "truth" | "ritual" | "myth" | "unsafe" | "none";
export function kind(v?: Variant): Kind {
  if (!v) return "none";
  if (v.practice < 0.4) return "unsafe";
  if (v.myth >= 0.5) return "myth";
  if (v.belief >= 0.55) return "truth";
  return "ritual";
}
export const LABEL: Record<Kind, string> = { truth: "knows why", ritual: "boils, forgot why", myth: "sacred myth", unsafe: "doesn't boil", none: "hasn't heard" };
export const SCENARIO: Record<string, string> = { baseline: "one healer", healers_everywhere: "healers everywhere", priests_everywhere: "priests everywhere" };

export function useEpi(speedMs = 450) {
  const [list, setList] = useState<{ id: string; scenario: string; ever_sick: number; population: number }[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [data, setData] = useState<Epi | null>(null);
  const [day, setDay] = useState(0);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    const want = new URLSearchParams(location.hash.split("?")[1] ?? "").get("run");
    fetch("/api/epi").then((r) => r.json()).then((l) => { setList(l); setRunId(want ?? l[0]?.id ?? null); }).catch(() => {});
  }, []);
  useEffect(() => {
    if (!runId) return;
    fetch(`/api/epi/${runId}`).then((r) => r.json()).then((d: Epi) => { setData(d); setDay(0); }).catch(() => {});
  }, [runId]);
  useEffect(() => {
    if (!playing || !data) return;
    if (day >= data.days) { setPlaying(false); return; }
    const t = setTimeout(() => setDay((d) => d + 1), speedMs);
    return () => clearTimeout(t);
  }, [playing, day, data, speedMs]);

  const nbrs = useMemo(() => {
    const m = new Map<number, number[]>();
    data?.edges.forEach(([a, b]) => { m.set(a, [...(m.get(a) ?? []), b]); m.set(b, [...(m.get(b) ?? []), a]); });
    return m;
  }, [data]);

  // who passed a saying to whom on a given day
  const transfers = (d: number): Transfer[] => {
    if (!data || d === 0) return [];
    const prev = data.frames[d - 1], cur = data.frames[d];
    const out: Transfer[] = [];
    cur.b.forEach((v, i) => {
      if (v === null || v === prev.b[i]) return;
      const src = (nbrs.get(i) ?? []).find((n) => prev.b[n] === v) ?? (nbrs.get(i) ?? []).find((n) => prev.b[n] !== null);
      if (src !== undefined) out.push({ from: src, to: i, variant: v });
    });
    return out;
  };

  const toggle = () => { if (data && day >= data.days) setDay(0); setPlaying((p) => !p); };
  return { list, runId, setRunId, data, day, setDay, playing, setPlaying, toggle, nbrs, transfers };
}

export function dominant(data: Epi, day: number): { v: Variant; n: number } | null {
  const share = new Map<number, number>();
  data.frames[day].b.forEach((v) => v !== null && share.set(v, (share.get(v) ?? 0) + 1));
  let best: [number, number] | null = null;
  share.forEach((n, v) => { if (!best || n > best[1]) best = [v, n]; });
  return best ? { v: data.variants[best[0]], n: best[1] } : null;
}

export function villageCenters(data: Epi): [number, number][] {
  return data.villages.map((_, vi) => {
    const ms = data.people.filter((p) => p.village === vi);
    return [ms.reduce((s, p) => s + p.x, 0) / ms.length, ms.reduce((s, p) => s + p.y, 0) / ms.length];
  });
}
