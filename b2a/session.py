"""Persona sessions: each persona really browses the product in a headless browser and decides.

Every step: screenshot → a vision model, in the persona's voice, looks at the page and chooses what to do (click a link,
scroll, go back, or decide). Each step is saved (screenshot, thought, feeling, action) so the UI can replay it.
"""
from __future__ import annotations

import base64
import json
import random
import threading
from pathlib import Path
from typing import Literal

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from .models import fast

ARCHETYPES = ["price-sensitive", "quality-first", "brand-loyal", "function-first", "first-time user", "skeptic", "enthusiast"]


class Persona(BaseModel):
    name: str = Field(description="a first name")
    age: int = Field(ge=16, le=90)
    occupation: str
    archetype: Literal["price-sensitive", "quality-first", "brand-loyal", "function-first", "first-time user", "skeptic", "enthusiast"]
    segment: str = Field(description="which customer segment they belong to")
    share: float = Field(ge=0, le=1, description="how much of the real customer base this persona stands for; all shares sum to about 1")
    goal: str = Field(description="what they came to the product for, in their words, one sentence")
    budget: str = Field(description="what they are willing to spend, concretely")
    voice: str = Field(description="how they talk and think, one sentence")


class Cast(BaseModel):
    personas: list[Persona] = Field(min_length=4, max_length=7)


CAST = """Create the customers who will test this product.

Product: {name}. {category}
What changed / context from the business: {context}
World they live in: {world}
Who the customers are: {customers}

Make 4 to 7 personas covering the real customer segments. Include, where it fits this product: a price-sensitive buyer,
a quality-first buyer, a brand-loyal buyer, a function-first buyer, a first-time user, a skeptic and an enthusiast.
Give each a share of the real customer base (enthusiasts and skeptics are usually small). Make them specific people."""


class Step(BaseModel):
    thought: str = Field(description="what you think right now, first person, in your voice, max 30 words")
    feeling: Literal["delighted", "interested", "neutral", "confused", "annoyed", "skeptical"]
    action: Literal["click", "scroll", "back", "decide"]
    target: str = Field(default="", description="for click: the exact text of the link or button to click; otherwise empty")


class Decision(BaseModel):
    decision: Literal["buy", "not buy", "maybe later", "would complain", "would recommend"]
    rating: int = Field(ge=1, le=5)
    feeling: Literal["delighted", "interested", "neutral", "confused", "annoyed", "skeptical"]
    quote: str = Field(description="what you'd tell a friend about it, first person, max 35 words")
    reasons: list[str] = Field(default_factory=list, description="2-4 concrete reasons, each tied to something you saw")
    missing: str = Field(default="", description="what would have changed your mind, one sentence")


STEP = """You are {name}, {age}, {occupation}. You are a {archetype} customer. {voice}
Your goal: {goal}. Your budget: {budget}.
The world right now: {world}
What the business says changed: {context}

You are looking at {url} (step {n} of at most {max_steps}). Visible links and buttons: {links}
Page text (excerpt): {text}
What you've done so far: {history}

Look at the screenshot like a real person would. Decide your next move: click one of the visible links or buttons to find what
you need, scroll, go back, or decide (once you know enough). Stay in character."""

DECIDE = """You are {name}, {age}, {occupation}, a {archetype} customer. {voice} Goal: {goal}. Budget: {budget}. World: {world}.
You browsed {product}. Here is everything you saw and thought:
{history}
Make your decision, honestly and in character. If a page was blocked by an automated bot check, real customers would not
have seen that block: do not penalize the business for it; judge only what you actually saw."""

BOT_WALL = ("performing security verification", "verify you are human", "checking your browser", "are you a robot",
            "captcha", "just a moment...", "access denied", "attention required")


def is_bot_wall(text: str, title: str) -> bool:
    t = (text[:1500] + " " + title).lower()
    return any(k in t for k in BOT_WALL)


class Site(BaseModel):
    name: str = Field(description="the business or product name")
    category: str = Field(description="what it sells and where, one short line")
    customers: str = Field(description="who its real customers are, 2-3 sentences, with rough shares")


def read_site(url: str) -> dict:
    """From just a URL: what the business is and who buys from it."""
    from .scan import fetch_text
    try:
        text = fetch_text(url, 6000)
    except Exception:
        text = ""
    s: Site = fast().with_structured_output(Site, method="json_schema").invoke(
        f"Website: {url}\nPage text:\n{text or '(could not load; infer from the address)'}\n\nWhat is this business and who are its customers?")
    return s.model_dump()


FEELINGS = ["delighted", "interested", "neutral", "confused", "annoyed", "skeptical"]


def cast(name: str, category: str, context: str, world: str, customers: str) -> list[dict]:
    c: Cast = fast().with_structured_output(Cast, method="json_schema").invoke(CAST.format(name=name, category=category, context=context or "none", world=world or "today, normal times", customers=customers))
    total = sum(p.share for p in c.personas) or 1
    rng = random.Random(name)
    out = []
    for i, p in enumerate(c.personas):
        d = p.model_dump()
        d["id"] = f"p{i + 1}"
        d["share"] = round(p.share / total, 3)
        d["avatar"] = {"seed": rng.randint(0, 10_000)}
        out.append(d)
    return out


def _img_msg(text: str, jpg: bytes) -> HumanMessage:
    return HumanMessage(content=[{"type": "text", "text": text},
                                 {"type": "image", "source_type": "base64", "mime_type": "image/jpeg", "data": base64.b64encode(jpg).decode()}])


def browse(persona: dict, url: str, world: str, context: str, out_dir: Path, on_step, max_steps: int = 5) -> dict:
    """One persona, one real browser session. Returns the session with every step and the final decision."""
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    steps: list[dict] = []
    history: list[str] = []
    model = fast()
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--disable-gpu", "--use-gl=swiftshader", "--disable-dev-shm-usage"])
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg = ctx.new_page()
        try:
            pg.goto(url, timeout=30000, wait_until="domcontentloaded")
        except Exception:
            pass
        for n in range(1, max_steps + 1):
            pg.wait_for_timeout(900)
            shot = out_dir / f"{persona['id']}_{n}.jpg"
            try:
                jpg = pg.screenshot(type="jpeg", quality=55, timeout=15000)
                shot.write_bytes(jpg)
            except Exception:
                jpg = b""
            try:
                links = pg.eval_on_selector_all("a, button", "els => [...new Set(els.map(e => (e.innerText||'').trim()).filter(t => t && t.length < 40))].slice(0, 30)")
                text = pg.inner_text("body", timeout=5000)[:2500]
            except Exception:
                links, text = [], ""
            blocked = is_bot_wall(text, pg.title() if pg else "")
            if blocked:
                # Our automated browser hit a bot check. Real customers would not see this, so it must not count against the business.
                step = {"n": n, "url": pg.url, "title": pg.title(), "shot": shot.name if jpg else None, "blocked": True,
                        "thought": "(A security check blocked our test browser here. Real customers wouldn't see this, so it doesn't count.)",
                        "feeling": "neutral", "action": "back", "target": ""}
                steps.append(step)
                history.append(f"[{pg.url}] BLOCKED by an automated bot check that real customers would not see. Do not hold this against the business; judge only what you could see elsewhere.")
                on_step(persona["id"], step)
                try:
                    pg.go_back(timeout=10000)
                except Exception:
                    pass
                continue
            prompt = STEP.format(**persona, world=world or "today, normal times", context=context or "none", url=pg.url, n=n, max_steps=max_steps,
                                 links=", ".join(links) or "(none)", text=text, history=" → ".join(history) or "just arrived")
            try:
                s: Step = model.with_structured_output(Step).invoke([_img_msg(prompt, jpg)] if jpg else prompt)
            except Exception as e:
                s = Step(thought=f"(couldn't read the page: {type(e).__name__})", feeling="confused", action="decide")
            step = {"n": n, "url": pg.url, "title": pg.title() if pg else "", "shot": shot.name if jpg else None,
                    "thought": s.thought, "feeling": s.feeling, "action": s.action, "target": s.target}
            steps.append(step)
            history.append(f"[{pg.url}] thought: {s.thought} ({s.feeling}) → {s.action} {s.target}".strip())
            on_step(persona["id"], step)
            if s.action == "decide" or n == max_steps:
                break
            try:
                if s.action == "click" and s.target:
                    before = len(ctx.pages)
                    pg.get_by_text(s.target, exact=False).first.click(timeout=6000)
                    pg.wait_for_timeout(1200)
                    if len(ctx.pages) > before:  # link opened a new tab: follow it like a real person would
                        pg = ctx.pages[-1]
                    pg.wait_for_load_state("domcontentloaded", timeout=15000)
                elif s.action == "scroll":
                    pg.mouse.wheel(0, 700)
                elif s.action == "back":
                    pg.go_back(timeout=10000)
            except Exception:
                history.append(f"(tried to {s.action} '{s.target}' but it didn't work)")
        b.close()
    ask = DECIDE.format(**persona, world=world or "today, normal times", product=url, history="\n".join(history))
    try:
        d: Decision = model.with_structured_output(Decision).invoke(ask)
    except Exception:
        d = model.with_structured_output(Decision).invoke(ask + "\nFill in every field.")
    return {"persona": persona["id"], "steps": steps, "decision": d.model_dump()}


def run_all(personas: list[dict], url: str, world: str, context: str, out_dir: Path, on_step, on_done) -> list[dict]:
    """All personas browse in parallel, each in its own browser."""
    results: list[dict] = []
    lock = threading.Lock()

    def go(p):
        try:
            r = browse(p, url, world, context, out_dir, on_step)
        except Exception as e:
            r = {"persona": p["id"], "steps": [], "decision": None, "error": f"{type(e).__name__}: {e}"[:200]}
        with lock:
            results.append(r)
        on_done(p["id"], r)

    threads = [threading.Thread(target=go, args=(p,), daemon=True) for p in personas]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results
