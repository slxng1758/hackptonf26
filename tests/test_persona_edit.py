"""Persona editor backend: cast cleanup and custom instructions reaching the prompts. Made-up personas."""
from __future__ import annotations

from b2a import persona_edit, session


def test_normalize_fills_defaults_ids_and_shares():
    cast = [{"id": "p1", "name": "Maya", "age": 24, "occupation": "student", "archetype": "price-sensitive", "segment": "students",
             "share": 0.3, "goal": "cheap coffee", "budget": "$5", "voice": "blunt", "avatar": {"seed": 1}, "model": "Gemini"},
            {"id": "new-abc", "name": "  Rosa  ", "age": "200", "archetype": "not-a-type", "share": 0.3, "instructions": "x" * 2000},
            {"id": "p1", "name": "Dup", "share": 0.4},
            {"id": "a1", "kind": "agent", "name": "Shopper bot", "archetype": "AI agent", "share": 0, "goal": "buy it"}]
    out = persona_edit.normalize_cast(cast)
    ids = [p["id"] for p in out]
    assert len(ids) == len(set(ids)) and ids[0] == "p1" and ids[1] == "new-abc"
    rosa = out[1]
    assert rosa["name"] == "Rosa" and rosa["age"] == 90 and rosa["archetype"] == "first-time user"
    assert len(rosa["instructions"]) == 1000 and rosa["goal"] and rosa["avatar"]["seed"] >= 0
    people = [p for p in out if p.get("kind") != "agent"]
    assert abs(sum(p["share"] for p in people) - 1) < 0.01 and out[3]["share"] == 0 and out[3]["archetype"] == "AI agent"


def test_equal_shares_when_all_zero():
    out = persona_edit.normalize_cast([{"name": "A", "share": 0}, {"name": "B", "share": 0}])
    assert [p["share"] for p in out] == [0.5, 0.5] and {p["id"] for p in out} == {"p1", "p2"}


def test_instructions_reach_the_prompts():
    p = {"name": "Rosa", "age": 67, "occupation": "retired nurse", "archetype": "skeptic", "voice": "Careful.", "goal": "a gift",
         "budget": "$30", "memory": "nothing yet", "instructions": "Never pays for a subscription."}
    step = session.STEP.format(**{**p, "instructions": session.instructions(p)}, world="today", context="none", url="u", n=1,
                               max_steps=7, links="", text="", history="")
    decide = session.DECIDE.format(**{**p, "instructions": session.instructions(p)}, world="today", product="u", history="")
    assert "Never pays for a subscription." in step and "Never pays for a subscription." in decide
    assert session.instructions({"instructions": "  "}) == ""
