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


class SimExtras(BaseModel):
    """The three keys added to the simulation view."""
    evals: list[EvalScore] = Field(default_factory=list)
    persona_changes: list[PersonaChange] = Field(default_factory=list)
    social: Social | None = None
