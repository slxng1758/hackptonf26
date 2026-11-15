"""One model plays every customer in a run (picked on the start page). A failing model never gets another model standing
in: that customer is counted as left, with the reason, so every customer ends with a decision. AI calls stubbed; made-up data."""
from __future__ import annotations

import pytest

from b2a import models, persona_edit, session, sim


def _cast():
    arch = ["price-sensitive", "quality-first", "skeptic", "enthusiast", "first-time user"]
    return session.Cast(personas=[session.Persona(name=f"P{i}", age=30, occupation="x", archetype=a, segment="s", share=.2,
                                                  goal="g", budget="$5", voice="v") for i, a in enumerate(arch)])


def test_cast_with_one_model_gives_everyone_that_model(monkeypatch):
    class Fake:
        def with_structured_output(self, *a, **k):
            return self

        def invoke(self, *a, **k):
            return _cast()
    monkeypatch.setattr(session, "fast", lambda: Fake())
    monkeypatch.setattr(models, "persona_models", lambda: {"Gemini": None, "Claude": None})
    assert {p["model"] for p in session.cast("Cafe", "coffee", "", "", "students", models=["Claude"])} == {"Claude"}
    assert {p["model"] for p in session.cast("Cafe", "coffee", "", "", "students")} == {"Gemini", "Claude"}  # no pick: as before


def test_simjob_cast_passes_the_picked_model(tmp_path, monkeypatch):
    from b2a import memory, mongo
    monkeypatch.setattr(sim, "SIMS", tmp_path)
    monkeypatch.setattr(mongo, "mirror", lambda v: None)
    monkeypatch.setattr(memory, "for_persona", lambda p: "")
    monkeypatch.setattr(session, "think_about_customers", lambda *a, **k: "reasoning")
    monkeypatch.setattr(session, "agent_shoppers", lambda *a, **k: [])
    seen = {}

    def cast(*a, models=None, **k):
        seen["models"] = models
        return [{"id": "p1", "name": "Maya", "age": 22, "archetype": "skeptic", "share": 1, "model": "Gemini"}]
    monkeypatch.setattr(session, "cast", cast)
    job = sim.SimJob({"url": "http://example.test", "name": "Cafe", "category": "coffee", "customers": "students", "offer": "lattes", "models": ["Gemini"]})
    job.cast()
    assert job.status == "awaiting_approval", job.error
    assert seen["models"] == ["Gemini"]


def test_auto_model_becomes_the_runs_model():
    out = persona_edit.normalize_cast([{"name": "A", "model": ""}, {"name": "B", "model": "Gemini"},
                                       {"name": "Bot", "kind": "agent", "model": "Claude", "share": 0}], default_model="Claude")
    assert [p["model"] for p in out] == ["Claude", "Gemini", "Claude"]


def test_retry_then_give_up(monkeypatch):
    monkeypatch.setattr(models, "RETRY_WAITS", (0, 0))
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("quota")
        return "ok"
    assert models.call_with_retry(flaky, "Gemini") == "ok" and len(calls) == 3
    with pytest.raises(models.ModelUnavailable, match="Gemini failed 3 times: RuntimeError: quota"):
        models.call_with_retry(lambda: (_ for _ in ()).throw(RuntimeError("quota")), "Gemini")


def test_failed_customer_is_counted_as_left_not_replaced(tmp_path, monkeypatch):
    def browse(p, *a, **k):
        if p["id"] == "p2":
            raise models.ModelUnavailable("Gemini failed 3 times: ResourceExhausted: quota")
        return {"persona": p["id"], "steps": [], "decision": {"decision": "buy", "rating": 5}}
    monkeypatch.setattr(session, "browse", browse)
    monkeypatch.setattr(session.time, "sleep", lambda s: None)
    done = {}
    session.run_all([{"id": "p1", "model": "Gemini"}, {"id": "p2", "model": "Gemini"}], "http://example.test", "", "", tmp_path,
                    lambda *a: None, lambda pid, r: done.__setitem__(pid, r))
    assert done["p1"]["decision"]["decision"] == "buy"
    d = done["p2"]["decision"]
    assert d["outcome"] == "left" and "Gemini failed" in d["stuck"] and "Gemini failed" in done["p2"]["error"]


def test_stuck_customer_is_counted_as_left_after_the_timeout(tmp_path, monkeypatch):
    import threading
    release = threading.Event()

    def browse(p, url, world, context, out, on_step, **k):
        on_step(p["id"], {"n": 1, "url": url, "thought": "hmm", "feeling": "neutral", "action": "scroll", "target": ""})
        release.wait(5)  # hangs, like a model call that never returns
        on_step(p["id"], {"n": 2, "url": url, "thought": "late", "feeling": "neutral", "action": "decide", "target": ""})
        return {"persona": p["id"], "steps": [], "decision": {"decision": "buy", "rating": 5}}
    monkeypatch.setattr(session, "browse", browse)
    monkeypatch.setattr(session.time, "sleep", lambda s: None)
    monkeypatch.setattr(session, "SESSION_TIMEOUT", 0.3)
    done = {}
    session.run_all([{"id": "p1", "model": "Gemini"}], "http://example.test", "", "", tmp_path,
                    lambda *a: None, lambda pid, r: done.__setitem__(pid, r))
    release.set()
    d = done["p1"]["decision"]
    assert d["outcome"] == "left" and d["decision"] == "not buy" and "still thinking" in d["stuck"] and len(done["p1"]["steps"]) == 1


def test_decision_accepts_a_single_string_for_a_list():
    d = session.Decision.model_validate({"decision": "buy", "rating": 4, "feeling": "neutral", "quote": "q", "liked": "the price", "disliked": None})
    assert d.liked == ["the price"] and d.disliked == []
