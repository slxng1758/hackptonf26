"""Infodemic: a waterborne disease and the sayings about it spread through the same population.

- People live in 4 villages, linked by families, a market and travelers.
- The disease is a plain SIR model. People who boil their water are much less likely to catch it.
- Beliefs are real sayings. When a saying passes from one person to another, some roles retell it
  (an LLM rewrites it in that role's voice), creating a new variant with a parent.
- Every new variant is scored once by the hidden evaluator. Its `practice` score is the chance a
  believer boils their water. So which variant wins decides how many people get sick.

CLI:  python -m sim.epidemic --days 60 --scenario baseline
"""
from __future__ import annotations

import argparse
import statistics
import json
import math
import random
from datetime import datetime
from pathlib import Path

from .evaluator import evaluate
from .models import villager_model

OUT = Path(__file__).resolve().parent.parent / "runs" / "epi"
CACHE = OUT / "cache.json"


def _load_cache():
    try:
        return json.loads(CACHE.read_text())
    except Exception:
        return {"retell": {}, "score": {}}


def _save_cache(c):
    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(c))

VILLAGES = [
    {"name": "Hillfold", "water": "spring"},
    {"name": "Millbrook", "water": "well"},
    {"name": "Rivermouth", "water": "river"},
    {"name": "Ashby", "water": "well"},
]

ROLES = {  # (count per village, chance they retell instead of repeating, voice)
    "villager": (12, 0.04, "an ordinary villager repeating what they heard, a little loosely"),
    "child": (3, 0.25, "a child who half-heard it and fills gaps with what sounds right"),
    "priest": (1, 0.35, "a priest who credits the ancestors and the sacred fire and wants the saying to inspire awe"),
    "healer": (1, 0.03, "a healer who cares about what actually keeps people alive and says why plainly"),
}
HUB_ROLES = {"merchant": (4, 0.15, "a market merchant who makes sayings short, catchy and good for business"),
             "traveler": (3, 0.2, "a traveler who mixes in sayings and stories from far away")}

ORIGIN = "Boil water from the well before drinking. Boiling stops the sickness."

RETELL = """You are {voice}, in a pre-modern village. Someone just told you this saying about drinking water:

"{saying}"

Retell it the way you would pass it on to the next person. One saying only, at most 14 words.
Do not explain. Do not add quotes. Your version may drift from what you heard."""


def build_population(rng: random.Random):
    people, edges = [], set()
    centers = [(math.cos(a) * 0.62, math.sin(a) * 0.62) for a in [math.pi * (0.25 + 0.5 * i) for i in range(4)]]
    for vi, v in enumerate(VILLAGES):
        members = []
        for role, (n, _, _) in ROLES.items():
            for _ in range(n):
                ang, r = rng.random() * math.tau, 0.22 * math.sqrt(rng.random())
                cx, cy = centers[vi]
                members.append(len(people))
                people.append({"id": len(people), "village": vi, "role": role, "x": cx + r * math.cos(ang), "y": cy + r * math.sin(ang)})
        for a in members:  # small world inside a village
            for b in rng.sample(members, 4):
                if a != b:
                    edges.add((min(a, b), max(a, b)))
    by_village = [[p["id"] for p in people if p["village"] == vi] for vi in range(4)]
    for role, (n, _, _) in HUB_ROLES.items():
        for _ in range(n):
            pid = len(people)
            ang, r = rng.random() * math.tau, 0.12 * math.sqrt(rng.random())
            people.append({"id": pid, "village": -1, "role": role, "x": r * math.cos(ang), "y": r * math.sin(ang)})
            reach = range(4) if role == "merchant" else rng.sample(range(4), 2)
            for vi in reach:
                for b in rng.sample(by_village[vi], 3):
                    edges.add((min(pid, b), max(pid, b)))
    nbrs = {p["id"]: [] for p in people}
    for a, b in edges:
        nbrs[a].append(b)
        nbrs[b].append(a)
    return people, sorted(edges), nbrs


def _text(content) -> str:
    """Model replies can be a string or a list of blocks (thinking + text). Keep only the spoken text."""
    if isinstance(content, list):
        content = " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    line = str(content).strip().strip('"').split("\n")[0].strip().strip('"')
    return line[:140]


def role_info(role):
    return ROLES.get(role) or HUB_ROLES[role]


SACRED = "Drink only what the sacred fire has blessed, lest the ancestors' wrath take you."


def run(days=60, scenario="baseline", seed=7, max_mutations=22, save=True, verbose=True, llm_budget=None):
    """llm_budget caps fresh model calls per run; past that, retellings come only from the cache."""
    rng = random.Random(seed)
    people, edges, nbrs = build_population(random.Random(7))  # same population every time; only events vary by seed
    model = villager_model()
    cache = _load_cache()
    llm_left = max_mutations if llm_budget is None else llm_budget

    variants = []  # {id, parent, text, born_day, born_at, role, score}

    def add_variant(text, parent, day, pid, role):
        score = cache["score"].get(text)
        if score is None:
            score = evaluate("village", len(variants), {"saying.md": text})
            cache["score"][text] = {k: score[k] for k in ("belief", "practice", "myth", "short")}
        variants.append({"id": len(variants), "parent": parent, "text": text, "day": day, "person": pid, "role": role,
                         "short": score.get("short") or text, "belief": score["belief"], "practice": score["practice"], "myth": score["myth"]})
        if verbose:
            print(f"  variant {len(variants) - 1} (from {parent}, {role}, day {day}): {text} | belief {score['belief']} practice {score['practice']} myth {score['myth']}")
        return len(variants) - 1


    def variant_for(text, parent, day, pid, role):
        for v in variants:
            if v["text"] == text:
                return v["id"]
        return add_variant(text, parent, day, pid, role)

    belief = [None] * len(people)  # variant id per person
    health = ["S"] * len(people)   # S, I, R
    sick_since = [0] * len(people)
    ever_sick = 0

    # the truth starts with Millbrook's healer
    origin_healer = next(p["id"] for p in people if p["village"] == 1 and p["role"] == "healer")
    belief[origin_healer] = add_variant(ORIGIN, None, 0, origin_healer, "healer")
    if scenario == "healers_everywhere":
        for p in people:
            if p["role"] == "healer":
                belief[p["id"]] = 0
    if scenario == "priests_everywhere":
        sacred = add_variant(SACRED, 0, 0, -1, "priest")
        for p in people:
            if p["role"] == "priest":
                belief[p["id"]] = sacred

    contaminated = {2: 4, 1: 22, 3: 34}  # village -> day its water turns bad (river first, then a flood)
    mutations, frames = 0, []

    for day in range(days + 1):
        # 1. talk: each believer may pass their saying to one neighbor
        order = list(range(len(people)))
        rng.shuffle(order)
        for a in order:
            if belief[a] is None or rng.random() > 0.35:
                continue
            b = rng.choice(nbrs[a])
            v = variants[belief[a]]
            catchy = 0.35 + 0.45 * v["myth"] + 0.2 * (1 - min(1, len(v["text"]) / 90))
            if belief[b] is not None and rng.random() > catchy * 0.5:
                continue  # already believes something and wasn't convinced
            role = people[b]["role"]
            _, retell, voice = role_info(role)
            if mutations < max_mutations and rng.random() < retell:
                key = f"{role}|{v['text']}"
                seen = cache["retell"].get(key, [])
                if seen and (llm_left <= 0 or rng.random() < 0.7):
                    text = rng.choice(seen)
                elif llm_left > 0:
                    text = _text(model.invoke(RETELL.format(voice=voice, saying=v["text"])).content)
                    llm_left -= 1
                    if text:
                        cache["retell"].setdefault(key, []).append(text)
                else:
                    text = ""
                if not text:
                    belief[b] = v["id"]  # nothing usable; pass the saying on unchanged
                    continue
                mutations += 1
                belief[b] = variant_for(text, v["id"], day, b, role)
            else:
                belief[b] = v["id"]

        # 2. disease
        new_health = health[:]
        for p in people:
            i = p["id"]
            boils = belief[i] is not None and rng.random() < variants[belief[i]]["practice"]
            if health[i] == "S":
                risk = 0.0
                vi = p["village"]
                if vi >= 0 and vi in contaminated and day >= contaminated[vi]:
                    risk += 0.05
                risk += 0.03 * sum(1 for n in nbrs[i] if health[n] == "I")
                if boils:
                    risk *= 0.12
                if rng.random() < risk:
                    new_health[i] = "I"
                    sick_since[i] = day
                    ever_sick += 1
            elif health[i] == "I" and day - sick_since[i] >= 7:
                new_health[i] = "R"
                # getting sick makes people listen: they adopt the most practical saying among their neighbors
                best = max((belief[n] for n in nbrs[i] if belief[n] is not None), key=lambda v: variants[v]["practice"], default=None)
                if best is not None and rng.random() < 0.6:
                    belief[i] = best
        health = new_health

        frames.append({"day": day, "b": belief[:], "h": "".join(health), "sick_total": ever_sick})

    result = {
        "id": datetime.now().strftime("%m%d-%H%M%S-") + scenario,
        "scenario": scenario,
        "days": days,
        "villages": VILLAGES,
        "contaminated": contaminated,
        "people": people,
        "edges": edges,
        "variants": variants,
        "frames": frames,
        "ever_sick": ever_sick,
        "population": len(people),
        "created": datetime.now().isoformat(),
    }
    _save_cache(cache)
    if not save:
        return result
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{result['id']}.json").write_text(json.dumps(result))
    print(f"done: {ever_sick}/{len(people)} fell sick, {len(variants)} variants -> {result['id']}")
    return result


def sweep(seeds=30, scenarios=("baseline", "healers_everywhere", "priests_everywhere"), llm_budget=0):
    """Run every scenario across many random worlds. One run proves nothing; averages might."""
    out = {"seeds": seeds, "scenarios": {}}
    for sc in scenarios:
        sick = []
        for sd in range(1, seeds + 1):
            r = run(scenario=sc, seed=sd, save=False, verbose=False, llm_budget=llm_budget)
            sick.append(r["ever_sick"])
            print(f"{sc} seed {sd}: {r['ever_sick']}/{r['population']} sick", flush=True)
        out["scenarios"][sc] = {"sick": sick, "mean": statistics.mean(sick), "sd": statistics.stdev(sick) if len(sick) > 1 else 0, "population": r["population"]}
        print(f"== {sc}: mean {out['scenarios'][sc]['mean']:.1f} sd {out['scenarios'][sc]['sd']:.1f}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sweep.json").write_text(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    import sys
    if "--sweep" in sys.argv:
        sweep()
        raise SystemExit
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--scenario", default="baseline", choices=["baseline", "healers_everywhere", "priests_everywhere"])
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    run(a.days, a.scenario, a.seed)
