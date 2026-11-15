"""The customer subagent (the director's p*/a* subagents) shopping a fake store with a real model.

    .venv/bin/python -m pytest evals/test_customer.py -v
    EVAL_CUSTOMER_MODELS=Claude,Gemini,GPT .venv/bin/python -m pytest evals/test_customer.py -v   # compare families
"""
from __future__ import annotations

import os

import pytest
from langsmith import testing as t

from . import checks, judges
from .conftest import expect, record
from .fixtures import CUSTOMER_SCENARIOS
from .harness import run_customer, sandbox

pytestmark = pytest.mark.langsmith
FAMILIES = [m.strip() for m in (os.getenv("EVAL_CUSTOMER_MODELS") or "Claude").split(",") if m.strip()]


@pytest.fixture(scope="module", params=[(s, f) for s in CUSTOMER_SCENARIOS for f in FAMILIES], ids=lambda p: f"{p[0]}-{p[1]}")
def run(request, tmp_path_factory):
    scenario, family = request.param
    root = tmp_path_factory.mktemp(f"customer-{scenario}-{family}")
    with sandbox(root):
        r = run_customer(scenario, root, family)
    r.meta["subject"] = f"customer:{scenario}:{family}"
    return r


def _log(run):
    t.log_inputs({"persona": run.meta["persona"], "price": run.meta["price"]})
    t.log_outputs({"visit": run.meta["visit_text"], "outcome": run.meta["decision"].get("outcome"), "error": run.meta["error"]})


@pytest.mark.parametrize("check", checks.CUSTOMER_CHECKS, ids=lambda f: f.__name__)
def test_tool_calling(run, check):
    _log(run)
    lo = checks.CUSTOMER_MIN.get(check.__name__, 1.0)
    expect(record(run.meta["subject"], check(run), lo), lo)


def test_in_character(run):
    _log(run)
    expect(record(run.meta["subject"], judges.judge_customer(run.meta["persona"], run.meta["visit_text"]), 0.6), 0.6)
