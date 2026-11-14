// Mirror of b2a/contract.py: the three keys added to a simulation (GET /api/sims/{id}).
// Example data: fixtures/sim_extras_example.json. Change both files together.

export interface Theme { theme: string; kind: "like" | "complaint"; mentions: number }

export interface EvalScore {
  iteration: number
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

export interface GraphNode { id: string; label: string; archetype: string; sentiment: number; centrality: number; community: number }
export interface GraphEdge { source: string; target: string; kind: "reply" | "repost"; weight: number }

export interface Social { posts: SocialPost[]; nodes: GraphNode[]; edges: GraphEdge[]; top_influencers: string[]; summary: string }

export interface SimExtras { evals: EvalScore[]; persona_changes: PersonaChange[]; social: Social | null }
