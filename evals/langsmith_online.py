"""The tool-calling checks as LangSmith online evaluators: they show on the Evaluators page and score every live trace.

    .venv/bin/python -m evals.langsmith_online                        # create or update them on $LANGSMITH_PROJECT
    .venv/bin/python -m evals.langsmith_online --backfill 2026-11-15  # also score the traces since that day
    .venv/bin/python -m evals.langsmith_online --print customer       # show the code LangSmith runs, change nothing

Each evaluator is built from the check functions in checks.py (their source is copied in), plus a small parser for the
message dicts LangSmith stores, so a check is written once and runs both in `pytest evals` and on production traces.
Run this again after changing a check. LangSmith runs the code in its own sandbox (standard library only, no network).

Only checks that need nothing but the agent's own messages are here. The ones that need the job view, the files the
agents wrote, scenario facts or an LLM judge stay in `pytest evals`.
"""
from __future__ import annotations

import argparse
import inspect
import json
import os
import re
import sys
import time

import httpx

from b2a.session import ARCHETYPES

from . import checks, trajectory

C = checks
CUSTOMER_CHECKS = [C.opens_site_first, C.decided_with_tool, C.clicks_visible_targets, C.moves_well_formed, C.no_corrective_results]
DIRECTOR_CHECKS = [C.starts_with_brief, C.setup_order, C.own_tools_serial, C.reasons_given, C.cast_rules,
                   C.approval_before_rounds, C.layer1_first, C.round_protocol, C.no_corrective_results,
                   C.critic_after_layer2, C.loop_stop_rule, C.spawn_rule, C.finish_last, C.efficiency]
HELPERS = ["briefer", "segmenter", "critic", "analyst", "evolver"]

# name: (which runs, the regex the code double-checks names with, when a run is ready to score, checks)
SPECS = {
    "customer": {
        "title": "customer tool use",
        "filter": 'and(eq(run_type, "chain"), or(like(name, "customer:%"), like(name, "p%-%"), like(name, "a%-agent")))',
        "names": r"^(customer:|[ap]\d+-)",
        "ready": "def ready(r):\n    return bool(r.traj.calls)\n",
        "checks": CUSTOMER_CHECKS,
    },
    "director": {
        "title": "director tool use",
        "filter": 'eq(name, "director")',
        "names": r"^director$",
        # the director pauses for the owner's approval: each resume is a new run. Score the one that finished.
        "ready": "def ready(r):\n    return any(c.name == 'finish' for c in r.traj.calls)\n",
        "checks": DIRECTOR_CHECKS,
    },
    "helpers": {
        "title": "helper subagent tool use",
        "filter": "or(" + ", ".join(f'eq(name, "{n}")' for n in HELPERS) + ")",
        "names": "^(" + "|".join(HELPERS) + ")$",
        # sim.py's "analyst" is an orchestrator with its own subagents (it calls `task`): not a helper
        "ready": "def ready(r):\n    return bool(r.traj.calls) and not r.traj.of('task')\n",
        "checks": [C.only_file_tools],
        "extra": ("def critic_spawn_line(r):\n    return spawn_line(r) if r.meta.get('name') == 'critic' else None\n",
                  [C.spawn_line], ["critic_spawn_line"]),
    },
}

PRELUDE = '''import json
import re
from collections import Counter
from dataclasses import dataclass, field

OWN = {own!r}
FILE_TOOLS = {file_tools!r}
INF = 10 ** 9
ARCHETYPES = {archetypes!r}
CORRECTIVE = re.compile({corrective!r}, {flags})
CUSTOMER_NAME = re.compile({customer_name!r})
APPLIES = re.compile({applies!r})


{text_of}

{call}

def _kind(m):
    if m.get("lc") == 1 and isinstance(m.get("kwargs"), dict):  # langchain-serialized message
        return str((m.get("id") or [""])[-1]).lower().replace("messagechunk", "").replace("message", ""), m["kwargs"]
    return str(m.get("type") or m.get("role") or "").lower().replace("messagechunk", "").replace("message", ""), m


@dataclass
class Trajectory:
    """trajectory.Trajectory, read from the message dicts LangSmith stores instead of langchain message objects."""
    calls: list = field(default_factory=list)
    turns: list = field(default_factory=list)
    final_text: str = ""
    tokens: dict = field(default_factory=lambda: {{"input": 0, "output": 0}})

    @classmethod
    def from_dicts(cls, messages):
        t, by_id = cls(), {{}}
        for raw in messages or []:
            if not isinstance(raw, dict):
                continue
            kind, m = _kind(raw)
            if kind in ("ai", "assistant"):
                turn = []
                for tc in m.get("tool_calls") or []:
                    c = Call(tc.get("name", ""), dict(tc.get("args") or {{}}), tc.get("id") or "", len(t.calls), len(t.turns))
                    t.calls.append(c)
                    turn.append(c)
                    by_id[c.id] = c
                t.turns.append(turn)
                u = m.get("usage_metadata") or {{}}
                t.tokens["input"] += u.get("input_tokens", 0) or 0
                t.tokens["output"] += u.get("output_tokens", 0) or 0
                if text_of(m.get("content")).strip() and not m.get("tool_calls"):
                    t.final_text = text_of(m.get("content")).strip()
            elif kind == "tool" and m.get("tool_call_id") in by_id:
                c = by_id[m["tool_call_id"]]
                c.result = text_of(m.get("content"))
                c.error = m.get("status", "success") == "error"
        return t

    def of(self, *names):
        return [c for c in self.calls if c.name in names or c.label in names]

    def first(self, name):
        return next(iter(self.of(name)), None)


@dataclass
class RunRecord:
    traj: Trajectory
    view: dict = field(default_factory=dict)
    files: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)


{ready}
'''

FOOTER = '''

CHECKS = [{checks}]


def perform_eval(run):
    get = run.get if isinstance(run, dict) else (lambda k, d=None: getattr(run, k, d))
    name = get("name") or ""
    if not APPLIES.search(name):
        return {{}}
    outputs = get("outputs") or {{}}
    r = RunRecord(Trajectory.from_dicts(outputs.get("messages") if isinstance(outputs, dict) else []), meta={{"name": name}})
    if not ready(r):
        return {{}}
    out = {{}}
    for check in CHECKS:
        try:
            x = check(r)
        except Exception as e:  # a check that can't read this run is skipped, not scored 0
            out.setdefault("_errors", []).append(f"{{check.__name__}}: {{type(e).__name__}}: {{e}}"[:200])
            continue
        if x is not None:
            out[x["key"]] = x["score"]
    out.pop("_errors", None)
    return out
'''

# helpers in checks.py that the checks above call
HELPER_FNS = [C.res, C._frac, C.own_calls, C.opened_rounds, C.round_names, C.approved_at, C.keep_going, C.budget_hit,
              C._visible]


def build_code(kind: str) -> str:
    s = SPECS[kind]
    extra_src, extra_fns, extra_names = s.get("extra", ("", [], []))
    fns = HELPER_FNS + list(extra_fns) + [f for f in s["checks"] if f not in extra_fns]
    body = "\n\n".join(inspect.getsource(f) for f in dict.fromkeys(fns))
    code = PRELUDE.format(own=C.OWN, file_tools=sorted(C.FILE_TOOLS), archetypes=list(ARCHETYPES),
                          corrective=C.CORRECTIVE.pattern, flags="re.I" if C.CORRECTIVE.flags & re.I else "0",
                          customer_name=trajectory.CUSTOMER_NAME.pattern, applies=s["names"],
                          text_of=inspect.getsource(trajectory.text_of), call=inspect.getsource(trajectory.Call),
                          ready=s["ready"])
    code += "\n" + body + "\n\n" + extra_src
    code += FOOTER.format(checks=", ".join([f.__name__ for f in s["checks"]] + list(extra_names)))
    return code


# ---------------------------------------------------------------- LangSmith API

class API:
    def __init__(self):
        key = os.getenv("LANGSMITH_API_KEY")
        if not key:
            sys.exit("LANGSMITH_API_KEY is not set")
        base = (os.getenv("LANGSMITH_ENDPOINT") or "https://api.smith.langchain.com").rstrip("/")
        self.h = httpx.Client(base_url=f"{base}/api/v1", headers={"x-api-key": key}, timeout=60)

    def __call__(self, method: str, path: str, **kw):
        r = self.h.request(method, path, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {path}: {r.status_code} {r.text[:500]}")
        return r.json() if r.content else None

    def project_id(self, name: str) -> str:
        got = self("GET", "/sessions", params={"name": name})
        if not got:
            sys.exit(f"no LangSmith project named {name!r} (it is created by the first trace)")
        return got[0]["id"]

    def evaluator(self, name: str) -> dict | None:
        got = self("GET", "/platform/evaluators", params={"name_contains": name, "type": "code", "limit": 100})
        return next((e for e in got.get("evaluators") or [] if e["name"] == name), None)

    def wait_built(self, eid: str, timeout: float = 300) -> dict:
        t0 = time.time()
        while True:
            e = self("GET", f"/platform/evaluators/{eid}")
            st = (e.get("code_evaluator") or {}).get("evaluator_build_status")
            if st in (None, "READY"):
                return e
            if st == "FAILED":
                raise RuntimeError(f"build failed: {(e.get('code_evaluator') or {}).get('evaluator_build_error')}")
            if time.time() - t0 > timeout:
                raise RuntimeError(f"build still {st} after {timeout:.0f}s")
            time.sleep(3)


def sync(project: str, backfill: str | None = None, only: list[str] | None = None) -> None:
    api = API()
    sid = api.project_id(project)
    for kind in only or list(SPECS):
        s, code = SPECS[kind], build_code(kind)
        compile(code, kind, "exec")
        name = f"hackpton: {s['title']}"
        body = {"code": code, "language": "python"}
        e = api.evaluator(name)
        if e:
            api.wait_built(e["id"])
            api("PATCH", f"/platform/evaluators/{e['id']}", json={"code_evaluator": body})
            print(f"updated  {name}")
        else:
            e = api("POST", "/platform/evaluators", json={"name": name, "type": "code", "code_evaluator": body})["evaluator"]
            print(f"created  {name}")
        api.wait_built(e["id"])
        rules = [x for x in api("GET", "/runs/rules", params={"session_id": sid}) or []  # the API ignores evaluator_id
                 if x.get("evaluator_id") == e["id"] and x.get("session_id") == sid]
        rule = {"display_name": name, "session_id": sid, "sampling_rate": 1.0, "filter": s["filter"], "evaluator_id": e["id"],
                "is_enabled": True}
        if backfill:
            rule["backfill_from"] = backfill
        if rules:
            api("PATCH", f"/runs/rules/{rules[0]['id']}", json=rule)
            print(f"         rule on {project!r} updated: {s['filter']}")
        else:
            api("POST", "/runs/rules", json=rule)
            print(f"         rule on {project!r} created: {s['filter']}")
        keys = [f.__name__ for f in s["checks"]] + [n.replace("critic_", "") for n in s.get("extra", ("", [], []))[2]]
        print(f"         feedback keys: {', '.join(keys)}")


def main(argv: list[str]) -> None:
    from dotenv import load_dotenv
    load_dotenv()
    ap = argparse.ArgumentParser(prog="python -m evals.langsmith_online")
    ap.add_argument("--project", default=os.getenv("LANGSMITH_PROJECT") or "default")
    ap.add_argument("--backfill", metavar="YYYY-MM-DD", help="also score the project's traces since this day")
    ap.add_argument("--only", nargs="*", choices=list(SPECS))
    ap.add_argument("--print", dest="show", choices=list(SPECS), help="print one evaluator's code and exit")
    a = ap.parse_args(argv)
    if a.show:
        print(build_code(a.show))
        return
    sync(a.project, a.backfill, a.only)


if __name__ == "__main__":
    main(sys.argv[1:])
