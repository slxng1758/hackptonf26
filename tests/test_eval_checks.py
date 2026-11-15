"""The eval checks themselves, offline: a director trajectory that follows every rule passes every check, and each
planted mistake is caught by the check meant for it. Plus the fake store the customer evals shop in. Made-up data."""
from __future__ import annotations

import copy
import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from evals import checks
from evals.trajectory import RunRecord, Trajectory

BUDGET = '\nBudget left: {"personas": 3, "sessions": 20, "evolve_loops": 2, "social_rounds": 1, "minutes": 12.0}'
PEOPLE = ["p1-maya", "p2-jordan", "p3-priya", "p4-tom", "p5-lena"]
AGENTS = ["a1-claude-agent", "a2-gpt-agent"]


class Build:
    """Write a trajectory turn by turn: each turn is a list of (tool, args, result)."""

    def __init__(self):
        self.msgs, self.n = [], 0

    def turn(self, *calls):
        tcs = []
        for name, args, _ in calls:
            self.n += 1
            tcs.append({"name": name, "args": args, "id": f"c{self.n}"})
        self.msgs.append(AIMessage(content="", tool_calls=tcs))
        for tc, (_, _, result) in zip(tcs, calls):
            self.msgs.append(ToolMessage(content=result, tool_call_id=tc["id"], name=tc["name"]))
        return self

    def own(self, name, result, **args):
        return self.turn((name, {"reason": f"because the last result says we should {name} now", **args}, result + BUDGET))

    def round(self, layer, names, digest):
        n = sum(1 for m in self.msgs if isinstance(m, ToolMessage) and "is open for" in m.content) + 1
        self.own("start_round", f"Round {n} (layer {layer}) is open for: {', '.join(names)}. Now call task once for each of them", layer=layer)
        self.turn(*[("task", {"subagent_type": c, "description": "Visit the site as yourself and decide."}, f"{c}: bought") for c in names])
        return self.own("end_round", digest)

    def done(self, text="Your tote sells to 3 in 5 customers; show the size on the product page."):
        self.msgs.append(AIMessage(content=text))
        return self.msgs


def l2(split="none", conf="0.62"):
    return f"Run 2 (layer 2): buy rate 60%, rating 3.8, avg confidence {conf}. Segments that split: {split}.\np1 Maya: bought"


def good_messages(flat_loops=2):
    b = Build()
    b.turn(("write_todos", {"todos": [{"content": "brief", "status": "in_progress"}]}, "Updated todo list"))
    b.own("brief_product", "Harbor Canvas Co.: handmade canvas bags. Wrote /site.md.")
    b.turn(("task", {"subagent_type": "briefer", "description": "Write /product.md and /world.md"}, "A $48 waxed tote..."))
    b.turn(("task", {"subagent_type": "segmenter", "description": "Segments please"}, "n=5: price-sensitive, ..."))
    b.own("cast_personas", "Cast 5: p1 Maya (price-sensitive, 20%, Claude); p2 Jordan (skeptic, 20%, GPT)", n=5,
          archetypes=["price-sensitive", "quality-first", "function-first", "skeptic", "enthusiast"])
    b.own("request_approval", "Approved: p1 Maya (Claude), p2 Jordan (GPT)")
    b.round(1, AGENTS, "Round 1 (layer 1, AI agents): Claude: bought; GPT: left")
    b.round(2, PEOPLE, l2())
    b.turn(("task", {"subagent_type": "critic", "description": "Can we trust this?"}, "Looks balanced.\nSPAWN: none"))
    b.own("score", "Loop 0: rating_error 0.90, theme_recall 0.40. keep_going=True.\nFeedback for the evolver: missed dryer shrink")
    keeps = ["True"] + ["False"] * flat_loops
    for k, keep in enumerate(keeps[1:] or ["True"], start=1):
        b.own("evolve", f"Loop {k}: p1 → v{k}: real buyers say it shrinks", persona_ids=["p1", "p2"], focus="real buyers mention it shrinks in the dryer")
        b.round(2, PEOPLE, l2())
        b.own("score", f"Loop {k}: rating_error 0.30, theme_recall 0.70. keep_going={keep}.\nFeedback for the evolver: none")
    b.own("run_social", "5 posts, 3 replies, 1 reposts.", rounds=2)
    b.own("summarize", "Buy rate 60%, rating 3.8/5")
    b.own("finish", "Report written, lesson saved.", lesson="Cast a gift buyer next time.")
    return b.done()


def view_for(traj: Trajectory, people=5):
    personas = [{"id": f"a{i}", "kind": "agent"} for i in (1, 2)] + [{"id": f"p{i}"} for i in range(1, people + 1)]
    runs = [{"n": i + 1, "agents": ["x"], "decisions": {"x": {}}} for i in range(3)]
    director = [{"tool": c.name, "reason": c.args.get("reason")} for c in traj.calls if c.name in checks.OWN]
    return {"personas": personas, "runs": runs, "director": director, "status": "done", "budget": {"max_evolve_loops": 4}}


FILES = {"product.md": "# Tote\n$48\n\n## Unclear\n- size", "world.md": "today\nnormal times\nprices are up\n", "segments.md": "- skeptic 20%"}


def record(msgs, **meta) -> RunRecord:
    t = Trajectory.from_messages(msgs)
    return RunRecord(t, view_for(t), dict(FILES), {"has_truth": True, **meta})


@pytest.fixture
def good():
    return record(good_messages())


def test_good_run_passes_every_check(good):
    for check in checks.DIRECTOR_CHECKS:
        r = check(good)
        if r is not None:
            assert r["score"] == 1, r
    assert checks.hitl_recast(good) is None  # no owner feedback in this run


def test_reference_superset_from_agentevals(good):
    from evals.judges import reference_superset
    assert reference_superset(good)["score"] == 1
    missing_critic = record([m for m in good.traj.messages if not (
        (isinstance(m, AIMessage) and any(tc["args"].get("subagent_type") == "critic" for tc in m.tool_calls)) or
        (isinstance(m, ToolMessage) and "SPAWN" in m.content))])
    r = reference_superset(missing_critic)
    assert r["score"] == 0 and "task:critic" in r["comment"]


def _mutate(msgs, fn):
    msgs = copy.deepcopy(msgs)
    fn(msgs)
    return record(msgs)


def test_two_own_tools_in_one_turn():
    b = Build()
    b.turn(("brief_product", {"reason": "start with the product page"}, "ok"), ("cast_personas", {"reason": "cast them all now", "n": 5}, "Cast 5"))
    assert checks.own_tools_serial(record(b.done()))["score"] < 1


def test_customers_sent_over_two_turns():
    b = Build()
    b.own("start_round", f"Round 1 (layer 2) is open for: {', '.join(PEOPLE[:2])}. Now call task", layer=2)
    for c in PEOPLE[:2]:
        b.turn(("task", {"subagent_type": c}, "done"))
    b.own("end_round", l2())
    r = checks.round_protocol(record(b.done()))
    assert r["score"] == 0 and "over 2 turns" in r["comment"]


def test_customer_never_sent():
    b = Build()
    b.own("start_round", f"Round 1 (layer 2) is open for: {', '.join(PEOPLE[:3])}. Now call task", layer=2)
    b.turn(*[("task", {"subagent_type": c}, "done") for c in PEOPLE[:2]])
    b.own("end_round", l2())
    assert "never sent ['p3-priya']" in checks.round_protocol(record(b.done()))["comment"]


def test_missing_reason(good):
    def drop(msgs):
        next(m for m in msgs if isinstance(m, AIMessage) and m.tool_calls and m.tool_calls[0]["name"] == "score").tool_calls[0]["args"]["reason"] = "ok"
    assert checks.reasons_given(_mutate(good.traj.messages, drop))["score"] < 1


def test_cast_without_skeptic(good):
    def no_skeptic(msgs):
        c = next(m for m in msgs if isinstance(m, AIMessage) and m.tool_calls and m.tool_calls[0]["name"] == "cast_personas")
        c.tool_calls[0]["args"]["archetypes"] = ["price-sensitive", "quality-first", "function-first", "brand-loyal", "enthusiast"]
    r = checks.cast_rules(_mutate(good.traj.messages, no_skeptic))
    assert r["score"] == 0 and "no skeptic" in r["comment"]


def test_kept_evolving_after_two_flat_loops():
    r = checks.loop_stop_rule(record(good_messages(flat_loops=3)))  # True, F, F, then evolves again
    assert r["score"] == 0 and "kept evolving" in r["comment"]


def test_stopped_while_still_improving():
    r = checks.loop_stop_rule(record(good_messages(flat_loops=0)))  # one loop, keep_going=True, then stops
    assert r["score"] == 0 and "keep_going=True" in r["comment"]


def test_stopped_after_one_flat_loop_is_half():
    assert checks.loop_stop_rule(record(good_messages(flat_loops=1)))["score"] == 0.5


def test_split_segment_without_spawn():
    msgs = good_messages()
    for m in msgs:
        if isinstance(m, ToolMessage) and "Segments that split: none" in m.content:
            m.content = m.content.replace("Segments that split: none", "Segments that split: commuters")
            break
    r = checks.spawn_rule(record(msgs))
    assert r["score"] == 0 and "never spawned" in r["comment"]


def _spawn_run(evolve_between: bool):
    b = Build()
    b.own("request_approval", "Approved: p1 Maya (Claude)")
    b.round(2, PEOPLE[:2], l2(split="commuters"))
    b.own("cast_personas", "Cast 1: p6 Ruth (function-first, 10%, GPT)", n=1, archetypes=["function-first"])
    if evolve_between:
        b.own("evolve", "Loop 1: p1 → v1: ok", persona_ids=["p1"], focus="real buyers mention the dryer")
    b.round(2, PEOPLE[:2] + ["p6-ruth"], l2())
    return checks.spawn_rule(record(b.done()))


def test_spawn_then_resend_everyone():
    assert "resent old personas" in _spawn_run(evolve_between=False)["comment"]
    assert _spawn_run(evolve_between=True)["score"] == 1  # folded into the learning-loop round: fine


def test_subagent_called_a_director_tool(good):
    good.view["director"].append({"tool": "cast_personas", "reason": "the critic wanted more"})  # logged, not in the trajectory
    r = checks.subagent_tool_scope(good)
    assert r["score"] == 0 and "cast_personas" in r["comment"]


def test_hitl_recast():
    def run(replace):
        b = Build()
        b.own("brief_product", "ok")
        b.own("cast_personas", "Cast 5: p1 Maya (skeptic)", n=5, archetypes=["skeptic"] * 5)
        b.own("request_approval", 'The owner says the cast is off: "more retirees". Cast again with cast_personas(replace=true)')
        b.own("cast_personas", "Cast 5: p6 Ruth (skeptic)", n=5, archetypes=["skeptic"] * 5, replace=replace)
        b.own("request_approval", "Approved: p6 Ruth (Claude)")
        b.round(1, AGENTS, "Round 1 (layer 1, AI agents): ok")
        return checks.hitl_recast(record(b.done(), owner_feedback=["more retirees"]))["score"]
    assert run(True) == 1 and run(False) == 0


def test_corrective_results_are_counted():
    b = Build()
    b.own("end_round", "No round is open.")
    b.own("start_round", "Round 2 is still open: call end_round first.", layer=2)
    assert checks.no_corrective_results(record(b.done()))["score"] == 0


# ---------------------------------------------------------------- customer checks + the fake store

def test_customer_checks_and_fake_store(tmp_path, monkeypatch):
    """Drive the real customer tools on the fake store by hand: the visit, outcome and checks all line up."""
    from b2a import customer
    from evals.fixtures import STORE_URL, store
    from evals.harness import FakeBrowser

    monkeypatch.setattr(customer, "BrowserSession", lambda: FakeBrowser(store(48), STORE_URL))
    p = {"id": "p1", "name": "Dana", "age": 31, "occupation": "nurse", "archetype": "function-first", "segment": "x", "share": 1,
         "goal": "a tote", "budget": "$60", "voice": "direct", "model": "Claude", "memory": ""}
    host = customer._OneCustomer(p, STORE_URL, "", "", tmp_path, lambda cid, s: None, 10, "")
    tools = {t.name: t for t in customer.tools_for(host, "p1")}
    b = Build()
    b.turn(("open_site", {}, tools["open_site"].invoke({})))
    for target in ("Market Tote", "Add to cart", "Checkout", "Place order"):
        args = {"target": target, "thought": f"I'll click {target}", "feeling": "interested"}
        b.turn(("click", args, tools["click"].invoke(args)))
    dec = {"decision": "buy", "rating": 5, "feeling": "delighted", "quote": "Great tote.", "last_thought": "Done, ordered it."}
    b.turn(("decide", dec, tools["decide"].invoke(dec)))
    msgs = b.done("I bought the tote.")
    assert host.v.decision["outcome"] == "bought" and host.v.ordered_at

    r = RunRecord(Trajectory.from_messages(msgs), {}, {}, {"decision": host.v.decision, "steps": host.v.steps, "can_order": True,
                                                         "forced": False, "expect_outcomes": {"bought"}})
    for check in checks.CUSTOMER_CHECKS:
        assert check(r)["score"] == 1, check(r)

    bad = copy.deepcopy(msgs)
    bad[2].tool_calls[0]["args"]["target"] = "Buy now with Apple Pay"  # a button that was never on the page
    assert checks.clicks_visible_targets(RunRecord(Trajectory.from_messages(bad)))["score"] < 1


def test_compact_transcript_is_readable(good):
    text = good.traj.compact()
    assert "task:critic" in text and "FINAL REPLY" in text
    assert all(isinstance(m, (AIMessage, ToolMessage)) for m in good.traj.compact_messages())
    json.dumps([c.args for c in good.traj.calls])  # args stay JSON-serializable for LangSmith
