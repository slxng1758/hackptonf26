"""Word of mouth: after shopping, customers post about it, read each other's posts, and reply, repost or ignore.

Round 0: every customer who decided writes one post in their own voice, about what they actually saw.
Rounds 1..N: each customer reads the feed and picks at most two actions (reply, repost) or stays quiet.
Then: a who-reacted-to-whom network, PageRank for influence (whose posts spread furthest), and a short summary of which
opinion spread and through whom. Output matches b2a/contract.py `Social`.
"""
from __future__ import annotations

import threading
from typing import Literal

from pydantic import BaseModel, Field

from .models import fast

POST = """You are {name}, {age}, {occupation}, a {archetype} customer. {voice}
You just visited {product}. Your verdict: {decision}, {rating}/5. What you'd tell a friend: "{quote}"
Reasons: {reasons}

Write ONE social media post about it, the way you'd really post (max 240 characters, no hashtags spam, at most one).
Be specific about something you saw. Give its sentiment from -1 (very negative) to 1 (very positive)."""

REACT = """You are {name}, {age}, {occupation}, a {archetype} customer. {voice}
You visited {product} yourself: {decision}, {rating}/5, "{quote}"

Here is the feed so far (id · author · text):
{feed}

Real people mostly scroll past. Pick at most TWO actions: reply to a post you have something to add to (agree, push back,
add what you saw), or repost one you think friends should see. Never react to your own posts. If nothing moves you,
return no actions. Replies max 200 characters, in your voice."""

SUMMARY = """Customers of {product} posted about it. Posts (id · author · kind → target · sentiment · text):
{posts}
Influence (PageRank over replies and reposts, higher = spread further): {influence}

In 2-3 plain sentences for the business owner: which opinion spread furthest, through whom, and why it matters
(e.g. which complaint to fix first). Use names, not ids."""


class Post(BaseModel):
    text: str
    sentiment: float = Field(ge=-1, le=1)


class Action(BaseModel):
    kind: Literal["reply", "repost"]
    target: str = Field(description="the id of the post you react to")
    text: str = Field(default="", description="your reply, or a short comment on the repost")
    sentiment: float = Field(ge=-1, le=1)


class Reactions(BaseModel):
    actions: list[Action] = Field(default_factory=list, max_length=2)


def _parallel(fn, items):
    out = [None] * len(items)

    def go(i, it):
        try:
            out[i] = fn(it)
        except Exception:
            out[i] = None

    ts = [threading.Thread(target=go, args=(i, it), daemon=True) for i, it in enumerate(items)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return out


def pagerank(nodes: list[str], edges: list[tuple[str, str, int]], d: float = 0.85, iters: int = 60) -> dict[str, float]:
    """Edge (a, b, w): a replied to or reposted b, so influence flows to b."""
    n = len(nodes)
    if not n:
        return {}
    out_w = {v: 0 for v in nodes}
    for a, _b, w in edges:
        out_w[a] += w
    r = {v: 1 / n for v in nodes}
    for _ in range(iters):
        dangling = sum(r[v] for v in nodes if out_w[v] == 0)
        nxt = {v: (1 - d) / n + d * dangling / n for v in nodes}
        for a, b, w in edges:
            nxt[b] += d * r[a] * w / out_w[a]
        r = nxt
    return r


def run(personas: list[dict], decisions: dict[str, dict], product: str, rounds: int = 2) -> dict | None:
    who = [p for p in personas if p["id"] in decisions]
    if len(who) < 2:
        return None
    model = fast()

    def ctx(p):
        d = decisions[p["id"]]
        from .session import instructions
        return dict(name=p["name"], age=p["age"], occupation=p["occupation"], archetype=p["archetype"], voice=p["voice"] + instructions(p),
                    product=product, decision=d["decision"], rating=d["rating"], quote=d["quote"], reasons="; ".join(d.get("reasons") or []))

    posts: list[dict] = []
    first = _parallel(lambda p: model.with_structured_output(Post).invoke(POST.format(**ctx(p))), who)
    for p, r in zip(who, first):
        if r:
            posts.append({"id": f"s{len(posts) + 1}", "round": 0, "author": p["id"], "kind": "post", "target": None,
                          "text": r.text[:280], "sentiment": max(-1, min(1, r.sentiment))})

    names = {p["id"]: p["name"] for p in personas}
    for rnd in range(1, rounds + 1):
        feed = "\n".join(f"{x['id']} · {names[x['author']]} · {('reposted: ' if x['kind'] == 'repost' else '')}{x['text']}" for x in posts)
        reacts = _parallel(lambda p: model.with_structured_output(Reactions).invoke(REACT.format(**ctx(p), feed=feed)), who)
        by_id = {x["id"]: x for x in posts}
        for p, r in zip(who, reacts):
            for a in (r.actions if r else [])[:2]:
                t = by_id.get(a.target)
                if not t or t["author"] == p["id"]:
                    continue
                posts.append({"id": f"s{len(posts) + 1}", "round": rnd, "author": p["id"], "kind": a.kind, "target": t["id"],
                              "text": (a.text or ("" if a.kind == "repost" else "…"))[:280], "sentiment": max(-1, min(1, a.sentiment))})

    by_id = {x["id"]: x for x in posts}
    weights: dict[tuple[str, str, str], int] = {}
    for x in posts:
        if x["target"]:
            key = (x["author"], by_id[x["target"]]["author"], x["kind"])
            weights[key] = weights.get(key, 0) + 1
    edges = [{"source": a, "target": b, "kind": k, "weight": w} for (a, b, k), w in weights.items()]
    ids = [p["id"] for p in who]
    pr = pagerank(ids, [(e["source"], e["target"], e["weight"]) for e in edges])
    nodes = []
    for p in who:
        mine = [x["sentiment"] for x in posts if x["author"] == p["id"]]
        s = sum(mine) / len(mine) if mine else 0.0
        nodes.append({"id": p["id"], "label": p["name"], "archetype": p["archetype"], "sentiment": round(s, 2),
                      "centrality": round(pr.get(p["id"], 0), 3), "community": 0 if s >= 0 else 1})
    top = [n["id"] for n in sorted(nodes, key=lambda n: -n["centrality"])][:3]

    lines = "\n".join(f"{x['id']} · {names[x['author']]} · {x['kind']}{(' → ' + x['target']) if x['target'] else ''} · {x['sentiment']:+.1f} · {x['text']}" for x in posts)
    infl = ", ".join(f"{names[n['id']]} {n['centrality']:.2f}" for n in sorted(nodes, key=lambda n: -n["centrality"]))
    try:
        summary = model.invoke(SUMMARY.format(product=product, posts=lines, influence=infl)).content
        summary = summary if isinstance(summary, str) else " ".join(b.get("text", "") for b in summary if isinstance(b, dict))
    except Exception:
        summary = ""
    out = {"posts": posts, "nodes": nodes, "edges": edges, "top_influencers": top, "summary": summary.replace("**", "").strip()}
    return enrich(out, who)


def enrich(out: dict, personas: list[dict]) -> dict:
    """Content x connectivity (Arlequin Track 2): b2a/network.py adds real communities (modularity, not sentiment),
    cascades (how far each post's thread spread, across how many communities), themes (which topics crossed between
    communities and which stayed inside one) and a by-model breakdown. Keeps the posts and the summary above; on any
    error returns them unchanged."""
    try:
        from . import network
        n = network.analyze({"social": {"posts": out["posts"]}, "personas": personas}).model_dump()
    except Exception:
        return out
    n["network_summary"] = n["summary"]
    n["summary"] = out["summary"] or n["summary"]
    return n
