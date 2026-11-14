"""One input → everything. Give a website or a business name; an agent reads the site, searches the web for real
competitors, and drafts the customer description. The user reviews instead of typing.
"""
from __future__ import annotations

import html
import json
import re
import urllib.request

from openai import OpenAI
from pydantic import BaseModel, Field

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def fetch_text(url: str, limit: int = 8000) -> str:
    """Visible text of one public web page. Best effort; returns '' on failure."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        raw = urllib.request.urlopen(req, timeout=12).read(800_000).decode("utf-8", "ignore")
    except Exception:
        return ""
    raw = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", raw)
    text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw))
    return re.sub(r"\s+", " ", text).strip()[:limit]


class Competitor(BaseModel):
    name: str
    url: str
    listing: str = Field(description="what this business's own site says, as concrete facts, 50-90 words, starting with its name. As detailed as the business's own listing, so the comparison is fair")


class Scan(BaseModel):
    name: str
    website: str = Field(description="the business's own website URL")
    category: str = Field(description="what it sells and where, e.g. 'Event catering in Princeton, NJ'")
    listing: str = Field(description="how the business describes itself today on its site, max 60 words, quoted or closely paraphrased")
    facts: list[str] = Field(description="8 to 12 concrete, checkable facts from the business's own site: prices, sizes, hours, area, notice, options")
    competitors: list[Competitor] = Field(description="4 real competitors serving the same customers in the same area")
    customers: str = Field(description="who likely buys from this business and what they care about, 2-3 sentences")
    sources: list[str] = Field(description="URLs used")


PROMPT = """You are setting up a test of how AI shopping agents see a business.

Business: {query}
{page}

1. Work out the business's name, what it sells and where.
2. Write how it describes itself today (from its own site), and list concrete facts from its own site only. Do not invent facts;
   if the site says little, list fewer facts.
3. Search the web for 4 REAL competitors: OTHER businesses (never this business itself, never a directory, review site or
   chamber-of-commerce page) that serve the same customers in the same area. For each, read its own site and list its concrete
   facts (prices, group sizes, notice, delivery, dietary options, hours) at the same level of detail as you used for the business.
   The test is only fair if every listing gets the same care.
4. Describe its likely customers.
Return JSON only."""


def scan(query: str) -> dict:
    url = query if re.match(r"^https?://", query.strip()) else (f"https://{query.strip()}" if re.match(r"^[\w-]+(\.[\w-]+)+(/.*)?$", query.strip()) else "")
    page = fetch_text(url) if url else ""
    client = OpenAI(timeout=120)
    r = client.responses.create(
        model="gpt-5.4-mini",
        tools=[{"type": "web_search"}],
        input=PROMPT.format(query=query, page=f"Text from its website ({url}):\n{page}" if page else "No page text was fetched; search for it."),
        text={"format": {"type": "json_schema", "name": "scan", "schema": _schema(Scan), "strict": True}},
    )
    data = Scan.model_validate(json.loads(r.output_text)).model_dump()
    # never let the business compete with itself, or a directory page about it
    own = re.sub(r"[^a-z]", "", data["name"].lower().split(" ")[0])
    data["competitors"] = [c for c in data["competitors"]
                           if own not in re.sub(r"[^a-z]", "", c["name"].lower())
                           and not re.search(r"chamber|directory|yelp|tripadvisor|yellowpages", (c["name"] + c["url"]).lower())]
    return {
        "name": data["name"], "url": url or data["website"], "category": data["category"], "listing": data["listing"], "facts": data["facts"],
        "competitors": [c["listing"] for c in data["competitors"]],
        "competitor_meta": [{"name": c["name"], "url": c["url"]} for c in data["competitors"]],
        "customers": data["customers"], "sources": data["sources"], "fetched_site": bool(page),
    }


def _schema(model) -> dict:
    """Pydantic JSON schema made strict-mode friendly (all fields required, no extra keys)."""
    s = model.model_json_schema()

    def fix(node):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["required"] = list(node["properties"].keys())
                node["additionalProperties"] = False
            for k in ("title", "description", "default"):
                node.pop(k, None) if k != "description" else None
            for v in list(node.values()):
                fix(v)
        elif isinstance(node, list):
            for v in node:
                fix(v)
    fix(s)
    return s
