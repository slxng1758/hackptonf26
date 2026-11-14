"""The deep agent: segment customers, test the listing on real AI shoppers, diagnose, rewrite from the business's own facts, re-test, remember.

Deep Agents features in use:
  planning     write_todos, shown live in the UI
  sub-agents   critic (why agents said no) and rewriter (facts-only rewrite), each with its own context
  filesystem   every test is written to /tests, the business facts to /facts.md; sub-agents read them, the agent writes /report.md
  memory       lessons persist in runs/memory.md and are loaded into every future job
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_core.tools import tool

from . import market, personas
from .models import brain, shoppers

RUNS = Path(__file__).resolve().parent.parent / "runs"
JOBS_DIR = RUNS / "jobs"
MEMORY = RUNS / "memory.md"
MAX_TESTS = 3

AGENT = """You help a business get chosen by AI shopping agents.

Business: {name} ({category})
Their current listing: "{listing}"
Their confirmed facts are in /facts.md. Competitors are fixed. You can only change the business's listing.

Lessons from past jobs:
{memory}

Steps, keep your todo list updated:
1. Call segment_customers once.
2. Call test_listing with the current listing. This is the baseline.
3. Ask the critic to explain why shopping agents chose competitors.
4. Ask the rewriter for a new listing built only from /facts.md.
5. Call test_listing with the new listing. If the pick rate did not clearly improve, do one more critic + rewriter round ({max_tests} tests max).
6. Call remember with one or two general lessons about what makes AI shopping agents choose a listing.
7. Write /report.md: the pick rate of EVERY test you ran (use the numbers test_listing returned), the best listing, what changed and why, and "Worth adding if true": facts the business
   did not give but that buyers asked for (never put these in the listing itself).
Reply with one sentence."""

CRITIC = ("You explain why AI shopping agents chose competitors over the business. Read the JSON files in /tests and /facts.md. "
          "In at most 120 words: which customer segments and requests were lost, which competitor won them, and which concrete facts "
          "the winners stated that the business's listing left out. Separate facts the business HAS (in /facts.md) from facts it does not.")
REWRITER = ("You rewrite a business listing so AI shopping agents can match it to customer requests. Read /facts.md and the critic's notes. "
            "Use ONLY facts from /facts.md. Never invent prices, limits, speeds or ratings, and never copy a competitor's claims. "
            "Write full sentences with the numbers from the facts, most buyer-relevant first, at most 90 words. Reply with only the listing.")


class Job:
    def __init__(self, inp: dict):
        self.id = datetime.now().strftime("%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        self.inp = inp
        self.status, self.error, self.report = "running", None, ""
        self.steps: list[dict] = []
        self.segments: list[dict] = []
        self.tests: list[dict] = []
        self.live: list[dict] = []
        self.lessons: list[str] = []
        self.dir = JOBS_DIR / self.id
        (self.dir / "tests").mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def log(self, kind: str, note: str):
        with self._lock:
            self.steps.append({"t": datetime.now().strftime("%H:%M:%S"), "kind": kind, "note": str(note)[:400]})
        self.save()

    def view(self) -> dict:
        return {"id": self.id, "input": self.inp, "status": self.status, "error": self.error, "steps": self.steps,
                "segments": self.segments, "tests": [{k: v for k, v in t.items() if k != "results"} for t in self.tests],
                "live": self.live[-400:], "lessons": self.lessons, "report": self.report, "shoppers": list(shoppers().keys())}

    def save(self):
        with self._lock:
            (self.dir / "job.json").write_text(json.dumps(self.view(), indent=2))

    def run(self):
        try:
            self._run()
            self.status = "done"
        except Exception as e:
            self.status, self.error = "error", f"{type(e).__name__}: {e}"[:400]
            self.log("error", self.error)
        self.save()

    def _run(self):
        job, inp = self, self.inp
        (self.dir / "facts.md").write_text("# Confirmed facts\n" + "\n".join(f"- {f}" for f in inp["facts"]) + "\n")

        @tool
        def segment_customers() -> str:
            """Split the business's customers into segments and write the requests each segment would give its AI shopping agent."""
            if not job.segments:
                job.segments = personas.segment(inp["category"], inp["customers"])
                (job.dir / "segments.json").write_text(json.dumps(job.segments, indent=2))
                job.log("segments", " · ".join(f"{s['name']} ({round(s['share'] * 100)}%)" for s in job.segments))
            return json.dumps(job.segments)

        @tool
        def test_listing(listing: str) -> str:
            """Send real AI shopping agents (several models) on every customer request with this listing in the market. Returns weighted pick rate, per-segment results and why they chose others."""
            if not job.segments:
                return "Call segment_customers first."
            if len(job.tests) >= MAX_TESTS:
                done = [{"test": t["n"], "pick_rate": round(t["pick_rate"], 3), "wins": t["wins"], "total": t["total"], "listing": t["listing"]} for t in job.tests]
                return (f"Test budget used ({MAX_TESTS}); this listing was NOT tested. Results of the tests that did run: {json.dumps(done)}. "
                        "Write the report from these results now.")
            n = len(job.tests) + 1
            job.log("test", f"test {n}: {market.clean(listing)[:160]}")
            job.live = []

            def on_result(r):
                job.live.append({"n": n, "shopper": r["shopper"], "segment": r["segment"], "won": r["picked"] == "ours", "picked": r["picked"]})
                if len(job.live) % 4 == 0:
                    job.save()

            r = market.run(listing, inp["competitors"], job.segments, seed=n, on_result=on_result)
            r["n"] = n
            job.tests.append(r)
            slim = {k: v for k, v in r.items() if k != "results"}
            slim["losses"] = [{"segment": job.segments[x["segment"]]["name"], "request": x["task"], "shopper": x["shopper"],
                               "chose": inp["competitors"][int(x["picked"][1:])].split(".")[0], "reason": x["reason"], "missing": x["missing"]}
                              for x in r["results"] if x["picked"] not in ("ours", "error")][:30]
            (job.dir / "tests" / f"test_{n}.json").write_text(json.dumps(slim, indent=2))
            job.tests[-1]["losses"] = slim["losses"]
            job.log("result", f"test {n}: picked {round(r['pick_rate'] * 100)}% (weighted by segment) · " +
                    " · ".join(f"{k} {v['wins']}/{v['total']}" for k, v in r["by_shopper"].items()))
            return json.dumps({k: v for k, v in slim.items() if k not in ("losses",)} | {"losses": slim["losses"][:12]})

        @tool
        def remember(lesson: str) -> str:
            """Save one general lesson about what makes AI shopping agents choose a listing. Future jobs will see it."""
            MEMORY.parent.mkdir(parents=True, exist_ok=True)
            with MEMORY.open("a") as f:
                f.write(f"- {lesson.strip()}\n")
            job.lessons.append(lesson.strip())
            job.log("memory", lesson)
            return "saved"

        memory = MEMORY.read_text()[-1500:] if MEMORY.exists() else "(none yet)"
        agent = create_deep_agent(
            model=brain(),
            system_prompt=AGENT.format(name=inp["name"], category=inp["category"], listing=inp["listing"], memory=memory, max_tests=MAX_TESTS),
            tools=[segment_customers, test_listing, remember],
            subagents=[
                {"name": "critic", "description": "Explains why AI shopping agents chose competitors.", "system_prompt": CRITIC},
                {"name": "rewriter", "description": "Rewrites the listing using only the business's confirmed facts.", "system_prompt": REWRITER},
            ],
            backend=FilesystemBackend(root_dir=str(self.dir), virtual_mode=True),
        )
        self.log("plan", "started")
        for update in agent.stream({"messages": [{"role": "user", "content": "Begin."}]}, config={"recursion_limit": 100}, stream_mode="updates"):
            for node in update.values():
                for m in (node or {}).get("messages", []) if isinstance(node, dict) else []:
                    for call in getattr(m, "tool_calls", None) or []:
                        a = call.get("args", {})
                        if call["name"] == "write_todos":
                            self.log("plan", " → ".join(f"{'✓ ' if t.get('status') == 'completed' else ''}{t.get('content', '')}" for t in a.get("todos", [])))
                        elif call["name"] == "task":
                            self.log(a.get("subagent_type", "subagent"), (a.get("description") or "")[:300])
                    if getattr(m, "type", "") == "tool" and getattr(m, "name", "") == "task":
                        c = m.content if isinstance(m.content, str) else json.dumps(m.content)
                        self.log("answer", c[:400])
        rp = self.dir / "report.md"
        self.report = rp.read_text() if rp.exists() else ""


JOBS: dict[str, Job] = {}


def start(inp: dict) -> Job:
    job = Job(inp)
    JOBS[job.id] = job
    job.save()
    threading.Thread(target=job.run, daemon=True).start()
    return job


def get(job_id: str):
    if job_id in JOBS:
        return JOBS[job_id].view()
    p = JOBS_DIR / Path(job_id).name / "job.json"
    return json.loads(p.read_text()) if p.exists() else None


def list_jobs():
    out = []
    for p in sorted(JOBS_DIR.glob("*/job.json"), reverse=True):
        try:
            d = json.loads(p.read_text())
            tests = d.get("tests", [])
            out.append({"id": d["id"], "name": d["input"]["name"], "status": d["status"],
                        "first": tests[0]["pick_rate"] if tests else None, "best": max((t["pick_rate"] for t in tests), default=None)})
        except Exception:
            pass
    return out


def lessons() -> list[str]:
    return [l[2:].strip() for l in MEMORY.read_text().splitlines() if l.startswith("- ")] if MEMORY.exists() else []
