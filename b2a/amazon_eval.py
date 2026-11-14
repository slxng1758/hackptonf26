"""Accuracy check on real Amazon products: do our customers predict what real reviewers said?

    .venv/bin/python -m b2a.amazon_eval            # pick a product, run 3 rounds, attach scores to each simulation

1. Pick one All_Beauty product with 200-1000 real reviews (Amazon Reviews 2023, McAuley Lab).
2. Build a plain product page from its listing (title, price, features, description, images). The page never shows the
   star rating or review count, so the customers can't copy the answer.
3. Split the reviews by date: the older half can teach the customers, the newer half is held out and only used to score.
4. Round 0: customers shop the page cold. Score it.
   Round 1+: teach them what the older reviews say, run the same customers again, score again.
Scores (b2a/contract.py EvalScore) go to the simulation through the API, so "Were we right?" shows them.
"""
from __future__ import annotations

import html
import json
import random
import time
import urllib.request
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, Field

from .models import fast

ROOT = Path(__file__).resolve().parent.parent / "runs" / "amazon"
PAGES = ROOT / "pages"
API = "http://127.0.0.1:4620"


# ---------- data ----------
def pick_product(lo: int = 200, hi: int = 1000) -> tuple[dict, list[dict]]:
    counts: Counter = Counter()
    with open(ROOT / "All_Beauty.jsonl") as f:
        for line in f:
            counts[json.loads(line)["parent_asin"]] += 1
    wanted = {a for a, n in counts.items() if lo <= n <= hi}
    best = None
    with open(ROOT / "meta_All_Beauty.jsonl") as f:
        for line in f:
            m = json.loads(line)
            if m["parent_asin"] in wanted and m.get("price") and len(m.get("features") or []) >= 3 and m.get("images"):
                if best is None or counts[m["parent_asin"]] > counts[best["parent_asin"]]:
                    best = m
    if not best:
        raise SystemExit("no product with a price, features and images in that review range")
    reviews = []
    with open(ROOT / "All_Beauty.jsonl") as f:
        for line in f:
            r = json.loads(line)
            if r["parent_asin"] == best["parent_asin"]:
                reviews.append(r)
    reviews.sort(key=lambda r: r["timestamp"])
    return best, reviews


def page(m: dict) -> str:
    """A plain store page from the listing only: no stars, no review count, no reviews."""
    img = next((i.get("large") or i.get("hi_res") for i in m.get("images") or [] if i.get("large") or i.get("hi_res")), "")
    feats = "".join(f"<li>{html.escape(x)}</li>" for x in m.get("features") or [])
    desc = "".join(f"<p>{html.escape(x)}</p>" for x in m.get("description") or [])
    details = "".join(f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>" for k, v in (m.get("details") or {}).items())
    t = html.escape(m["title"])
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{t}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:980px;margin:24px auto;padding:0 16px;color:#111}}
.grid{{display:grid;grid-template-columns:380px 1fr;gap:32px}}img{{max-width:100%;border-radius:12px}}
.price{{font-size:28px;font-weight:700;margin:8px 0}}button{{background:#ffd814;border:0;border-radius:20px;padding:12px 28px;font-size:16px;cursor:pointer}}
th{{text-align:left;padding-right:12px;color:#555}}</style></head><body>
<div class="grid"><div><img src="{html.escape(img)}" alt="{t}"></div><div>
<h1>{t}</h1><div>by {html.escape(m.get("store") or "")}</div>
<div class="price">${m["price"]:.2f}</div>
<button onclick="this.textContent='Added to cart ✓'">Add to Cart</button>
<h3>About this item</h3><ul>{feats}</ul></div></div>
<h3>Product description</h3>{desc or "<p>(none)</p>"}
<h3>Details</h3><table>{details}</table></body></html>"""


# ---------- what real reviewers said ----------
class Theme(BaseModel):
    theme: str = Field(description="short phrase, e.g. 'leaves hair greasy'")
    kind: str = Field(description="like or complaint")
    mentions: int = Field(ge=0, description="how many of the given reviews raise it")


class Themes(BaseModel):
    themes: list[Theme] = Field(min_length=3, max_length=6)


def themes_of(reviews: list[dict], title: str) -> list[dict]:
    sample = random.Random(7).sample(reviews, min(150, len(reviews)))
    text = "\n".join(f"- {r['rating']:.0f}★ {r['title']}: {r['text'][:300]}" for r in sample)
    t: Themes = fast().with_structured_output(Themes, method="json_schema").invoke(
        f"Real Amazon reviews of '{title}':\n{text}\n\nList the 4-6 most common themes (likes and complaints) with how many of these reviews mention each.")
    return [x.model_dump() for x in t.themes]


def teach_text(reviews: list[dict], title: str) -> str:
    sample = random.Random(3).sample(reviews, min(150, len(reviews)))
    text = "\n".join(f"- {r['rating']:.0f}★ {r['title']}: {r['text'][:300]}" for r in sample)
    out = fast().invoke(f"Real Amazon reviews of '{title}':\n{text}\n\nIn 4-6 short sentences, tell a group of shoppers what real buyers "
                         f"of this product actually did and felt: who bought it, what pleased them, what disappointed them, and "
                         f"roughly how satisfied they were overall. No star numbers. Under 900 characters.").content
    if not isinstance(out, str):  # the model may return reasoning blocks alongside the text
        out = " ".join(b.get("text", "") for b in out if isinstance(b, dict) and b.get("type") == "text")
    return out.strip()[:1900]


class Match(BaseModel):
    matched: list[str] = Field(description="real themes (copied exactly) that the customers also raised")
    persona_themes: list[str] = Field(description="the distinct themes the customers raised, 3-8 short phrases")
    persona_themes_real: int = Field(ge=0, description="how many of persona_themes match any real theme")


# ---------- API ----------
def api(path: str, body: dict | None = None):
    req = urllib.request.Request(API + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="GET" if body is None else "POST")
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def wait(sim_id: str, until: set[str], every: int = 8) -> dict:
    while True:
        s = api(f"/api/sims/{sim_id}")
        if s["status"] in until | {"error"}:
            return s
        time.sleep(every)


def score(sim: dict, held: list[dict], real: list[dict], iteration: int, notes: str) -> dict:
    people = [p for p in sim["personas"] if p.get("kind") != "agent" and p["id"] in sim["decisions"]]
    share = {p["id"]: p["share"] for p in people}
    w = sum(share.values()) or 1
    # reviewers rate after buying and using it, so compare with the customers' "after a few weeks of use" stars,
    # not their pre-purchase impression of the page (that's the "rating" field)
    star = lambda p: sim["decisions"][p["id"]].get("stars_after_use") or sim["decisions"][p["id"]]["rating"]
    pred = sum(share[p["id"]] * star(p) for p in people) / w
    actual = sum(r["rating"] for r in held) / len(held)
    said = "\n".join(f"- {sim['decisions'][p['id']]['quote']} | reasons: {'; '.join(sim['decisions'][p['id']].get('reasons') or [])} | "
                     f"missing: {sim['decisions'][p['id']].get('missing', '')}" for p in people)
    m: Match = fast().with_structured_output(Match, method="json_schema").invoke(
        f"Real reviewer themes: {[t['theme'] for t in real]}\nWhat simulated customers said:\n{said}\n\n"
        "Which real themes did the customers also raise (same meaning, not exact words)? List the customers' own themes and count how many match a real theme.")
    matched = [t["theme"] for t in real if t["theme"] in m.matched]
    recall = len(matched) / len(real)
    precision = m.persona_themes_real / max(len(m.persona_themes), 1)
    # star distributions: share-weighted predicted vs held-out real, total variation distance
    pd = Counter()
    for p in people:
        pd[star(p)] += share[p["id"]] / w
    rd = Counter(round(r["rating"]) for r in held)
    dist = 0.5 * sum(abs(pd.get(k, 0) - rd.get(k, 0) / len(held)) for k in range(1, 6))
    bought = [p for p in people if any(x.get("cart") for x in sim["live"].get(p["id"], [])) or sim["decisions"][p["id"]]["decision"] in ("buy", "would recommend")]
    return {"iteration": iteration, "actual_rating": round(actual, 2), "predicted_rating": round(pred, 2), "rating_error": round(abs(pred - actual), 2),
            "actual_buy_rate": None, "predicted_buy_rate": round(len(bought) / max(len(people), 1), 2), "direction_correct": None,
            "theme_recall": round(recall, 2), "theme_precision": round(precision, 2), "distribution_distance": round(dist, 3),
            "real_themes": real, "matched_themes": matched, "missed_themes": [t["theme"] for t in real if t["theme"] not in matched], "notes": notes}


def main(rounds: int = 2, resume: str | None = None):
    PAGES.mkdir(parents=True, exist_ok=True)
    m, reviews = pick_product()
    asin = m["parent_asin"]
    half = len(reviews) // 2
    teach, held = reviews[:half], reviews[half:]
    (PAGES / f"{asin}.html").write_text(page(m))
    print(f"product: {m['title'][:80]} ({asin}), ${m['price']}, {len(reviews)} reviews → teach {len(teach)}, held out {len(held)}")
    if resume:  # round 0 already scored: reuse its themes so every round is judged against the same answer key
        real = api(f"/api/sims/{resume}")["evals"][0]["real_themes"]
        return later_rounds(resume, m, teach, held, real, rounds)
    real = themes_of(held, m["title"])
    print("held-out themes:", [t["theme"] for t in real])
    url = f"{API}/api/product/{asin}.html"
    s = api("/api/sims", {"url": url, "name": m["title"][:110], "category": f"{m.get('main_category') or 'Beauty'} product sold on Amazon by {m.get('store') or 'a small brand'}",
                          "customers": "people who shop for this kind of beauty product on Amazon", "offer": f"{m['title']} for ${m['price']:.2f}"})
    sid = s["id"]
    wait(sid, {"awaiting_approval"}, 3)
    api(f"/api/sims/{sid}/approve", {})
    print("round 0:", sid)
    sim = wait(sid, {"done"})
    sc = score(sim, held, real, 0, "Cold start: customers saw only the store page.")
    api(f"/api/sims/{sid}/evals", sc)
    print(f"  predicted {sc['predicted_rating']} vs real {sc['actual_rating']} (error {sc['rating_error']}), themes caught {sc['theme_recall']:.0%}")
    later_rounds(sid, m, teach, held, real, rounds)


def later_rounds(sid: str, m: dict, teach: list[dict], held: list[dict], real: list[dict], rounds: int):
    lesson = teach_text(teach, m["title"])
    for it in range(1, rounds + 1):
        api(f"/api/sims/{sid}/teach", {"truth": lesson})
        sid = api(f"/api/sims/{sid}/rerun", {})["id"]
        print(f"round {it}:", sid)
        sim = wait(sid, {"done"})
        sc = score(sim, held, real, it, "Taught from the older half of the real reviews; scored on the newer half they never saw.")
        api(f"/api/sims/{sid}/evals", sc)
        print(f"  predicted {sc['predicted_rating']} vs real {sc['actual_rating']} (error {sc['rating_error']}), themes caught {sc['theme_recall']:.0%}")
    print(f"open: http://localhost:4621/#sim={sid}")


if __name__ == "__main__":
    import sys
    main(resume=sys.argv[1] if len(sys.argv) > 1 else None)
