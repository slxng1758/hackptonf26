"""Message Lab: stress-test a public-health message before it goes out.

The user gives a message and describes a community in plain words. A deep agent then:
  1. designs the community (who people trust, how groups connect, what the hazard is),
  2. runs the message through a simulated population where messengers retell it in their own voice,
  3. has a critic sub-agent explain where it broke and who distorted it,
  4. has a rewriter sub-agent propose a sturdier message and which messengers to brief first,
  5. re-tests, and writes a report.

Every trial is saved in the same shape as sim/epidemic.py output, so all the views can replay it.
"""
from __future__ import annotations

import json
import math
import random
import statistics
import threading
import uuid
from datetime import datetime
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from .models import evaluator_model, villager_model

ROOT = Path(__file__).resolve().parent.parent / "runs"
LAB = ROOT / "lab"
EPI = ROOT / "epi"


# ---------- schemas ----------
class Messenger(BaseModel):
    role: str = Field(description="short role name, e.g. 'pastor', 'grandmother', 'pharmacist', 'WeChat group admin'")
    voice: str = Field(description="how this person retells things, one sentence, specific to this community")
    count: int = Field(ge=1, le=4, description="how many of them per group")
    retell: float = Field(ge=0, le=0.6, description="chance they rephrase a message instead of repeating it")


class Group(BaseModel):
    name: str = Field(description="a real-sounding name for this part of the community")
    size: int = Field(ge=8, le=22, description="ordinary members in this group")
    exposed_from_day: int = Field(ge=0, le=40, description="day the hazard reaches this group")


class Community(BaseModel):
    name: str
    groups: list[Group] = Field(min_length=3, max_length=5)
    messengers: list[Messenger] = Field(min_length=2, max_length=5, description="messenger roles present in every group")
    hubs: list[Messenger] = Field(min_length=1, max_length=3, description="roles that connect groups, e.g. a market, a group chat, a clinic")
    hazard: str = Field(description="the health hazard the message is about, in a few words")
    action: str = Field(description="the protective action people must take, in a few words")
    why: str = Field(description="the true reason the action works, one sentence")
    contagious: bool = Field(description="true if people infect each other, false if the hazard comes from the environment (water, heat, smoke)")


class VariantScore(BaseModel):
    practice: float = Field(ge=0, le=1, description="chance someone who believes this text still takes the protective action correctly")
    belief: float = Field(ge=0, le=1, description="how much of the true reason survives")
    myth: float = Field(ge=0, le=1, description="how much the reason has turned into rumor, superstition, authority or fear instead of the real cause")
    short: str = Field(description="the text in at most 8 words")


DESIGN = """Design a realistic simulated community for stress-testing a public-health message.

Community description from the user: {description}
The message being tested: "{message}"

Use the real kinds of trusted messengers in this community (faith leaders, elders, shopkeepers, group chats, clinics...),
with voices specific to it. Make exposure days differ between groups. Keep it respectful and grounded, no caricatures.
Use generic descriptive names for groups and roles (e.g. "temple congregation", "walk-up seniors"). Never name real
institutions, businesses, streets or people: this is a simulation and must not imply real organizations spread misinformation."""

SCORE = """You judge how a health message survived retelling.
Protective action: {action}
True reason it works: {why}
Text people now believe: "{text}"
Score it strictly. If the action is missing, distorted or replaced, practice is low."""

RETELL = """You are {voice} ({role}) in {community}. Someone just told you:

"{saying}"

Pass it on the way you really would, in one sentence of at most 22 words. You may simplify, add a reason you believe,
or change the wording. Do not add quotes or explanations."""


def _text(content) -> str:
    if isinstance(content, list):
        content = " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return str(content).strip().strip('"').split("\n")[0].strip().strip('"')[:180]


# ---------- the simulated population ----------
def build(com: Community, rng: random.Random):
    people, edges, groups = [], set(), []
    k = len(com.groups)
    centers = [(math.cos(a) * 0.62, math.sin(a) * 0.62) for a in [math.pi * (0.25 + 2 * i / k) for i in range(k)]]
    for gi, g in enumerate(com.groups):
        members = []
        roles = [("member", g.size)] + [(m.role, m.count) for m in com.messengers]
        for role, n in roles:
            for _ in range(n):
                a, r = rng.random() * math.tau, 0.22 * math.sqrt(rng.random())
                members.append(len(people))
                people.append({"id": len(people), "village": gi, "role": role, "x": centers[gi][0] + r * math.cos(a), "y": centers[gi][1] + r * math.sin(a)})
        for a in members:
            for b in rng.sample(members, min(4, len(members))):
                if a != b:
                    edges.add((min(a, b), max(a, b)))
        groups.append(members)
    for h in com.hubs:
        for _ in range(max(2, h.count)):
            pid = len(people)
            a, r = rng.random() * math.tau, 0.12 * math.sqrt(rng.random())
            people.append({"id": pid, "village": -1, "role": h.role, "x": r * math.cos(a), "y": r * math.sin(a)})
            for gi in rng.sample(range(k), min(k, 3)):
                for b in rng.sample(groups[gi], 3):
                    edges.add((min(pid, b), max(pid, b)))
    nbrs = {p["id"]: [] for p in people}
    for a, b in edges:
        nbrs[a].append(b)
        nbrs[b].append(a)
    return people, sorted(edges), nbrs


class Trial:
    """One message through one community, many random worlds. The first world is kept for replay."""

    def __init__(self, com: Community, log=None):
        self.com = com
        self.model = villager_model()
        self.judge = villager_model()  # fast model for the many variant scores; the report uses the strong one
        self.cache_retell: dict[str, list[str]] = {}
        self.cache_score: dict[str, dict] = {}
        self.log = log or (lambda *_: None)
        self.lock = threading.Lock()
        self.roles = {m.role: m for m in [*com.messengers, *com.hubs]}

    def score(self, text: str) -> dict:
        if text in self.cache_score:
            return self.cache_score[text]
        s: VariantScore = self.judge.with_structured_output(VariantScore, method="json_schema").invoke(
            SCORE.format(action=self.com.action, why=self.com.why, text=text))
        self.cache_score[text] = s.model_dump()
        return self.cache_score[text]

    def retell(self, role: str, saying: str, rng: random.Random, fresh_left: list[int]) -> str:
        key = f"{role}|{saying}"
        seen = self.cache_retell.get(key, [])
        if seen and (fresh_left[0] <= 0 or rng.random() < 0.6):
            return rng.choice(seen)
        if fresh_left[0] <= 0:
            return ""
        m = self.roles.get(role)
        voice = m.voice if m else "an ordinary member of the community who repeats what they heard, a little loosely"
        out = _text(self.model.invoke(RETELL.format(voice=voice, role=role, community=self.com.name, saying=saying)).content)
        fresh_left[0] -= 1
        if out:
            self.cache_retell.setdefault(key, []).append(out)
        return out

    def world(self, message: str, seed: int, brief: list[str], days=50, fresh=10):
        rng = random.Random(seed)
        people, edges, nbrs = build(self.com, random.Random(11))
        variants: list[dict] = []
        fresh_left = [fresh]

        def add(text, parent, day, pid, role):
            for v in variants:
                if v["text"] == text:
                    return v["id"]
            s = self.score(text)
            variants.append({"id": len(variants), "parent": parent, "text": text, "day": day, "person": pid, "role": role, **s})
            return len(variants) - 1

        belief: list[int | None] = [None] * len(people)
        health, since, ever = ["S"] * len(people), [0] * len(people), 0
        root = add(message, None, 0, -1, "health department")
        # the message goes out through hubs, plus any messengers we briefed directly
        for p in people:
            if p["village"] == -1 or p["role"] in brief:
                belief[p["id"]] = root
        frames = []
        for day in range(days + 1):
            order = list(range(len(people)))
            rng.shuffle(order)
            for a in order:
                if belief[a] is None or rng.random() > 0.35:
                    continue
                b = rng.choice(nbrs[a])
                v = variants[belief[a]]
                if belief[b] is not None and rng.random() > 0.2 + 0.4 * v["myth"]:
                    continue
                role = people[b]["role"]
                r = self.roles[role].retell if role in self.roles else 0.04
                if rng.random() < r:
                    t = self.retell(role, v["text"], rng, fresh_left)
                    belief[b] = add(t, v["id"], day, b, role) if t else v["id"]
                else:
                    belief[b] = v["id"]
            new = health[:]
            for p in people:
                i = p["id"]
                acts = belief[i] is not None and rng.random() < variants[belief[i]]["practice"]
                if health[i] == "S":
                    risk = 0.0
                    g = p["village"]
                    if g >= 0 and day >= self.com.groups[g].exposed_from_day:
                        risk += 0.035
                    if self.com.contagious:
                        risk += 0.03 * sum(1 for n in nbrs[i] if health[n] == "I")
                    if acts:
                        risk *= 0.12
                    if rng.random() < risk:
                        new[i], since[i] = "I", day
                        ever += 1
                elif health[i] == "I" and day - since[i] >= 7:
                    new[i] = "R"
            health = new
            frames.append({"day": day, "b": belief[:], "h": "".join(health), "sick_total": ever})
        final = frames[-1]["b"]
        acting = sum(variants[v]["practice"] for v in final if v is not None) / len(people)
        return {"people": people, "edges": edges, "variants": variants, "frames": frames, "ever_sick": ever, "acting": acting}

    def run(self, message: str, brief: list[str], worlds=6) -> dict:
        results = []
        for s in range(1, worlds + 1):
            # only the first world generates fresh retellings live; the rest reuse them, so a trial takes ~1 minute
            results.append(self.world(message, s, brief, fresh=10 if s == 1 else 2))
            self.log("trial", f"world {s}/{worlds}: {results[-1]['ever_sick']} sick")
        sick = [r["ever_sick"] for r in results]
        best = results[0]
        # who bent the message most: drift by role, weighted by how many people heard their version
        final = best["frames"][-1]["b"]
        reach: dict[str, list[float]] = {}
        for v in best["variants"]:
            if v["parent"] is None:
                continue
            n = sum(1 for x in final if x == v["id"])
            reach.setdefault(v["role"], []).append(n * (1 - v["practice"]))
        distorters = sorted(((r, round(sum(xs), 1)) for r, xs in reach.items()), key=lambda t: -t[1])[:3]
        top = sorted(best["variants"], key=lambda v: -sum(1 for x in final if x == v["id"]))[:4]
        return {
            "message": message, "brief": brief, "worlds": worlds,
            "sick_mean": statistics.mean(sick), "sick_sd": statistics.stdev(sick) if len(sick) > 1 else 0,
            "acting_mean": statistics.mean(r["acting"] for r in results), "population": len(best["people"]),
            "distorters": distorters,
            "top_variants": [{"text": v["text"], "practice": v["practice"], "myth": v["myth"], "role": v["role"]} for v in top],
            "replay": best,
        }


# ---------- the deep agent ----------
AGENT = """You run Message Lab for a public-health team. Your job: make a health message survive being retold.

The message: "{message}"
The community: {description}

Work like this, and keep your todo list updated as you go:
1. Call design_community once.
2. Call run_trial with the original message and no briefed messengers. This is the baseline.
3. Ask the critic to read /trials and explain where the message broke, quoting the worst variants and naming who distorted it.
4. Ask the rewriter for an improved message and which messenger roles to brief first.
5. Call run_trial with that improved message and those messengers.
6. If people taking the action did not clearly improve, do one more critic and rewriter round and test again (at most 3 trials total).
7. Write /report.md: the best message, who to brief, the numbers for every trial, and an honest caveat that this is a simulation.
Reply with one sentence summarizing the result."""

CRITIC = ("You are a risk-communication critic. Read the trial files in /trials (JSON). Explain in at most 120 words where the message "
          "broke: quote the most harmful variants, name the roles that distorted it, and say why the original wording invited that.")
REWRITER = ("You are a public-health writer. Read /community.json and the critic's notes. Propose ONE improved message (max 25 words) that is "
            "hard to distort: concrete action, short reason, easy to repeat, culturally fitting. Also name 1 to 3 messenger roles from "
            "/community.json to brief directly. Answer exactly as: MESSAGE: <text> | BRIEF: <role>, <role>")


class Job:
    def __init__(self, message: str, description: str):
        self.id = datetime.now().strftime("%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        self.message, self.description = message, description
        self.status, self.error = "running", None
        self.steps: list[dict] = []
        self.community: dict | None = None
        self.trials: list[dict] = []
        self.report = ""
        self.dir = LAB / self.id
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "trials").mkdir(exist_ok=True)

    def log(self, kind: str, note: str):
        self.steps.append({"t": datetime.now().strftime("%H:%M:%S"), "kind": kind, "note": note[:300]})
        self.save()

    def summary(self) -> dict:
        return {"id": self.id, "message": self.message, "description": self.description, "status": self.status, "error": self.error,
                "steps": self.steps, "community": self.community, "report": self.report,
                "trials": [{k: v for k, v in t.items() if k != "replay"} for t in self.trials]}

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
        job = self
        state: dict = {}

        @tool
        def design_community() -> str:
            """Design the simulated community from the user's description. Call once, first."""
            if "com" in state:  # every trial must run on the same community, or comparisons are meaningless
                return json.dumps(job.community) + "\n(Already designed. Reusing this community for every trial.)"
            com: Community = evaluator_model().with_structured_output(Community, method="json_schema").invoke(
                DESIGN.format(description=job.description, message=job.message))
            state["com"] = com
            state["trial"] = Trial(com, log=job.log)
            job.community = com.model_dump()
            (job.dir / "community.json").write_text(json.dumps(job.community, indent=2))
            job.log("community", f"{com.name}: {len(com.groups)} groups, messengers {', '.join(m.role for m in com.messengers)}; hubs {', '.join(h.role for h in com.hubs)}")
            return json.dumps(job.community)

        @tool
        def run_trial(message: str, brief: list[str] | None = None) -> str:
            """Simulate the message spreading through the community across several random worlds.
            `brief` lists messenger roles told the message directly by the health team. Returns people taking the action, sickness, top variants and who distorted it."""
            if "trial" not in state:
                return "Call design_community first."
            job.log("trial", f"testing: \"{message}\"" + (f" (briefing {', '.join(brief)})" if brief else ""))
            r = state["trial"].run(message, brief or [])
            n = len(job.trials) + 1
            replay = r["replay"]
            epi_id = f"{job.id}-trial{n}"
            com: Community = state["com"]
            EPI.mkdir(parents=True, exist_ok=True)
            (EPI / f"{epi_id}.json").write_text(json.dumps({
                "id": epi_id, "scenario": f"lab trial {n}", "days": len(replay["frames"]) - 1, "population": len(replay["people"]),
                "ever_sick": replay["ever_sick"], "villages": [{"name": g.name, "water": com.hazard} for g in com.groups],
                "contaminated": {str(i): g.exposed_from_day for i, g in enumerate(com.groups)},
                "people": replay["people"], "edges": replay["edges"], "variants": replay["variants"], "frames": replay["frames"],
                "lab": job.id, "message": message,
            }))
            r["replay_id"] = epi_id
            job.trials.append(r)
            slim = {k: v for k, v in r.items() if k != "replay"}
            (job.dir / "trials" / f"trial_{n}.json").write_text(json.dumps(slim, indent=2))
            job.log("result", f"trial {n}: {round(r['acting_mean'] * 100)}% take the action, {r['sick_mean']:.1f} ± {r['sick_sd']:.1f} of {r['population']} fell sick")
            return json.dumps(slim)

        agent = create_deep_agent(
            model=evaluator_model(),
            system_prompt=AGENT.format(message=self.message, description=self.description),
            tools=[design_community, run_trial],
            subagents=[
                {"name": "critic", "description": "Explains where a tested message broke and who distorted it.", "system_prompt": CRITIC},
                {"name": "rewriter", "description": "Proposes a sturdier message and which messengers to brief.", "system_prompt": REWRITER},
            ],
            backend=FilesystemBackend(root_dir=str(self.dir), virtual_mode=True),
        )
        self.log("plan", "agent started")
        for update in agent.stream({"messages": [{"role": "user", "content": "Begin."}]}, config={"recursion_limit": 120}, stream_mode="updates"):
            for node in update.values():
                for m in (node or {}).get("messages", []) if isinstance(node, dict) else []:
                    for call in getattr(m, "tool_calls", None) or []:
                        a = call.get("args", {})
                        if call["name"] == "write_todos":
                            self.log("plan", " → ".join(f"{'✓ ' if t.get('status') == 'completed' else ''}{t.get('content', '')}" for t in a.get("todos", [])))
                        elif call["name"] == "task":
                            self.log(a.get("subagent_type", "subagent"), (a.get("description") or "")[:240])
                        elif call["name"] in ("write_file", "edit_file"):
                            self.log("file", str(a.get("file_path", "")))
                    if getattr(m, "type", "") == "tool" and getattr(m, "name", "") == "task":
                        self.log("answer", _text(m.content)[:300])
        rp = self.dir / "report.md"
        self.report = rp.read_text() if rp.exists() else ""


JOBS: dict[str, Job] = {}


def start(message: str, description: str) -> Job:
    job = Job(message, description)
    JOBS[job.id] = job
    job.save()
    threading.Thread(target=job.run, daemon=True).start()
    return job


def get(job_id: str) -> dict | None:
    if job_id in JOBS:
        return JOBS[job_id].summary()
    p = LAB / Path(job_id).name / "job.json"
    return json.loads(p.read_text()) if p.exists() else None


def list_jobs() -> list[dict]:
    out = []
    for p in sorted(LAB.glob("*/job.json"), reverse=True):
        try:
            d = json.loads(p.read_text())
            out.append({"id": d["id"], "message": d["message"], "status": d["status"], "trials": len(d["trials"])})
        except Exception:
            pass
    return out
