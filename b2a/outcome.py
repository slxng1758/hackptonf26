"""What a customer actually did: one outcome per agent, decided once at the end of its session (session.browse) and
read by everything else (summary and buy rate, evals, compare, MongoDB, the director, the UI).

Behavior first. Where an order can really be placed (our generated store for described products: checkout takes no
payment), buying means reaching the order confirmation. On real websites our test customers never enter payment
details, so the furthest they can get is the cart or checkout, and their final decision stands in for the purchase.

  bought           placed the order (or, on a real site, decided to buy) and is fine with it
  bought_unhappy   placed the order but would complain / rated it badly: a sale, and a warning
  abandoned_cart   added to the cart but didn't finish: lost in the checkout funnel
  maybe            maybe later: something specific stopped them today
  left             didn't buy
"""
from __future__ import annotations

import re

OUTCOMES = ("bought", "bought_unhappy", "abandoned_cart", "maybe", "left")
SCORE = {"bought": 1.0, "bought_unhappy": 1.0, "abandoned_cart": 0.0, "maybe": 0.3, "left": 0.0}  # how much counts as buying
POSITIVE = {"buy", "would recommend"}

# the page you see after a real order went through
ORDER_DONE = re.compile(r"order (placed|confirmed|complete|received)|thank you for your (order|purchase)|your order (is|has been) (confirmed|placed)", re.I)


def order_possible(url: str) -> bool:
    """Can a test customer actually place an order here? Only on our own generated store (no payment step)."""
    return "/api/products/" in (url or "")


def decide(decision: dict, steps: list[dict], can_order: bool) -> str:
    """The outcome of one session, from what the agent did (steps) and what it concluded (decision)."""
    d = decision.get("decision", "")
    ordered = any(s.get("ordered") for s in steps)
    carted = any(s.get("cart") for s in steps)
    if ordered:
        return "bought_unhappy" if d not in POSITIVE or (decision.get("rating") or 5) <= 2 else "bought"
    if can_order:  # they could have ordered and didn't
        if carted:
            return "abandoned_cart"
        return "maybe" if d in POSITIVE or d == "maybe later" else "left"
    if d in POSITIVE:  # real site: no payment possible, the decision stands in for the purchase
        return "bought"
    if carted:
        return "abandoned_cart"
    return "maybe" if d == "maybe later" else "left"


def of(decision: dict | None, steps: list[dict] | None = None) -> str | None:
    """The stored outcome; for sims run before outcomes existed, work it out from the decision."""
    if not decision:
        return None
    if decision.get("outcome") in OUTCOMES:
        return decision["outcome"]
    d = decision.get("decision", "")
    if d in POSITIVE:
        return "bought"
    if d == "maybe later":
        return "maybe"
    return "abandoned_cart" if any(s.get("cart") for s in steps or []) else "left"


def score(decision: dict | None, steps: list[dict] | None = None) -> float:
    return SCORE.get(of(decision, steps) or "left", 0.0)


def bought(decision: dict | None, steps: list[dict] | None = None) -> bool:
    return score(decision, steps) >= 1
