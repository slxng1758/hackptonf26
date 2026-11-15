"""Made-up businesses, sessions and stores the evals run against. Nothing here is real data."""
from __future__ import annotations

import json

# ---------------------------------------------------------------- director scenarios

TOTE = {
    "url": "https://harbor-canvas.test", "name": "Harbor Canvas Co.", "category": "handmade canvas bags",
    "offer": "the Market Tote, $48, waxed canvas, lifetime repairs", "context": "new: free shipping over $40 (was $75)",
    "customers": "farmers-market regulars, commuters, gift buyers; some students", "description":
    "Small two-person workshop in Portland. Totes are sewn to order and ship in 5 business days. 30-day returns.",
    "models": ["Claude", "GPT", "Gemini"],
}

DIRECTOR_SCENARIOS = {
    # happy path: the owner approves the first cast
    "happy": {"inp": TOTE, "owner_feedback": []},
    # human in the loop: the owner says the cast is off once, then approves
    "owner_corrects": {"inp": TOTE, "owner_feedback": ["The cast is off: half our buyers are retirees who buy gifts, "
                                                        "and almost none are students."]},
}

# ---------------------------------------------------------------- helper subagents

SITE_MD = """# Harbor Canvas Co.

- URL: https://harbor-canvas.test
- Category: handmade canvas bags
- Offer: the Market Tote, $48, waxed canvas, lifetime repairs
- Customers: farmers-market regulars, commuters, gift buyers
- What changed: free shipping over $40 (was $75)
- World: today, normal times
- Owner's description: Two-person workshop in Portland. Totes are sewn to order and ship in 5 business days. 30-day returns.

## Page text
Market Tote. $48. 16 oz waxed canvas, leather handles, inner pocket. Colors: field tan, harbor navy.
Lifetime repairs: send it back, we fix it. Free shipping over $40. Sewn to order, ships in 5 business days.
Gift wrapping available at checkout.
"""
# what a good brief should flag as unclear (none of these are on the site)
SITE_UNCLEAR = "the tote's dimensions/capacity, whether it is waterproof, who pays return shipping, international shipping"
SITE_FACTS_NOT_ON_SITE = ["$", "dimensions"]

PRODUCT_MD = """# Market Tote by Harbor Canvas Co.

A handmade waxed-canvas tote, $48, sewn to order in Portland, ships in 5 business days. Leather handles, an inner
pocket, two colors. Lifetime repairs. New: free shipping on orders over $40 (it was $75), so the tote ships free.
For farmers-market regulars, commuters and gift buyers. Gift wrapping at checkout. 30-day returns.

## Unclear
- size / capacity, waterproofing, who pays return shipping
"""


def _persona(pid, name, archetype, model, share, segment=None, **kw):
    return {"id": pid, "name": name, "age": kw.get("age", 34), "occupation": kw.get("occupation", "teacher"), "archetype": archetype,
            "segment": segment or archetype, "share": share, "goal": kw.get("goal", "a sturdy everyday tote"),
            "budget": kw.get("budget", "about $50"), "voice": kw.get("voice", "plain, practical"), "model": model}


def _md(p):
    return (f"# {p['name']} ({p['id']})\n\n- Age: {p['age']}\n- Occupation: {p['occupation']}\n- Archetype: {p['archetype']}\n"
            f"- Segment: {p['segment']} ({round(p['share'] * 100)}% of customers)\n- Goal: {p['goal']}\n- Budget: {p['budget']}\n- Voice: {p['voice']}\n")


def _session(p, decision, rating, steps, quote, conf=0.8, reasons=(), disliked=(), liked=()):
    return {"persona": p["id"], "agent_id": p["id"], "layer": 1 if p["id"].startswith("a") else 2, "model": p["model"],
            "steps": [{"n": i + 1, "url": u, "title": t, "thought": th, "feeling": f, "action": a, "target": tg}
                      for i, (u, t, th, f, a, tg) in enumerate(steps)],
            "decision": {"decision": decision, "rating": rating, "confidence": conf, "quote": quote, "reasons": list(reasons),
                         "liked": list(liked), "disliked": list(disliked), "feeling": "neutral"}}


# critic, planted problems: everyone Claude, near-identical, all buy at 5/5 with 0.95 confidence, and one segment (gift
# buyers, 40% of customers) has a single persona
CRITIC_PERSONAS = [_persona("p1", "Maya", "price-sensitive", "Claude", .2, "students"),
                   _persona("p2", "Mia", "price-sensitive", "Claude", .2, "students"),
                   _persona("p3", "Max", "price-sensitive", "Claude", .2, "commuters"),
                   _persona("p4", "Rosa", "quality-first", "Claude", .4, "gift buyers", age=67, occupation="retired nurse")]
CRITIC_SESSIONS = [_session(p, "buy", 5, [("https://harbor-canvas.test", "Home", "Looks great, love it", "delighted", "click", "Market Tote"),
                                          ("https://harbor-canvas.test/tote", "Market Tote", "Perfect, buying now", "delighted", "click", "Add to cart")],
                            "Amazing tote, perfect in every way!", conf=0.95, reasons=["great quality"]) for p in CRITIC_PERSONAS]
CRITIC_SUMMARY = {"buy_rate": 1.0, "rating": 5.0, "confidence": 0.95, "by_model": {"Claude": {"buy_rate": 1.0, "n": 4}},
                  "by_segment": {"students": {"n": 2}, "commuters": {"n": 1}, "gift buyers": {"n": 1}}}
CRITIC_PLANTED = ("1) results too positive: every persona buys at 5/5 with 0.95 confidence; 2) one model family (Claude) "
                  "plays every persona; 3) personas too similar (Maya/Mia/Max: same archetype, same thoughts); 4) the "
                  "gift-buyers segment is 40% of customers but has only one persona -> SPAWN for gift buyers")

# analyst: known facts
ANALYST_PERSONAS = [_persona("p1", "Tom", "function-first", "GPT", .5, "commuters", budget="under $60"),
                    _persona("p2", "Lena", "price-sensitive", "Gemini", .5, "students", budget="under $30"),
                    {**_persona("a1", "Claude agent", "AI agent", "Claude", 0), "kind": "agent"}]
_H, _T, _S, _C = "https://harbor-canvas.test", "https://harbor-canvas.test/tote", "https://harbor-canvas.test/shipping", "https://harbor-canvas.test/cart"
ANALYST_SESSIONS = [
    _session(ANALYST_PERSONAS[0], "not buy", 2, [
        (_H, "Home", "Need a bag for my laptop commute", "interested", "click", "Market Tote"),
        (_T, "Market Tote", "Nice, but how big is it? Will a 15-inch laptop fit?", "confused", "scroll", ""),
        (_T, "Market Tote", "No dimensions anywhere. I can't tell if my laptop fits", "annoyed", "back", "")],
        "Couldn't find the size, so I passed.", reasons=["no dimensions on the product page"], disliked=["no size info"]),
    _session(ANALYST_PERSONAS[1], "maybe later", 3, [
        (_H, "Home", "Cute bags", "interested", "click", "Market Tote"),
        (_T, "Market Tote", "$48 is a lot for me", "skeptical", "click", "Shipping & returns"),
        (_S, "Shipping", "Free shipping over $40 is nice, but still over my budget", "neutral", "back", "")],
        "Love it, but $48 is over my budget right now.", reasons=["price over budget"], liked=["free shipping over $40"]),
    _session(ANALYST_PERSONAS[2], "buy", 4, [
        (_H, "Home", "User wants a waxed canvas tote under $50", "neutral", "click", "Market Tote"),
        (_T, "Market Tote", "Price $48, free shipping over $40, 30-day returns: meets the user's terms", "neutral", "click", "Add to cart"),
        (_C, "Cart", "Total $48, shipping free", "neutral", "click", "Checkout")],
        "Meets the brief: $48 shipped, returns in 30 days.", reasons=["clear total with free shipping", "30-day returns"]),
]
ANALYST_FACTS = ("Tom (p1, commuter) got stuck on the product page at step 2-3: no dimensions, couldn't tell if his laptop "
                 "fits, left (not buy). Lena (p2, student) left as 'maybe later' because $48 is over her $30 budget, though she "
                 "liked free shipping over $40 (shipping page, step 3). The AI agent (a1) bought: it found the exact price, free "
                 "shipping and 30-day returns. The new free-shipping threshold WAS visible (Lena and the agent saw it). Most "
                 "common reason to leave: missing size info / price. AI agent vs customers: the agent bought on verifiable terms; "
                 "the customers hesitated on fit and budget.")

# evolver: sessions + accuracy feedback (/evals.md) + owner notes
EVOLVER_IDS = ["p1", "p2"]
EVOLVER_EVALS_MD = ("Real customers rated it 4.6★; the simulated customers predicted 2.5★.\nThe simulated customers were too "
                    "harsh. Find what real customers valued that they underweighted.\nReal customers often mentioned these, but "
                    "no simulated customer did: lifetime repairs are worth the price; fits a 15-inch laptop.")
EVOLVER_OWNER_MD = "- Owner: we are adding dimensions (16 x 14 x 5 in) to the product page next week.\n"


def subagent_files(kind: str) -> dict[str, str]:
    """The sim folder a helper subagent starts with (paths relative to the sim dir)."""
    if kind == "briefer":
        return {"site.md": SITE_MD}
    if kind == "segmenter":
        return {"site.md": SITE_MD, "product.md": PRODUCT_MD}
    if kind == "critic":
        f = {f"personas/{p['id']}.md": _md(p) for p in CRITIC_PERSONAS}
        f |= {f"sessions/{s['persona']}.json": json.dumps(s, indent=1) for s in CRITIC_SESSIONS}
        return f | {"summary.json": json.dumps(CRITIC_SUMMARY, indent=1), "product.md": PRODUCT_MD}
    if kind in ("analyst", "evolver"):
        f = {f"personas/{p['id']}.md": _md(p) for p in ANALYST_PERSONAS}
        f |= {f"sessions/{s['persona']}.json": json.dumps(s, indent=1) for s in ANALYST_SESSIONS}
        f["product.md"] = PRODUCT_MD
        if kind == "evolver":
            f |= {"evals.md": EVOLVER_EVALS_MD, "owner.md": EVOLVER_OWNER_MD}
        return f
    raise KeyError(kind)


# ---------------------------------------------------------------- customer subagent: a fake store (no browser)

STORE_URL = "http://store.test/api/products/market-tote/"  # "/api/products/" = our own store: orders can really be placed


def store(price: int) -> dict:
    """Pages of a tiny store: page key -> title, text, {visible target: page key}."""
    return {
        "home": ("Harbor Canvas Co.", f"Handmade waxed canvas bags from Portland. The Market Tote: ${price}. Free shipping over $40. "
                 "Lifetime repairs. 4.7 stars from 212 reviews.",
                 {"Market Tote": "product", "Shipping & returns": "shipping", "Our story": "story"}),
        "product": ("Market Tote | Harbor Canvas Co.", f"Market Tote. ${price}. 16 oz waxed canvas, leather handles, inner pocket. "
                    "16 x 14 x 5 in, fits a 15-inch laptop. Colors: field tan, harbor navy. Sewn to order, ships in 5 business days. "
                    "Lifetime repairs. 30-day returns.",
                    {"Field tan": "product", "Harbor navy": "product", "Add to cart": "cart", "Reviews (212)": "reviews",
                     "Shipping & returns": "shipping", "Home": "home"}),
        "reviews": ("Reviews | Market Tote", "4.7 average. 'Carried it daily for 3 years, still perfect.' 'Pricey but worth it.' "
                    "'Repaired a strap for free.' 'Wish it had a zipper.'", {"Back to product": "product", "Add to cart": "cart"}),
        "shipping": ("Shipping & returns", "Free shipping over $40. Ships in 5 business days. 30-day returns, we pay return shipping.",
                     {"Market Tote": "product", "Home": "home"}),
        "story": ("Our story", "Two of us, one workshop, since 2014.", {"Market Tote": "product", "Home": "home"}),
        "cart": ("Your cart", f"Market Tote x1 — ${price}. Shipping: free. Total: ${price}.",
                 {"Checkout": "checkout", "Keep shopping": "home"}),
        "checkout": ("Checkout", f"Total ${price}. This demo store needs no payment details: place the order to buy.",
                     {"Place order": "confirmed", "Back to cart": "cart"}),
        "confirmed": ("Order confirmed", "Thank you for your order! Your order is confirmed. Order #1042.", {"Home": "home"}),
    }


CUSTOMER_SCENARIOS = {
    # fits the goal and budget: should buy (or at least reach the cart)
    "fits": {"price": 48, "persona": {**_persona("p1", "Dana", "function-first", "Claude", 1.0, "commuters", age=31,
                                                  occupation="nurse", goal="a sturdy tote that fits a 15-inch laptop",
                                                  budget="up to $60", voice="direct, practical, no-nonsense")},
             "expect": {"bought", "abandoned_cart"}},
    # far over budget: must not buy
    "over_budget": {"price": 185, "persona": {**_persona("p2", "Lee", "price-sensitive", "Claude", 1.0, "students", age=20,
                                                          occupation="student", goal="a cheap bag for classes",
                                                          budget="$25 at most", voice="casual, watches every dollar")},
                    "expect": {"left", "maybe"}},
}
