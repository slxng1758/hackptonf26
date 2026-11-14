"""Were the customer agents right? Score a simulation against what real people did.

A "case" is the truth for one product, in data/<case_id>/:
    case.json             name, kind ("backtest" | "business"), product_url / wayback_url, context, world,
                          optional previous_rating (for direction-of-change) and actual_buy_rate
    reviews_train.json    real reviews the evolver may learn from        [{rating: 1-5, text, date?, source?}]
    reviews_holdout.json  real reviews used only for scoring (agents never see these)
    themes.json           top themes of the holdout reviews (made once by `themes`, then fixed so scores are comparable)

For the business we visit (Peri track), the holdout is the answers from the in-person customer poll, in the same format.

    python -m b2a.evals make-case mask_covid reviews.csv --name "Cloth mask" --wayback https://web.archive.org/...
    python -m b2a.evals themes mask_covid
    python -m b2a.evals score <sim_id> mask_covid

Scoring works without API keys (keyword matching), but the LLM judge is the real one: it understands that
"my ears hurt by hour three" and "ear loops are painful" are the same theme.
"""
from __future__ import annotations

import csv
import json
import random
import re
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .contract import EvalScore, Theme

try:  # traces show up in LangSmith when LANGSMITH_TRACING=true and LANGSMITH_API_KEY are set
    from langsmith import traceable
except Exception:  # pragma: no cover
    def traceable(*a, **k):
        return (lambda f: f) if not (a and callable(a[0])) else a[0]

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SIMS = ROOT / "runs" / "sims"

# Same mapping as b2a/sim.py (BUYS): how much each decision counts as buying.
BUYS = {"buy": 1.0, "would recommend": 1.0, "maybe later": 0.3, "not buy": 0.0, "would complain": 0.0}


# ---------------------------------------------------------------- cases

class Case(BaseModel):
    id: str
    name: str
    kind: Literal["backtest", "business"] = "backtest"
    product_url: str = ""
    wayback_url: str = ""
    context: str = ""
    world: str = ""
    previous_rating: float | None = Field(default=None, description="real rating of the previous version, for direction-of-change")
    actual_buy_rate: float | None = None
    source: str = Field(default="", description="where the reviews came from")
    split: str = Field(default="", description="'date' (older = train, newer = holdout) or 'random'")
    notes: str = ""
    train: list[dict] = Field(default_factory=list, exclude=True)
    holdout: list[dict] = Field(default_factory=list, exclude=True)
    themes: list[Theme] = Field(default_factory=list, exclude=True)

    @property
    def actual_rating(self) -> float:
        return round(sum(r["rating"] for r in self.holdout) / len(self.holdout), 3)

    @property
    def distribution(self) -> list[float]:
        return _hist([r["rating"] for r in self.holdout])


def load_case(case_id: str, root: Path = DATA) -> Case:
    d = root / Path(case_id).name
    if not (d / "case.json").exists():
        raise FileNotFoundError(f"no case at {d}/case.json")
    c = Case(**json.loads((d / "case.json").read_text()))
    c.train = _load_reviews(d / "reviews_train.json")
    c.holdout = _load_reviews(d / "reviews_holdout.json")
    if not c.holdout:
        raise ValueError(f"{d}/reviews_holdout.json is empty: nothing to score against")
    if (d / "themes.json").exists():
        c.themes = [Theme(**t) for t in json.loads((d / "themes.json").read_text())]
    return c


def _load_reviews(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for r in json.loads(p.read_text()):
        rating = int(round(float(r["rating"])))
        if 1 <= rating <= 5 and str(r.get("text", "")).strip():
            out.append({**r, "rating": rating, "text": str(r["text"]).strip()})
    return out


def read_reviews_file(path: str | Path) -> list[dict]:
    """CSV (columns: rating, text, optional date/source/title) or JSON list of the same."""
    p = Path(path)
    if p.suffix.lower() == ".json":
        rows = json.loads(p.read_text())
    else:
        with p.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        r = {k.strip().lower(): v for k, v in r.items() if k}
        text = " ".join(x for x in (r.get("title", ""), r.get("text") or r.get("review") or r.get("body") or "") if x).strip()
        rating = r.get("rating") or r.get("stars") or r.get("score")
        if text and rating not in (None, ""):
            out.append({"rating": float(rating), "text": text, **{k: r[k] for k in ("date", "source") if r.get(k)}})
    return out


def make_case(case_id: str, reviews: list[dict], name: str, holdout: float = 0.5, seed: int = 7, root: Path = DATA,
              split: Literal["auto", "date", "random"] = "auto", **meta) -> Path:
    """Split real reviews into train (evolver may learn from it) and holdout (only for scoring). Deterministic.

    By date when every review has one (older = train, newer = holdout: the agents learn from the past and are
    scored on the future, like a real forecast). Otherwise random.
    """
    d = root / Path(case_id).name
    d.mkdir(parents=True, exist_ok=True)
    rows = list(reviews)
    by_date = split == "date" or (split == "auto" and rows and all(r.get("date") not in (None, "") for r in rows))
    k = max(1, int(len(rows) * holdout))
    if by_date:
        rows.sort(key=lambda r: (str(r["date"]), r.get("text", "")))
        hold, train = rows[len(rows) - k:], rows[: len(rows) - k]
    else:
        random.Random(seed).shuffle(rows)
        hold, train = rows[:k], rows[k:]
    meta["split"] = "date" if by_date else "random"
    (d / "reviews_holdout.json").write_text(json.dumps(hold, indent=2))
    (d / "reviews_train.json").write_text(json.dumps(train, indent=2))
    case = {"id": d.name, "name": name, **{k: v for k, v in meta.items() if v not in (None, "")}}
    (d / "case.json").write_text(json.dumps(case, indent=2))
    return d


# ---------------------------------------------------------------- the agents' side

def agents(view: dict, layer: int | None = None) -> list[dict]:
    """Every agent that decided, flattened: id, name, archetype, model, layer, share, decision, bought.

    Layer 2 agents are the personas. Layer 1 (base model, no persona) agents are personas with "layer": 1.
    """
    decisions = view.get("decisions") or {}
    clicked = set((view.get("summary") or {}).get("clicked_buy") or [])
    out = []
    for p in view.get("personas") or []:
        d = decisions.get(p["id"])
        if not d:
            continue
        lay = int(p.get("layer") or 2)
        if layer is not None and lay != layer:
            continue
        bought = p["id"] in clicked or BUYS.get(d.get("decision", ""), 0) >= 1
        out.append({"id": p["id"], "name": p.get("name", p["id"]), "archetype": p.get("archetype", ""), "model": p.get("model", ""),
                    "layer": lay, "share": float(p.get("share") or 0), "memory_version": int(p.get("memory_version") or 0),
                    "decision": d, "bought": bought,
                    "buy_score": 1.0 if p["id"] in clicked else BUYS.get(d.get("decision", ""), 0.0)})
    return out


def _weights(ags: list[dict]) -> list[float]:
    ws = [a["share"] for a in ags]
    return ws if sum(ws) > 0 else [1.0] * len(ags)  # base-model agents have no share: weigh equally


def predicted(ags: list[dict]) -> dict:
    ws = _weights(ags)
    t = sum(ws)
    rating = sum(w * a["decision"]["rating"] for w, a in zip(ws, ags)) / t
    buy = sum(w * a["buy_score"] for w, a in zip(ws, ags)) / t
    return {"rating": round(rating, 3), "buy_rate": round(buy, 3), "distribution": _hist([a["decision"]["rating"] for a in ags], ws)}


def statements(a: dict) -> list[str]:
    """Everything an agent said about the product that could match a real review theme."""
    d = a["decision"]
    out = list(d.get("reasons") or []) + list(d.get("liked") or []) + list(d.get("disliked") or [])
    for s in d.get("suggestions") or []:
        out.append(s.get("change", "") if isinstance(s, dict) else str(s))
    out += [d.get("missing", ""), d.get("quote", ""), d.get("review", ""), d.get("first_impression", "")]
    return [s.strip() for s in out if s and s.strip()]


# ---------------------------------------------------------------- numbers

def _hist(ratings: list[int], weights: list[float] | None = None) -> list[float]:
    weights = weights or [1.0] * len(ratings)
    h = [0.0] * 5
    for r, w in zip(ratings, weights):
        h[min(5, max(1, int(r))) - 1] += w
    t = sum(h) or 1
    return [round(x / t, 4) for x in h]


def distribution_distance(p: list[float], q: list[float]) -> float:
    """Earth mover's distance between two 1-5 star distributions, scaled to 0..1 (0 = identical, 1 = all 1★ vs all 5★)."""
    cp = cq = dist = 0.0
    for a, b in zip(p, q):
        cp, cq = cp + a, cq + b
        dist += abs(cp - cq)
    return round(dist / 4, 4)


# ---------------------------------------------------------------- themes

THEMES_PROMPT = """These are real customer reviews of "{name}". List the {k} most important themes: concrete things many
reviewers liked or complained about (e.g. "ear loops hurt after a few hours", not "comfort"). Count roughly how many
reviews mention each. Use short phrases a shop owner would understand.

Reviews:
{reviews}"""


class _Themes(BaseModel):
    themes: list[Theme] = Field(min_length=3, max_length=12)


def extract_themes(case: Case, k: int = 8, save: bool = True, root: Path = DATA) -> list[Theme]:
    """Top themes of the holdout reviews, by LLM. Saved to themes.json so every later score uses the same yardstick."""
    from .models import fast
    reviews = "\n".join(f"- ({r['rating']}★) {r['text'][:400]}" for r in case.holdout[:150])
    t: _Themes = fast().with_structured_output(_Themes).invoke(THEMES_PROMPT.format(name=case.name, k=k, reviews=reviews))
    themes = sorted(t.themes, key=lambda x: -x.mentions)
    if save:
        (root / case.id / "themes.json").write_text(json.dumps([x.model_dump() for x in themes], indent=2))
    case.themes = themes
    return themes


JUDGE_PROMPT = """You check whether simulated customers raised the same points as real customers.

Real themes (from real reviews):
{themes}

What the simulated customers said (agent id in brackets):
{said}

For each real theme: did at least one simulated customer clearly raise it (same point, any wording)? Which agents?
Then list points the simulated customers made that NO real theme covers (things real reviewers never mentioned).
Be strict: a vague mention of "comfort" does not match "ear loops hurt after a few hours"."""


class _Hit(BaseModel):
    theme: str = Field(description="the real theme, copied exactly")
    raised: bool
    by: list[str] = Field(default_factory=list, description="agent ids that raised it")


class _Invented(BaseModel):
    point: str
    by: list[str] = Field(default_factory=list)


class _Judgement(BaseModel):
    hits: list[_Hit]
    invented: list[_Invented] = Field(default_factory=list)


STOP = set("a an the and or but if of to in on at for with without is are was were be been it its this that these those i my me you your "
           "we our they them their he she his her not no too very so just really after before about from as by than then there here "
           "can could would should will do does did have has had get got one ones".split())


def _tokens(s: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z0-9$]+", s.lower()):
        if w in STOP or len(w) < 3:
            continue
        for suf in ("ing", "ed", "es", "s"):
            if w.endswith(suf) and len(w) - len(suf) >= 3:
                w = w[: -len(suf)]
                break
        out.add(w)
    return out


def _keyword_match(theme: str, text: str) -> bool:
    t, x = _tokens(theme), _tokens(text)
    if not t:
        return False
    hit = len(t & x)
    return hit >= 2 or (len(t) <= 2 and hit >= 1)


def judge_themes(themes: list[Theme], ags: list[dict], judge: str = "auto") -> tuple[list[str], list[str], list[str], str]:
    """Returns (matched real themes, missed real themes, invented agent points, judge used)."""
    said = {a["id"]: statements(a) for a in ags}
    if judge in ("auto", "llm"):
        try:
            from .models import fast
            text = "\n".join(f"[{aid}] {s}" for aid, ss in said.items() for s in ss)
            j: _Judgement = fast().with_structured_output(_Judgement).invoke(
                JUDGE_PROMPT.format(themes="\n".join(f"- {t.theme}" for t in themes), said=text))
            raised = {h.theme.strip().lower() for h in j.hits if h.raised}
            matched = [t.theme for t in themes if t.theme.strip().lower() in raised]
            missed = [t.theme for t in themes if t.theme not in matched]
            return matched, missed, [i.point for i in j.invented], "llm"
        except Exception:
            if judge == "llm":
                raise
    # keyword fallback: offline, cruder
    alltext = [s for ss in said.values() for s in ss]
    matched = [t.theme for t in themes if any(_keyword_match(t.theme, s) for s in alltext)]
    missed = [t.theme for t in themes if t.theme not in matched]
    points = [s for a in ags for s in (list(a["decision"].get("reasons") or []) + list(a["decision"].get("disliked") or []) + list(a["decision"].get("liked") or []))]
    invented = [s for s in points if not any(_keyword_match(t.theme, s) for t in themes)]
    return matched, missed, invented, "keyword"


# ---------------------------------------------------------------- score

def _stage(layer: int | None, iteration: int) -> str:
    if layer == 1:
        return "base"
    if layer == 2:
        return "evolved" if iteration > 0 else "memory"
    return "all"


@traceable(name="score_simulation")
def score(view: dict, case: Case, layer: int | None = None, iteration: int | None = None, judge: str = "auto") -> EvalScore:
    """Score one simulation (or one layer of it) against the case's held-out truth."""
    ags = agents(view, layer)
    if not ags:
        raise ValueError(f"no agents with decisions{f' in layer {layer}' if layer else ''} to score")
    if not case.themes:
        if judge == "keyword":
            raise ValueError(f"case {case.id} has no themes.json; run `python -m b2a.evals themes {case.id}` once (needs an API key)")
        extract_themes(case)
    it = int(view.get("round") or 0) if iteration is None else iteration
    pred = predicted(ags)
    matched, missed, invented, used = judge_themes(case.themes, ags, judge)
    n_real = len(case.themes) or 1
    recall = len(matched) / n_real
    precision = len(matched) / (len(matched) + len(invented)) if (matched or invented) else 0.0
    direction = None
    if case.previous_rating is not None:
        real_up = case.actual_rating - case.previous_rating
        pred_up = pred["rating"] - case.previous_rating
        direction = (real_up >= 0) == (pred_up >= 0)
    err = abs(pred["rating"] - case.actual_rating)
    notes = []
    if pred["rating"] < case.actual_rating - 0.3:
        notes.append(f"agents are harsher than real customers by {err:.1f}★")
    elif pred["rating"] > case.actual_rating + 0.3:
        notes.append(f"agents are kinder than real customers by {err:.1f}★")
    if missed:
        notes.append("missed: " + "; ".join(missed[:3]))
    return EvalScore(
        iteration=it, case_id=case.id, layer=layer, stage=_stage(layer, it), agents=len(ags),
        actual_rating=case.actual_rating, predicted_rating=pred["rating"], rating_error=round(err, 3),
        actual_buy_rate=case.actual_buy_rate, predicted_buy_rate=pred["buy_rate"], direction_correct=direction,
        theme_recall=round(recall, 3), theme_precision=round(precision, 3),
        distribution_distance=distribution_distance(pred["distribution"], case.distribution),
        real_themes=case.themes, matched_themes=matched, missed_themes=missed, invented_themes=invented[:10],
        judge=used, notes=". ".join(notes))


def score_layers(view: dict, case: Case, judge: str = "auto") -> list[EvalScore]:
    """One score per layer present (base models, personas), plus nothing else. Use for the base → memory → evolved chart."""
    layers = sorted({a["layer"] for a in agents(view)})
    return [score(view, case, layer=l, judge=judge) for l in layers]


def feedback_for_evolver(s: EvalScore) -> str:
    """Plain-language error report the director passes to the evolver: what the agents got wrong vs real people."""
    lines = [f"Real customers rated it {s.actual_rating:.1f}★; the simulated customers predicted {s.predicted_rating:.1f}★."]
    if s.predicted_rating < s.actual_rating - 0.3:
        lines.append("The simulated customers were too harsh. Find what real customers valued that they underweighted.")
    elif s.predicted_rating > s.actual_rating + 0.3:
        lines.append("The simulated customers were too kind. Find what real customers disliked that they overlooked.")
    if s.missed_themes:
        lines.append("Real customers often mentioned these, but no simulated customer did: " + "; ".join(s.missed_themes) + ".")
    if s.invented_themes:
        lines.append("Simulated customers raised these, but real customers rarely did: " + "; ".join(s.invented_themes[:5]) + ".")
    return "\n".join(lines)


def improvement(prev: EvalScore | None, cur: EvalScore) -> dict:
    """How much better this loop is than the last one. The director stops looping when both gains are < 0.1."""
    if prev is None:
        return {"rating_error": None, "theme_recall": None, "keep_going": True}
    de = round(prev.rating_error - cur.rating_error, 3)
    dr = round(cur.theme_recall - prev.theme_recall, 3)
    return {"rating_error": de, "theme_recall": dr, "keep_going": de >= 0.1 or dr >= 0.1}


# ---------------------------------------------------------------- CLI

def _load_view(sim_id: str) -> dict:
    p = SIMS / Path(sim_id).name / "sim.json"
    if not p.exists():
        p = Path(sim_id)
    return json.loads(p.read_text())


def main(argv: list[str]) -> None:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m b2a.evals")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make-case", help="split a reviews CSV/JSON into a case")
    m.add_argument("case_id"); m.add_argument("reviews"); m.add_argument("--name", required=True)
    m.add_argument("--kind", default="backtest", choices=["backtest", "business"])
    m.add_argument("--url", default=""); m.add_argument("--wayback", default=""); m.add_argument("--context", default="")
    m.add_argument("--world", default=""); m.add_argument("--previous-rating", type=float); m.add_argument("--buy-rate", type=float)
    m.add_argument("--source", default=""); m.add_argument("--holdout", type=float, default=0.5)
    t = sub.add_parser("themes", help="extract and freeze the holdout themes (needs an API key)")
    t.add_argument("case_id")
    s = sub.add_parser("score", help="score a finished simulation against a case")
    s.add_argument("sim"); s.add_argument("case_id"); s.add_argument("--judge", default="auto", choices=["auto", "llm", "keyword"])
    a = ap.parse_args(argv)
    if a.cmd == "make-case":
        d = make_case(a.case_id, read_reviews_file(a.reviews), a.name, a.holdout, kind=a.kind, product_url=a.url, wayback_url=a.wayback,
                      context=a.context, world=a.world, previous_rating=a.previous_rating, actual_buy_rate=a.buy_rate, source=a.source)
        c = load_case(a.case_id)
        print(f"{d}: {len(c.train)} train, {len(c.holdout)} holdout, holdout avg {c.actual_rating}★")
    elif a.cmd == "themes":
        for th in extract_themes(load_case(a.case_id)):
            print(f"{th.kind:9} {th.mentions:4}  {th.theme}")
    else:
        view, case = _load_view(a.sim), load_case(a.case_id)
        for sc in score_layers(view, case, a.judge):
            print(json.dumps(sc.model_dump(exclude={"real_themes"}), indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
