"""Customer simulation job: cast → owner approves → every persona browses the real product → analyst + evolution.

Deep Agents features in use here:
  human-in-the-loop   the run pauses after casting until the business owner approves (or edits) the personas
  filesystem          personas/<id>.md (each persona's profile + memory, rewritten as it evolves), sessions/<id>.json
  sub-agents          analyst (reads every session, finds where people got stuck) and evolver (updates persona files)
  long-term memory    evolved personas are copied to runs/persona_library/ and reused by future simulations
"""
from __future__ import annotations

import json
import shutil
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend

from . import memory, mongo, session
from .models import brain

RUNS = Path(__file__).resolve().parent.parent / "runs"
SIMS = RUNS / "sims"
LIBRARY = RUNS / "persona_library"

BUYS = {"buy": 1.0, "would recommend": 1.0, "maybe later": 0.3, "not buy": 0.0, "would complain": 0.0}

ANALYST = """You analyze a customer simulation for a small business.
Product: {name} ({url}). What the business says changed: {context}. World: {world}.
Personas are in /personas/*.md, their real browsing sessions (every page, thought, feeling, click) in /sessions/*.json,
and what they posted about it afterwards (posts, replies, reposts, who influenced whom) in /social.json if it exists.

Do this, keeping your todo list updated:
1. Ask the analyst sub-agent to read every session and find: where people got stuck (which page, which step), what made them buy,
   what made them leave, and whether the business's claimed change was actually visible to them.
2. Ask the evolver sub-agent to update every persona file with a "## Memory" section: 1-3 concrete things this persona learned
   about this kind of product, so the next simulation starts smarter. It must also update the long-term memory in
   /memories/<archetype>.md (e.g. /memories/price-sensitive.md, spaces as hyphens): general lessons for that kind of customer
   that will help on ANY business's site, not just this one. That memory outlives this run.
3. Write /report.md for the business owner, short, with these sections: the weighted buy rate and rating, broken down by
   customer type (archetype and share); where people got stuck (which page); what convinced the buyers; the top 3 fixes
   (each tied to a persona and a page they saw); which complaint is most likely to spread by word of mouth and why (use /social.json: who replied to or reposted whom); and
   where the simulation might be wrong.
Reply with one sentence."""

ANALYST_SUB = ("You read customer browsing sessions (JSON) and persona files. Report in at most 180 words: where each persona got stuck "
               "(page + step), the most common reason to leave, what convinced buyers, and whether the business's claimed change was visible.")
EVOLVER_SUB = ("You update persona files. For every file in /personas, append or replace a '## Memory' section with 1-3 short lessons that "
               "persona learned from its session (concrete, about this kind of product). Keep the rest of the file. Edit the files directly. "
               "Then update long-term memory: for each persona's archetype, read /memories/<archetype>.md (archetype with spaces as hyphens; "
               "it may not exist yet) and rewrite it as at most 6 short bullets of general lessons for that kind of customer on any website "
               "(how they shop, what convinces or loses them). Merge with what's there, drop duplicates, never name this business.")


def persona_md(p: dict) -> str:
    return (f"# {p['name']} ({p['id']})\n\n- Age: {p['age']}\n- Occupation: {p['occupation']}\n- Archetype: {p['archetype']}\n"
            f"- Segment: {p['segment']} ({round(p['share'] * 100)}% of customers)\n- Goal: {p['goal']}\n- Budget: {p['budget']}\n- Voice: {p['voice']}\n"
            + (f"- Instructions from the owner: {p['instructions']}\n" if p.get("instructions") else "")
            + (f"- Edited by the owner\n" if p.get("custom") else "")
            + (f"\n## Memory\n{p['memory']}\n" if p.get("memory") else ""))


class SimJob:
    def __init__(self, inp: dict, sim_id: str | None = None):
        self.id = sim_id or datetime.now().strftime("%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        self.inp = inp
        self.status = "casting"
        self.error = None
        self.personas: list[dict] = []
        self.live: dict[str, list[dict]] = {}
        self.decisions: dict[str, dict] = {}
        self.summary: dict | None = None
        self.report = ""
        self.steps: list[dict] = []
        self.round = inp.get("round", 0)
        self.parent = inp.get("parent")
        self.persona_changes: list[dict] = []
        self.evals: list[dict] = list(inp.get("evals_so_far") or [])
        self.social: dict | None = None
        self.actions: list[dict] = []
        # director mode (b2a/director.py): every browsing pass, the director's reasons, its plan and budget
        self.runs: list[dict] = []
        self.director: list[dict] = []
        self.todos: list[dict] = []
        self.budget: dict | None = None
        # live feed of what the agent is doing (casting reasoning streamed token by token, steps, each persona as it's cast)
        self.thinking: list[dict] = []
        self._saved_at = 0.0
        inp["lineage"] = inp.get("lineage") or self.id  # business-memory lineage: rerun() keeps it, a fresh sim starts one
        self.dir = SIMS / self.id
        for d in ("personas", "sessions", "shots"):
            (self.dir / d).mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # ---- live feed: what the agent is doing right now (shown while customers are being cast)
    def think(self, kind: str, title: str, text: str = "", status: str = "running", **extra) -> int:
        """kind: step | reason | persona | plan | subagent | decision | owner. Returns the event's index."""
        self.thinking.append({"t": datetime.now().strftime("%H:%M:%S"), "kind": kind, "title": title, "text": text,
                              "status": status, **extra})
        self.save()
        return len(self.thinking) - 1

    def think_more(self, i: int, text: str):
        """Append streamed text to event i; saves at most ~3 times a second."""
        self.thinking[i]["text"] += text
        if time.monotonic() - self._saved_at > 0.3:
            self.save()

    def think_done(self, i: int, text: str | None = None, status: str = "done", **extra):
        ev = self.thinking[i]
        if text is not None:
            ev["text"] = text
        ev.update(status=status, **extra)
        self.save()

    def log(self, kind, note):
        self.steps.append({"t": datetime.now().strftime("%H:%M:%S"), "kind": kind, "note": str(note)[:400]})
        self.save()

    def view(self):
        evolved = {}
        for p in self.personas:
            f = self.dir / "personas" / f"{p['id']}.md"
            if f.exists() and "## Memory" in f.read_text():
                evolved[p["id"]] = f.read_text().split("## Memory", 1)[1].strip()
        return {"id": self.id, "input": self.inp, "status": self.status, "error": self.error, "personas": self.personas,
                "live": self.live, "decisions": self.decisions, "summary": self.summary, "report": self.report,
                "steps": self.steps, "memory": evolved, "round": self.round, "parent": self.parent,
                "persona_changes": self.persona_changes, "evals": self.evals, "social": self.social, "actions": self.actions,
                "runs": self.runs, "director": self.director, "todos": self.todos, "budget": self.budget,
                "thinking": self.thinking}

    def save(self):
        self._saved_at = time.monotonic()
        with self._lock:
            v = self.view()
            (self.dir / "sim.json").write_text(json.dumps(v, indent=2))
        mongo.mirror(v)  # MongoDB Atlas copy, in the background (no-op without MONGODB_URI)

    # ---- phase 1: cast, then pause for the owner
    def cast(self, feedback: str = ""):
        try:
            i = self.inp
            if feedback:
                i["customers"] = (i.get("customers") or "") + f"\nThe owner corrected the cast: {feedback}"
                self.log("owner", f"correction: {feedback}")
                self.think("owner", "Your correction", feedback, status="done")
            # 1. understand the product
            if not i.get("name") or not i.get("customers") or not i.get("offer"):
                ev = self.think("step", "Reading your product", i["url"] if not i.get("product_id") else "your description")
                site = session.read_site(i["url"])
                for k in ("name", "category", "customers", "offer"):
                    i[k] = i.get(k) or site[k]
                self.log("read", f"{i['name']}: {i['category']}")
                self.think_done(ev, facts={"Business": i["name"], "What it is": i.get("category", ""), "Who buys": i.get("customers", ""),
                                           "What it sells": i.get("offer", "")})
            # 2. reason about who the customers are (streamed live; the result drives the casting)
            ev = self.think("reason", "Thinking about who buys this")
            reasoning = session.think_about_customers(i["name"], i.get("category", ""), i.get("offer", ""), i.get("customers", ""),
                                                      i.get("context", ""), i.get("world", ""), feedback, on_text=lambda t: self.think_more(ev, t))
            self.think_done(ev, reasoning)
            # 3. write the personas
            ev = self.think("step", "Writing the personas", "turning that reasoning into specific people")
            self.personas = session.cast(i["name"], i["category"], i.get("context", ""), i.get("world", ""), i["customers"], i.get("offer", ""),
                                         segments=reasoning)
            models = sorted({p.get("model", "") for p in self.personas} - {""})
            self.think_done(ev, f"{len(self.personas)} customers, played by {' and '.join(models) or 'the default model'}")
            for p in self.personas:  # long-term memory: start from what this type of customer learned on other sites
                p["memory"] = memory.for_persona(p)  # own type's lessons + similar customers' (vector search)
                p["inherited"] = bool(p["memory"])
                self.think("persona", f"{p['name']}, {p['age']}", p.get("why", ""), status="done", persona_id=p["id"],
                           memory=("starts with lessons from earlier tests (vector search over past customers)" if p["inherited"] else ""))
            # 4. layer 1: plain AI shopping agents on the same site, one per model family
            try:
                from .models import persona_models
                ev = self.think("step", "Adding AI shopping agents", "one per model family, sent on a user's errand")
                agents = session.agent_shoppers(i["name"], i.get("offer", ""), list(persona_models()))
                self.personas += agents
                self.think_done(ev, " · ".join(f"{a['name']} ({a.get('model', '')})" for a in agents) or "none available")
            except Exception as e:
                self.log("error", f"agents: {type(e).__name__}: {e}"[:200])
            self.log("cast", " · ".join(f"{p['name']} ({p['archetype']}, {round(p['share'] * 100)}%)" for p in self.personas))
            self.think("step", "Ready for your review", "edit anyone, add your own, then start the test", status="done")
            self.status = "awaiting_approval"
        except Exception as e:
            self.status, self.error = "error", f"{type(e).__name__}: {e}"[:300]
            running = [k for k, e2 in enumerate(self.thinking) if e2["status"] == "running"]
            for k in running:
                self.thinking[k]["status"] = "error"
        self.save()

    # ---- phase 2: owner approved → browse → analyze
    def approve(self, personas: list[dict] | None):
        if personas:
            self.personas = personas
        self.status = "browsing"
        self.log("approved", f"owner approved {len(self.personas)} personas")
        threading.Thread(target=self._run, daemon=True).start()

    def trace_meta(self) -> dict:
        """LangSmith metadata, so every trace can be found by sim, business and memory lineage."""
        return {"sim_id": self.id, "host": _host(self.inp["url"]), "lineage": self.inp.get("lineage"), "round": self.round,
                "director": bool(self.inp.get("director")), "stub": bool(self.inp.get("stub"))}

    def _run(self):
        import langsmith
        with langsmith.trace("simulation", metadata=self.trace_meta(), tags=["sim"]):
            self._pipeline()

    def _pipeline(self):
        i = self.inp
        try:
            for p in self.personas:
                (self.dir / "personas" / f"{p['id']}.md").write_text(persona_md(p))
                self.live[p["id"]] = []

            def on_step(pid, step):
                if step is not None:  # None = an earlier step was updated in place
                    with self._lock:
                        self.live[pid].append(step)
                self.save()

            def on_done(pid, r):
                (self.dir / "sessions" / f"{pid}.json").write_text(json.dumps(r, indent=2))
                self._note_fallback(pid, r)
                if r.get("decision"):
                    self.decisions[pid] = r["decision"]
                    self.log("decision", f"{next(p['name'] for p in self.personas if p['id'] == pid)}: {r['decision']['decision']} ({r['decision']['rating']}/5)")
                else:
                    self.log("error", f"{pid}: {r.get('error')}")

            session.run_all(self.personas, i["url"], i.get("world", ""), i.get("context", ""), self.dir / "shots", on_step, on_done)
            self.summary = self._summarize()
            self.status = "talking"
            self.save()
            try:  # word of mouth: they post, read each other, reply or repost
                from . import social
                self.social = social.run([p for p in self.personas if p.get("kind") != "agent"], self.decisions, i.get("name") or i["url"])
                if self.social:
                    (self.dir / "social.json").write_text(json.dumps(self.social, indent=2))
                    self.log("social", f"{len(self.social['posts'])} posts · spreads furthest: "
                             + ", ".join(next(p['name'] for p in self.personas if p['id'] == t) for t in self.social["top_influencers"][:2]))
            except Exception as e:
                self.log("error", f"social: {type(e).__name__}: {e}"[:200])
            self.status = "analyzing"
            self.save()
            before = {p["id"]: (p.get("memory") or "").strip() for p in self.personas}
            self._analyze()
            self._record_changes(before)
            self._actions()
            self.status = "done"
        except Exception as e:
            self.status, self.error = "error", f"{type(e).__name__}: {e}"[:300]
            self.log("error", self.error)
        self.save()

    def browse_agents(self, agents: list[dict], layer: int) -> dict:
        """One browsing pass (used by the director): these agents browse in parallel. Every pass is kept in self.runs, so
        scores can compare layer 1, layer 2 and every memory version. Layer 1 = AI shopping agents (session.agent_shoppers)."""
        i = self.inp
        run = {"n": 0, "layer": layer, "agents": [a["id"] for a in agents], "decisions": {}, "clicked_buy": [],
               "memory_versions": {a["id"]: a.get("memory_version", 0) for a in agents}, "status": "running"}
        with self._lock:  # the director can start two passes at once (parallel tool calls)
            n = run["n"] = len(self.runs) + 1
            self.runs.append(run)
            for a in agents:
                self.live[a["id"]] = []
        (self.dir / "shots" / f"r{n}").mkdir(parents=True, exist_ok=True)
        hist = self.dir / "runs" / f"r{n}"  # per-run history, outside /sessions so the analyst only reads the latest
        hist.mkdir(parents=True, exist_ok=True)
        names = {p["id"]: p["name"] for p in self.personas}
        for a in agents:
            (self.dir / "personas" / f"{a['id']}.md").write_text(persona_md(a))
        got = run["decisions"]

        def on_step(aid, step):
            if step is not None:
                with self._lock:
                    self.live[aid].append(step)
            self.save()

        def on_done(aid, r):
            (self.dir / "sessions" / f"{aid}.json").write_text(json.dumps(r, indent=2))
            self._note_fallback(aid, r)
            (hist / f"{aid}.json").write_text(json.dumps(r, indent=2))
            if r.get("decision"):
                got[aid] = self.decisions[aid] = {**r["decision"], **{k: r.get(k) for k in ("layer", "model", "persona_id", "memory_version")}}
                self.log("decision", f"{names.get(aid, aid)}: {r['decision']['decision']} ({r['decision']['rating']}/5)")
            else:
                self.log("error", f"{aid}: {r.get('error')}")

        session.run_all(agents, i["url"], i.get("world", ""), i.get("context", ""), self.dir / "shots" / f"r{n}", on_step, on_done, shot_prefix=f"r{n}/")
        run["clicked_buy"] = sorted(a for a in got if any(x.get("cart") for x in self.live.get(a, [])))
        run["status"] = "done"
        self.summary = {**(self.summary or {}), **self._summarize()}
        run["summary"] = {k: self.summary.get(k) for k in ("buy_rate", "rating", "confidence")}
        self.save()
        return run

    def _note_fallback(self, pid: str, r: dict):
        """If a persona's model failed and Claude stood in, record what actually played it (no false 'played by Gemini')."""
        if not r.get("fallbacks"):
            return
        p = next((x for x in self.personas if x["id"] == pid), None)
        if p and p.get("model") and not p.get("played_by"):
            p["played_by"] = "Claude"
            p["model_note"] = f"{p['model']} unavailable ({r.get('fallback_reason', '')[:80]}), Claude stood in for {r['fallbacks']} step(s)"
            self.log("fallback", f"{p['name']}: {p['model_note']}")

    def _summarize(self):
        agents = {p["id"] for p in self.personas if p.get("kind") == "agent"}
        share = {p["id"]: p["share"] for p in self.personas}
        got = {pid: d for pid, d in self.decisions.items() if pid not in agents}
        w = sum(share[pid] for pid in got) or 1
        carted = {pid for pid, steps in self.live.items() if any(x.get("cart") for x in steps)}
        # what they did beats what they said: a buy/download click counts as buying
        buy = sum(share[pid] * (1.0 if pid in carted else BUYS.get(d["decision"], 0)) for pid, d in got.items()) / w
        rating = sum(share[pid] * d["rating"] for pid, d in got.items()) / w
        counts: dict[str, int] = {}
        for d in got.values():
            counts[d["decision"]] = counts.get(d["decision"], 0) + 1
        by_model: dict[str, list[int]] = {}
        for p in self.personas:
            if p["id"] in got and p.get("kind") != "agent":
                m = by_model.setdefault(p.get("played_by") or p.get("model", "Claude"), [0, 0])
                m[1] += 1
                m[0] += int(p["id"] in carted or BUYS.get(got[p["id"]]["decision"], 0) >= 1)
        agent_rows = []
        for p in self.personas:
            if p["id"] in agents and p["id"] in self.decisions:
                d = self.decisions[p["id"]]
                agent_rows.append({"persona": p["id"], "model": p.get("model"), "bought": p["id"] in carted or BUYS.get(d["decision"], 0) >= 1,
                                   "decision": d["decision"], "missing": d.get("missing", ""), "quote": d.get("quote", "")})
        conf = [d.get("confidence") for d in got.values() if d.get("confidence") is not None]
        return {"agents": agent_rows, "confidence": round(sum(conf) / len(conf), 2) if conf else None, "buy_rate": round(buy, 3), "clicked_buy": sorted(carted), "by_model": {k: {"bought": v[0], "of": v[1]} for k, v in by_model.items()}, "rating": round(rating, 2), "decisions": counts,
                "missing": [{"persona": pid, "text": d["missing"]} for pid, d in got.items()]}

    def _actions(self):
        """The to-do list for the owner: concrete fixes, each tied to who it wins back and the evidence."""
        from typing import Literal
        from pydantic import BaseModel, Field

        class Action(BaseModel):
            fix: str = Field(description="the change, imperative and concrete, max 14 words (e.g. 'Put one Buy button on the product page')")
            why: str = Field(description="the evidence, quoting or paraphrasing what customers or agents said or hit, max 30 words")
            audience: Literal["people", "AI agents", "both"]
            who: list[str] = Field(description="names of the customers or agents this would win back")
            page: str = Field(default="", description="the page or step it's on, if known")
            effort: Literal["small", "medium", "big"]

        class Actions(BaseModel):
            items: list[Action] = Field(min_length=1, max_length=5)

        people = {p["id"]: p for p in self.personas}
        lines = []
        for pid, d in self.decisions.items():
            p = people.get(pid, {})
            kind = "AI agent" if p.get("kind") == "agent" else f"customer ({p.get('archetype')}, {round(p.get('share', 0) * 100)}%)"
            lines.append(f"- {p.get('name')} [{kind}]: {d['decision']} {d['rating']}/5. \"{d['quote']}\" Missing: {d.get('missing', '')}")
        spread = (self.social or {}).get("summary", "")
        ask = (f"A simulated test of {self.inp.get('name')} ({self.inp['url']}). Results:\n" + "\n".join(lines)
               + (f"\nWord of mouth: {spread}" if spread else "") + f"\nAnalyst report:\n{self.report[:3000]}\n\n"
               "List the 3-5 fixes that would win back the most customers and AI agents, most valuable first. Separate what AI "
               "shopping agents need (clear facts, prices, structure, a path to buy) from what people need (trust, feeling, "
               "price, ease). Only fixes grounded in the evidence above.")
        try:
            r: Actions = brain().with_structured_output(Actions, method="json_schema").invoke(ask)
            self.actions = [a.model_dump() for a in r.items]
        except Exception as e:
            self.log("error", f"actions: {type(e).__name__}: {e}"[:200])

    def _record_changes(self, before: dict):
        """What each persona learned this round: its memory before and after the evolver ran."""
        for p in self.personas:
            f = self.dir / "personas" / f"{p['id']}.md"
            after = f.read_text().split("## Memory", 1)[1].strip() if f.exists() and "## Memory" in f.read_text() else ""
            if after and after != before.get(p["id"], ""):
                new = [l.strip("-• ").strip() for l in after.splitlines() if l.strip() and l.strip() not in before.get(p["id"], "")]
                self.persona_changes.append({"persona_id": p["id"], "iteration": self.round + 1, "lesson": (new or [after])[0][:240],
                                             "before": before.get(p["id"], ""), "after": after, "source": "simulation"})
                p["memory"] = after
        self.save()

    def _analyze(self):
        i = self.inp
        agent = create_deep_agent(
            model=brain(),
            system_prompt=ANALYST.format(name=i["name"], url=i["url"], context=i.get("context") or "none", world=i.get("world") or "today"),
            subagents=[
                {"name": "analyst", "description": "Finds where personas got stuck and why they bought or left.", "system_prompt": ANALYST_SUB},
                {"name": "evolver", "description": "Updates every persona file with what that persona learned.", "system_prompt": EVOLVER_SUB},
            ],
            backend=memory.backend_for(self.dir),  # sim files + /memories/ (long-term, shared across businesses)
        )
        for update in agent.stream({"messages": [{"role": "user", "content": "Begin."}]}, config={"recursion_limit": 80, "run_name": "analyst", "metadata": self.trace_meta(), "tags": ["sim"]}, stream_mode="updates"):
            for node in update.values():
                for m in (node or {}).get("messages", []) if isinstance(node, dict) else []:
                    for call in getattr(m, "tool_calls", None) or []:
                        a = call.get("args", {})
                        if call["name"] == "task":
                            self.log(a.get("subagent_type", "subagent"), (a.get("description") or "")[:240])
                        elif call["name"] in ("edit_file", "write_file"):
                            self.log("file", str(a.get("file_path", "")))
        rp = self.dir / "report.md"
        self.report = rp.read_text() if rp.exists() else ""
        # long-term memory: keep the evolved personas for future simulations
        LIBRARY.mkdir(parents=True, exist_ok=True)
        for f in (self.dir / "personas").glob("*.md"):
            shutil.copy(f, LIBRARY / f"{self.id}_{f.name}")
        memory.persist()
        self.log("memory", f"long-term memory now covers: {', '.join(memory.everything()) or 'nothing yet'}")


SIMS_LIVE: dict[str, SimJob] = {}


def start(inp: dict) -> SimJob:
    from . import director
    if director.enabled(inp):
        return director.start(inp)
    job = SimJob(inp)
    SIMS_LIVE[job.id] = job
    job.save()
    threading.Thread(target=job.cast, daemon=True).start()
    return job


def get(sim_id: str):
    if sim_id in SIMS_LIVE:
        return SIMS_LIVE[sim_id].view()
    p = SIMS / Path(sim_id).name / "sim.json"
    return json.loads(p.read_text()) if p.exists() else None


def _live_or_restored(sim_id: str):
    """The running job, or a director sim paused for approval before a server restart, rebuilt from disk."""
    job = SIMS_LIVE.get(sim_id)
    if job:
        return job
    from . import director
    return director.restore(sim_id)


def approve(sim_id: str, personas: list[dict] | None) -> bool:
    job = _live_or_restored(sim_id)
    if not job or job.status != "awaiting_approval":
        return False
    job.approve(personas)
    return True


TEACH = """You are updating a simulated customer's memory with what REAL people told the business owner.
Persona: {persona}
Its current memory: {memory}
What happened in the simulation for this persona: {decision}
What the owner says really happens with real customers: {truth}

If the owner's account applies to this kind of customer, rewrite the memory: keep what still holds, correct what the real
customers contradict, add at most 2 concrete lessons. If it doesn't apply to this persona, return the memory unchanged."""


def teach(sim_id: str, truth: str) -> list[dict] | None:
    """Human context in: the owner tells the personas what real customers actually did. Each persona's memory is
    corrected, so the next round starts from people, not just from its own guesses."""
    from pydantic import BaseModel, Field
    from .models import fast

    class Lesson(BaseModel):
        applies: bool
        memory: str = Field(description="the full updated memory, as 1-4 short bullet lines starting with '- '")
        lesson: str = Field(description="what changed and why, one sentence; empty if nothing applies")

    job = SIMS_LIVE.get(sim_id)
    view = job.view() if job else get(sim_id)
    if not view or view.get("status") != "done":
        return None
    changes = []
    mem = view.get("memory") or {}
    for p in view["personas"]:
        before = mem.get(p["id"], p.get("memory", "")) or ""
        info = {k: p[k] for k in ("name", "age", "occupation", "archetype", "segment", "goal", "budget")}
        d = (view.get("decisions") or {}).get(p["id"], {})
        r: Lesson = fast().with_structured_output(Lesson).invoke(TEACH.format(persona=info, memory=before or "(empty)", decision=d.get("quote", "no decision"), truth=truth))
        if not r.applies or r.memory.strip() == before.strip():
            continue
        f = SIMS / sim_id / "personas" / f"{p['id']}.md"
        body = f.read_text().split("## Memory", 1)[0].rstrip() if f.exists() else persona_md(p).rstrip()
        f.write_text(body + "\n\n## Memory\n" + r.memory.strip() + "\n")
        change = {"persona_id": p["id"], "iteration": view.get("round", 0) + 1, "lesson": "From the owner: " + r.lesson,
                  "before": before, "after": r.memory.strip(), "source": "human"}
        if view["input"].get("director") and p.get("kind") != "agent":
            change["memory_version"] = memory.business_write(memory.business_ns(view["input"]["url"], view["input"].get("lineage") or sim_id), p["id"], r.memory)
        changes.append(change)
    if job:
        job.persona_changes.extend(changes)
        job.log("owner", f"real-world context: {truth[:200]}")
        job.save()
    else:
        sj = SIMS / sim_id / "sim.json"
        d = json.loads(sj.read_text())
        d["persona_changes"] = (d.get("persona_changes") or []) + changes
        d["memory"] = {**(d.get("memory") or {}), **{c["persona_id"]: c["after"] for c in changes}}
        sj.write_text(json.dumps(d, indent=2))
    return changes


def _patch(sim_id: str, fn) -> bool:
    """Change a simulation whether it's still in memory or only on disk."""
    job = SIMS_LIVE.get(sim_id)
    if job:
        fn(job.__dict__)
        job.save()
        return True
    f = SIMS / Path(sim_id).name / "sim.json"
    if not f.exists():
        return False
    d = json.loads(f.read_text())
    fn(d)
    f.write_text(json.dumps(d, indent=2))
    mongo.mirror(d)
    return True


def add_eval(sim_id: str, score: dict) -> bool:
    """Attach one accuracy score (b2a/contract.py EvalScore as a dict) to a simulation. Shows in "Were we right?"."""
    return _patch(sim_id, lambda d: d.setdefault("evals", []).append(score))


def set_social(sim_id: str, social: dict) -> bool:
    """Attach the social layer (b2a/contract.py Social as a dict)."""
    return _patch(sim_id, lambda d: d.__setitem__("social", social))


def recast(sim_id: str, feedback: str) -> bool:
    """Owner says the personas are off ("my customers are older"): cast again with that correction."""
    job = _live_or_restored(sim_id)
    if not job or job.status != "awaiting_approval":
        return False
    job.status = "casting"
    job.save()
    threading.Thread(target=job.cast, args=(feedback,), daemon=True).start()
    return True


def rerun(sim_id: str, change: str = "") -> SimJob | None:
    """Next round: the same customers, now carrying what they learned, visit again. With `change`, the owner changed the
    site and wants a fair before/after with the same people."""
    src = get(sim_id)
    if not src or src.get("status") != "done":
        return None
    if (src.get("input") or {}).get("director"):
        from . import director
        return director.rerun(src, change)
    inp = {**src["input"], "round": src.get("round", 0) + 1, "parent": sim_id, "evals_so_far": src.get("evals") or []}
    if change:
        inp["context"] = change
    job = SimJob(inp)
    SIMS_LIVE[job.id] = job
    mem = src.get("memory") or {}
    job.personas = [{**p, "memory": mem.get(p["id"], p.get("memory", ""))} for p in src["personas"]]
    job.log("round", f"round {job.round}: same {len(job.personas)} customers, carrying what they learned")
    job.approve(None)
    return job


def _host(url: str) -> str:
    from urllib.parse import urlparse
    u = url if url.startswith("http") else "https://" + url
    parts = urlparse(u).path.strip("/").split("/")
    if parts[:2] == ["api", "products"] and len(parts) > 2:  # described product (b2a/product_page.py): one "site" per product
        return parts[2]
    return urlparse(u).netloc.removeprefix("www.").lower()


def _row(d: dict) -> dict:
    # People and AI agents are counted separately, so the sidebar and timeline match the headline ("0 of 6 people").
    agents = {p["id"] for p in d.get("personas") or [] if p.get("kind") == "agent"}
    bought = a_bought = people = 0
    for pid, dec in (d.get("decisions") or {}).items():
        carted = any(x.get("cart") for x in (d.get("live") or {}).get(pid, []))
        b = int(carted or BUYS.get(dec.get("decision"), 0) >= 1)
        if pid in agents:
            a_bought += b
        else:
            bought += b
            people += 1
    i = d["input"]
    return {"id": d["id"], "name": i.get("name") or _host(i["url"]), "host": _host(i["url"]), "status": d["status"],
            "round": d.get("round", 0), "context": i.get("context", ""), "world": i.get("world", ""),
            "bought": bought, "of": people, "agents_bought": a_bought, "agents_of": len(agents & set(d.get("decisions") or {})), "buy_rate": (d.get("summary") or {}).get("buy_rate")}


def list_sims(host: str | None = None):
    """Every run, newest first; with host, the timeline for one business."""
    out = []
    for p in sorted(SIMS.glob("*/sim.json"), reverse=True):
        try:
            r = _row(json.loads(p.read_text()))
        except Exception:
            continue
        if host and r["host"] != _host(host):
            continue
        out.append(r)
    return out
