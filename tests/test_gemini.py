"""Gemini lens + grounded world, with a fake Gemini client (no key, no network). All data here is made up."""
from __future__ import annotations

import json
from types import SimpleNamespace as NS

from b2a import gemini


class FakeModels:
    def __init__(self, boxes_by_thought=None, text=""):
        self.boxes_by_thought = boxes_by_thought or {}
        self.text = text
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append(contents)
        if isinstance(contents, list):  # lens: [image part, prompt]
            prompt = contents[1]
            boxes = next((b for k, b in self.boxes_by_thought.items() if k in prompt), [])
            return NS(parsed=gemini._Boxes(boxes=[gemini._Box(**b) for b in boxes]), text="")
        chunks = [NS(web=NS(uri="https://example.org/a", title="Source A")), NS(web=NS(uri="https://example.org/a", title="dup"))]
        return NS(text=self.text, candidates=[NS(grounding_metadata=NS(grounding_chunks=chunks))])


def fake(**kw):
    return NS(models=FakeModels(**kw))


BOX_SHIP = {"box_2d": [800, 100, 860, 600], "label": "shipping cost line", "issue": "Shipping cost only shows at checkout.", "fix": "Show shipping on the product page.", "severity": 3}


def view():
    return {
        "personas": [{"id": "p1", "name": "Maya", "archetype": "price-sensitive", "model": "Gemini"},
                     {"id": "p2", "name": "Dan", "archetype": "skeptic", "model": "GPT"},
                     {"id": "p3", "name": "Ana", "archetype": "enthusiast", "model": "Claude"}],
        "decisions": {"p1": {"decision": "not buy"}, "p2": {"decision": "maybe later"}, "p3": {"decision": "buy"}},
        "summary": {"clicked_buy": ["p3"]},
        "live": {
            "p1": [{"n": 1, "url": "http://shop/p", "shot": "p1_1.jpg", "feeling": "interested", "thought": "nice", "action": "scroll"},
                   {"n": 2, "url": "http://shop/p", "shot": "p1_2.jpg", "feeling": "annoyed", "thought": "where is shipping cost", "action": "decide"}],
            "p2": [{"n": 1, "url": "http://shop/p/", "shot": "p2_1.jpg", "feeling": "skeptical", "thought": "shipping hidden again", "action": "back"},
                   {"n": 2, "url": "http://shop/x", "shot": None, "feeling": "confused", "thought": "no shot", "action": "decide"}],
            "p3": [{"n": 1, "url": "http://shop/p", "shot": "p3_1.jpg", "feeling": "delighted", "thought": "love it", "action": "click", "cart": True}],
        },
    }


def test_friction_steps_picks_bad_moments_only():
    steps = gemini.friction_steps(view())
    assert {(s["persona_id"], s["step"]) for s in steps} == {("p1", 2), ("p2", 1)}
    assert steps[0]["why"] == "left without buying"  # strongest signal first


def test_lens_boxes_and_hotspots(tmp_path):
    (tmp_path / "shots").mkdir()
    for f in ("p1_2.jpg", "p2_1.jpg"):
        (tmp_path / "shots" / f).write_bytes(b"\xff\xd8fake")
    bad = {**BOX_SHIP, "box_2d": [900, 10, 100, 20]}  # inverted box: dropped
    c = fake(boxes_by_thought={"where is shipping": [BOX_SHIP, bad],
                               "shipping hidden": [{**BOX_SHIP, "label": "shipping line", "issue": "Shipping cost hidden until checkout.", "severity": 2}]})
    out = gemini.lens(view(), tmp_path, client=c)
    assert len(out.shots) == 2 and all(len(s.boxes) == 1 for s in out.shots)
    h = out.hotspots[0]
    assert h.count == 2 and set(h.personas) == {"p1", "p2"} and set(h.models) == {"Gemini", "GPT"} and h.page == "/p"
    assert "2 of 3 customers" in out.summary
    json.dumps(out.model_dump())


def test_lens_survives_a_failing_screenshot(tmp_path):
    (tmp_path / "shots").mkdir()
    (tmp_path / "shots" / "p1_2.jpg").write_bytes(b"x")  # p2's shot missing on disk: skipped

    class Boom(FakeModels):
        def generate_content(self, *a, **k):
            raise ValueError("bad image")
    out = gemini.lens(view(), tmp_path, client=NS(models=Boom()))
    assert len(out.shots) == 1 and out.shots[0].error == "ValueError" and out.hotspots == []


def test_ground_world_parses_facts_and_dedupes_sources():
    text = "- Masks required in stores from April 2020.\n- Cloth masks sold out in many shops.\nSUMMARY: People needed reusable masks fast."
    g = gemini.ground_world("spring 2020, COVID", "cloth mask", client=fake(text=text))
    assert g.grounded and len(g.sources) == 1 and len(g.facts) == 2 and g.summary.startswith("People needed")
    t = gemini.world_text(g)
    assert t.startswith("spring 2020, COVID. People needed") and len(t) <= 300
