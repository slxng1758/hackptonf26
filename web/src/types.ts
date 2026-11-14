export interface Preset { name: string; category: string; listing: string; facts: string[]; competitors: string[]; customers: string }
export interface Draft extends Preset { url?: string; customers_csv: boolean; source: "scan" | "demo"; competitor_meta?: { name: string; url: string }[]; sources?: string[] }
export interface Segment { name: string; share: number; cares_about: string; tasks: string[] }
export interface Loss { segment: string; request: string; shopper: string; chose: string; reason: string; missing: string }
export interface Test {
  n: number; share?: number[]; listing: string; to_confirm: string[]; pick_rate: number; raw_rate: number; wins: number; total: number; errors: number;
  by_segment: { segment: string; share: number; rate: number; wins: number; total: number }[];
  by_shopper: Record<string, { wins: number; total: number }>;
  lost_to: { competitor: number; times: number }[];
  losses?: Loss[];
}
export interface Job {
  id: string; input: Preset & { competitor_meta?: { name: string; url: string }[] | null }; status: "running" | "done" | "error"; error: string | null;
  steps: { t: string; kind: string; note: string }[]; segments: Segment[]; tests: Test[];
  live: { n: number; shopper: string; segment: number; won: boolean; picked: string }[];
  lessons: string[]; report: string; shoppers: string[];
  matrix: { names: string[]; rows: { attribute: string; values: string[] }[] } | null;
}
export interface JobRow { id: string; name: string; status: string; first: number | null; best: number | null }
