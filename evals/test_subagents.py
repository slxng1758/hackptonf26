"""The director's helper subagents, one at a time, each on a fixture sim folder with known answers.

briefer / segmenter / critic / analyst run as the director's own compiled subagent graphs (same prompt, same inherited
tools, same middleware as in production); the evolver runs as DirectorJob.evolve builds it.
    .venv/bin/python -m pytest evals/test_subagents.py -v -k critic
"""
from __future__ import annotations

import pytest
from langsmith import testing as t

from . import checks, fixtures as fx, judges
from .conftest import expect_all
from .harness import run_evolver, run_helper, sandbox

pytestmark = pytest.mark.langsmith


def _run(tmp_path_factory, name, fn):
    with sandbox(tmp_path_factory.mktemp(name)):
        return fn()


def _check(subject, run, *pairs):
    """pairs: (result, min score). Every result is recorded before any assertion."""
    t.log_inputs({"subagent": subject, "files": sorted(fx.subagent_files(subject))})
    t.log_outputs({"tool_calls": run.traj.labels(), "reply": run.traj.final_text})
    expect_all(f"subagent:{subject}", list(pairs))


# ---------------------------------------------------------------- briefer

@pytest.fixture(scope="module")
def briefer(tmp_path_factory):
    return _run(tmp_path_factory, "briefer", lambda: run_helper("briefer", fx.subagent_files("briefer")))


def test_briefer_tool_calls(briefer):
    _check("briefer", briefer, (checks.only_file_tools(briefer), 1),
           (checks.read_before_write(briefer, ("site.md",), ("product.md", "world.md")), 1),
           (checks.brief_files(briefer), 1), (checks.reply_length(briefer, 80), 0.8))


def test_briefer_judge(briefer):
    brief = briefer.files.get("product.md", "") + "\n\n---\n" + briefer.files.get("world.md", "")
    _check("briefer", briefer, (judges.judge_brief(fx.SITE_MD, brief, fx.SITE_UNCLEAR), 0.7))


# ---------------------------------------------------------------- segmenter

@pytest.fixture(scope="module")
def segmenter(tmp_path_factory):
    return _run(tmp_path_factory, "segmenter", lambda: run_helper("segmenter", fx.subagent_files("segmenter")))


def test_segmenter_tool_calls(segmenter):
    _check("segmenter", segmenter, (checks.only_file_tools(segmenter), 1),
           (checks.read_before_write(segmenter, ("product.md", "site.md"), ("segments.md",)), 1),
           (checks.segments_valid(segmenter), 1), (checks.reply_length(segmenter, 100), 0.8))


def test_segmenter_judge(segmenter):
    out = segmenter.files.get("segments.md", "") + "\n\nReply: " + segmenter.traj.final_text
    _check("segmenter", segmenter, (judges.judge_segments(fx.PRODUCT_MD, out), 0.6))


# ---------------------------------------------------------------- critic: planted problems

@pytest.fixture(scope="module")
def critic(tmp_path_factory):
    return _run(tmp_path_factory, "critic", lambda: run_helper("critic", fx.subagent_files("critic")))


def test_critic_tool_calls(critic):
    _check("critic", critic, (checks.only_file_tools(critic), 1),
           (checks.read_before_write(critic, ("personas", "sessions", "summary"), ()), 1),
           (checks.spawn_line(critic), 1), (checks.reply_length(critic, 120), 0.8))


def test_critic_catches_planted_problems(critic):
    _check("critic", critic, (judges.judge_critic(fx.CRITIC_PLANTED, critic.traj.final_text), 0.75))


# ---------------------------------------------------------------- analyst: known facts

@pytest.fixture(scope="module")
def analyst(tmp_path_factory):
    return _run(tmp_path_factory, "analyst", lambda: run_helper("analyst", fx.subagent_files("analyst")))


def test_analyst_tool_calls(analyst):
    _check("analyst", analyst, (checks.only_file_tools(analyst), 1),
           (checks.read_before_write(analyst, ("sessions",), ()), 1), (checks.reply_length(analyst, 180), 0.8))


def test_analyst_grounded(analyst):
    data = "\n\n".join(f"## /{k}\n{v}" for k, v in fx.subagent_files("analyst").items() if k.startswith(("personas/", "sessions/")))
    _check("analyst", analyst, (judges.judge_analyst(data, fx.ANALYST_FACTS, analyst.traj.final_text), 0.7))


# ---------------------------------------------------------------- evolver: memory from sessions + accuracy feedback

EVOLVE_ARCH = sorted({p["archetype"] for p in fx.ANALYST_PERSONAS if p["id"] in fx.EVOLVER_IDS})


@pytest.fixture(scope="module")
def evolver(tmp_path_factory):
    focus = fx.EVOLVER_EVALS_MD.split("\n", 2)[-1]
    return _run(tmp_path_factory, "evolver", lambda: run_evolver(fx.subagent_files("evolver"), fx.EVOLVER_IDS, focus, EVOLVE_ARCH))


def test_evolver_tool_calls(evolver):
    _check("evolver", evolver,
           (checks.read_before_write(evolver, ("sessions",), tuple(f"memories/business/{pid}.md" for pid in fx.EVOLVER_IDS)), 1),
           (checks.evolver_memory(evolver, fx.EVOLVER_IDS, "Harbor Canvas", EVOLVE_ARCH), 0.75))


def test_evolver_grounded(evolver):
    inputs = "\n\n".join(f"## /{k}\n{v}" for k, v in fx.subagent_files("evolver").items()
                         if k.startswith(("personas/", "sessions/", "evals", "owner")))
    memory = "\n\n".join(f"## {k}\n{v}" for k, v in evolver.files.items() if k.startswith("memories/"))
    _check("evolver", evolver, (judges.judge_evolver(inputs, memory), 0.6))
