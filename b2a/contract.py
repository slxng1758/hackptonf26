"""Data shapes for what the customer simulation (b2a/sim.py) doesn't produce yet: accuracy evals, persona change history,
and the social media layer.

These are added to SimJob.view() as three new keys: "evals", "persona_changes", "social". Example data:
fixtures/sim_extras_example.json. TypeScript mirror: web/src/sim-extras.ts. Contract: docs/CONTRACT.md.

Persona ids are the simulation's ids ("p1", "p2", ...). Feelings and decisions reuse the labels in b2a/session.py.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------- accuracy against real outcomes ----------

class Theme(BaseModel):
    theme: str = Field(description="short phrase, e.g. 'ear loops hurt after hours'")
    kind: Literal["like", "complaint"]
    mentions: int = Field(ge=0)


class EvalScore(BaseModel):
    """One calibration iteration, scored on held-out real reviews (never shown to the personas)."""
    iteration: int = Field(ge=0, description="0 = personas before any evolution")
    case_id: str = Field(default="", description="which truth this was scored against: data/<case_id>/")
    layer: int | None = Field(default=None, description="1 = base models, no persona; 2 = personas with memory; None = all agents")
    stage: Literal["base", "memory", "evolved", "all"] = Field(default="all", description="base = layer 1; memory = layer 2 before evolving; evolved = layer 2 after >=1 evolve loop")
    agents: int = Field(default=0, ge=0, description="how many agents' decisions were scored")
    actual_rating: float = Field(ge=1, le=5, description="mean star rating of the held-out real reviews")
    predicted_rating: float = Field(ge=1, le=5, description="share-weighted rating from the simulation (summary.rating)")
    rating_error: float = Field(ge=0, description="|predicted - actual|")
    actual_buy_rate: float | None = Field(default=None, ge=0, le=1, description="if known, e.g. from the business's own sales")
    predicted_buy_rate: float = Field(ge=0, le=1, description="summary.buy_rate")
    direction_correct: bool | None = Field(default=None, description="for before/after comparisons: did we predict the direction of change")
    theme_recall: float = Field(ge=0, le=1, description="share of real top themes the personas raised")
    theme_precision: float = Field(ge=0, le=1, description="share of persona themes that real reviewers also raised")
    distribution_distance: float = Field(ge=0, description="distance between predicted and real star distributions, lower is better")
    real_themes: list[Theme] = Field(default_factory=list)
    matched_themes: list[str] = Field(default_factory=list, description="real themes the personas also raised")
    missed_themes: list[str] = Field(default_factory=list, description="real themes no persona raised")
    invented_themes: list[str] = Field(default_factory=list, description="themes the agents raised that no real reviewer did")
    judge: Literal["llm", "keyword"] = Field(default="llm", description="how themes were matched")
    notes: str = ""


class PersonaChange(BaseModel):
    """One edit the evolver made to a persona file, so the UI can show what each persona learned."""
    persona_id: str
    iteration: int = Field(ge=1, description="the calibration iteration that produced this change")
    lesson: str = Field(description="what changed and why, one sentence")
    before: str = Field(description="the persona's '## Memory' section before (empty if none)")
    after: str = Field(description="the '## Memory' section after")
    source: Literal["simulation", "human"] = Field(default="simulation", description="human = the owner taught it what real customers do")


# ---------- social media layer ----------

class SocialPost(BaseModel):
    id: str
    round: int = Field(ge=0, description="0 = first posts right after browsing; later rounds react to the feed")
    author: str = Field(description="persona id")
    kind: Literal["post", "reply", "repost"]
    target: str | None = Field(default=None, description="post id replied to or reposted; None for an original post")
    text: str = Field(description="the post, in the persona's voice, max 280 characters")
    sentiment: float = Field(ge=-1, le=1)


class GraphNode(BaseModel):
    id: str = Field(description="persona id")
    label: str = Field(description="persona name")
    archetype: str
    sentiment: float = Field(ge=-1, le=1, description="mean sentiment of this persona's posts")
    centrality: float = Field(ge=0, description="influence, e.g. PageRank over reply/repost edges")
    community: int
    model: str = Field(default="", description="model family playing this agent")
    layer: int | None = Field(default=None, description="1 = base model, 2 = persona with memory")
    posts: int = Field(default=0, ge=0, description="posts, replies and reposts written")
    reactions_received: int = Field(default=0, ge=0, description="replies + reposts others made to this agent's posts")


class Cascade(BaseModel):
    """One original post and everything it set off."""
    post_id: str
    author: str
    text: str
    theme: str = ""
    size: int = Field(ge=0, description="replies + reposts in its whole thread, all rounds")
    depth: int = Field(ge=0, description="longest reply chain")
    reach: int = Field(ge=0, description="distinct agents who reacted")
    communities_reached: int = Field(ge=0, description="communities other than the author's that reacted")
    sentiment: float = Field(ge=-1, le=1, description="mean sentiment of the thread")


class ThemeSpread(BaseModel):
    theme: str
    posts: int
    agents: int
    communities: int = Field(description="how many communities talked about it")
    sentiment: float = Field(ge=-1, le=1)
    crosses_communities: bool


class Community(BaseModel):
    id: int
    members: list[str]
    sentiment: float = Field(ge=-1, le=1)
    archetypes: list[str]
    models: list[str]


class GraphEdge(BaseModel):
    source: str = Field(description="persona who replied or reposted")
    target: str = Field(description="persona whose post it was")
    kind: Literal["reply", "repost"]
    weight: int = Field(default=1, ge=1)


class Social(BaseModel):
    posts: list[SocialPost]
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    top_influencers: list[str] = Field(description="persona ids, most influential first")
    summary: str = Field(description="what spread, through whom, and why; 2-3 sentences")
    cascades: list[Cascade] = Field(default_factory=list, description="original posts, biggest first")
    themes: list[ThemeSpread] = Field(default_factory=list, description="content x connectivity: which themes travel across communities")
    communities: list[Community] = Field(default_factory=list)
    by_model: dict[str, dict] = Field(default_factory=dict, description="model family -> {agents, posts, reactions_received, sentiment}")
    network_summary: str = Field(default="", description="what the network analysis found: biggest cascade, themes that crossed communities, top influencer")


class SimExtras(BaseModel):
    """The three keys added to the simulation view."""
    evals: list[EvalScore] = Field(default_factory=list)
    persona_changes: list[PersonaChange] = Field(default_factory=list)
    social: Social | None = None


# ---------- Gemini: UX lens + grounded world (b2a/gemini.py) ----------

class LensBox(BaseModel):
    """One spot on a screenshot that caused a customer's reaction. Draw it over the screenshot."""
    box_2d: list[int] = Field(description="[ymin, xmin, ymax, xmax] normalized 0-1000; CSS: top=ymin/10 %, left=xmin/10 %, height=(ymax-ymin)/10 %, width=(xmax-xmin)/10 %")
    label: str = Field(description="the page element, e.g. 'shipping cost line'")
    issue: str
    fix: str
    severity: int = Field(ge=1, le=3, description="1 minor, 2 slows them down, 3 makes them leave")


class LensShot(BaseModel):
    persona_id: str
    persona: str
    archetype: str = ""
    model: str = Field(default="", description="model family playing the customer")
    step: int
    url: str
    shot: str = Field(description="screenshot file: GET /api/shots/{sim_id}/shots/{shot}")
    feeling: str
    thought: str
    why: Literal["feeling", "went back", "left without buying"]
    boxes: list[LensBox] = Field(default_factory=list)
    error: str = ""


class Hotspot(BaseModel):
    """The same problem, found on the same page by several customers."""
    page: str
    label: str
    issue: str
    fix: str
    severity: float
    count: int = Field(description="distinct customers who hit it")
    personas: list[str]
    names: list[str]
    models: list[str]
    shots: list[str] = Field(description="'persona_id:step' references into shots")


class Lens(BaseModel):
    model: str
    shots: list[LensShot]
    hotspots: list[Hotspot] = Field(description="biggest first")
    summary: str


class Source(BaseModel):
    title: str
    url: str


class GroundedWorld(BaseModel):
    world: str = Field(description="what the owner typed")
    summary: str = Field(description="background a persona can use, 1-2 sentences")
    facts: list[str]
    sources: list[Source] = Field(default_factory=list, description="Google Search results Gemini grounded on")
    model: str
    grounded: bool = Field(description="false if Gemini answered without search results")
