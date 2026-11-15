"""The director deep agent, end to end (stub mode: real director + briefer/segmenter/critic, fixture customers).

One run per scenario (module-scoped), then every tool-calling check and every judge grades that same run.
    .venv/bin/python -m pytest evals/test_director.py -v            # both scenarios
    .venv/bin/python -m pytest evals/test_director.py -v -k happy   # one
"""
from __future__ import annotations

import pytest
from langsmith import testing as t

from . import checks, judges
from .conftest import expect, record
from .fixtures import DIRECTOR_SCENARIOS
from .harness import run_director, sandbox

pytestmark = pytest.mark.langsmith


@pytest.fixture(scope="module", params=list(DIRECTOR_SCENARIOS))
def run(request, tmp_path_factory):
    with sandbox(tmp_path_factory.mktemp(f"director-{request.param}")):
        return run_director(request.param)


def _log(run):
    t.log_inputs(run.meta["scenario"])
    t.log_outputs({"status": run.meta["status"], "error": run.meta["error"], "tool_calls": run.traj.labels(),
                   "final_reply": run.traj.final_text, "summary": run.view.get("summary"), "dir": run.meta["dir"]})


def test_run_completes(run):
    _log(run)
    r = record(f"director:{run.meta['scenario']['name']}",
               checks.res("completed", run.meta["status"] == "done" and not run.meta["error"], f"{run.meta['status']} {run.meta['error'] or ''}"))
    expect(r)


@pytest.mark.parametrize("check", checks.DIRECTOR_CHECKS + [judges.reference_superset], ids=lambda f: f.__name__)
def test_tool_calling(run, check):
    _log(run)
    lo = checks.DIRECTOR_MIN.get(check.__name__, 1.0)
    expect(record(f"director:{run.meta['scenario']['name']}", check(run), lo), lo)


@pytest.mark.parametrize("judge,lo", [(judges.director_judgment, 0.6), (judges.reason_quality, 0.6), (judges.final_reply, 0.6)],
                         ids=["director_judgment", "reason_quality", "final_reply"])
def test_llm_judge(run, judge, lo):
    _log(run)
    expect(record(f"director:{run.meta['scenario']['name']}", judge(run), lo), lo)
