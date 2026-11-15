"""Run the real agents in a sandbox and record what they did.

  run_director   the director deep agent end to end in stub mode: the director and its briefer/segmenter/critic subagents
                 are the real models making real decisions; browsing, scoring, social and evolving return fixtures
  run_helper     one of the director's own compiled subagent graphs (exactly what `task` runs: same prompt, inherited
                 tools, middleware), on a fixture sim folder
  run_evolver    the evolver deep agent (as DirectorJob.evolve builds it) on fixture sessions + accuracy feedback
  run_customer   a customer subagent (its real deepagents spec) shopping a fake store: no browser, real model

Everything writes to a temp folder: sims, the memory store, the checkpointer. MongoDB and embeddings are off.
"""
from __future__ import annotations

import inspect
from contextlib import contextmanager
from pathlib import Path

import pytest
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from b2a import customer, director, memory, mongo, outcome, sim

from .fixtures import CUSTOMER_SCENARIOS, DIRECTOR_SCENARIOS, STORE_URL, TOTE, store
from .trajectory import RunRecord, Trajectory, text_of


@contextmanager
def sandbox(root: Path):
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.store.memory import InMemoryStore
    root.mkdir(parents=True, exist_ok=True)
    saver = InMemorySaver()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sim, "SIMS", root / "sims")
        mp.setattr(mongo, "mirror", lambda v: None)
        mp.setattr(mongo, "enabled", lambda: False)
        mp.setattr(mongo, "can_embed", lambda: False)
        mp.setattr(memory, "_store", InMemoryStore())
        mp.setattr(memory, "FILE", root / "memory_store.json")
        mp.setattr(memory, "EXTRA_FILE", root / "memory_store_extra.json")
        mp.setattr(director, "checkpointer", lambda: saver)
        mp.setattr(director, "persona_models", lambda: {m: None for m in ("Claude", "GPT", "Gemini")})
        yield


def _files(d: Path) -> dict[str, str]:
    return {p.relative_to(d).as_posix(): p.read_text(errors="replace") for p in d.rglob("*")
            if p.is_file() and p.suffix in (".md", ".json") and p.name != "sim.json"}


def subagent_graphs(agent) -> dict:
    """The compiled subagent graphs a deep agent's `task` tool runs (deepagents 0.7.x keeps them in its closure)."""
    task = agent.nodes["tools"].bound.tools_by_name["task"]
    return inspect.getclosurevars(task.func).nonlocals["subagent_graphs"]


# ---------------------------------------------------------------- director

def run_director(name: str, model=None) -> RunRecord:
    """Call inside sandbox(). Plays the owner: gives the scenario's corrections in order, then approves."""
    sc = DIRECTOR_SCENARIOS[name]
    job = director.DirectorJob({**sc["inp"], "stub": True}, model=model)

    def resume(value):  # synchronous, so the eval waits for the whole run
        job.status = "resuming"
        job._drive(Command(resume=value))
    job._resume = resume

    job.cast()
    feedback = list(sc["owner_feedback"])
    for _ in range(5):
        if job.status != "awaiting_approval":
            break
        if feedback:
            job.cast(feedback.pop(0))
        else:
            job.approve(None)
    state = (job._agent or job._build()).get_state(job.cfg)
    traj = Trajectory.from_messages(state.values.get("messages", []))
    return RunRecord(traj, job.view(), _files(job.dir), {
        "scenario": {"name": name, "business": sc["inp"], "owner_feedback": sc["owner_feedback"],
                     "real_outcomes": "fixture scores (stub mode): error falls for 2 loops, then flattens"},
        "owner_feedback": sc["owner_feedback"], "has_truth": True, "status": job.status, "error": job.error, "dir": str(job.dir)})


# ---------------------------------------------------------------- the director's helper subagents

TASKS = {  # what the director typically sends each one
    "briefer": "Read /site.md and write /product.md and /world.md.",
    "segmenter": "Decide the customer segments for this product from /product.md and write /segments.md.",
    "critic": "Can the results of this simulation be trusted? Check the personas, sessions and summary.",
    "analyst": "Analyze every session: where people got stuck, why they left, what convinced buyers, AI agents vs customers.",
}


def _job_with(files: dict[str, str]) -> director.DirectorJob:
    job = director.DirectorJob({**TOTE, "stub": True})  # brain(): the production model
    for rel, text in files.items():
        p = job.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return job


def run_helper(name: str, files: dict[str, str], task: str | None = None) -> RunRecord:
    """Call inside sandbox(). Runs the director's own compiled `name` subagent, as `task` would."""
    job = _job_with(files)
    graph = subagent_graphs(job._build())[name]
    out = graph.invoke({"messages": [HumanMessage(task or TASKS[name])]},
                       config={"recursion_limit": 60, "run_name": f"eval:{name}", "tags": ["eval", name]})
    return RunRecord(Trajectory.from_messages(out["messages"]), job.view(), _files(job.dir), {"subagent": name})


def run_evolver(files: dict[str, str], ids: list[str], focus: str, archetypes: list[str]) -> RunRecord:
    """Call inside sandbox(). The evolver exactly as DirectorJob.evolve builds it (job._sub), returning its messages."""
    from deepagents import create_deep_agent
    job = _job_with(files)
    agent = create_deep_agent(model=job._brain(), system_prompt=director.EVOLVER.format(focus=focus), subagents=[],
                              backend=job._backend(), store=memory.store())
    out = agent.invoke({"messages": [HumanMessage(f"Update the memory of: {', '.join(ids)}.")]},
                       config={"recursion_limit": 80, "run_name": "eval:evolver", "tags": ["eval", "evolver"]})
    files_after = _files(job.dir)
    for pid in ids:
        files_after[f"memories/business/{pid}.md"] = memory.business_read(job.ns, pid)[0]
    for a in archetypes:
        files_after[f"memories/{a.replace(' ', '-')}.md"] = memory.for_archetype(a)
    return RunRecord(Trajectory.from_messages(out["messages"]), job.view(), files_after, {"subagent": "evolver"})


# ---------------------------------------------------------------- customer subagent on a fake store

class FakeBrowser:
    """BrowserSession's interface over a dict of pages, so customers shop with real models and no Playwright."""

    def __init__(self, pages: dict, base: str):
        self.pages, self.base, self.cur, self.history = pages, base, "home", []

    def do(self, fn, *args, timeout: float = 120):
        return fn(*args)

    def close(self):
        pass

    def _url(self, key: str) -> str:
        return self.base if key == "home" else self.base + key

    def goto(self, url: str):
        self.cur = "home"

    def look(self, shot: Path) -> dict:
        title, text, targets = self.pages[self.cur]
        url = self._url(self.cur)
        return {"url": url, "title": title, "targets": {t: self._url(k) for t, k in targets.items()}, "text": text, "jpg": b"",
                "blocked": False, "order_done": outcome.order_confirmed(text, outcome.order_possible(url))}

    def disabled(self, t: str) -> bool:
        return False

    def click(self, t: str, targets: dict) -> dict:
        here = self.pages[self.cur][2]
        tl = t.lower()
        key = here.get(t) or next((k for x, k in here.items() if x.lower() == tl), None) \
            or next((k for x, k in here.items() if tl in x.lower() or x.lower() in tl), None)
        if key is None:
            raise LookupError(f"nothing called {t!r} on this page")
        if key != self.cur:
            self.history.append(self.cur)
        self.cur = key
        return {"unchanged": False}

    def scroll(self):
        pass

    def back(self, home: str):
        self.cur = self.history.pop() if self.history else "home"

    def search(self, query: str) -> bool:
        return False


def run_customer(name: str, root: Path, family: str = "Claude") -> RunRecord:
    """Call inside sandbox(). The customer's real deepagents subagent (prompt, tools, middleware, read-only files)."""
    from deepagents import create_deep_agent
    sc = CUSTOMER_SCENARIOS[name]
    p = {**sc["persona"], "model": family, "memory": ""}
    pages = store(sc["price"])
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(customer, "BrowserSession", lambda: FakeBrowser(pages, STORE_URL))
        host = customer._OneCustomer(p, STORE_URL, "today, normal times", "new: free shipping over $40 (was $75)",
                                     root / "shots" / name, lambda cid, step: None, customer.MAX_STEPS, "")
        spec = customer.customer_subagent(p, host)
        backend = memory.backend_for(root, memory.business_ns(STORE_URL, "eval"))  # the director's backend: sim files + /memories/
        parent = create_deep_agent(model=spec["model"], subagents=[spec], backend=backend, store=memory.store())
        graph = subagent_graphs(parent)[spec["name"]]
        err = ""
        try:
            out = graph.invoke({"messages": [HumanMessage("Visit the site as yourself and decide.")]},
                               config={"recursion_limit": 4 * customer.MAX_STEPS + 12, "run_name": f"eval:customer:{name}",
                                       "tags": ["eval", "customer"]})
            msgs = out["messages"]
        except Exception as e:  # e.g. recursion limit: still grade what it did
            msgs, err = [], f"{type(e).__name__}: {e}"[:200]
        if not host.v:
            host.begin(p["id"])
        forced = host.v.decision is None
        if forced:
            host.v.notes.append("(the visit stopped without a decision)")
            host.v.force_decision()
        host.v.close()
        r = host.v.result()
    visit = "\n".join(f"step {s['n']} [{s['url'].replace(STORE_URL, '/')}] ({s['feeling']}) {s['thought']} -> {s['action']} {s['target']}"
                      for s in r["steps"])
    d = r["decision"]
    visit += (f"\nDECISION: {d['decision']} ({d['rating']}/5, outcome {d.get('outcome')}). Quote: {d.get('quote')}\n"
              f"Reasons: {d.get('reasons')}\nLiked: {d.get('liked')} Disliked: {d.get('disliked')}\nWould pay: {d.get('would_pay')}\n"
              f"Review: {d.get('review')}")
    return RunRecord(Trajectory.from_messages(msgs), {}, {}, {
        "persona": p, "price": sc["price"], "decision": d, "steps": r["steps"], "can_order": outcome.order_possible(STORE_URL),
        "forced": forced, "expect_outcomes": sc["expect"], "visit_text": visit, "error": err,
        "final_text": text_of(msgs[-1].content) if msgs else ""})
