"""Live agent evals (real models, costs money). Run:   .venv/bin/python -m pytest evals -v

Each eval result goes to LangSmith as feedback when LANGSMITH_API_KEY is set (an experiment per run, in the test suite
"hackpton-agent-evals"); without a key it runs locally. Either way the scores are written to runs/evals/<time>.json and
printed as a table at the end.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from b2a.models import _anthropic_key

if not os.getenv("LANGSMITH_API_KEY"):
    os.environ["LANGSMITH_TEST_TRACKING"] = "false"   # the @pytest.mark.langsmith tests still run, just not uploaded
os.environ.setdefault("LANGSMITH_TEST_SUITE", "hackpton-agent-evals")

RESULTS: list[dict] = []
OUT = Path(__file__).resolve().parent.parent / "runs" / "evals"


def record(subject: str, result: dict | None, min_score: float = 1.0) -> dict | None:
    """Log one eval result (LangSmith feedback + local report) and return it. None = not applicable to this run."""
    if result is None:
        return None
    from langsmith import testing as t
    t.log_feedback(key=result["key"], score=result["score"], comment=result.get("comment") or None)
    RESULTS.append({"subject": subject, **result, "min": min_score, "passed": result["score"] >= min_score})
    return result


def expect(result: dict | None, min_score: float = 1.0):
    if result is None:
        pytest.skip("not applicable to this run")
    assert result["score"] >= min_score, f"{result['key']} = {result['score']} (< {min_score}): {result['comment']}"


def expect_all(subject: str, pairs: list[tuple[dict | None, float]]):
    """Record every result first, then fail with all the misses at once."""
    got = [(record(subject, r, lo), lo) for r, lo in pairs]
    misses = [f"{r['key']} = {r['score']} (< {lo}): {r['comment']}" for r, lo in got if r is not None and r["score"] < lo]
    assert not misses, "\n".join(misses)


@pytest.fixture(scope="session", autouse=True)
def _keys():
    if not _anthropic_key():
        pytest.skip("live evals need ANTHROPIC_API_KEY")


def pytest_terminal_summary(terminalreporter):
    if not RESULTS:
        return
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"{time.strftime('%Y%m%d-%H%M%S')}.json"
    f.write_text(json.dumps(RESULTS, indent=2, default=str))
    w = terminalreporter
    w.section("agent eval scores")
    for r in RESULTS:
        mark = "PASS" if r["passed"] else "FAIL"
        w.write_line(f"{mark}  {r['score']:.2f}  (min {r['min']:.2f})  {r['subject']:28} {r['key']:24} {str(r['comment'])[:110]}")
    by = {}
    for r in RESULTS:
        by.setdefault(r["subject"], []).append(r["score"])
    w.write_line("")
    for s, v in by.items():
        w.write_line(f"  {s:28} mean {sum(v) / len(v):.2f} over {len(v)} evals")
    w.write_line(f"\nsaved {f}")
