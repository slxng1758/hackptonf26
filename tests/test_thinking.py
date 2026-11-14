"""The live casting feed: steps, streamed reasoning, each persona with why. AI calls stubbed; made-up data."""
from __future__ import annotations

from b2a import memory, mongo, session, sim


def test_cast_records_live_feed(tmp_path, monkeypatch):
    monkeypatch.setattr(sim, "SIMS", tmp_path)
    monkeypatch.setattr(mongo, "mirror", lambda v: None)
    monkeypatch.setattr(memory, "for_persona", lambda p: "- likes clear prices" if p["id"] == "p1" else "")
    monkeypatch.setattr(session, "read_site", lambda url: {"name": "Made-up Cafe", "category": "coffee", "customers": "students", "offer": "lattes $5"})
    seen = {}

    def think(*a, on_text=None, **k):
        for piece in ["Students ", "buy most ", "coffee here."]:
            on_text(piece)
        return "Students buy most coffee here."

    def cast(*a, segments="", **k):
        seen["segments"] = segments
        return [{"id": "p1", "name": "Maya", "age": 22, "archetype": "price-sensitive", "share": .6, "model": "Claude", "why": "Most buyers are students."},
                {"id": "p2", "name": "Dan", "age": 40, "archetype": "skeptic", "share": .4, "model": "Gemini", "why": "Covers doubters."}]
    monkeypatch.setattr(session, "think_about_customers", think)
    monkeypatch.setattr(session, "cast", cast)
    monkeypatch.setattr(session, "agent_shoppers", lambda *a, **k: [{"id": "a1", "name": "Agent", "model": "Claude", "kind": "agent", "archetype": "AI agent", "share": 0}])

    job = sim.SimJob({"url": "http://example.test"})
    job.cast()
    ev = job.thinking
    kinds = [e["kind"] for e in ev]
    assert job.status == "awaiting_approval", job.error
    assert seen["segments"] == "Students buy most coffee here."   # reasoning drives casting
    assert kinds[:3] == ["step", "reason", "step"] and kinds.count("persona") == 2
    assert ev[0]["facts"]["Business"] == "Made-up Cafe" and ev[1]["text"] == "Students buy most coffee here."
    p1 = next(e for e in ev if e.get("persona_id") == "p1")
    assert p1["text"] == "Most buyers are students." and p1["memory"]
    assert all(e["status"] == "done" for e in ev) and ev[-1]["title"] == "Ready for your review"
    assert job.view()["thinking"] == ev


def test_failed_cast_marks_running_step_as_error(tmp_path, monkeypatch):
    monkeypatch.setattr(sim, "SIMS", tmp_path)
    monkeypatch.setattr(mongo, "mirror", lambda v: None)
    monkeypatch.setattr(session, "read_site", lambda url: (_ for _ in ()).throw(RuntimeError("site down")))
    job = sim.SimJob({"url": "http://example.test"})
    job.cast()
    assert job.status == "error" and job.thinking[0]["status"] == "error"
