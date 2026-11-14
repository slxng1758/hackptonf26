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
import uuid
from datetime import datetime
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend

from . import session
from .models import brain

RUNS = Path(__file__).resolve().parent.parent / "runs"
SIMS = RUNS / "sims"
LIBRARY = RUNS / "persona_library"

BUYS = {"buy": 1.0, "would recommend": 1.0, "maybe later": 0.3, "not buy": 0.0, "would complain": 0.0}

ANALYST = """You analyze a customer simulation for a small business.
Product: {name} ({url}). What the business says changed: {context}. World: {world}.
Personas are in /personas/*.md, their real browsing sessions (every page, thought, feeling, click) in /sessions/*.json.

Do this, keeping your todo list updated:
1. Ask the analyst sub-agent to read every session and find: where people got stuck (which page, which step), what made them buy,
   what made them leave, and whether the business's claimed change was actually visible to them.
2. Ask the evolver sub-agent to update every persona file with a "## Memory" section: 1-3 concrete things this persona learned
   about this kind of product, so the next simulation starts smarter.
3. Write /report.md for the business owner, short, with these sections: the weighted buy rate and rating, broken down by
   customer type (archetype and share); where people got stuck (which page); what convinced the buyers; the top 3 fixes
   (each tied to a persona and a page they saw); which complaint is most likely to spread by word of mouth and why; and
   where the simulation might be wrong.
Reply with one sentence."""

ANALYST_SUB = ("You read customer browsing sessions (JSON) and persona files. Report in at most 180 words: where each persona got stuck "
               "(page + step), the most common reason to leave, what convinced buyers, and whether the business's claimed change was visible.")
EVOLVER_SUB = ("You update persona files. For every file in /personas, append or replace a '## Memory' section with 1-3 short lessons that "
               "persona learned from its session (concrete, about this kind of product). Keep the rest of the file. Edit the files directly.")


def persona_md(p: dict) -> str:
    return (f"# {p['name']} ({p['id']})\n\n- Age: {p['age']}\n- Occupation: {p['occupation']}\n- Archetype: {p['archetype']}\n"
            f"- Segment: {p['segment']} ({round(p['share'] * 100)}% of customers)\n- Goal: {p['goal']}\n- Budget: {p['budget']}\n- Voice: {p['voice']}\n"
            + (f"\n## Memory\n{p['memory']}\n" if p.get("memory") else ""))


class SimJob:
    def __init__(self, inp: dict):
        self.id = datetime.now().strftime("%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
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
        self.dir = SIMS / self.id
        for d in ("personas", "sessions", "shots"):
            (self.dir / d).mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

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
                "persona_changes": self.persona_changes}

    def save(self):
        with self._lock:
            (self.dir / "sim.json").write_text(json.dumps(self.view(), indent=2))

    # ---- phase 1: cast, then pause for the owner
    def cast(self, feedback: str = ""):
        try:
            i = self.inp
            if feedback:
                i["customers"] = (i.get("customers") or "") + f"\nThe owner corrected the cast: {feedback}"
                self.log("owner", f"correction: {feedback}")
            if not i.get("name") or not i.get("customers") or not i.get("offer"):
                site = session.read_site(i["url"])
                for k in ("name", "category", "customers", "offer"):
                    i[k] = i.get(k) or site[k]
                self.log("read", f"{i['name']}: {i['category']}")
            self.personas = session.cast(i["name"], i["category"], i.get("context", ""), i.get("world", ""), i["customers"], i.get("offer", ""))
            self.log("cast", " · ".join(f"{p['name']} ({p['archetype']}, {round(p['share'] * 100)}%)" for p in self.personas))
            self.status = "awaiting_approval"
        except Exception as e:
            self.status, self.error = "error", f"{type(e).__name__}: {e}"[:300]
        self.save()

    # ---- phase 2: owner approved → browse → analyze
    def approve(self, personas: list[dict] | None):
        if personas:
            self.personas = personas
        self.status = "browsing"
        self.log("approved", f"owner approved {len(self.personas)} personas")
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
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
                if r.get("decision"):
                    self.decisions[pid] = r["decision"]
                    self.log("decision", f"{next(p['name'] for p in self.personas if p['id'] == pid)}: {r['decision']['decision']} ({r['decision']['rating']}/5)")
                else:
                    self.log("error", f"{pid}: {r.get('error')}")

            session.run_all(self.personas, i["url"], i.get("world", ""), i.get("context", ""), self.dir / "shots", on_step, on_done)
            self.summary = self._summarize()
            self.status = "analyzing"
            self.save()
            before = {p["id"]: (p.get("memory") or "").strip() for p in self.personas}
            self._analyze()
            self._record_changes(before)
            self.status = "done"
        except Exception as e:
            self.status, self.error = "error", f"{type(e).__name__}: {e}"[:300]
            self.log("error", self.error)
        self.save()

    def _summarize(self):
        share = {p["id"]: p["share"] for p in self.personas}
        got = {pid: d for pid, d in self.decisions.items()}
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
            if p["id"] in got:
                m = by_model.setdefault(p.get("model", "Claude"), [0, 0])
                m[1] += 1
                m[0] += int(p["id"] in carted or BUYS.get(got[p["id"]]["decision"], 0) >= 1)
        return {"buy_rate": round(buy, 3), "clicked_buy": sorted(carted), "by_model": {k: {"bought": v[0], "of": v[1]} for k, v in by_model.items()}, "rating": round(rating, 2), "decisions": counts,
                "missing": [{"persona": pid, "text": d["missing"]} for pid, d in got.items()]}

    def _record_changes(self, before: dict):
        """What each persona learned this round: its memory before and after the evolver ran."""
        for p in self.personas:
            f = self.dir / "personas" / f"{p['id']}.md"
            after = f.read_text().split("## Memory", 1)[1].strip() if f.exists() and "## Memory" in f.read_text() else ""
            if after and after != before.get(p["id"], ""):
                new = [l.strip("-• ").strip() for l in after.splitlines() if l.strip() and l.strip() not in before.get(p["id"], "")]
                self.persona_changes.append({"persona_id": p["id"], "iteration": self.round + 1, "lesson": (new or [after])[0][:240],
                                             "before": before.get(p["id"], ""), "after": after})
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
            backend=FilesystemBackend(root_dir=str(self.dir), virtual_mode=True),
        )
        for update in agent.stream({"messages": [{"role": "user", "content": "Begin."}]}, config={"recursion_limit": 80}, stream_mode="updates"):
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
        self.log("memory", f"saved {len(self.personas)} evolved personas to the persona library")


SIMS_LIVE: dict[str, SimJob] = {}


def start(inp: dict) -> SimJob:
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


def approve(sim_id: str, personas: list[dict] | None) -> bool:
    job = SIMS_LIVE.get(sim_id)
    if not job or job.status != "awaiting_approval":
        return False
    job.approve(personas)
    return True


def recast(sim_id: str, feedback: str) -> bool:
    """Owner says the personas are off ("my customers are older"): cast again with that correction."""
    job = SIMS_LIVE.get(sim_id)
    if not job or job.status != "awaiting_approval":
        return False
    job.status = "casting"
    job.save()
    threading.Thread(target=job.cast, args=(feedback,), daemon=True).start()
    return True


def rerun(sim_id: str) -> SimJob | None:
    """Next round: the same customers, now carrying what they learned, visit again."""
    src = get(sim_id)
    if not src or src.get("status") != "done":
        return None
    inp = {**src["input"], "round": src.get("round", 0) + 1, "parent": sim_id}
    job = SimJob(inp)
    SIMS_LIVE[job.id] = job
    mem = src.get("memory") or {}
    job.personas = [{**p, "memory": mem.get(p["id"], p.get("memory", ""))} for p in src["personas"]]
    job.log("round", f"round {job.round}: same {len(job.personas)} customers, carrying what they learned")
    job.approve(None)
    return job


def list_sims():
    out = []
    for p in sorted(SIMS.glob("*/sim.json"), reverse=True):
        try:
            d = json.loads(p.read_text())
            out.append({"id": d["id"], "name": d["input"]["name"], "status": d["status"], "buy_rate": (d.get("summary") or {}).get("buy_rate")})
        except Exception:
            pass
    return out
