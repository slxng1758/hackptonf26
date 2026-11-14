"""Customer segments from a plain description or a CSV, and the buyer tasks each segment's AI agent would run.

Segments are a simulation (a cheap precursor to human testing). The shoppers that act on their tasks are real models.
"""
from __future__ import annotations

import csv
import io

from pydantic import BaseModel, Field

from .models import fast


class Segment(BaseModel):
    name: str = Field(description="short name for this customer segment, e.g. 'new-authority owner-operators'")
    share: float = Field(ge=0, le=1, description="fraction of customers in this segment; all shares sum to about 1")
    cares_about: str = Field(description="what this segment cares about most, one sentence")
    tasks: list[str] = Field(min_length=2, max_length=2, description="two requests a person in this segment would give their AI shopping agent, in their own words, first person, specific")


class Segments(BaseModel):
    segments: list[Segment] = Field(min_length=3, max_length=5)


SEGMENT = """You are a market researcher. Split this business's customers into 3 to 5 realistic segments.

Business category: {category}
What we know about the customers:
{customers}

For each segment, write two requests that someone in it would type to their AI shopping agent (ChatGPT, Claude, Gemini) when
looking for this kind of business. Make them concrete and different from each other. Do not mention any business by name."""


def summarize_csv(text: str, limit: int = 40) -> str:
    """Turn uploaded customer data into a short description: columns, row count and a few anonymized rows."""
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        return text[:2000]
    cols = list(rows[0].keys())
    drop = {c for c in cols if any(k in c.lower() for k in ("name", "email", "phone", "address", "ssn", "dob", "id"))}
    keep = [c for c in cols if c not in drop]
    sample = "\n".join(", ".join(f"{c}={r.get(c, '')}" for c in keep) for r in rows[:limit])
    return f"{len(rows)} customers. Columns used: {', '.join(keep)} (identifying columns dropped: {', '.join(sorted(drop)) or 'none'}).\nSample rows:\n{sample}"


def segment(category: str, customers: str) -> list[dict]:
    s: Segments = fast().with_structured_output(Segments, method="json_schema").invoke(SEGMENT.format(category=category, customers=customers))
    total = sum(x.share for x in s.segments) or 1
    return [{**x.model_dump(), "share": round(x.share / total, 3)} for x in s.segments]
