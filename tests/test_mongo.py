"""MongoDB layer without a real cluster: mongomock for documents + aggregation, fake embeddings for vector recall.
All data here is made up."""
from __future__ import annotations

import json
import re

import pytest

from b2a import memory, mongo

WORDS = ["price", "cheap", "budget", "student", "coffee", "quality", "brand", "skeptic", "reviews", "first", "new", "mask", "wash"]


def fake_embed(texts):
    """Bag-of-words vectors: texts sharing words are close. Deterministic, no network."""
    out = []
    for t in texts:
        toks = set(re.findall(r"[a-z]+", t.lower()))
        v = [1.0 if w in toks or any(x.startswith(w) for x in toks) else 0.0 for w in WORDS]
        out.append(v if any(v) else [0.01] * len(WORDS))
    return out


def made_up_view(sid="s1", rnd=0, evals=None):
    return {"id": sid, "status": "done", "round": rnd, "input": {"name": "Made-up latte"},
            "personas": [{"id": "p1", "name": "Maya", "archetype": "price-sensitive", "model": "Gemini", "share": .6, "inherited": True},
                         {"id": "p2", "name": "Dan", "archetype": "skeptic", "model": "GPT", "share": .4},
                         {"id": "b1", "name": "base", "archetype": "", "model": "Gemini", "layer": 1}],
            "decisions": {"p1": {"decision": "buy", "rating": 4}, "p2": {"decision": "not buy", "rating": 2}, "b1": {"decision": "maybe later", "rating": 3}},
            "summary": {"clicked_buy": []}, "live": {"p1": [{"n": 1, "thought": "ok"}]},
            "evals": evals or [{"iteration": rnd, "stage": "memory", "rating_error": 0.8 - .3 * rnd, "theme_recall": .4 + .2 * rnd}]}


@pytest.fixture
def local_memory(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "FILE", tmp_path / "memory_store.json")
    monkeypatch.setattr(memory, "_store", None)
    monkeypatch.setattr(mongo, "enabled", lambda: False)
    monkeypatch.setattr(mongo, "can_embed", lambda: True)
    monkeypatch.setattr(mongo, "EMBED_DIMS", len(WORDS))
    monkeypatch.setattr(mongo, "embed", fake_embed)
    b = memory._backend()
    b.write("/price-sensitive.md", "- compares price per use, cheap per cup beats a low sticker price\n- watches the budget")
    b.write("/skeptic.md", "- reads reviews before buying\n- distrusts brand claims")
    b.write("/quality-first.md", "- pays for quality coffee beans")
    return b


def test_similar_finds_other_types(local_memory):
    near = memory.similar("budget student who buys cheap coffee at a low price", exclude="first-time user")
    assert near and near[0]["type"] == "price-sensitive" and near[0]["lessons"][0].startswith("- compares price")


def test_similar_excludes_own_type(local_memory):
    near = memory.similar("budget student who buys cheap coffee", exclude="price-sensitive", min_score=0.0)
    assert all(n["type"] != "price-sensitive" for n in near)


def test_for_persona_adds_similar_lessons(local_memory):
    p = {"archetype": "first-time user", "age": 22, "occupation": "student", "goal": "a cheap coffee at a low price", "budget": "tight budget"}
    m = memory.for_persona(p)
    assert m.startswith("From similar customers:") and "price-sensitive customer" in m


def test_embedding_failure_never_breaks_writes(local_memory, monkeypatch):
    def boom(texts):
        raise RuntimeError("quota")
    monkeypatch.setattr(mongo, "embed", boom)
    assert local_memory.write("/enthusiast.md", "- loves new things").error is None


def test_persist_writes_file_for_local_store(local_memory):
    memory.persist()
    assert "/skeptic.md" in json.loads(memory.FILE.read_text())


def test_agents_of_and_sim_doc():
    d = mongo.sim_doc(made_up_view())
    assert d["_id"] == "s1" and "live" not in d and len(d["agents"]) == 3
    a = {x["persona_id"]: x for x in d["agents"]}
    assert a["p1"]["bought"] and not a["p2"]["bought"] and a["b1"]["layer"] == 1 and a["p1"]["inherited_memory"]


def test_save_and_aggregate_match_local(monkeypatch, tmp_path):
    mongomock = pytest.importorskip("mongomock")
    fake = mongomock.MongoClient()["test"]
    monkeypatch.setattr(mongo, "db", lambda: fake)
    monkeypatch.setattr(mongo, "SIMS", tmp_path)
    for v in (made_up_view("s1", 0), made_up_view("s2", 1)):
        mongo.save_sim(v)
        (tmp_path / v["id"]).mkdir()
        (tmp_path / v["id"] / "sim.json").write_text(json.dumps(v))
    mongo.save_sim(made_up_view("s1", 0))  # upsert: no duplicates
    assert fake["simulations"].count_documents({}) == 2 and fake["sessions"].count_documents({}) == 2 and fake["evals"].count_documents({}) == 2
    by_model = mongo._rounded(fake["simulations"].aggregate(mongo.BY_MODEL))
    acc = mongo._rounded(fake["evals"].aggregate(mongo.ACCURACY_BY_ROUND))
    local = mongo._insights_local()
    key = lambda r: (r["model"], r["layer"])
    assert sorted((key(r), r["customers"], r["bought"]) for r in by_model) == sorted((key(r), r["customers"], r["bought"]) for r in local["by_model"])
    assert [r["iteration"] for r in acc] == [0, 1] and acc[1]["rating_error"] < acc[0]["rating_error"]


def test_mirror_is_noop_without_uri(monkeypatch):
    monkeypatch.setattr(mongo, "enabled", lambda: False)
    mongo.mirror(made_up_view())
    assert mongo._pending == {}
