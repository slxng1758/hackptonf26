export interface Score {
  belief: number; practice: number; myth: number;
  short?: string; rule: string; reason: string; drift: string; false_beliefs: string[];
}
export interface Step { tool: string; who: string; note: string }
export interface Gen {
  gen: number; event: string; summary: string;
  drafts: Record<string, string>; archive: Record<string, string>;
  chars_lost: number; trace: Step[]; score?: Score; seconds?: number;
}
export interface Run {
  id: string; preset: string; title: string; truth: string; truth_short?: string; generations_planned: number; limit: number;
  models: { villagers: string; evaluator: string }; status: "running" | "done" | "error"; error?: string; created: string;
  generations?: Gen[];
}
