// Mirror of b2a/contract.py: the three keys added to a simulation (GET /api/sims/{id}).
// Example data: fixtures/sim_extras_example.json. Change both files together.

export interface Theme { theme: string; kind: "like" | "complaint"; mentions: number }

export interface EvalScore {
  iteration: number
  case_id?: string
  layer?: 1 | 2 | null          // 1 = base models, 2 = personas with memory, null = all agents
  stage?: "base" | "memory" | "evolved" | "all"
  agents?: number
  actual_rating: number
  predicted_rating: number
  rating_error: number
  actual_buy_rate: number | null
  predicted_buy_rate: number
  direction_correct: boolean | null
  theme_recall: number
  theme_precision: number
  distribution_distance: number
  real_themes: Theme[]
  matched_themes: string[]
  missed_themes: string[]
  invented_themes?: string[]    // raised by agents, never by real reviewers
  judge?: "llm" | "keyword"
  notes: string
}

export interface PersonaChange { persona_id: string; iteration: number; lesson: string; before: string; after: string; source?: "simulation" | "human" }

export interface SocialPost {
  id: string
  round: number
  author: string               // persona id ("p1")
  kind: "post" | "reply" | "repost"
  target: string | null        // post id
  text: string
  sentiment: number            // -1 … 1
}

export interface GraphNode {
  id: string; label: string; archetype: string; sentiment: number; centrality: number; community: number
  model?: string; layer?: 1 | 2 | null; posts?: number; reactions_received?: number
}

export interface Cascade { post_id: string; author: string; text: string; theme: string; size: number; depth: number; reach: number; communities_reached: number; sentiment: number }
export interface ThemeSpread { theme: string; posts: number; agents: number; communities: number; sentiment: number; crosses_communities: boolean }
export interface Community { id: number; members: string[]; sentiment: number; archetypes: string[]; models: string[] }
export interface GraphEdge { source: string; target: string; kind: "reply" | "repost"; weight: number }

export interface Social {
  posts: SocialPost[]; nodes: GraphNode[]; edges: GraphEdge[]; top_influencers: string[]; summary: string
  cascades?: Cascade[]          // original posts, biggest first
  themes?: ThemeSpread[]        // content x connectivity
  communities?: Community[]
  by_model?: Record<string, { agents: number; posts: number; reactions_received: number; sentiment: number }>
  network_summary?: string      // what the network analysis found (content x connectivity)
}

export interface SimExtras { evals: EvalScore[]; persona_changes: PersonaChange[]; social: Social | null }

// ---------- Gemini (b2a/gemini.py) ----------
// POST /api/sims/{id}/lens runs it (after status "done"); GET /api/sims/{id}/lens returns the saved one.
// Draw each box over GET /api/shots/{id}/shots/{shot}:
//   top: ymin/10 %, left: xmin/10 %, height: (ymax-ymin)/10 %, width: (xmax-xmin)/10 %
export interface LensBox { box_2d: [number, number, number, number]; label: string; issue: string; fix: string; severity: 1 | 2 | 3 }
export interface LensShot {
  persona_id: string; persona: string; archetype: string; model: string; step: number; url: string; shot: string
  feeling: string; thought: string; why: "feeling" | "went back" | "left without buying"; boxes: LensBox[]; error: string
}
export interface Hotspot {
  page: string; label: string; issue: string; fix: string; severity: number; count: number
  personas: string[]; names: string[]; models: string[]; shots: string[]   // "persona_id:step"
}
export interface Lens { model: string; shots: LensShot[]; hotspots: Hotspot[]; summary: string }

// POST /api/world {world, product} -> GroundedWorld & { text }   (put `text` in the sim's world field)
export interface GroundedWorld { world: string; summary: string; facts: string[]; sources: { title: string; url: string }[]; model: string; grounded: boolean; text?: string }
