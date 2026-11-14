"""B2A: will an AI shopping agent pick your listing?

Real models (the kind people actually shop with) get real buying tasks and a market of listings, including yours.
They choose one and say why. We measure your pick rate and collect the reasons you lost. Then a deep agent
critiques and rewrites your listing, re-tests it, and remembers what worked for next time.

Nothing about the shoppers is simulated: for B2A, the agent is the customer.
"""
from __future__ import annotations

import json
import os
import random
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from .models import _ensure_anthropic_key, evaluator_model

ROOT = Path(__file__).resolve().parent.parent / "runs" / "b2a"
MEMORY = ROOT / "memory" / "learnings.md"

# ---------- demo market: commercial truck insurance (all companies fictional) ----------
DEMO = {
    "name": "Commercial truck insurance",
    "ours": (
        "Ironline Commercial Auto. Insurance for trucking businesses. We offer competitive rates and great service. "
        "Get a quote today. Liability, cargo and physical damage available."
    ),
    "competitors": [
        "Roadstar Truck Insurance. Primary liability from $1M, cargo up to $250k including reefer breakdown. "
        "New authorities welcome (0-12 months). Online quote in 10 minutes, certificate of insurance same day. Owner-operators from $780/month.",
        "Bluehaul Fleet Cover. Built for fleets of 5-50 power units. Telematics discount up to 15%. Liability $1M-$2M, cargo $100k, "
        "physical damage stated value. Dedicated claims adjuster, 24/7 FNOL hotline.",
        "Cardinal Freight Protect. Low-cost liability meeting the FMCSA $750k minimum for owner-operators. Monthly pay, no down payment. "
        "Cargo add-on $100k. Quote by phone only, business hours.",
        "Summit Mutual Commercial. A-rated carrier (AM Best A). Liability, cargo, physical damage, non-trucking liability and occupational "
        "accident in one policy. Discounts for 3+ years authority and clean CSA scores.",
    ],
    "tasks": [
        "I'm an owner-operator with one truck and new authority (4 months). Find me insurance I can actually get approved for and buy online today.",
        "I run 8 reefer trucks hauling produce. I need cargo coverage that includes refrigeration breakdown. Pick the best fit.",
        "Cheapest insurance that meets the federal minimum for one truck. I don't care about extras.",
        "I need a certificate of insurance today so a broker will load me tomorrow. Which provider should I use?",
        "We're a 12-truck fleet with telematics in every cab. Find the policy that gives us the best value.",
        "I want one policy that covers liability, cargo, physical damage and occupational accident with a strong carrier. Choose for me.",
    ],
}


class Choice(BaseModel):
    pick: int = Field(description="the number of the listing you choose")
    reason: str = Field(description="one sentence: why this one")
    missing: str = Field(description="one sentence: what the listings you rejected failed to tell you, if anything")


SHOP = """You are an AI shopping agent acting for a customer. Customer's request:
"{task}"

Here are the options you found:
{listings}

Choose the single best option for this customer, based only on what the listings say. Be decisive."""


def shoppers() -> dict:
    """Real models people shop with. Each is optional, depending on which keys are present."""
    out = {}
    _ensure_anthropic_key()
    if os.getenv("ANTHROPIC_API_KEY"):
        from langchain_anthropic import ChatAnthropic
        out["Claude"] = ChatAnthropic(model=os.getenv("CLAUDE_SHOPPER_MODEL", "claude-haiku-5-5"), max_tokens=600, timeout=60, max_retries=2)
    if os.getenv("OPENAI_API_KEY"):
        from langchain_openai import ChatOpenAI
        out["GPT"] = ChatOpenAI(model=os.getenv("OPENAI_SHOPPER_MODEL", "gpt-5.4-mini"), timeout=60, max_retries=2)
    if os.getenv("GOOGLE_API_KEY"):
        from langchain_google_genai import ChatGoogleGenerativeAI
        out["Gemini"] = ChatGoogleGenerativeAI(model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"), timeout=60, max_retries=2)
    return out


import re as _re


def to_confirm(listing: str) -> list[str]:
    """Claims the rewriter added that the business has not stated yet."""
    return [m.strip(" .;,") for m in _re.findall(r"\[confirm\]\s*([^.\n\[]+)", listing)]


def clean(listing: str) -> str:
    """What a shopper would actually read: no internal [confirm] markers."""
    return _re.sub(r"\s*\[confirm\]\s*", " ", listing).strip()


def market_test(ours: str, competitors: list[str], tasks: list[str], orders: int = 2, seed: int = 0, log=None) -> dict:
    """Every shopper x every task x a few shuffled orders (to cancel position bias). Returns pick rate and why we lost."""
    rng = random.Random(seed)
    models = shoppers()
    jobs = []
    for name, model in models.items():
        for ti, task in enumerate(tasks):
            for o in range(orders):
                items = [("ours", clean(ours))] + [(f"c{i}", c) for i, c in enumerate(competitors)]
                rng.shuffle(items)
                jobs.append((name, model, ti, task, items))

    def run(job):
        name, model, ti, task, items = job
        listings = "\n".join(f"{i + 1}. {text}" for i, (_, text) in enumerate(items))
        try:
            c: Choice = model.with_structured_output(Choice).invoke(SHOP.format(task=task, listings=listings))
            idx = max(1, min(len(items), c.pick)) - 1
            return {"shopper": name, "task": ti, "picked": items[idx][0], "ours_pos": [k for k, _ in items].index("ours") + 1,
                    "reason": c.reason, "missing": c.missing}
        except Exception as e:
            return {"shopper": name, "task": ti, "picked": "error", "reason": f"{type(e).__name__}", "missing": ""}

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(run, jobs))
    ok = [r for r in results if r["picked"] != "error"]
    wins = [r for r in ok if r["picked"] == "ours"]
    by_shopper = {n: {"wins": sum(1 for r in ok if r["shopper"] == n and r["picked"] == "ours"), "total": sum(1 for r in ok if r["shopper"] == n)} for n in models}
    by_task = [{"task": t, "wins": sum(1 for r in ok if r["task"] == i and r["picked"] == "ours"), "total": sum(1 for r in ok if r["task"] == i)} for i, t in enumerate(tasks)]
    winners = {}
    for r in ok:
        if r["picked"] != "ours":
            winners[r["picked"]] = winners.get(r["picked"], 0) + 1
    out = {
        "pick_rate": len(wins) / max(1, len(ok)), "wins": len(wins), "total": len(ok), "errors": len(results) - len(ok),
        "by_shopper": by_shopper, "by_task": by_task,
        "lost_to": sorted(({"competitor": int(k[1:]), "times": v} for k, v in winners.items()), key=lambda x: -x["times"]),
        "losses": [{"shopper": r["shopper"], "task": tasks[r["task"]], "reason": r["reason"], "missing": r["missing"]} for r in ok if r["picked"] != "ours"][:24],
        "wins_why": [{"shopper": r["shopper"], "task": tasks[r["task"]], "reason": r["reason"]} for r in wins][:12],
    }
    if log:
        log("result", f"pick rate {round(out['pick_rate'] * 100)}% ({out['wins']}/{out['total']})" + "".join(f" · {n} {d['wins']}/{d['total']}" for n, d in by_shopper.items()))
    return out


# ---------- the deep agent that improves the listing ----------
AGENT = """You help a business win AI shopping agents (B2A). Your client's listing:
"{ours}"

Market: {name}. Competitors and real buyer tasks are fixed; you can only change the client's listing.
What you learned on past jobs (may be empty):
{memory}

Work like this and keep your todo list updated:
1. Call test_listing on the original listing. This is the baseline.
2. Ask the critic to read /tests and explain why shopping agents rejected the listing.
3. Ask the rewriter for an improved listing. It must stay truthful: only state things the business can do. Mark any new
   claim the business must confirm with [confirm], e.g. "[confirm] certificate of insurance same day".
4. Call test_listing on the rewrite. If the pick rate did not clearly improve, do one more critic and rewriter round (max 3 tests).
5. Call remember with one or two general lessons about what makes shopping agents choose a listing.
6. Write /report.md: the best listing, the pick rate for each test, what changed, and which claims the business must confirm.
Reply with one sentence."""

CRITIC = ("You analyze why AI shopping agents rejected a listing. Read the JSON files in /tests. In at most 120 words: which buyer "
          "tasks lost, which competitor won them and the concrete facts that competitor stated that the client's listing did not.")
REWRITER = ("You rewrite a business listing so AI shopping agents can match it to buyer tasks. Read the critic's notes. Write ONE listing "
            "(max 90 words): concrete facts (coverage amounts, who it is for, how fast, how to buy), no vague claims. Never invent facts: "
            "put [confirm] before any claim the business has not stated. Reply with only the listing text.")


class Job:
    def __init__(self, ours: str, market: dict):
        self.id = datetime.now().strftime("%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        self.ours, self.market = ours, market
        self.status, self.error, self.report = "running", None, ""
        self.steps: list[dict] = []
        self.tests: list[dict] = []
        self.dir = ROOT / self.id
        (self.dir / "tests").mkdir(parents=True, exist_ok=True)
        MEMORY.parent.mkdir(parents=True, exist_ok=True)

    def log(self, kind, note):
        self.steps.append({"t": datetime.now().strftime("%H:%M:%S"), "kind": kind, "note": str(note)[:320]})
        self.save()

    def summary(self):
        return {"id": self.id, "ours": self.ours, "market": self.market, "status": self.status, "error": self.error,
                "steps": self.steps, "tests": self.tests, "report": self.report,
                "shoppers": list(shoppers().keys())}

    def save(self):
        (self.dir / "job.json").write_text(json.dumps(self.summary(), indent=2))

    def run(self):
        try:
            self._run()
            self.status = "done"
        except Exception as e:
            self.status, self.error = "error", f"{type(e).__name__}: {e}"[:400]
            self.log("error", self.error)
        self.save()

    def _run(self):
        job, m = self, self.market

        @tool
        def test_listing(listing: str) -> str:
            """Run real AI shopping agents on every buyer task with this listing in the market. Returns pick rate, losses and reasons."""
            if len(job.tests) >= 3:
                return "Test budget used (3). Write the report now."
            job.log("test", f"testing listing {len(job.tests) + 1}: \"{listing[:140]}…\"")
            r = market_test(listing, m["competitors"], m["tasks"], log=job.log, seed=len(job.tests))
            r["listing"] = clean(listing)
            r["to_confirm"] = to_confirm(listing)
            job.tests.append(r)
            (job.dir / "tests" / f"test_{len(job.tests)}.json").write_text(json.dumps(r, indent=2))
            return json.dumps({k: v for k, v in r.items() if k != "wins_why"})

        @tool
        def remember(lesson: str) -> str:
            """Save one general lesson about what makes AI shopping agents choose a listing. It is shown on future jobs."""
            with MEMORY.open("a") as f:
                f.write(f"- {lesson.strip()}\n")
            job.log("memory", lesson)
            return "saved"

        memory = MEMORY.read_text() if MEMORY.exists() else "(nothing yet)"
        agent = create_deep_agent(
            model=evaluator_model(),
            system_prompt=AGENT.format(ours=self.ours, name=m["name"], memory=memory[-1500:]),
            tools=[test_listing, remember],
            subagents=[
                {"name": "critic", "description": "Explains why shopping agents rejected the listing.", "system_prompt": CRITIC},
                {"name": "rewriter", "description": "Rewrites the listing so agents can match it to buyer tasks.", "system_prompt": REWRITER},
            ],
            backend=FilesystemBackend(root_dir=str(self.dir), virtual_mode=True),
        )
        (self.dir / "market.json").write_text(json.dumps(m, indent=2))
        self.log("plan", "agent started")
        for update in agent.stream({"messages": [{"role": "user", "content": "Begin."}]}, config={"recursion_limit": 100}, stream_mode="updates"):
            for node in update.values():
                for msg in (node or {}).get("messages", []) if isinstance(node, dict) else []:
                    for call in getattr(msg, "tool_calls", None) or []:
                        a = call.get("args", {})
                        if call["name"] == "write_todos":
                            self.log("plan", " → ".join(f"{'✓ ' if t.get('status') == 'completed' else ''}{t.get('content', '')}" for t in a.get("todos", [])))
                        elif call["name"] == "task":
                            self.log(a.get("subagent_type", "subagent"), (a.get("description") or "")[:240])
                    if getattr(msg, "type", "") == "tool" and getattr(msg, "name", "") == "task":
                        c = msg.content if isinstance(msg.content, str) else json.dumps(msg.content)
                        self.log("answer", c[:320])
        rp = self.dir / "report.md"
        self.report = rp.read_text() if rp.exists() else ""


JOBS: dict[str, Job] = {}


def start(ours: str | None = None, market: dict | None = None) -> Job:
    m = {**DEMO, **(market or {})}
    job = Job(ours or m["ours"], m)
    JOBS[job.id] = job
    job.save()
    threading.Thread(target=job.run, daemon=True).start()
    return job


def get(job_id: str):
    if job_id in JOBS:
        return JOBS[job_id].summary()
    p = ROOT / Path(job_id).name / "job.json"
    return json.loads(p.read_text()) if p.exists() else None


def list_jobs():
    out = []
    for p in sorted(ROOT.glob("*/job.json"), reverse=True):
        try:
            d = json.loads(p.read_text())
            out.append({"id": d["id"], "ours": d["ours"][:80], "status": d["status"], "tests": len(d["tests"])})
        except Exception:
            pass
    return out


if __name__ == "__main__":
    r = market_test(DEMO["ours"], DEMO["competitors"], DEMO["tasks"], log=lambda k, n: print(k, n))
    print(json.dumps({k: r[k] for k in ("pick_rate", "by_shopper", "lost_to")}, indent=2))
    for l in r["losses"][:6]:
        print("-", l["shopper"], "|", l["reason"], "| missing:", l["missing"])
