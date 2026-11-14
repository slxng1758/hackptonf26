"""Fact matrix: for the things buyers ask about, what each listing actually states. Shows at a glance why agents chose others."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .models import fast


class Row(BaseModel):
    attribute: str = Field(description="a thing buyers ask about, 1-3 words, e.g. 'Price', 'Group size', 'Notice needed', 'Vegan/GF', 'Delivery'")
    values: list[str] = Field(description="one entry per listing, in the same order as given: what that listing states, max 6 words, or '' if it does not say")


class Matrix(BaseModel):
    rows: list[Row] = Field(min_length=5, max_length=8)


PROMPT = """Buyers of {category} ask about things like this (from real requests):
{requests}

For the 5 to 8 attributes buyers ask about most, say what each listing below states. Use '' when a listing does not say.
Listings, in order:
{listings}"""


def build(category: str, segments: list[dict], names: list[str], listings: list[str]) -> dict:
    reqs = "\n".join(f"- {t}" for s in segments for t in s["tasks"])
    lst = "\n".join(f"{i + 1}. [{n}] {l}" for i, (n, l) in enumerate(zip(names, listings)))
    m: Matrix = fast().with_structured_output(Matrix, method="json_schema").invoke(PROMPT.format(category=category, requests=reqs, listings=lst))
    rows = [{"attribute": r.attribute, "values": (r.values + [""] * len(names))[: len(names)]} for r in m.rows]
    return {"names": names, "rows": rows}
