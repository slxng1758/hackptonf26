"""Gemini's two jobs that no other model here does.

1. UX lens: Gemini looks at the exact screenshots where a customer got confused, annoyed, skeptical or gave up, and
   draws boxes around the part of the page that caused it (Gemini's spatial understanding returns box_2d coordinates).
   The boxes from every customer are grouped into friction hotspots: "3 of 5 customers got stuck on the size chart".
   The persona agents say what they felt; Gemini shows where on the page it happened.

2. Grounded world: when the owner picks a world ("spring 2020, COVID"), Gemini with Google Search grounding writes
   what that world was really like for this product's customers, with sources, so the simulation's context is
   researched, not imagined.

    POST /api/sims/{id}/lens     run the lens on a finished simulation -> Lens (also saved to runs/sims/<id>/lens.json)
    GET  /api/sims/{id}/lens     the saved lens
    POST /api/world              {world, product} -> GroundedWorld

Needs GOOGLE_API_KEY. Model: GEMINI_LENS_MODEL, else GEMINI_MODEL, else gemini-3.5-flash.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from .contract import GroundedWorld, Hotspot, Lens, LensBox, LensShot, Source
from .evals import _tokens

ROOT = Path(__file__).resolve().parent.parent
SIMS = ROOT / "runs" / "sims"

FRICTION = {"confused", "annoyed", "skeptical"}
MAX_SHOTS = int(os.getenv("LENS_SHOTS", "6"))  # each shot is one Gemini call; free tier is ~20 a day


def model_name() -> str:
    return os.getenv("GEMINI_LENS_MODEL") or os.getenv("GEMINI_MODEL") or "gemini-3.5-flash"


_CLIENT = None


def _client():
    """One shared Gemini client (the SDK closes a client once nothing references it, mid-request included)."""
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    from dotenv import load_dotenv
    load_dotenv()
    key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("Gemini needs GOOGLE_API_KEY in .env")
    from google import genai
    _CLIENT = genai.Client(api_key=key)
    return _CLIENT


# ---------------------------------------------------------------- 1. UX lens

def friction_steps(view: dict, limit: int = MAX_SHOTS) -> list[dict]:
    """The moments worth looking at: a bad feeling, going back, or the last screen before a customer didn't buy."""
    personas = {p["id"]: p for p in view.get("personas") or []}
    decisions = view.get("decisions") or {}
    clicked = set((view.get("summary") or {}).get("clicked_buy") or [])
    picked = []
    for pid, steps in (view.get("live") or {}).items():
        steps = [s for s in steps if s.get("shot") and not s.get("blocked")]
        d = decisions.get(pid) or {}
        lost = pid not in clicked and d.get("decision") in ("not buy", "maybe later", "would complain")
        for i, s in enumerate(steps):
            last = i == len(steps) - 1
            why = ("left without buying" if last and lost else "feeling" if s.get("feeling") in FRICTION
                   else "went back" if s.get("action") == "back" else None)
            if why:
                p = personas.get(pid, {})
                picked.append({"persona_id": pid, "persona": p.get("name", pid), "archetype": p.get("archetype", ""),
                               "model": p.get("model", ""), "step": s.get("n", i + 1), "url": s.get("url", ""), "shot": s["shot"],
                               "feeling": s.get("feeling", ""), "thought": s.get("thought", ""), "why": why,
                               "weight": {"feeling": 2, "left without buying": 3, "went back": 1}[why]})
    # strongest signals first, at most 3 per customer so one persona can't fill the budget
    picked.sort(key=lambda x: -x["weight"])
    per: dict[str, int] = defaultdict(int)
    out = []
    for x in picked:
        if per[x["persona_id"]] < 3:
            per[x["persona_id"]] += 1
            out.append(x)
    return out[:limit]


LENS_PROMPT = """This is a screenshot of a web page, seen by a customer: {persona} ({archetype}).
At this moment they felt {feeling} and thought: "{thought}"
({why})

Find the parts of THIS page that caused that reaction: something confusing, missing, hidden, hard to read, or off-putting.
Return up to 3 boxes, most important first. Each box must tightly surround a visible element on the screenshot.
box_2d is [ymin, xmin, ymax, xmax] normalized to 0-1000. If the problem is something missing, box the place where the
customer looked for it and say what was missing. Fixes must be concrete changes to this page."""


class _Box(BaseModel):
    box_2d: list[int] = Field(description="[ymin, xmin, ymax, xmax], each 0-1000")
    label: str = Field(description="the element, 2-5 words, e.g. 'shipping cost line'")
    issue: str = Field(description="what's wrong with it for this customer, one sentence")
    fix: str = Field(description="concrete change to the page, one sentence")
    severity: int = Field(description="1 = minor, 2 = slows them down, 3 = makes them leave")


class _Boxes(BaseModel):
    boxes: list[_Box]


def _clean_box(b: _Box) -> LensBox | None:
    if len(b.box_2d) != 4:
        return None
    y0, x0, y1, x1 = (max(0, min(1000, int(v))) for v in b.box_2d)
    if y1 <= y0 or x1 <= x0:
        return None
    return LensBox(box_2d=[y0, x0, y1, x1], label=b.label.strip(), issue=b.issue.strip(), fix=b.fix.strip(),
                   severity=max(1, min(3, int(b.severity))))


def look(step: dict, jpg: bytes, client=None) -> list[LensBox]:
    """Gemini looks at one screenshot and boxes what caused the customer's reaction."""
    from google.genai import types
    client = client or _client()
    r = client.models.generate_content(
        model=model_name(),
        contents=[types.Part.from_bytes(data=jpg, mime_type="image/jpeg"), LENS_PROMPT.format(**step)],
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=_Boxes, temperature=0.2))
    parsed = r.parsed if isinstance(r.parsed, _Boxes) else _Boxes.model_validate_json(r.text)
    return [b for b in (_clean_box(x) for x in parsed.boxes[:3]) if b]


def _page(url: str) -> str:
    u = urlparse(url)
    return (u.path or "/").rstrip("/") or "/"


def hotspots(shots: list[LensShot], limit: int = 6) -> list[Hotspot]:
    """Group boxes from all customers that point at the same problem on the same page."""
    groups: list[dict] = []
    for s in shots:
        for b in s.boxes:
            toks = _tokens(f"{b.label} {b.issue}")
            page = _page(s.url)
            for g in groups:
                if g["page"] == page and toks and g["toks"] and len(toks & g["toks"]) / min(len(toks), len(g["toks"])) >= 0.4:
                    g["items"].append((s, b))
                    g["toks"] |= toks
                    break
            else:
                groups.append({"page": page, "toks": set(toks), "items": [(s, b)]})
    out = []
    for g in groups:
        items = g["items"]
        first = max(items, key=lambda x: x[1].severity)[1]
        who = {s.persona_id: s for s, _ in items}
        out.append(Hotspot(page=g["page"], label=first.label, issue=first.issue, fix=first.fix,
                           severity=round(sum(b.severity for _, b in items) / len(items), 2),
                           personas=list(who), names=[s.persona for s in who.values()],
                           models=sorted({s.model for s in who.values() if s.model}),
                           count=len(who), shots=[f"{s.persona_id}:{s.step}" for s, _ in items]))
    return sorted(out, key=lambda h: (-h.count, -h.severity))[:limit]


def _summary(hs: list[Hotspot], n_customers: int) -> str:
    if not hs:
        return "Gemini found no specific spot on the pages that caused friction."
    h = hs[0]
    s = (f"The biggest friction point is the {h.label} on {h.page}: {h.count} of {n_customers} customers "
         f"hit it ({', '.join(h.names[:3])}). {h.issue} Fix: {h.fix}")
    if len(hs) > 1:
        s += f" Next: {hs[1].label} on {hs[1].page} ({hs[1].count})."
    return s


def lens(view: dict, sim_dir: Path, client=None, workers: int = 4) -> Lens:
    """Run the UX lens over a finished simulation's friction screenshots."""
    steps = friction_steps(view)
    client = client or _client()

    def one(st: dict) -> LensShot | None:
        f = sim_dir / "shots" / st["shot"]
        if not f.exists():
            return None
        try:
            boxes = look(st, f.read_bytes(), client)
        except Exception as e:  # one bad screenshot shouldn't sink the lens
            boxes, st = [], {**st, "error": f"{type(e).__name__}"}
        return LensShot(**{k: st[k] for k in ("persona_id", "persona", "archetype", "model", "step", "url", "shot", "feeling", "thought", "why")},
                        boxes=boxes, error=st.get("error", ""))

    with ThreadPoolExecutor(max_workers=workers) as ex:
        shots = [s for s in ex.map(one, steps) if s]
    hs = hotspots(shots)
    n = len({p["id"] for p in view.get("personas") or []}) or len({s.persona_id for s in shots})
    errors = [x.error for x in shots if x.error]
    if shots and len(errors) == len(shots):  # Gemini never answered: say why instead of "no friction found"
        why = "Gemini's daily free-tier quota is used up" if any("429" in e or "RESOURCE_EXHAUSTED" in e or "Client" in e for e in errors) else errors[0][:120]
        return Lens(model=model_name(), shots=shots, hotspots=[], summary=f"Gemini couldn't look at the screenshots: {why}. Try again later or with a paid key.")
    return Lens(model=model_name(), shots=shots, hotspots=hs, summary=_summary(hs, n))


def run_lens(sim_id: str, view: dict, client=None) -> Lens:
    d = SIMS / Path(sim_id).name
    out = lens(view, d, client)
    (d / "lens.json").write_text(out.model_dump_json(indent=2))
    return out


def saved_lens(sim_id: str) -> dict | None:
    f = SIMS / Path(sim_id).name / "lens.json"
    return json.loads(f.read_text()) if f.exists() else None


# ---------------------------------------------------------------- 2. grounded world

WORLD_PROMPT = """A small business wants to know how customers would react to its product in this world:
"{world}"
Product: {product}

Using Google Search, describe what that world was (or is) really like for people buying this kind of product:
prices, availability, what people worried about, rules or habits that changed buying, and what they valued.
Write 4-6 short factual bullet points starting with "- ", each specific (numbers, dates, places when known).
Then one line starting with "SUMMARY:" that a customer persona could use as background, 1-2 sentences."""


def ground_world(world: str, product: str, client=None) -> GroundedWorld:
    """Gemini + Google Search: the real context of the chosen world, with sources."""
    from google.genai import types
    client = client or _client()
    prompt = WORLD_PROMPT.format(world=world, product=product)
    try:
        r = client.models.generate_content(model=model_name(), contents=prompt, config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())], temperature=0.3,
            http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1))))
    except Exception as e:
        # Search grounding isn't in every key's quota (free keys often get 429): answer from Gemini's own knowledge
        # and say so (grounded=False, no sources), rather than fail.
        if "429" not in str(e) and "RESOURCE_EXHAUSTED" not in str(e) and "search" not in str(e).lower():
            raise
        r = client.models.generate_content(model=model_name(), contents=prompt.replace("Using Google Search, describe", "From what you know, describe"),
                                           config=types.GenerateContentConfig(temperature=0.3))
    text = r.text or ""
    facts = [l[2:].strip() for l in text.splitlines() if l.strip().startswith("- ")]
    summary = next((l.split(":", 1)[1].strip() for l in text.splitlines() if l.strip().upper().startswith("SUMMARY:")), "")
    sources, seen = [], set()
    try:
        for c in (r.candidates[0].grounding_metadata.grounding_chunks or []):
            web = getattr(c, "web", None)
            if web and web.uri and web.uri not in seen:
                seen.add(web.uri)
                sources.append(Source(title=web.title or web.uri, url=web.uri))
    except Exception:
        pass
    return GroundedWorld(world=world, summary=summary or (facts[0] if facts else text[:300]), facts=facts[:6],
                         sources=sources[:8], model=model_name(), grounded=bool(sources))


def world_text(g: GroundedWorld, limit: int = 300) -> str:
    """What to put in the simulation's `world` field (max 300 chars in POST /api/sims): owner's words + researched summary."""
    s = f"{g.world.rstrip('. ')}. {g.summary}".strip()
    for f in g.facts:
        if len(s) + len(f) + 1 > limit:
            break
        s += " " + f
    return s[:limit]
