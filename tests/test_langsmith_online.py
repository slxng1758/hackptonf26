"""The code the LangSmith online evaluators run, offline: executed the way LangSmith runs it (on the message dicts a
trace stores, standard library only) it gives the same scores as checks.py on the langchain messages."""
from __future__ import annotations

import copy

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from evals import checks
from evals.langsmith_online import SPECS, build_code
from evals.trajectory import RunRecord, Trajectory

from test_eval_checks import Build, good_messages


def evaluator(kind):
    ns = {"__name__": f"langsmith_{kind}"}
    exec(compile(build_code(kind), kind, "exec", dont_inherit=True), ns)  # as LangSmith: no __future__ flags
    return ns["perform_eval"]


def as_run(name, msgs):
    return {"name": name, "run_type": "chain", "outputs": {"messages": [m.model_dump() for m in msgs]}}


def expected(fns, msgs):
    r = RunRecord(Trajectory.from_messages(msgs))
    return {x["key"]: x["score"] for x in (f(r) for f in fns) if x is not None}


def customer_messages():
    b = Build()
    b.msgs.append(HumanMessage("Visit the site as yourself: open_site, shop, then decide."))
    b.turn(("open_site", {}, "You are on shop.html.\nVisible links and buttons: Market Tote, About\nMoves left: 4."))
    b.turn(("click", {"target": "Market Tote", "thought": "that's the bag", "feeling": "interested"},
            "You are on tote.html.\nVisible links and buttons: Add to cart\nMoves left: 3."))
    b.turn(("click", {"target": "Checkout now", "thought": "pay", "feeling": "interested"}, "No such button."))
    b.turn(("decide", {"decision": "buy", "rating": 4, "feeling": "interested", "quote": "Nice."}, "Recorded: bought."))
    return b.done("I bought it.")


def test_generated_code_compiles_without_the_project():
    for kind in SPECS:
        code = build_code(kind)
        imports = [l for l in code.splitlines() if l.startswith(("import ", "from "))]
        assert {l.split()[1].split(".")[0] for l in imports} <= {"json", "re", "collections", "dataclasses"}, imports
        evaluator(kind)


def test_director_scores_match_checks():
    msgs = good_messages()
    got = evaluator("director")(as_run("director", msgs))
    want = expected(SPECS["director"]["checks"], msgs)
    assert got == want and len(got) >= 12
    assert all(v == 1 for k, v in got.items() if k != "efficiency")


def test_director_waits_for_the_finished_run():
    paused = good_messages()[:12]  # stopped at the owner's approval: no finish yet
    assert evaluator("director")(as_run("director", paused)) == {}


def test_director_mistake_is_caught():
    msgs = copy.deepcopy(good_messages())
    c = next(m for m in msgs if isinstance(m, AIMessage) and m.tool_calls and m.tool_calls[0]["name"] == "cast_personas")
    c.tool_calls[0]["args"]["archetypes"] = ["price-sensitive"] * 5
    assert evaluator("director")(as_run("director", msgs))["cast_rules"] == 0


def test_customer_scores_match_checks_and_names():
    msgs = customer_messages()
    want = expected(SPECS["customer"]["checks"], msgs)
    assert want["clicks_visible_targets"] == 0.5 and want["decided_with_tool"] == 1
    ev = evaluator("customer")
    for name in ("customer:Ana", "p3-maya", "a1-claude-agent"):
        assert ev(as_run(name, msgs)) == want
    assert ev(as_run("PatchToolCalls-x", msgs)) == {}  # caught by the rule's like() filter, not a customer


def test_helpers():
    b = Build()
    b.turn(("read_file", {"file_path": "/sessions/p1.md"}, "..."))
    b.turn(("cast_personas", {"n": 2}, "Cast 2"))
    msgs = b.done("Looks balanced.\nSPAWN: none")
    ev = evaluator("helpers")
    assert ev(as_run("critic", msgs)) == {"only_file_tools": 0, "spawn_line": 1}
    assert ev(as_run("briefer", msgs)) == {"only_file_tools": 0}
    orchestrator = Build().turn(("task", {"subagent_type": "evolver"}, "done")).done("ok")
    assert ev(as_run("analyst", orchestrator)) == {}


def test_langchain_serialized_messages_are_read_too():
    from langchain_core.load import dumpd
    msgs = customer_messages()
    run = {"name": "customer:Ana", "outputs": {"messages": [dumpd(m) for m in msgs]}}
    assert evaluator("customer")(run) == expected(SPECS["customer"]["checks"], msgs)
    assert checks.CUSTOMER_CHECKS  # the pytest evals keep their own full list
