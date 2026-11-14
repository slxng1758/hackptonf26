"""The director: one deep agent that runs the whole customer simulation and gives a reason for every decision.

    create_deep_agent(brain(), tools=[10 tools below], subagents=[briefer, segmenter, analyst, critic],
                      backend=memory.backend_for(sim dir, business namespace), checkpointer=SQLite)

Tools do the heavy, repeatable work in plain Python with hard budget caps; the director and its subagents make the
judgment calls (who to cast, which models, whether to loop again, when to stop). Built on the team's modules:

  layer 1      session.agent_shoppers: one AI shopping agent per model family, on a user's errand (ids a1, a2, ...)
  layer 2      session.cast personas, each starting from memory.for_persona (what its customer type learned on every
               site + similar types, vector search) plus its own memory at THIS business (memory.business_*)
  scoring      evals.score(view, case) against held-out real reviews; evals.feedback_for_evolver tells the evolver what
               was wrong; evals.improvement decides whether another loop is worth it
  word of mouth  social.run (posts, replies, reposts, PageRank), then network.analyze (communities, cascades, themes)
  summary      compare.summary (by model, by segment, layer 1 -> 2 delta, top suggestions)

  briefer    (subagent)  /product.md + /world.md: the product as a customer would understand it
  segmenter  (subagent)  how many customer types and which archetypes -> /segments.md
  critic     (subagent)  can the results be trusted? which segments need more personas?
  analyst    (subagent, and inside `finish`)  where people got stuck, what convinced buyers -> /report.md
  evolver    (inside `evolve`, its own deep agent)  edits /memories/business/<id>.md (this business) and
             /memories/<archetype>.md (every business); the tool records each change with a new memory_version

Owner approval is a real pause (LangGraph interrupt) saved in runs/checkpoints.sqlite, so it survives a restart.
DIRECTOR_STUB=1 (or "stub": true): browsing, scoring, social and evolving return fixture-like data at once, so the
director's decisions can be tested in seconds with no browsers and no customer-model cost.
"""
from __future__ import annotations

import json
import os
import random
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from deepagents import create_deep_agent
from langchain.agents.middleware import TodoListMiddleware
from langchain_core.tools import tool
from langgraph.types import Command, interrupt

from . import memory, session
from .models import brain, persona_models
from .sim import BUYS, RUNS, SIMS_LIVE, SimJob, _host, persona_md

MODEL = None  # tests only: a chat model to use instead of brain() (restored and rerun jobs pick it up too)
CHECKPOINTS = RUNS / "checkpoints.sqlite"

WORLDS = {
    "today": "today, normal times",
    "pre-covid-2019": "2019, before COVID: people shop in stores and online as usual, nobody wears masks",
    "covid-2020": "spring 2020, COVID: lockdowns, masks required in stores, people stuck at home and worried about money",
    "previous-version": "the product as it was before the latest change",
    "new-version": "the product right after the latest change",
}


@lru_cache
def checkpointer():
    """Where paused director graphs are saved, so an approval still resumes after a server restart."""
    from langgraph.checkpoint.sqlite import SqliteSaver
    CHECKPOINTS.parent.mkdir(parents=True, exist_ok=True)
    s = SqliteSaver(sqlite3.connect(str(CHECKPOINTS), check_same_thread=False))  # SqliteSaver locks internally
    s.setup()
    return s


# ---------------------------------------------------------------- budget


@dataclass
class Budget:
    max_personas: int = 8
    max_sessions: int = 40
    max_evolve_loops: int = 4
    max_social_rounds: int = 3
    max_minutes: float = 20
    personas: int = 0
    sessions: int = 0
    evolve_loops: int = 0
    social_rounds: int = 0
    started: float = field(default_factory=time.time)

    def left(self) -> dict:
        return {"personas": self.max_personas - self.personas, "sessions": self.max_sessions - self.sessions,
                "evolve_loops": self.max_evolve_loops - self.evolve_loops, "social_rounds": self.max_social_rounds - self.social_rounds,
                "minutes": round(self.max_minutes - (time.time() - self.started) / 60, 1)}

    def blocked(self, kind: str, n: int = 1) -> str | None:
        left = self.left()
        if left["minutes"] <= 0:
            return "time budget used"
        if kind in left and left[kind] < n:
            return f"{kind} budget used ({left[kind]} left, {n} needed)"
        return None

    def view(self) -> dict:
        d = asdict(self)
        d.pop("started")
        return {**d, "left": self.left()}


# ---------------------------------------------------------------- prompts

DIRECTOR = """You run a customer simulation for a small business. Simulated customers (personas) and AI shopping agents
really browse the product, decide whether to buy, review it, talk about it, get scored against real outcomes and learn.
You decide everything: who to cast, which models play them, how many learning loops to run, and when to stop. Every
tool needs a `reason`: one plain sentence the business owner will read, saying why you are doing this now.

The business: {name} ({url}). Category: {category}
What changed: {context}
World the customers live in: {world}
Who the customers are (owner's words): {customers}
Models the owner chose to play customers: {models}
Real outcomes to score against: {truth}
{rerun}
What you learned running past simulations:
{lessons}

How to run it (keep your todo list updated with write_todos):
1. brief_product. Then ask the `briefer` subagent to write /product.md and /world.md from /site.md.
2. Ask the `segmenter` subagent for the customer types (it reads /product.md and writes /segments.md).
   Then cast_personas with its mix.
3. request_approval. The owner may edit the cast, or say it's off: if so, cast again (replace=true) and ask again.
4. run_base_models once (layer 1: one AI shopping agent per model, on a user's errand; the baseline).
   Then run_personas for everyone (layer 2: customers with memory).
5. Ask the `critic` subagent whether the results can be trusted. Spawn more personas when a segment split or confidence
   is low (rules below), and run only the new ones.
6. Learning loop (rules below): score, then evolve, then run_personas again.
7. run_social (rules below).
8. summarize, then finish with one lesson for next time.

Decision rules:
- Casting: default 5 personas, range 3-8. Use fewer for simple products, more when the customers include many distinct
  groups. Always include at least one skeptic. Include a first-time user only if the product needs learning or navigating.
  Use these archetypes: price-sensitive, quality-first, brand-loyal, function-first, first-time user, skeptic, enthusiast.
  Spread the chosen models evenly (cast_personas does round-robin): no family plays more than ~40% of personas.
- Spawning: after a run, if a segment's agents split (some buy, some don't), or the average confidence is below 0.5, or
  the critic flags a gap, cast 1-2 more personas in that segment and run_personas on only those.
- Learning loop WITH real outcomes: score after each run. Loop score -> evolve -> run_personas while score says
  keep_going (rating_error or theme_recall improved by >= 0.1). Stop after 2 loops in a row without that, or when the
  budget is used. Only evolve the personas that were wrong or uncertain, and pass score's feedback as the focus.
- Learning loop WITHOUT real outcomes: evolve once from the sessions, run_personas again, and stop when the buy rate moves
  by less than 5 points between runs.
- Word of mouth: run_social once after the last run, with 2 reaction rounds (3 if there are 6+ personas).
- Budget: every tool result shows what is left. When a tool says the budget is used, summarize and finish.

Reply to the owner at the end with one sentence."""

BRIEFER = """You write the product brief for a customer simulation. Read /site.md (what the site says, plus the owner's
input). Write /product.md: what it is, what it costs, who it is for, the key features, and what changed, in plain words a
customer would understand. Write /world.md: the world the customers live in right now, 3-5 lines. List anything unclear at
the end of /product.md under "## Unclear". Reply with the brief in at most 80 words."""

SEGMENTER = """You decide which customer types this product really has. Read /product.md (or /site.md if it isn't there yet).
Write /segments.md listing each segment with its share of customers and one archetype from: price-sensitive,
quality-first, brand-loyal, function-first, first-time user, skeptic, enthusiast. Propose a number of personas between
3 and 8 and say why. Reply in at most 100 words: n, archetypes in casting order, and the segments."""

ANALYST = """You analyze customer browsing sessions for a small business. Personas are in /personas/*.md. Their sessions
(every page, thought, feeling, click, decision, review and suggestions) are in /sessions/*.json. Ids starting with "a"
are AI shopping agents acting for a user (layer 1); ids starting with "p" are customer personas with memory (layer 2).
Report in at most 180 words: where each one got stuck (page + step), the most common reason to leave, what convinced
buyers, whether the claimed change was visible, and how the AI agents and the customers differ."""

CRITIC = """You check whether a customer simulation can be trusted. Read /personas/*.md, /sessions/*.json and /summary.json.
Look for: personas that are too similar, results that are too positive (models agreeing to please), one model family
dominating the cast or the outcome, a segment with too few agents, or decisions that contradict what the agent saw.
Reply in at most 120 words, ending with a line "SPAWN: <segment or archetype>" for each gap that needs more personas,
or "SPAWN: none"."""

EVOLVER = """You update customer personas' memory. For each persona id you are given:
1. Edit /memories/business/<id>.md (create it if missing): what THIS persona learned about THIS business. Base it on its
   session in /sessions/<id>.json, the accuracy feedback in /evals.md (what real customers said that the personas missed,
   and whether they were too harsh or too kind) and what the owner said in /owner.md. Keep 2-6 short bullets starting
   with "- ", each tagged with its source, e.g. "- (session) the size guide was hard to find" or "- (eval) real buyers
   say it shrinks in the dryer". Keep what still holds, correct what was wrong.
2. Then update long-term memory for its archetype (from /personas/<id>.md): read /memories/<archetype>.md (spaces as
   hyphens; it may not exist yet) and rewrite it as at most 6 short bullets of general lessons for that kind of customer
   on ANY website. Merge with what's there, drop duplicates, never name this business.
Never change who the persona is (name, age, archetype, goal, budget). Focus: {focus}
Reply with one line per persona: "<id>: <the one lesson that changed>"."""

REPORT = """Write /report.md for the business owner, short, with these sections: the weighted buy rate and rating, broken
down by customer type (archetype and share); how the AI shopping agents (layer 1) compare with the customers (layer 2);
where people got stuck (which page); what convinced the buyers; the top 3 suggestions (each tied to someone and a page
they saw, see /summary.json top_suggestions); which complaint is most likely to spread by word of mouth and why (see
/social.json); how accurate the simulation was against real outcomes (/evals.json) and where it might be wrong. Use the
`analyst` subagent for the session analysis. Reply with one sentence."""


# ---------------------------------------------------------------- the job


class DirectorJob(SimJob):
    """A SimJob run by the director agent instead of the fixed cast → browse → analyze order."""

    def __init__(self, inp: dict, model=None, saved: dict | None = None):
        inp = dict(inp)
        if inp.get("world_preset") in WORLDS and not inp.get("world"):
            inp["world"] = WORLDS[inp["world_preset"]]
        inp["director"] = True
        super().__init__(inp, sim_id=(saved or {}).get("id"))
        self.stub = bool(inp.get("stub") or os.getenv("DIRECTOR_STUB") == "1")
        self.model = model
        self.b = Budget()
        self.budget = self.b.view()
        self.ns = memory.business_ns(self.inp["url"], self.inp["lineage"])
        self.cfg = {"configurable": {"thread_id": self.id}, "recursion_limit": 300, "run_name": "director",
                    "metadata": {**self.trace_meta(), "thread_id": self.id},  # LangSmith Threads: pause + resume = one thread
                    "tags": ["sim", "director"] + (["stub"] if self.stub else [])}
        self.status = "briefing"
        self._agent = None
        self._started = False
        if saved:
            self._load(saved)

    def _load(self, v: dict):
        """Rebuild from sim.json after a restart. The graph itself resumes from the SQLite checkpoint (thread_id = sim id)."""
        for k in ("personas", "live", "decisions", "summary", "report", "steps", "persona_changes", "evals", "social",
                  "actions", "runs", "director", "todos", "status", "error"):
            if k in v and v[k] is not None:
                setattr(self, k, v[k])
        b = v.get("budget") or {}
        for k in ("personas", "sessions", "evolve_loops", "social_rounds"):
            setattr(self.b, k, b.get(k, 0))
        used = b.get("max_minutes", self.b.max_minutes) - (b.get("left") or {}).get("minutes", self.b.max_minutes)
        self.b.started = time.time() - max(used, 0) * 60  # keep the time already spent, not the time the server was down
        self.budget = self.b.view()
        self._started = True

    # ---- lifecycle: sim.start() calls cast(); sim.recast() calls cast(feedback); sim.approve() calls approve()
    def cast(self, feedback: str = ""):
        if not self._started:
            self._started = True
            self._drive({"messages": [{"role": "user", "content": "Begin."}]})
        else:
            self.log("owner", f"correction: {feedback}")
            self._resume({"feedback": feedback})

    def approve(self, personas: list[dict] | None):
        self.log("approved", f"owner approved {len(personas or self.personas)} personas")
        self._resume({"personas": personas})

    def _resume(self, value: dict):
        self.status = "resuming"
        self.save()
        threading.Thread(target=self._drive, args=(Command(resume=value),), daemon=True).start()

    def _drive(self, inp):
        try:
            agent = self._build()
            paused = False
            for update in agent.stream(inp, config=self.cfg, stream_mode="updates"):
                if "__interrupt__" in update:
                    paused = True
                    continue
                self._trace(update)
            if paused:
                self.status = "awaiting_approval"
            elif self.status != "done":
                self.log("director", "stopped without finish; closing the run")
                self.status = "done"
        except Exception as e:
            self.status, self.error = "error", f"{type(e).__name__}: {e}"[:300]
            self.log("error", self.error)
        self.save()

    def _trace(self, update: dict):
        for node in update.values():
            for m in (node or {}).get("messages", []) if isinstance(node, dict) else []:
                for call in getattr(m, "tool_calls", None) or []:
                    a = call.get("args", {})
                    if call["name"] == "write_todos":
                        self.todos = a.get("todos", [])
                        self.save()
                    elif call["name"] == "task":
                        self.log(a.get("subagent_type", "subagent"), (a.get("description") or "")[:300])
                if getattr(m, "type", "") == "tool" and getattr(m, "name", "") == "task":
                    c = m.content if isinstance(m.content, str) else json.dumps(m.content)
                    self.log("answer", c[:400])

    # ---- helpers
    def _decide(self, tool_name: str, reason: str, args: dict, result: str) -> str:
        self.budget = self.b.view()
        self.director.append({"t": datetime.now().strftime("%H:%M:%S"), "tool": tool_name, "reason": reason,
                              "args": {k: v for k, v in args.items() if k != "reason"}, "result": result[:400]})
        self.log("decision", f"{tool_name}: {reason}")
        return f"{result}\nBudget left: {json.dumps(self.b.left())}"

    def _backend(self):
        return memory.backend_for(self.dir, self.ns)

    def _brain(self):
        return self.model or MODEL or brain()

    def _sub(self, system_prompt: str, task: str, subagents=None, name: str = "subagent"):
        """A one-off deep agent over the same files and memory (used by evolve and finish)."""
        a = create_deep_agent(model=self._brain(), system_prompt=system_prompt, subagents=subagents or [],
                              backend=self._backend(), store=memory.store())
        for update in a.stream({"messages": [{"role": "user", "content": task}]},
                               config={"recursion_limit": 80, "run_name": name, "metadata": self.trace_meta(), "tags": ["sim", "director"]},
                               stream_mode="updates"):
            self._trace(update)

    def _models(self) -> list[str]:
        keyed = list(persona_models())
        chosen = [m for m in (self.inp.get("models") or keyed) if not keyed or m in keyed]
        return chosen or keyed or ["Claude"]

    def _people(self) -> list[dict]:
        return [p for p in self.personas if p.get("kind") != "agent"]

    def _with_memory(self, p: dict) -> dict:
        """A persona's memory = its own visits to this business (versioned) + what its type learned everywhere (Candy's)."""
        if "general_memory" not in p:
            try:
                p = {**p, "general_memory": "" if self.stub else memory.for_persona(p)}
            except Exception:
                p = {**p, "general_memory": ""}
        own, v = memory.business_read(self.ns, p["id"])
        parts = ([f"At this business (your own past visits):\n{own.strip()}"] if own.strip() else []) + \
                ([f"What customers like you learned on other sites:\n{p['general_memory']}"] if p["general_memory"] else [])
        return {**p, "memory": "\n".join(parts), "memory_version": v, "inherited": bool(p["general_memory"]), "layer": 2, "persona_id": p["id"]}

    def _write_json(self, name: str, data):
        (self.dir / name).write_text(json.dumps(data, indent=2))

    # ---- the agent
    def _build(self):
        if self._agent:
            return self._agent
        job, inp = self, self.inp

        @tool
        def brief_product(reason: str) -> str:
            """Read the product (website or the owner's description) and write /site.md for the briefer. Call first."""
            job.status = "briefing"
            if not job.stub and inp.get("url") and not (inp.get("name") and inp.get("customers") and inp.get("offer")):
                site = session.read_site(inp["url"])
                for k in ("name", "category", "customers", "offer"):
                    inp[k] = inp.get(k) or site[k]
            for k, d in (("name", _host(inp["url"])), ("category", "a small business"), ("customers", "its usual customers"), ("offer", "see the website")):
                inp[k] = inp.get(k) or d
            text = "" if job.stub else session.rendered_text(inp["url"], 4000)
            (job.dir / "site.md").write_text(
                f"# {inp['name']}\n\n- URL: {inp['url']}\n- Category: {inp['category']}\n- Offer: {inp['offer']}\n- Customers: {inp['customers']}\n"
                f"- What changed: {inp.get('context') or 'none'}\n- World: {inp.get('world') or 'today'}\n"
                + (f"- Owner's description: {inp['description']}\n" if inp.get("description") else "")
                + (f"\n## Page text\n{text}\n" if text else ""))
            job.save()
            return job._decide("brief_product", reason, {}, f"{inp['name']}: {inp['category']}. Offer: {inp['offer']}. Wrote /site.md.")

        @tool
        def cast_personas(n: int, archetypes: list[str], reason: str, segments: str = "", models: list[str] | None = None,
                          replace: bool = False) -> str:
            """Create n customer personas (archetypes in casting order; segments = the segment analysis) and spread the
            models across them. replace=true throws away the current cast (when the owner says it's off). Each persona
            starts with its memory: its own past visits here, plus what its customer type learned on other sites."""
            job.status = "casting"
            if replace:
                job.personas, job.b.personas = [p for p in job.personas if p.get("kind") == "agent"], 0
            n = max(1, min(n, 8))
            if job.b.blocked("personas", n):
                n = job.b.left()["personas"]
                if n <= 0:
                    return job._decide("cast_personas", reason, {"n": 0}, f"Not cast: persona budget used. Continue with the {len(job._people())} you have.")
            fams = [m for m in (models or job._models()) if m in job._models()] or job._models()
            start = len(job._people()) + 1
            if job.stub:
                new = _stub_personas(n, archetypes, fams, start)
            else:
                new = session.cast(inp["name"], inp["category"], inp.get("context", ""), inp.get("world", ""), inp["customers"],
                                   inp.get("offer", ""), n=n, archetypes=archetypes, models=fams, start=start, segments=segments)
            new = [job._with_memory(p) for p in new]
            for p in new:
                (job.dir / "personas" / f"{p['id']}.md").write_text(persona_md(p))
            job.personas += new
            job.b.personas += len(new)
            job.save()
            out = "; ".join(f"{p['id']} {p['name']} ({p['archetype']}, {round(p['share'] * 100)}%, {p['model']}"
                            f"{', memory v' + str(p['memory_version']) if p['memory_version'] else ''}"
                            f"{', inherits its type' + chr(39) + 's lessons' if p['inherited'] else ''})" for p in new)
            return job._decide("cast_personas", reason, {"n": n, "archetypes": archetypes, "models": fams, "replace": replace}, f"Cast {len(new)}: {out}")

        @tool
        def request_approval(reason: str) -> str:
            """Pause and show the cast to the business owner. They can edit personas or models, or say the cast is off."""
            job.status = "awaiting_approval"
            job.save()
            ans = interrupt({"personas": job.personas, "reason": reason})
            job.status = "approved"
            if ans.get("feedback"):
                with (job.dir / "owner.md").open("a") as f:
                    f.write(f"- Owner on the cast: {ans['feedback']}\n")
                inp["customers"] = (inp.get("customers") or "") + f"\nThe owner corrected the cast: {ans['feedback']}"
                return job._decide("request_approval", reason, {}, f"The owner says the cast is off: \"{ans['feedback']}\". "
                                   "Cast again with cast_personas(replace=true), then request_approval again.")
            if ans.get("personas"):
                agents = [p for p in job.personas if p.get("kind") == "agent"]
                people = [job._with_memory({**p, "share": p.get("share", 0)}) for p in ans["personas"] if p.get("kind") != "agent"]
                tot = sum(p["share"] for p in people)
                for p in people:
                    p["share"] = round(p["share"] / tot, 3) if tot else round(1 / len(people), 3)
                job.personas = agents + people
            job.save()
            return job._decide("request_approval", reason, {}, "Approved: " + ", ".join(f"{p['id']} {p['name']} ({p.get('model', '?')})" for p in job._people()))

        @tool
        def run_base_models(reason: str, models: list[str] | None = None) -> str:
            """Layer 1: one AI shopping agent per model, each on the same errand for a user, no persona and no memory."""
            job.status = "base_models"
            fams = [m for m in (models or job._models()) if m in job._models()] or job._models()
            if job.b.blocked("sessions", len(fams)):
                return job._decide("run_base_models", reason, {"models": fams}, "Not run: session budget used.")
            have = {p["model"]: p for p in job.personas if p.get("kind") == "agent"}
            missing = [m for m in fams if m not in have]
            if missing:
                first = len(have) + 1
                made = _stub_agents(missing, len(have)) if job.stub else session.agent_shoppers(inp["name"], inp.get("offer", ""), missing)
                for i, a in enumerate(made):
                    have[a["model"]] = {**a, "id": f"a{first + i}"}
                job.personas = list(have.values()) + job._people()
            agents = [have[m] for m in fams]
            job.b.sessions += len(agents)  # reserve first: another pass may be starting in parallel
            run = _stub_run(job, agents, 1) if job.stub else job.browse_agents(agents, layer=1)
            out = "; ".join(f"{a['model']}: {d['decision']} {d['rating']}/5, missing: {d.get('missing', '')[:80]}"
                            for a in agents if (d := run["decisions"].get(a["id"])))
            return job._decide("run_base_models", reason, {"models": fams}, f"Run {run['n']} (layer 1, AI agents on: {agents[0]['goal'][:90]}): {out}")

        @tool
        def run_personas(reason: str, persona_ids: list[str] | None = None) -> str:
            """Layer 2: these customer personas (default: all) browse the real site with their memory injected."""
            job.status = "browsing"
            ids = persona_ids or [p["id"] for p in job._people()]
            agents = [job._with_memory(p) for p in job._people() if p["id"] in ids]
            if not agents:
                return job._decide("run_personas", reason, {"persona_ids": ids}, "No such personas.")
            if job.b.blocked("sessions", len(agents)):
                return job._decide("run_personas", reason, {"persona_ids": ids}, "Not run: session budget used.")
            for a in agents:  # the cast shows what was injected
                next(p for p in job.personas if p["id"] == a["id"]).update(memory=a["memory"], memory_version=a["memory_version"],
                                                                           general_memory=a["general_memory"], inherited=a["inherited"])
            job.b.sessions += len(agents)
            run = _stub_run(job, agents, 2) if job.stub else job.browse_agents(agents, layer=2)
            job._write_json("summary.json", job.summary)
            return job._decide("run_personas", reason, {"persona_ids": ids}, _run_digest(job, run))

        @tool
        def score(reason: str) -> str:
            """Compare the latest customer results with real outcomes (held-out real reviews). Returns the errors, the
            feedback for the evolver, and keep_going (whether the last loop improved enough to try another)."""
            job.status = "scoring"
            prev = next((e for e in reversed(job.evals) if e.get("layer") == 2), None)
            if job.stub:
                s = _stub_score(job)
                fb = "Real customers often mentioned these, but no simulated customer did: " + "; ".join(s["missed_themes"]) if s["missed_themes"] else ""
                keep = prev is None or (prev["rating_error"] - s["rating_error"] >= 0.1 or s["theme_recall"] - prev["theme_recall"] >= 0.1)
            else:
                if not inp.get("case_id"):
                    return job._decide("score", reason, {}, "No real outcomes for this product: use the rules for runs without real outcomes.")
                try:
                    from . import evals
                    from .contract import EvalScore
                    case = evals.load_case(inp["case_id"])
                    if not any(e.get("layer") == 1 for e in job.evals) and any(p.get("layer") == 1 for p in job.personas if p["id"] in job.decisions):
                        job.evals.append(evals.score(job.view(), case, layer=1, iteration=0).model_dump())  # the base-model point
                    cur = evals.score(job.view(), case, layer=2, iteration=job.b.evolve_loops)
                except Exception as e:
                    return job._decide("score", reason, {}, f"Couldn't score ({type(e).__name__}: {str(e)[:150]}): treat this run as having no real outcomes.")
                s, fb = cur.model_dump(), evals.feedback_for_evolver(cur)
                keep = evals.improvement(EvalScore(**prev) if prev else None, cur)["keep_going"]
            job.evals.append(s)
            job._write_json("evals.json", job.evals)
            (job.dir / "evals.md").write_text(fb or "(no feedback)")
            job.save()
            delta = (f" Since last loop: rating_error {prev['rating_error'] - s['rating_error']:+.2f} better, theme_recall "
                     f"{s['theme_recall'] - prev['theme_recall']:+.2f}.") if prev else ""
            return job._decide("score", reason, {}, f"Loop {s['iteration']}: rating_error {s['rating_error']:.2f}, theme_recall "
                               f"{s['theme_recall']:.2f}.{delta} keep_going={keep}.\nFeedback for the evolver: {fb or 'none'}")

        @tool
        def evolve(persona_ids: list[str], focus: str, reason: str) -> str:
            """Update these personas' memory: what they learned at this business (versioned) and the general lessons for
            their customer type. focus = what to fix, e.g. score's feedback."""
            job.status = "evolving"
            if job.b.blocked("evolve_loops"):
                return job._decide("evolve", reason, {"persona_ids": persona_ids}, "Not evolved: evolve budget used.")
            ids = [p["id"] for p in job._people() if p["id"] in persona_ids]
            before = memory.business_snapshot(job.ns, ids)
            if not (job.dir / "owner.md").exists():
                (job.dir / "owner.md").write_text("(nothing yet)\n")
            if job.stub:
                for pid in ids:
                    memory.business_write(job.ns, pid, (before[pid][0].strip() + "\n" if before[pid][0].strip() else "") + f"- (eval) {focus}")
                changed = {pid: (before[pid][0].strip(), *[x.strip() if isinstance(x, str) else x for x in memory.business_read(job.ns, pid)]) for pid in ids}
            else:
                job._sub(EVOLVER.format(focus=focus), f"Update the memory of: {', '.join(ids)}.", name="evolver")
                changed = memory.business_bump(job.ns, before)
            memory.persist()
            job.b.evolve_loops += 1
            lines = []
            for pid, (old, new, v) in changed.items():
                added = [l.strip("-• ").strip() for l in new.splitlines() if l.strip() and l.strip() not in old]
                lesson = (added or [new])[0][:240]
                job.persona_changes.append({"persona_id": pid, "iteration": job.b.evolve_loops, "lesson": lesson, "before": old,
                                            "after": new, "source": "human" if "(owner)" in lesson else "simulation", "memory_version": v})
                lines.append(f"{pid} → v{v}: {lesson}")
            job.save()
            return job._decide("evolve", reason, {"persona_ids": ids, "focus": focus}, f"Loop {job.b.evolve_loops}: " + ("; ".join(lines) or "no memory changed"))

        @tool
        def run_social(reason: str, rounds: int = 2) -> str:
            """Word of mouth: every customer posts about the product, then for `rounds` rounds reads the feed and replies,
            reposts or stays quiet. Builds who-influenced-whom (PageRank), communities and which complaint spread."""
            job.status = "social"
            rounds = max(1, min(rounds, 3))
            if job.b.blocked("social_rounds", rounds):
                return job._decide("run_social", reason, {"rounds": rounds}, "Not run: social budget used.")
            people = [p for p in job._people() if p["id"] in job.decisions]
            if job.stub:
                job.social = _stub_social(people, job.decisions, rounds)
            else:
                from . import social
                job.social = social.run(people, job.decisions, inp.get("name") or inp["url"], rounds=rounds)
                if job.social:
                    try:
                        from . import network
                        job.social = {**job.social, **network.analyze(job.view()).model_dump(exclude={"posts"})}
                    except Exception as e:
                        job.log("error", f"network: {type(e).__name__}: {e}"[:200])
            job.b.social_rounds += rounds
            job._write_json("social.json", job.social or {})
            job.save()
            if not job.social:
                return job._decide("run_social", reason, {"rounds": rounds}, "Fewer than 2 customers decided: no feed.")
            posts = job.social["posts"]
            kinds = {k: sum(1 for p in posts if p["kind"] == k) for k in ("post", "reply", "repost")}
            return job._decide("run_social", reason, {"rounds": rounds}, f"{kinds['post']} posts, {kinds['reply']} replies, {kinds['repost']} reposts. "
                               f"Spreads furthest: {', '.join(job.social.get('top_influencers', [])[:3])}. {job.social.get('summary', '')[:200]}")

        @tool
        def summarize(reason: str) -> str:
            """Headline numbers: buy rate, rating, by model, by segment, layer 1 -> 2 delta, top suggestions."""
            job.status = "summarizing"
            _resummarize(job)
            s = job.summary
            tops = "; ".join(t.get("change", "")[:70] for t in (s.get("top_suggestions") or [])[:3])
            return job._decide("summarize", reason, {}, f"Buy rate {round(s['buy_rate'] * 100)}%, rating {s['rating']}/5, by model "
                               f"{json.dumps(s.get('by_model'))[:200]}, AI agents: {[(a['model'], a['decision']) for a in s.get('agents', [])]}. "
                               f"Top suggestions: {tops or 'none'}")

        @tool
        def finish(lesson: str, reason: str) -> str:
            """Write the owner's report and to-do list, and save one lesson about running simulations like this one. Call last."""
            job.status = "analyzing"
            _resummarize(job)
            job._write_json("social.json", job.social or {})
            job._write_json("evals.json", job.evals)
            if job.stub:
                s = job.summary
                (job.dir / "report.md").write_text(f"# {inp['name']}: stub report\n\nBuy rate {round(s['buy_rate'] * 100)}%, rating {s['rating']}/5.\n")
            else:
                job._sub(REPORT, "Write the report.", name="report", subagents=[
                    {"name": "analyst", "description": "Reads every session and finds where agents got stuck and why they bought or left.", "system_prompt": ANALYST}])
            rp = job.dir / "report.md"
            job.report = rp.read_text() if rp.exists() else ""
            if not job.stub:
                job._actions()  # the owner's do-these-first list (sim.py)
            memory.add_director_lesson(f"[{_host(inp['url'])}] {lesson}")
            memory.persist()
            job.status = "done"
            job.save()
            return job._decide("finish", reason, {"lesson": lesson}, "Report written, lesson saved. Reply to the owner in one sentence and stop.")

        truth = (f"held-out real reviews of backtest case {inp['case_id']}" if inp.get("case_id") else
                 "fixture scores (stub mode)" if self.stub else "none: use the rules for runs without real outcomes")
        self._agent = create_deep_agent(
            model=self._brain(),
            system_prompt=DIRECTOR.format(name=inp.get("name") or _host(inp["url"]), url=inp["url"], category=inp.get("category") or "(read it)",
                                          context=inp.get("context") or "none", world=inp.get("world") or "today, normal times",
                                          customers=inp.get("customers") or "(read it from the site)", models=", ".join(self._models()),
                                          truth=truth, lessons=memory.director_lessons() or "(none yet)", rerun=_rerun_note(self)),
            tools=[brief_product, cast_personas, request_approval, run_base_models, run_personas, score, evolve, run_social, summarize, finish],
            subagents=[
                {"name": "briefer", "description": "Writes /product.md and /world.md: the product as a customer would understand it.", "system_prompt": BRIEFER},
                {"name": "segmenter", "description": "Decides how many customer types there are and which archetypes to cast; writes /segments.md.", "system_prompt": SEGMENTER},
                {"name": "analyst", "description": "Reads every session: where agents got stuck, what convinced buyers, AI agents vs customers.", "system_prompt": ANALYST},
                {"name": "critic", "description": "Checks whether the results can be trusted and which segments need more personas.", "system_prompt": CRITIC},
            ],
            middleware=[TodoListMiddleware()],  # write_todos: the director's live plan (not a default in this deepagents version)
            backend=self._backend(),
            store=memory.store(),
            checkpointer=checkpointer(),  # survives restarts: a paused director resumes from here
        )
        return self._agent


def _resummarize(job: DirectorJob):
    """sim._summarize (Candy) + compare.summary (B): by model, by segment, layer delta, top suggestions."""
    job.summary = {**(job.summary or {}), **job._summarize()}
    try:
        from . import compare
        job.summary.update(compare.summary(job.view(), judge="keyword" if job.stub else "auto"))
    except Exception as e:
        job.log("error", f"compare: {type(e).__name__}: {e}"[:200])
    job._write_json("summary.json", job.summary)
    job.save()


def _rerun_note(job: DirectorJob) -> str:
    if not job.round:
        return ""
    cast = "; ".join(f"{p['id']} {p['name']} ({p['archetype']}, {round(p['share'] * 100)}%, {p.get('model')}, memory v{p.get('memory_version', 0)})"
                     for p in job._people())
    return (f"\nTHIS IS ROUND {job.round}, A RETURN VISIT (previous sim {job.parent}). The same customers come back carrying what they "
            f"learned. They are already cast and approved: {cast}.\n"
            f"What the owner changed since last time: {job.inp.get('context') or 'nothing'}.\n"
            "Do not brief, cast or ask for approval again (only cast_personas if a segment turns out to be missing). Start with "
            "run_base_models (the site may have changed, so layer 1 needs a new baseline), then run_personas for everyone, then "
            "the learning loop, run_social, summarize and finish. In finish, say how this round differed from the last.\n")


def _run_digest(job: DirectorJob, run: dict) -> str:
    """What the director needs for the spawn and loop rules: decisions, confidence, and which segments split."""
    by_id = {p["id"]: p for p in job.personas}
    segs: dict[str, list[int]] = {}
    lines = []
    for aid, d in run["decisions"].items():
        p = by_id.get(aid, {})
        bought = int(aid in run["clicked_buy"] or BUYS.get(d["decision"], 0) >= 1)
        segs.setdefault(p.get("segment", "?"), []).append(bought)
        lines.append(f"{aid} {p.get('name', '')} ({p.get('archetype', '')}, {d.get('model')}): {d['decision']} {d['rating']}/5, "
                     f"confidence {d.get('confidence', '?')}")
    split = [s for s, v in segs.items() if 0 < sum(v) < len(v)]
    s = job.summary or {}
    return (f"Run {run['n']} (layer 2): buy rate {round((s.get('buy_rate') or 0) * 100)}%, rating {s.get('rating')}, "
            f"avg confidence {s.get('confidence')}. Segments that split: {', '.join(split) or 'none'}.\n" + "\n".join(lines))


# ---------------------------------------------------------------- stub mode

_NAMES = ["Maya", "Jordan", "Priya", "Tom", "Lena", "Marcus", "Aiko", "Sam"]


def _stub_personas(n, archetypes, fams, start):
    arch = [a for a in (archetypes or []) if a in session.ARCHETYPES] + [a for a in session.ARCHETYPES if a not in (archetypes or [])]
    return [{"id": f"p{start + i}", "name": _NAMES[(start - 1 + i) % len(_NAMES)], "age": 25 + 7 * i, "occupation": "stub",
             "archetype": arch[i % len(arch)], "segment": arch[i % len(arch)], "share": round(1 / n, 3),
             "goal": "try the product", "budget": "typical", "voice": "plain", "avatar": {"seed": start + i},
             "model": fams[(start - 1 + i) % len(fams)]} for i in range(n)]


def _stub_agents(fams, have):
    return [{"id": f"a{have + i + 1}", "kind": "agent", "layer": 1, "name": f"{f} agent", "age": 30, "occupation": "AI shopping agent",
             "archetype": "AI agent", "segment": "AI shopping agents acting for a user", "share": 0.0,
             "goal": 'Your user asked: "find one that fits under budget"', "budget": "typical", "voice": session.AGENT_VOICE,
             "model": f, "avatar": {"seed": 900 + have + i}} for i, f in enumerate(fams)]


def _stub_run(job: DirectorJob, agents: list[dict], layer: int) -> dict:
    with job._lock:
        n = len(job.runs) + 1
        run = {"n": n, "layer": layer, "agents": [a["id"] for a in agents], "decisions": {}, "clicked_buy": [],
               "memory_versions": {a["id"]: a.get("memory_version", 0) for a in agents}, "status": "done"}
        job.runs.append(run)
    for a in agents:
        rng = random.Random(f"{a['id']}-{a.get('memory_version', 0)}-{n}")
        d = rng.choices(["buy", "not buy", "maybe later"], weights=[3 + a.get("memory_version", 0), 3, 2])[0]
        dec = session.Decision(decision=d, rating=rng.randint(2, 5), feeling="interested", confidence=round(rng.uniform(0.3, 0.9), 2),
                               quote="stub quote", reasons=["stub"], liked=["clear prices"], disliked=["slow checkout"],
                               suggestions=[session.Suggestion(change="show shipping cost early", why="surprise fees", where=job.inp["url"], impact="would make me buy")]).model_dump()
        tags = session.agent_tags({**a, "layer": layer})
        run["decisions"][a["id"]] = job.decisions[a["id"]] = {**dec, **{k: v for k, v in tags.items() if k != "agent_id"}}
        job.live[a["id"]] = []
        (job.dir / "sessions" / f"{a['id']}.json").write_text(json.dumps({"persona": a["id"], **tags, "steps": [], "decision": dec}))
    job.summary = {**(job.summary or {}), **job._summarize()}
    job.save()
    return run


def _stub_score(job: DirectorJob) -> dict:
    """Error falls fast for two loops, then flattens, so the stop rule can be seen working."""
    k = job.b.evolve_loops
    err = [0.9, 0.6, 0.35, 0.3, 0.28][min(k, 4)]
    rec = [0.4, 0.55, 0.7, 0.72, 0.73][min(k, 4)]
    from .contract import EvalScore
    return EvalScore(iteration=k, case_id="stub", layer=2, stage="evolved" if k else "memory", actual_rating=4.1,
                     predicted_rating=round(4.1 - err, 2), rating_error=err, predicted_buy_rate=(job.summary or {}).get("buy_rate") or 0,
                     theme_recall=rec, theme_precision=0.6, distribution_distance=err / 2,
                     missed_themes=["shrinks in the dryer"] if k < 2 else [], judge="keyword", notes="stub").model_dump()


def _stub_social(people: list[dict], decisions: dict, rounds: int) -> dict | None:
    if len(people) < 2:
        return None
    posts = [{"id": f"s{i + 1}", "round": 0, "author": p["id"], "kind": "post", "target": None, "text": decisions[p["id"]]["quote"],
              "sentiment": 0.5 if decisions[p["id"]]["decision"] == "buy" else -0.4} for i, p in enumerate(people)]
    for r in range(1, rounds + 1):
        for p in people[: max(0, len(people) - 2 * r)]:  # fewer reactions each round
            t = next(x for x in posts if x["author"] != p["id"])
            posts.append({"id": f"s{len(posts) + 1}", "round": r, "author": p["id"], "kind": "reply", "target": t["id"], "text": "Same here.", "sentiment": 0.2})
    return {"posts": posts, "nodes": [], "edges": [], "top_influencers": [people[0]["id"]], "summary": "stub feed"}


# ---------------------------------------------------------------- entry points (sim.py routes here when the director is on)

def start(inp: dict, model=None) -> DirectorJob:
    job = DirectorJob(inp, model=model)
    SIMS_LIVE[job.id] = job
    job.save()
    threading.Thread(target=job.cast, daemon=True).start()
    return job


def restore(sim_id: str) -> DirectorJob | None:
    """After a server restart: a director sim that was paused for approval, rebuilt from sim.json + its checkpoint."""
    from . import sim
    f = sim.SIMS / Path(sim_id).name / "sim.json"
    if not f.exists():
        return None
    v = json.loads(f.read_text())
    if not (v.get("input") or {}).get("director") or v.get("status") != "awaiting_approval":
        return None
    if not checkpointer().get_tuple({"configurable": {"thread_id": sim_id}}):
        return None  # paused before checkpoints were saved to disk: nothing to resume
    job = DirectorJob(v["input"], saved=v)
    SIMS_LIVE[job.id] = job
    job.log("restored", "server restarted while waiting for the owner; resuming from the saved checkpoint")
    return job


def rerun(src: dict, change: str = "") -> DirectorJob:
    """Run again with the director: same customers (same memory lineage), next round; the owner may have changed the site."""
    inp = {**src["input"], "round": src.get("round", 0) + 1, "parent": src["id"], "evals_so_far": src.get("evals") or []}
    if change:
        inp["context"] = change
    job = DirectorJob(inp)
    keep = ("memory", "memory_version")
    job.personas = [p for p in src["personas"] if p.get("kind") == "agent"] + \
                   [job._with_memory({k: v for k, v in p.items() if k not in keep}) for p in src["personas"] if p.get("kind") != "agent"]
    job.b.personas = len(job._people())
    for p in job.personas:
        (job.dir / "personas" / f"{p['id']}.md").write_text(persona_md(p))
    SIMS_LIVE[job.id] = job
    job.log("round", f"round {job.round}: same {len(job._people())} customers, carrying what they learned")
    job.save()
    threading.Thread(target=job.cast, daemon=True).start()
    return job


def enabled(inp: dict) -> bool:
    return bool(inp.get("director")) or os.getenv("DIRECTOR") == "1"
