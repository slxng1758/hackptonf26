"""Persona sessions: each persona really browses the product in a headless browser and decides.

Every step: screenshot → a vision model, in the persona's voice, looks at the page and chooses what to do (click a link,
scroll, go back, or decide). Each step is saved (screenshot, thought, feeling, action) so the UI can replay it.
"""
from __future__ import annotations

import base64
import re
import time
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
What it sells and for how much: {offer}
What changed / context from the business: {context}
World they live in: {world}
Who the customers are: {customers}

Make 4 to 7 personas covering the real customer segments. Include, where it fits this product: a price-sensitive buyer,
a quality-first buyer, a brand-loyal buyer, a function-first buyer, a first-time user, a skeptic and an enthusiast.
Give each a share of the real customer base (enthusiasts and skeptics are usually small). Make them specific people.
Everyone you cast actually came to this site on purpose (an ad, a search, a friend) because they want what it sells. Budgets
must be what real buyers of this kind of product spend: most can afford the typical price, a price-sensitive one may be
stretched. Do not cast people who want something this business doesn't sell.
Goals must be ordinary reasons people come to this business, never a specific item, version or feature you are guessing exists.
Only give someone a history with the business (a past purchase, a favorite) if their segment is clearly repeat customers."""


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
What you learned from past visits to sites like this: {memory}
The world right now: {world}
What the business says changed: {context}

You are looking at {url} (step {n} of at most {max_steps}). Visible links and buttons: {links}
Page text (excerpt): {text}
What you've done so far: {history}

Look at the screenshot like a real person would. Decide your next move: click one of the visible links or buttons, scroll,
go back, or decide. Shop like a real person with limited patience: use search, filters or menus instead of scrolling long lists.
If you find something that fits, pick it (size/option) and click "Add to cart" or the buy button, then decide. Don't enter
payment details. If the site clearly isn't for you, decide early. Stay in character."""

DECIDE = """You are {name}, {age}, {occupation}, a {archetype} customer. {voice} Goal: {goal}. Budget: {budget}. World: {world}.
What you learned from past visits: {memory}
You browsed {product}. Here is everything you saw and thought:
{history}
Make your decision like a real shopper on this visit, not a reviewer. Real people buy without perfect information:
if you found something that fits your goal and budget well enough and nothing put you off, you buy. "Maybe later" means you
leave now and most people who say it never come back, so only choose it if something specific stopped you today.
Choose "not buy" if it doesn't fit you, "would complain" if something went wrong. If a page was blocked by an automated bot check, real customers would not
have seen that block: do not penalize the business for it; judge only what you actually saw."""

# Visible links and buttons only (hidden mobile-menu copies are skipped), with where each link goes.
VISIBLE_LINKS = """() => {
  const out = [], seen = new Set();
  const els = [...document.querySelectorAll('a[href], button, label, summary, [role=button], [role=link], [role=tab], [role=checkbox], input[type=submit]')];
  const vh = innerHeight;
  // what's on screen first, then the rest of the page
  els.sort((a, b) => { const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect(); return (ra.top > vh || ra.bottom < 0) - (rb.top > vh || rb.bottom < 0); });
  for (const e of els) {
    const r = e.getBoundingClientRect(), st = getComputedStyle(e);
    if (r.width < 2 || r.height < 2 || st.visibility === 'hidden' || st.display === 'none' || st.opacity === '0') continue;
    let t = (e.innerText || e.getAttribute('aria-label') || e.value || '').trim().split('\\n').map(x => x.trim()).filter(Boolean).slice(0, 2).join(' ');
    if (!t) continue;
    if (t.length > 60) t = t.slice(0, 60);
    if (seen.has(t)) continue;
    seen.add(t); out.push({ t, href: (e.tagName === 'A' && e.href) || '' });
    if (out.length >= 60) break;
  }
  return out;
}"""

BOT_WALL = ("performing security verification", "verify you are human", "checking your browser", "are you a robot",
            "captcha", "just a moment...", "access denied", "attention required", "verifying your connection",
            "too many requests", "unusual traffic")

# Clicking one of these means the customer chose to buy. Sites often block automated browsers at the cart, so the click
# itself is the signal; an empty cart afterwards is our test setup, not the business.
CART = re.compile(r"add to (cart|bag|basket|order)|buy (it )?now|checkout|check out|order now|place order|book now|reserve|subscribe|get started|download", re.I)


def click_text(pg, t: str):
    """Click whatever visible thing carries this text: a button, a filter checkbox, a product card."""
    tries = [lambda: pg.locator("a:visible, button:visible, [role=button]:visible, summary:visible", has_text=t).first,
             lambda: pg.get_by_label(t, exact=False).first,
             lambda: pg.locator("label:visible, [role=checkbox]:visible", has_text=t).first,
             lambda: pg.get_by_text(t, exact=False).locator("visible=true").first]
    last = None
    for make in tries:
        try:
            make().click(timeout=3000)
            return
        except Exception as e:
            last = e
    raise last


def is_bot_wall(text: str, title: str) -> bool:
    t = (text[:1500] + " " + title).lower()
    return any(k in t for k in BOT_WALL)


class Site(BaseModel):
    name: str = Field(description="the business or product name")
    category: str = Field(description="what it sells and where, one short line")
    customers: str = Field(description="who its real customers are, 2-3 sentences, with rough shares")
    offer: str = Field(description="what exactly it sells and the price range seen on the page, one or two sentences")


def rendered_text(url: str, limit: int = 6000) -> str:
    """The page as a person sees it (JavaScript run), plus where its main links go."""
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(args=["--disable-gpu", "--use-gl=swiftshader", "--disable-dev-shm-usage"])
            pg = b.new_page(viewport={"width": 1280, "height": 800})
            pg.goto(url, timeout=30000, wait_until="domcontentloaded")
            pg.wait_for_timeout(2500)
            text = pg.inner_text("body", timeout=8000)
            b.close()
            return text[:limit]
    except Exception:
        from .scan import fetch_text
        try:
            return fetch_text(url, limit)
        except Exception:
            return ""


def read_site(url: str) -> dict:
    """From just a URL: what the business is and who buys from it."""
    text = rendered_text(url)
    s: Site = fast().with_structured_output(Site, method="json_schema").invoke(
        f"Website: {url}\nPage text:\n{text or '(could not load; infer from the address)'}\n\nWhat is this business and who are its customers?")
    return s.model_dump()


FEELINGS = ["delighted", "interested", "neutral", "confused", "annoyed", "skeptical"]


def cast(name: str, category: str, context: str, world: str, customers: str, offer: str = "") -> list[dict]:
    ask = CAST.format(name=name, category=category, context=context or "none", world=world or "today, normal times", customers=customers, offer=offer or "see the website")
    try:
        c: Cast = fast().with_structured_output(Cast, method="json_schema").invoke(ask)
    except Exception:
        c = fast().with_structured_output(Cast, method="json_schema").invoke(ask + "\nKeep every field short. Exactly 6 personas.")
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


def browse(persona: dict, url: str, world: str, context: str, out_dir: Path, on_step, max_steps: int = 10) -> dict:
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
        pg.wait_for_timeout(1500)
        pg.keyboard.press("Escape")  # close the signup popup a real person would dismiss
        for n in range(1, max_steps + 1):
            pg.wait_for_timeout(900)
            shot = out_dir / f"{persona['id']}_{n}.jpg"
            try:
                jpg = pg.screenshot(type="jpeg", quality=55, timeout=15000)
                shot.write_bytes(jpg)
            except Exception:
                jpg = b""
            try:
                found = pg.evaluate(VISIBLE_LINKS)
                targets = {f["t"]: f["href"] for f in found}
                links = list(targets)
                text = pg.inner_text("body", timeout=5000)[:2500]
            except Exception:
                links, text, targets = [], "", {}
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
            prompt = STEP.format(**{**persona, "memory": persona.get("memory") or "nothing yet"}, world=world or "today, normal times", context=context or "none", url=pg.url, n=n, max_steps=max_steps,
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
                    was = pg.url
                    t = s.target.strip()
                    href = targets.get(t) or next((h for k, h in targets.items() if k.lower() == t.lower()), None) \
                        or next((h for k, h in targets.items() if t.lower() in k.lower() or k.lower() in t.lower()), None)
                    if href and href.startswith("http"):
                        pg.goto(href, timeout=30000, wait_until="domcontentloaded")  # a link: go where it points
                    else:
                        before = len(ctx.pages)
                        click_text(pg, t)
                        pg.wait_for_timeout(1200)
                        if len(ctx.pages) > before:  # opened a new tab: follow it like a real person would
                            pg = ctx.pages[-1]
                        pg.wait_for_load_state("domcontentloaded", timeout=15000)
                    if CART.search(t):
                        step["cart"] = True
                        on_step(persona["id"], None)
                        history.append(f"(You clicked '{t}': you chose to buy. Test browsers are often blocked at the cart, so if the cart "
                                       "looks empty or an error shows after this, that is our test setup, not the business. Don't hold it against them.)")
                    elif pg.url == was and not href:
                        history.append(f"(clicked '{t}': the page stayed the same, maybe a menu opened)")
                elif s.action == "scroll":
                    pg.mouse.wheel(0, 900)
                elif s.action == "back":
                    pg.go_back(timeout=10000)
                    if not pg.url.startswith("http"):  # went back past the landing page
                        pg.goto(url, timeout=30000, wait_until="domcontentloaded")
            except Exception:
                history.append(f"(tried to {s.action} '{s.target}' but it didn't work)")
        b.close()
    ask = DECIDE.format(**{**persona, "memory": persona.get("memory") or "nothing yet"}, world=world or "today, normal times", product=url, history="\n".join(history))
    try:
        d: Decision = model.with_structured_output(Decision).invoke(ask)
    except Exception:
        d = model.with_structured_output(Decision).invoke(ask + "\nFill in every field.")
    return {"persona": persona["id"], "steps": steps, "decision": d.model_dump()}


def run_all(personas: list[dict], url: str, world: str, context: str, out_dir: Path, on_step, on_done) -> list[dict]:
    """All personas browse in parallel, each in its own browser."""
    results: list[dict] = []
    lock = threading.Lock()

    def go(p, i):
        time.sleep(i * 2.5)  # stagger arrivals so the site doesn't see seven bots at once
        try:
            r = browse(p, url, world, context, out_dir, on_step)
        except Exception as e:
            r = {"persona": p["id"], "steps": [], "decision": None, "error": f"{type(e).__name__}: {e}"[:200]}
        with lock:
            results.append(r)
        on_done(p["id"], r)

    threads = [threading.Thread(target=go, args=(p, i), daemon=True) for i, p in enumerate(personas)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results
