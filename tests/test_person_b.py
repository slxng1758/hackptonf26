"""Offline tests for evals, compare, network and product pages. No API keys, browsers or network needed.

    uv run --no-project --with pytest --with pydantic --with networkx --with fastapi --with httpx pytest -q tests

All data here is made up for the tests; it is not a real product or real reviews.
"""
from __future__ import annotations

import json

import pytest

from b2a import compare, evals, network, product_page
from b2a.contract import Theme

MADE_UP_REVIEWS = (
    [{"rating": 5, "text": "Nose wire stops my glasses fogging. Great.", "date": "2020-05-01"}] * 4
    + [{"rating": 4, "text": "Cheaper than disposables after two weeks.", "date": "2020-05-02"}] * 3
    + [{"rating": 2, "text": "Ear loops hurt after a few hours of wear.", "date": "2020-05-03"}] * 2
    + [{"rating": 1, "text": "It shrinks in the dryer, now too small.", "date": "2020-05-04"}]
)
THEMES = [Theme(theme="nose wire stops glasses fogging", kind="like", mentions=4),
          Theme(theme="cheaper than disposables", kind="like", mentions=3),
          Theme(theme="ear loops hurt after hours", kind="complaint", mentions=2),
          Theme(theme="shrinks in the dryer", kind="complaint", mentions=1)]


def dec(decision, rating, reasons, missing="", suggestions=None):
    return {"decision": decision, "rating": rating, "feeling": "neutral", "quote": "", "reasons": reasons, "missing": missing,
            **({"suggestions": suggestions} if suggestions else {})}


def made_up_view(**kw) -> dict:
    personas = [
        {"id": "p1", "name": "Maya", "archetype": "price-sensitive", "share": 0.5, "model": "Gemini"},
        {"id": "p2", "name": "Dan", "archetype": "quality-first", "share": 0.3, "model": "Claude"},
        {"id": "p3", "name": "Frank", "archetype": "skeptic", "share": 0.2, "model": "GPT"},
        {"id": "b1", "name": "Gemini base", "archetype": "", "share": 0, "model": "Gemini", "layer": 1},
        {"id": "b2", "name": "Claude base", "archetype": "", "share": 0, "model": "Claude", "layer": 1},
    ]
    decisions = {
        "p1": dec("buy", 4, ["nose wire means my glasses don't fog"], suggestions=[{"change": "show the price per wash", "why": "", "where": "product page", "impact": "nice to have"}]),
        "p2": dec("maybe later", 3, ["worried ear loops hurt after hours"], "softer ear loops",
                  [{"change": "softer ear loops", "why": "long shifts", "where": "", "impact": "would make me buy"}]),
        "p3": dec("not buy", 2, ["glitter packaging looks cheap"], "soft ear loops that don't hurt",
                  [{"change": "make the ear loops softer", "why": "", "where": "", "impact": "would make me buy"}]),
        "b1": dec("buy", 5, ["looks fine"]),
        "b2": dec("not buy", 3, ["unclear sizing"]),
    }
    return {"personas": personas, "decisions": decisions, "summary": {"clicked_buy": []}, "round": 0, **kw}


@pytest.fixture
def case(tmp_path):
    evals.make_case("made_up", MADE_UP_REVIEWS, "Made-up mask", holdout=0.5, root=tmp_path, previous_rating=3.0)
    (tmp_path / "made_up" / "themes.json").write_text(json.dumps([t.model_dump() for t in THEMES]))
    return evals.load_case("made_up", root=tmp_path)


# ---------------------------------------------------------------- evals

def test_make_case_splits_without_overlap(case, tmp_path):
    train = json.loads((tmp_path / "made_up" / "reviews_train.json").read_text())
    assert len(case.holdout) == 5 and len(train) == 5
    assert 1 <= case.actual_rating <= 5 and abs(sum(case.distribution) - 1) < 1e-6
    assert case.split == "date" and max(r["date"] for r in train) <= min(r["date"] for r in case.holdout)  # learn from the past, scored on the future


def test_distribution_distance():
    assert evals.distribution_distance([0, 0, 0, 0, 1], [0, 0, 0, 0, 1]) == 0
    assert evals.distribution_distance([1, 0, 0, 0, 0], [0, 0, 0, 0, 1]) == 1


def test_score_layers_keyword(case):
    scores = evals.score_layers(made_up_view(), case, judge="keyword")
    assert [s.stage for s in scores] == ["base", "memory"]
    personas = scores[1]
    assert personas.agents == 3 and personas.judge == "keyword"
    assert "nose wire stops glasses fogging" in personas.matched_themes
    assert "ear loops hurt after hours" in personas.matched_themes
    assert "shrinks in the dryer" in personas.missed_themes
    assert "glitter packaging looks cheap" in personas.invented_themes
    assert 0 < personas.theme_recall < 1 and personas.direction_correct is not None
    # weighted: 0.5*4 + 0.3*3 + 0.2*2 = 3.3
    assert personas.predicted_rating == pytest.approx(3.3)


def test_evolved_stage_and_feedback(case):
    s = evals.score(made_up_view(round=2), case, layer=2, judge="keyword")
    assert s.stage == "evolved" and s.iteration == 2
    text = evals.feedback_for_evolver(s)
    assert "shrinks in the dryer" in text


def test_improvement_rule(case):
    a = evals.score(made_up_view(), case, layer=2, judge="keyword")
    b = a.model_copy(update={"rating_error": a.rating_error - 0.05, "theme_recall": a.theme_recall + 0.25})
    assert evals.improvement(None, a)["keep_going"]
    assert evals.improvement(a, b)["keep_going"]
    assert not evals.improvement(a, a)["keep_going"]


def test_clicked_buy_counts_as_buying(case):
    v = made_up_view()
    v["summary"]["clicked_buy"] = ["p3"]
    assert {a["id"]: a["bought"] for a in evals.agents(v, 2)}["p3"] is True


# ---------------------------------------------------------------- compare

def test_compare_summary():
    s = compare.summary(made_up_view(), judge="keyword")
    assert set(s["by_model"]) == {"Gemini", "Claude", "GPT"} and s["by_model"]["Gemini"]["of"] == 1
    assert s["layer_delta"]["Gemini"]["buy_rate_change"] == 0.0
    assert s["layer_delta"]["Claude"]["base"]["rating"] == 3
    top = s["top_suggestions"][0]
    assert "ear loops" in top["change"] and top["would_buy_count"] == 2 and set(top["agents"]) == {"p2", "p3"}


def test_disagreement_same_persona_across_models():
    v = {"personas": [{"id": "p1-gemini", "model": "Gemini", "share": .5, "archetype": "skeptic"},
                      {"id": "p1-gpt", "model": "GPT", "share": .5, "archetype": "skeptic"}],
         "decisions": {"p1-gemini": dec("buy", 5, []), "p1-gpt": dec("not buy", 2, [])}, "summary": {}}
    d = compare.disagreement(v)
    assert d and d[0]["group"] == "p1" and d[0]["by"] == "persona" and d[0]["spread"] == 3


def test_accuracy_chart_order():
    rows = [{"stage": "evolved", "iteration": 1, "rating_error": .3, "theme_recall": .7},
            {"stage": "base", "iteration": 0, "rating_error": .9, "theme_recall": .3},
            {"stage": "memory", "iteration": 0, "rating_error": .6, "theme_recall": .5}]
    assert [r["label"] for r in compare.accuracy_chart(rows)] == ["base models", "+ memory", "+ evolved (loop 1)"]


# ---------------------------------------------------------------- network

def test_network_on_example_fixture():
    extras = json.loads(open("fixtures/sim_extras_example.json").read())
    personas = [{"id": n["id"], "name": n["label"], "archetype": n["archetype"], "model": m}
                for n, m in zip(extras["social"]["nodes"], ["Gemini", "Claude", "GPT", "Gemini"])]
    s = network.analyze({"social": extras["social"], "personas": personas}, judge="keyword")
    assert s.top_influencers[0] == "p4"                       # the skeptic's dryer post drew the most reactions
    assert s.cascades[0].post_id == "s2" and s.cascades[0].size == 2
    assert {e.kind for e in s.edges} <= {"reply", "repost"} and len(s.nodes) == 4
    assert sum(n.centrality for n in s.nodes) == pytest.approx(1, abs=1e-3)
    assert set(s.by_model) == {"Gemini", "Claude", "GPT"} and s.summary
    json.dumps(s.model_dump())                                # serializable for POST /api/sims/{id}/social


def test_network_no_reactions():
    s = network.analyze([{"id": "a", "round": 0, "author": "p1", "kind": "post", "text": "nice", "sentiment": .5}], [], judge="keyword")
    assert s.edges == [] and s.cascades[0].size == 0 and "Nobody reacted" in s.summary


# ---------------------------------------------------------------- product pages

def test_product_page_routes(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    monkeypatch.setattr(product_page, "PRODUCTS", tmp_path)
    app = FastAPI()
    app.include_router(product_page.router)
    c = TestClient(app)
    r = c.post("/api/products", json={"name": "Oat <b>Latte</b>", "description": "House oat latte. Made to order.", "price": "$5",
                                      "changes": "Now with less sugar.", "features": ["oat milk"]}).json()
    page = c.get(f"/api/products/{r['id']}/").text
    assert "Add to cart" in page and "$5" in page and "Now with less sugar." in page and "&lt;b&gt;" in page
    assert c.get(f"/api/products/{r['id']}/details").status_code == 200
    assert "Added to cart" in c.get(f"/api/products/{r['id']}/cart").text
    assert c.get("/api/products/nope/").status_code == 404


def test_from_brief():
    p = product_page.from_brief({"name": "Mask", "summary": "A washable mask.", "price": 24, "key_features": ["nose wire"]})
    assert p.price == "$24" and p.features == ["nose wire"]


def test_social_enrich_merges_network_analysis(monkeypatch):
    """social.run's output (Candy's shape) gets communities, cascades, themes, by_model; her summary is kept."""
    from b2a import social
    real = network.label_themes
    monkeypatch.setattr(network, "label_themes", lambda roots, judge="auto": real(roots, "keyword"))  # offline labels
    extras = json.loads(open("fixtures/sim_extras_example.json").read())
    personas = [{"id": n["id"], "name": n["label"], "archetype": n["archetype"], "model": m}
                for n, m in zip(extras["social"]["nodes"], ["Gemini", "Claude", "GPT", "Gemini"])]
    out = social.enrich({"posts": extras["social"]["posts"], "nodes": [], "edges": [], "top_influencers": [], "summary": "Her summary."}, personas)
    assert out["summary"] == "Her summary." and out["network_summary"]
    assert out["cascades"] and out["themes"] and out["communities"] and set(out["by_model"]) == {"Gemini", "Claude", "GPT"}
    assert out["top_influencers"][0] == "p4" and len(out["nodes"]) == 4
    from b2a.contract import Social
    Social(**out)                                  # still valid for POST /api/sims/{id}/social


def test_social_enrich_falls_back_on_error(monkeypatch):
    from b2a import social
    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(network, "analyze", boom)
    orig = {"posts": [], "nodes": [], "edges": [], "top_influencers": [], "summary": "s"}
    assert social.enrich(orig, []) is orig
