"""Compare the customer agents: by model family, by layer (base model vs persona with memory), and where they disagree.
Also groups every agent's suggestions into the owner's to-do list.

    from b2a import compare
    compare.summary(view)            # everything below, as one dict to merge into view["summary"]
    compare.accuracy_chart(evals)    # base -> memory -> evolved, for the headline chart
"""
from __future__ import annotations

from collections import Counter, defaultdict

from pydantic import BaseModel, Field

from .contract import EvalScore
from .evals import _tokens, agents, predicted


def _top(items: list[str], n: int = 1) -> list[str]:
    c = Counter(s.strip() for s in items if s and s.strip())
    return [s for s, _ in c.most_common(n)]


def _complaints(a: dict) -> list[str]:
    d = a["decision"]
    return list(d.get("disliked") or []) + ([d["missing"]] if d.get("missing") and not a["bought"] else [])


# ---------------------------------------------------------------- by model

def by_model(view: dict, layer: int | None = None) -> dict[str, dict]:
    """Per model family: how many agents, buy rate, average rating, and the complaint it raised most."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for a in agents(view, layer):
        groups[a["model"] or "unknown"].append(a)
    out = {}
    for model, ags in sorted(groups.items()):
        p = predicted(ags)
        out[model] = {"agents": len(ags), "bought": sum(a["bought"] for a in ags), "of": len(ags),  # "of": same shape as sim.py's by_model
                       "buy_rate": p["buy_rate"], "rating": p["rating"],
                      "top_complaint": (_top([c for a in ags for c in _complaints(a)]) or [""])[0],
                      "decisions": dict(Counter(a["decision"]["decision"] for a in ags))}
    return out


def layer_delta(view: dict) -> dict[str, dict]:
    """How each model family's verdict moves from Layer 1 (base model, no persona) to Layer 2 (persona + memory)."""
    l1, l2 = by_model(view, 1), by_model(view, 2)
    out = {}
    for m in sorted(set(l1) | set(l2)):
        a, b = l1.get(m), l2.get(m)
        out[m] = {"base": a and {k: a[k] for k in ("buy_rate", "rating", "agents")},
                  "persona": b and {k: b[k] for k in ("buy_rate", "rating", "agents")},
                  "buy_rate_change": round(b["buy_rate"] - a["buy_rate"], 3) if a and b else None,
                  "rating_change": round(b["rating"] - a["rating"], 3) if a and b else None}
    return out


def disagreement(view: dict) -> list[dict]:
    """Where agents that should agree don't.

    Same persona played by several models (ids like "p1-gemini", or a shared "persona_id"): did the models decide differently?
    Otherwise, same archetype across models.
    """
    ags = agents(view, 2) or agents(view)
    groups: dict[str, list[dict]] = defaultdict(list)
    same_persona = any("-" in a["id"] for a in ags)
    for a in ags:
        key = a["id"].split("-")[0] if same_persona else (a["archetype"] or a["id"])
        groups[key].append(a)
    out = []
    for key, g in groups.items():
        if len(g) < 2 or len({a["model"] for a in g}) < 2:
            continue
        verdicts = {a["model"]: ("buy" if a["bought"] else a["decision"]["decision"]) for a in g}
        ratings = [a["decision"]["rating"] for a in g]
        bought = {a["bought"] for a in g}
        if len(bought) > 1 or max(ratings) - min(ratings) >= 2:
            out.append({"group": key, "by": "persona" if same_persona else "archetype", "verdicts": verdicts,
                        "ratings": {a["model"]: a["decision"]["rating"] for a in g}, "spread": max(ratings) - min(ratings)})
    return sorted(out, key=lambda x: -x["spread"])


def by_segment(view: dict) -> list[dict]:
    """Layer 2 by archetype: share of customers, buy rate, rating."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for a in agents(view, 2):
        groups[a["archetype"] or "other"].append(a)
    out = []
    for arch, g in groups.items():
        p = predicted(g)
        out.append({"archetype": arch, "share": round(sum(a["share"] for a in g), 3), "agents": len(g), "buy_rate": p["buy_rate"], "rating": p["rating"]})
    return sorted(out, key=lambda x: -x["share"])


# ---------------------------------------------------------------- suggestions

class _Group(BaseModel):
    change: str = Field(description="the suggested change, merged wording, concrete")
    members: list[int] = Field(description="indexes of the suggestions merged into this group")
    where: str = ""


class _Groups(BaseModel):
    groups: list[_Group]


GROUP_PROMPT = """Customers made these suggestions about a product. Merge the ones that ask for the same change.
Keep each merged change concrete (e.g. "show the price before checkout", not "better pricing"). Every index must be in exactly one group.

{items}"""


def _raw_suggestions(view: dict) -> list[dict]:
    """Every suggestion, with who made it. Falls back to "what would have changed your mind" for older sims."""
    out = []
    for a in agents(view):
        d = a["decision"]
        sug = d.get("suggestions") or []
        if sug:
            for s in sug:
                s = s if isinstance(s, dict) else {"change": str(s)}
                out.append({"change": s.get("change", ""), "why": s.get("why", ""), "where": s.get("where", ""),
                            "would_make_buy": s.get("impact") == "would make me buy" and not a["bought"], "agent": a})
        elif d.get("missing") and not a["bought"]:
            out.append({"change": d["missing"], "why": "", "where": "", "would_make_buy": True, "agent": a})
    return [s for s in out if s["change"].strip()]


def _group_keyword(items: list[dict]) -> list[list[int]]:
    groups: list[list[int]] = []
    toks = [_tokens(s["change"]) for s in items]
    for i, t in enumerate(toks):
        for g in groups:
            rep = toks[g[0]]
            if t and rep and len(t & rep) / min(len(t), len(rep)) >= 0.5:
                g.append(i)
                break
        else:
            groups.append([i])
    return groups


def top_suggestions(view: dict, judge: str = "auto", limit: int = 8) -> list[dict]:
    """The owner's to-do list: similar suggestions merged, ranked by how many non-buyers said it would make them buy."""
    items = _raw_suggestions(view)
    if not items:
        return []
    groups: list[tuple[str, list[int], str]] = []
    if judge in ("auto", "llm") and len(items) > 1:
        try:
            from .models import fast
            g: _Groups = fast().with_structured_output(_Groups).invoke(
                GROUP_PROMPT.format(items="\n".join(f"{i}. {s['change']}" for i, s in enumerate(items))))
            seen: set[int] = set()
            for x in g.groups:
                mem = [i for i in x.members if 0 <= i < len(items) and i not in seen]
                seen.update(mem)
                if mem:
                    groups.append((x.change, mem, x.where))
            groups += [(items[i]["change"], [i], "") for i in range(len(items)) if i not in seen]
        except Exception:
            if judge == "llm":
                raise
            groups = []
    if not groups:
        groups = [(items[g[0]]["change"], g, "") for g in _group_keyword(items)]
    out = []
    for change, mem, where in groups:
        ss = [items[i] for i in mem]
        ags = {s["agent"]["id"]: s["agent"] for s in ss}
        out.append({"change": change,
                    "where": where or (_top([s["where"] for s in ss]) or [""])[0],
                    "why": [s["why"] for s in ss if s["why"]][:3],
                    "agents": list(ags), "names": [a["name"] for a in ags.values()],
                    "models": sorted({a["model"] for a in ags.values() if a["model"]}),
                    "archetypes": sorted({a["archetype"] for a in ags.values() if a["archetype"]}),
                    "count": len(ags), "would_buy_count": len({s["agent"]["id"] for s in ss if s["would_make_buy"]}),
                    "share": round(sum(a["share"] for a in ags.values()), 3)})
    return sorted(out, key=lambda x: (-x["would_buy_count"], -x["count"], -x["share"]))[:limit]


# ---------------------------------------------------------------- accuracy over stages

STAGE_ORDER = {"base": 0, "memory": 1, "evolved": 2, "all": 3}


def accuracy_chart(evals: list[dict | EvalScore]) -> list[dict]:
    """Points for the headline chart: base models → + memory → + evolved memory (one point per evolve loop)."""
    rows = [e if isinstance(e, dict) else e.model_dump() for e in evals]
    rows = sorted(rows, key=lambda e: (STAGE_ORDER.get(e.get("stage", "all"), 3), e.get("iteration", 0)))
    out = []
    for e in rows:
        st = e.get("stage", "all")
        label = {"base": "base models", "memory": "+ memory", "evolved": f"+ evolved (loop {e.get('iteration', 0)})"}.get(st, f"run {e.get('iteration', 0)}")
        out.append({"label": label, "stage": st, "iteration": e.get("iteration", 0), "case_id": e.get("case_id", ""),
                    "rating_error": e["rating_error"], "theme_recall": e["theme_recall"], "theme_precision": e.get("theme_precision"),
                    "distribution_distance": e.get("distribution_distance")})
    return out


# ---------------------------------------------------------------- all together

def summary(view: dict, judge: str = "auto") -> dict:
    """Merge into view["summary"]."""
    has_l1 = any(a["layer"] == 1 for a in agents(view))
    return {"by_model": by_model(view, 2 if has_l1 else None),
            "by_segment": by_segment(view),
            "layer_delta": layer_delta(view) if has_l1 else {},
            "disagreement": disagreement(view),
            "top_suggestions": top_suggestions(view, judge)}
