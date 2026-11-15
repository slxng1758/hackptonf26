"""The owner edits the cast before the test: change any customer, add new ones, pick the model that plays each, and
give each one custom instructions (a persona prompt) that go into every prompt that plays them.

normalize_cast()  makes whatever the editor sends safe to run: defaults, limits, unique ids, shares that sum to 1.
draft()           one sentence from the owner ("a retired nurse who hates subscriptions") -> a full persona to tweak.
"""
from __future__ import annotations

import random
import re

from pydantic import BaseModel, Field

from .session import ARCHETYPES

TEXT_LIMITS = {"name": 40, "occupation": 80, "segment": 120, "goal": 300, "budget": 120, "voice": 300, "instructions": 1000}


def _clean(v, limit: int) -> str:
    return " ".join(str(v or "").split())[:limit]


def normalize_cast(personas: list[dict], default_model: str = "") -> list[dict]:
    """Fill defaults, clamp values, keep ids unique, rebalance customers' shares to 100% (agents keep theirs).
    A customer left on "Auto" (no model) gets default_model: the model the owner picked for the whole run."""
    out, seen = [], set()
    used = {str(p.get("id")) for p in personas if p.get("id")}
    n = 1
    for raw in personas:
        p = dict(raw)
        agent = p.get("kind") == "agent"
        for k, lim in TEXT_LIMITS.items():
            if k in p or not agent:
                p[k] = _clean(p.get(k), lim)
        if not agent:
            p["name"] = p["name"] or "Customer"
            p["occupation"] = p["occupation"] or "shopper"
            p["archetype"] = p.get("archetype") if p.get("archetype") in ARCHETYPES else "first-time user"
            p["segment"] = p["segment"] or p["archetype"]
            p["goal"] = p["goal"] or "find out if this is right for me"
            p["budget"] = p["budget"] or "whatever seems fair"
            p["voice"] = p["voice"] or "Plain-spoken and practical."
            try:
                p["age"] = max(16, min(90, int(p.get("age") or 30)))
            except (TypeError, ValueError):
                p["age"] = 30
        pid = str(p.get("id") or "")
        if not pid or pid in seen:
            while f"p{n}" in used or f"p{n}" in seen:
                n += 1
            pid = f"p{n}"
        seen.add(pid)
        p["id"] = pid
        if not isinstance(p.get("avatar"), dict) or "seed" not in p["avatar"]:
            p["avatar"] = {"seed": random.Random(p.get("name", pid)).randint(0, 10_000)}
        p["model"] = _clean(p.get("model"), 40) or (_clean(default_model, 40) if not agent else "")
        out.append(p)
    people = [p for p in out if p.get("kind") != "agent"]
    shares = [max(0.0, float(p.get("share") or 0)) for p in people]
    total = sum(shares)
    for p, s in zip(people, shares):
        p["share"] = round(s / total, 3) if total > 0 else round(1 / len(people), 3)
    return out


class _Draft(BaseModel):
    name: str = Field(description="a first name")
    age: int = Field(ge=16, le=90)
    occupation: str
    archetype: str = Field(description=f"exactly one of: {', '.join(ARCHETYPES)}")
    segment: str = Field(description="the customer segment they belong to, a few words")
    goal: str = Field(description="what they came to this product for, in their words, one sentence")
    budget: str = Field(description="what they are willing to spend, concretely")
    voice: str = Field(description="how they talk and think, one sentence")
    instructions: str = Field(description="1-2 sentences on how this person behaves when shopping, specific to the owner's description")


DRAFT = """Create one realistic customer persona who will test this product.
Product: {product}
The business owner describes the customer they want: "{text}"
Stay faithful to the owner's description; fill in only what they didn't say. Pick the archetype that fits best."""


def draft(text: str, product: str = "") -> dict:
    from .models import fast
    d: _Draft = fast().with_structured_output(_Draft).invoke(DRAFT.format(text=_clean(text, 500), product=_clean(product, 300) or "(not given)"))
    p = d.model_dump()
    if p["archetype"] not in ARCHETYPES:
        p["archetype"] = next((a for a in ARCHETYPES if a.split()[0] in p["archetype"].lower()), "first-time user")
    p["share"] = 0.15
    p["avatar"] = {"seed": random.Random(re.sub(r"\W", "", text)).randint(0, 10_000)}
    p["custom"] = True
    return p
