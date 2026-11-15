"""Deterministic tool-calling evals: every rule the prompts give the agents, checked against what they actually called.

Each check takes a RunRecord and returns {"key", "score" (0..1), "comment"}, or None when it doesn't apply to this run.
They need no model, so they are unit-tested offline in tests/test_eval_checks.py.
"""
from __future__ import annotations

import re
from collections import Counter

from b2a.session import ARCHETYPES

from .trajectory import Call, RunRecord

OWN = ("brief_product", "cast_personas", "request_approval", "start_round", "end_round", "score", "evolve",
       "run_social", "summarize", "finish")
FILE_TOOLS = {"ls", "read_file", "write_file", "edit_file", "glob", "grep", "delete", "execute", "write_todos"}
INF = 10 ** 9

# tool results that mean the agent used a tool wrongly (budget messages are not errors: they're the budget working)
CORRECTIVE = re.compile(
    r"is still open: call end_round first|Nothing to approve yet|No round is open|No such customers|Didn't shop \(|"
    r"not part of the open round|wasn't part of the open round|only allowed types|validation error|"
    r"Error invoking tool|is not a valid tool|Call open_site first|You already decided|You have no moves left", re.I)


def res(key: str, score: float, comment: str = "") -> dict:
    return {"key": key, "score": round(float(score), 3), "comment": comment}


def _frac(key: str, ok: int, total: int, problems: list[str], empty: str = "nothing to check") -> dict:
    if not total:
        return res(key, 1.0, empty)
    return res(key, ok / total, "; ".join(problems[:6]) or f"all {total} ok")


# ---------------------------------------------------------------- director: helpers

def own_calls(r: RunRecord) -> list[Call]:
    return [c for c in r.traj.calls if c.name in OWN]


def opened_rounds(r: RunRecord) -> list[Call]:
    return [c for c in r.traj.of("start_round") if "is open for:" in c.result]


def round_names(c: Call) -> list[str]:
    m = re.search(r"is open for: (.*?)\. Now call", c.result, re.S)
    return [n.strip() for n in m.group(1).split(",")] if m else []


def approved_at(r: RunRecord) -> int:
    a = next((c for c in r.traj.of("request_approval") if c.result.startswith("Approved")), None)
    return a.i if a else -1


def keep_going(c: Call) -> bool | None:
    m = re.search(r"keep_going=(True|False)", c.result)
    return None if not m else m.group(1) == "True"


def budget_hit(r: RunRecord, kind: str = "") -> bool:
    return any("budget used" in c.result and kind in c.result for c in r.traj.calls)


# ---------------------------------------------------------------- director: checks

def starts_with_brief(r: RunRecord) -> dict:
    own = own_calls(r)
    first = own[0].name if own else "(none)"
    return res("starts_with_brief", first == "brief_product", f"first own tool: {first}")


def setup_order(r: RunRecord) -> dict | None:
    """brief_product -> briefer -> segmenter -> cast_personas -> request_approval, each first call in that order."""
    if r.meta.get("rerun"):
        return None
    want = ["brief_product", "task:briefer", "task:segmenter", "cast_personas", "request_approval"]
    idx = {w: next((c.i for c in r.traj.calls if c.label == w), -1) for w in want}
    missing = [w for w, i in idx.items() if i < 0]
    if missing:
        return res("setup_order", 0, f"never called: {', '.join(missing)}")
    order = sorted(want, key=idx.get)
    return res("setup_order", order == want, "in order" if order == want else f"actual order: {' -> '.join(order)}")


def own_tools_serial(r: RunRecord) -> dict:
    """The prompt: call your own tools one at a time (they change shared state); only `task` calls go together."""
    turns = [t for t in r.traj.turns if t]
    bad = [f"turn {t[0].turn}: {', '.join(c.name for c in t if c.name in OWN)}" for t in turns if sum(c.name in OWN for c in t) > 1]
    return _frac("own_tools_serial", len(turns) - len(bad), len(turns), bad)


def reasons_given(r: RunRecord) -> dict:
    """Every director tool needs a `reason`: one plain sentence for the owner."""
    own = own_calls(r)
    bad = [f"{c.name}#{c.i}: {str(c.args.get('reason', ''))[:40]!r}" for c in own if len(str(c.args.get("reason", "")).split()) < 4]
    return _frac("reasons_given", len(own) - len(bad), len(own), bad)


def cast_rules(r: RunRecord) -> dict | None:
    """First cast: 3-8 personas, a skeptic among them, archetypes from the list. Spawns after approval: 1-2."""
    casts = r.traj.of("cast_personas")
    if not casts:
        return None if r.meta.get("rerun") else res("cast_rules", 0, "never cast")
    appr, problems = approved_at(r), []
    for c in casts:
        n, arch = int(c.args.get("n") or 0), list(c.args.get("archetypes") or [])
        spawn = 0 <= appr < c.i
        lo, hi = (1, 2) if spawn else (3, 8)
        if not lo <= n <= hi:
            problems.append(f"cast#{c.i} ({'spawn' if spawn else 'initial'}) n={n}, rule {lo}-{hi}")
        if bad := [a for a in arch if a not in ARCHETYPES]:
            problems.append(f"cast#{c.i} unknown archetypes {bad}")
        if not spawn and "skeptic" not in arch[:n]:
            problems.append(f"cast#{c.i} has no skeptic among the first {n}: {arch[:n]}")
    return res("cast_rules", 0 if problems else 1, "; ".join(problems) or f"{len(casts)} cast(s) ok")


def approval_before_rounds(r: RunRecord) -> dict | None:
    rounds = opened_rounds(r)
    if not rounds:
        return res("approval_before_rounds", 0, "no round was ever opened")
    if r.meta.get("rerun"):
        return None
    a = approved_at(r)
    ok = 0 <= a < rounds[0].i
    return res("approval_before_rounds", ok, "approved before the first round" if ok else "a round opened before the owner approved")


def layer1_first(r: RunRecord) -> dict:
    rounds = opened_rounds(r)
    layers = [c.args.get("layer") for c in rounds]
    ok = bool(layers) and layers[0] == 1 and 2 in layers[1:]
    return res("layer1_first", ok, f"round layers in order: {layers}")


def round_protocol(r: RunRecord) -> dict:
    """start_round -> one `task` per opened customer, all in ONE turn -> end_round, before the next round."""
    rounds, problems = opened_rounds(r), []
    ends = r.traj.of("end_round")
    for sr in rounds:
        er = next((e for e in ends if e.i > sr.i), None)
        stop = er.i if er else INF
        tasks = [c for c in r.traj.calls if c.to_customer and sr.i < c.i < stop]
        want, sent = set(round_names(sr)), {c.args.get("subagent_type") for c in tasks}
        if want - sent:
            problems.append(f"round@{sr.i}: never sent {sorted(want - sent)}")
        if sent - want:
            problems.append(f"round@{sr.i}: sent customers not in the round {sorted(sent - want)}")
        if len({c.turn for c in tasks}) > 1:
            problems.append(f"round@{sr.i}: customers sent over {len({c.turn for c in tasks})} turns, not all at once")
        if er is None:
            problems.append(f"round@{sr.i}: never closed with end_round")
        nxt = next((x for x in rounds if x.i > sr.i), None)
        if nxt and er and er.i > nxt.i:
            problems.append(f"round@{sr.i}: next round opened before end_round")
    bad = len({p.split(":")[0] for p in problems})
    return _frac("round_protocol", len(rounds) - bad, len(rounds), problems, "no rounds")


def no_corrective_results(r: RunRecord) -> dict:
    """Tool results that tell the agent it misused a tool (wrong order, unknown subagent, bad args)."""
    hits = [f"{c.label}#{c.i}: {CORRECTIVE.search(c.result).group(0) if CORRECTIVE.search(c.result) else 'error'}"
            for c in r.traj.calls if c.error or CORRECTIVE.search(c.result)]
    total = len(r.traj.calls)
    return res("no_corrective_results", 1 - len(hits) / total if total else 1, "; ".join(hits[:6]) or "none")


def critic_after_layer2(r: RunRecord) -> dict:
    first_l2 = next((c for c in r.traj.of("end_round") if "(layer 2)" in c.result), None)
    if not first_l2:
        return res("critic_after_layer2", 0, "no layer-2 round finished")
    crit = [c for c in r.traj.of("task:critic") if c.i > first_l2.i]
    return res("critic_after_layer2", bool(crit), f"critic consulted {len(crit)}x after the first layer-2 round")


def learning_loop(r: RunRecord) -> dict | None:
    """With real outcomes: score -> evolve(the wrong/uncertain personas, score's feedback as focus) -> new layer-2 round."""
    if not r.meta.get("has_truth", True):
        return None
    scores, evolves = r.traj.of("score"), [e for e in r.traj.of("evolve") if e.result.startswith("Loop")]
    if not scores:
        return res("learning_loop", 0, "never scored, though real outcomes exist")
    if not evolves:
        return res("learning_loop", 0, "scored but never evolved")
    problems, prev = [], -1
    l2 = [c for c in opened_rounds(r) if c.args.get("layer") == 2]
    for e in evolves:
        if not any(prev < s.i < e.i for s in scores):
            problems.append(f"evolve#{e.i} without a score since the last loop")
        if not e.args.get("persona_ids"):
            problems.append(f"evolve#{e.i} has no persona_ids")
        if len(str(e.args.get("focus", "")).split()) < 3:
            problems.append(f"evolve#{e.i} focus is empty/vague")
        nxt = next((s.i for s in scores if s.i > e.i), INF)
        if not any(e.i < sr.i < nxt for sr in l2) and nxt != INF:
            problems.append(f"evolve#{e.i} not followed by a new layer-2 round before the next score")
        prev = e.i
    return res("learning_loop", 1 - min(1, len(problems) / len(evolves)), "; ".join(problems) or f"{len(evolves)} loop(s) ok")


def loop_stop_rule(r: RunRecord) -> dict | None:
    """Keep looping while score says keep_going; stop after 2 non-improving loops in a row or when the budget is used."""
    scores = [s for s in r.traj.of("score") if keep_going(s) is not None]
    if not scores:
        return None
    evolves = [e for e in r.traj.of("evolve") if e.result.startswith("Loop")]
    max_loops = int((r.view.get("budget") or {}).get("max_evolve_loops") or 4)
    out_of_budget = len(evolves) >= max_loops or budget_hit(r, "evolve") or budget_hit(r, "time")
    flat = 0
    for s in scores:
        flat = 0 if keep_going(s) else flat + 1
        if flat >= 2 and any(e.i > s.i for e in evolves):
            return res("loop_stop_rule", 0, f"kept evolving after 2 non-improving loops (score#{s.i})")
    last = scores[-1]
    if any(e.i > last.i for e in evolves) or out_of_budget:
        return res("loop_stop_rule", 1, f"{len(evolves)} loop(s); stopped on {'budget' if out_of_budget else 'rule'}")
    if keep_going(last):
        return res("loop_stop_rule", 0, "stopped while score still said keep_going=True, with budget left")
    if flat == 1:
        return res("loop_stop_rule", 0.5, "stopped after ONE non-improving loop; the rule says two in a row")
    return res("loop_stop_rule", 1, f"{len(evolves)} loop(s), stopped after 2 flat loops")


def spawn_rule(r: RunRecord) -> dict | None:
    """After a layer-2 run: a segment split, avg confidence < 0.5 or a critic SPAWN line -> cast 1-2 more and send only them."""
    social = r.traj.first("run_social")
    stop = social.i if social else INF
    triggers = []
    for c in r.traj.of("end_round"):
        if "(layer 2)" in c.result and c.i < stop:
            m = re.search(r"Segments that split: (.*?)\.\n", c.result)
            if m and m.group(1).strip().lower() != "none":
                triggers.append(f"split: {m.group(1)}")
            m = re.search(r"avg confidence (\d+(?:\.\d+)?)", c.result)
            if m and float(m.group(1)) < 0.5:
                triggers.append(f"confidence {m.group(1)}")
    for c in r.traj.of("task:critic"):
        if c.i < stop and (m := re.search(r"SPAWN:\s*(.+)", c.result)) and m.group(1).strip().lower().strip(".") != "none":
            triggers.append(f"critic: {m.group(1).strip()[:40]}")
    appr = approved_at(r)
    spawns = [c for c in r.traj.of("cast_personas") if 0 <= appr < c.i < stop and c.result.startswith("Cast")]
    if not triggers:
        return res("spawn_rule", 0.5 if spawns else 1, "spawned without a trigger" if spawns else "no trigger, no spawn")
    if not spawns:
        full = budget_hit(r, "persona") or len([p for p in r.view.get("personas", []) if p.get("kind") != "agent"]) >= 8
        return res("spawn_rule", 1 if full else 0, f"triggers {triggers[:3]}; " + ("persona budget full" if full else "never spawned"))
    problems = []
    evolves = [e.i for e in r.traj.of("evolve") if e.result.startswith("Loop")]
    for sp in spawns:  # the next round sends the new personas: only them, unless it is also the learning-loop round
        new = set(re.findall(r"\b(p\d+) ", sp.result))
        nxt = next((c for c in opened_rounds(r) if c.i > sp.i), None)
        sent = {n.split("-")[0] for n in round_names(nxt)} if nxt else set()
        loop_round = nxt is not None and any(sp.i < e < nxt.i for e in evolves)  # evolve -> everyone shops again anyway
        if not nxt:
            problems.append(f"spawn#{sp.i}: new personas never sent")
        elif new - sent:
            problems.append(f"spawn#{sp.i}: new personas {sorted(new - sent)} not in the next round")
        elif sent - new and not loop_round:
            problems.append(f"spawn#{sp.i}: next round resent old personas {sorted(sent - new)}")
    return res("spawn_rule", 0 if problems else 1, "; ".join(problems) or f"triggers {triggers[:3]}; spawned and sent only the new ones")


def social_rule(r: RunRecord) -> dict:
    soc = r.traj.of("run_social")
    if len(soc) != 1:
        return res("social_rule", 0, f"run_social called {len(soc)}x, rule is once")
    people = len([p for p in r.view.get("personas", []) if p.get("kind") != "agent"])
    want = 3 if people >= 6 else 2
    got = int(soc[0].args.get("rounds", 2))
    last_end = max((c.i for c in r.traj.of("end_round")), default=-1)
    problems = ([f"rounds={got}, rule says {want} for {people} personas"] if got != want else []) + \
               (["ran before the last browsing round"] if soc[0].i < last_end else [])
    return res("social_rule", 0 if problems else 1, "; ".join(problems) or f"once, {got} rounds, after the last run")


def finish_last(r: RunRecord) -> dict:
    own = [c.name for c in own_calls(r)]
    problems = []
    if own[-2:] != ["summarize", "finish"]:
        problems.append(f"last own tools: {own[-2:]}")
    if own.count("finish") != 1:
        problems.append(f"finish called {own.count('finish')}x")
    if r.view and r.view.get("status") != "done":
        problems.append(f"status {r.view.get('status')}")
    return res("finish_last", 0 if problems else 1, "; ".join(problems) or "summarize -> finish, once")


def all_customers_shopped(r: RunRecord) -> dict:
    runs = r.view.get("runs") or []
    bad = [f"run {x['n']}: {len(x['decisions'])}/{len(x['agents'])}" for x in runs if len(x.get("decisions") or {}) < len(x.get("agents") or [])]
    return _frac("all_customers_shopped", len(runs) - len(bad), len(runs), bad, "no runs")


def _brief_problems(f: dict[str, str]) -> list[str]:
    problems = []
    if not f.get("product.md", "").strip():
        problems.append("no /product.md")
    elif "## Unclear" not in f["product.md"]:
        problems.append("/product.md has no '## Unclear' section")
    world = [l for l in f.get("world.md", "").splitlines() if l.strip() and not l.startswith("#")]
    if not world:
        problems.append("no /world.md")
    elif not 3 <= len(world) <= 6:
        problems.append(f"/world.md has {len(world)} lines (want 3-5)")
    return problems


def brief_files(r: RunRecord) -> dict:
    """briefer: /product.md with a '## Unclear' section, /world.md of 3-5 lines."""
    problems = _brief_problems(r.files)
    return res("brief_files", 1 - len(problems) / 2, "; ".join(problems) or "both written")


def subagent_files(r: RunRecord) -> dict | None:
    """In a director run: the briefer's two files and the segmenter's /segments.md."""
    if r.meta.get("rerun"):
        return None
    f, problems = r.files, _brief_problems(r.files)
    if not f.get("segments.md", "").strip():
        problems.append("no /segments.md")
    return res("subagent_files", 1 - len(problems) / 3, "; ".join(problems) or "all written")


def subagent_tool_scope(r: RunRecord) -> dict:
    """Director tools must only be called by the director. deepagents gives a subagent spec without `tools` ALL of the
    parent's tools, so briefer/segmenter/analyst/critic can call cast_personas, finish, ... Every director tool logs
    itself in view['director']; anything logged that isn't in the director's own trajectory came from somewhere else."""
    logged = Counter(d["tool"] for d in r.view.get("director") or [] if d.get("reason") != "closing the round before summarizing")
    called = Counter(c.name for c in own_calls(r))
    extra = {k: v - called.get(k, 0) for k, v in logged.items() if v > called.get(k, 0)}
    return res("subagent_tool_scope", not extra, f"director tools called outside the director: {extra}" if extra else "only the director used them")


def efficiency(r: RunRecord, max_turns: int = 70) -> dict:
    n = len(r.traj.turns)
    return res("efficiency", min(1.0, max_turns / n) if n else 0,
               f"{n} model turns, {len(r.traj.calls)} tool calls, {r.traj.tokens['input']:,} in / {r.traj.tokens['output']:,} out tokens")


def hitl_recast(r: RunRecord) -> dict | None:
    """Owner says the cast is off -> cast_personas(replace=true) next, then request_approval again before any round."""
    offs = [c for c in r.traj.of("request_approval") if "cast is off" in c.result]
    if not r.meta.get("owner_feedback"):
        return None
    if not offs:
        return res("hitl_recast", 0, "owner feedback was given but never reached the director")
    problems = []
    for o in offs:
        nxt = next((c for c in own_calls(r) if c.i > o.i), None)
        if not nxt or nxt.name != "cast_personas" or not nxt.args.get("replace"):
            problems.append(f"after the correction the next tool was {nxt.name if nxt else None} {nxt.args if nxt else ''}")
            continue
        again = next((c for c in r.traj.of("request_approval") if c.i > nxt.i), None)
        first_round = next((c.i for c in opened_rounds(r)), INF)
        if not again or again.i > first_round:
            problems.append("didn't ask for approval again before the first round")
    return res("hitl_recast", 0 if problems else 1, "; ".join(problems) or "recast with replace=true, then asked again")


DIRECTOR_CHECKS = [starts_with_brief, setup_order, own_tools_serial, reasons_given, cast_rules, approval_before_rounds,
                   layer1_first, round_protocol, no_corrective_results, critic_after_layer2, learning_loop, loop_stop_rule,
                   spawn_rule, social_rule, finish_last, all_customers_shopped, subagent_files, subagent_tool_scope,
                   efficiency, hitl_recast]
# the score each check must reach for the eval to pass (lower = a soft rule we only track)
DIRECTOR_MIN = {"efficiency": 0.0, "spawn_rule": 0.5, "loop_stop_rule": 0.5, "no_corrective_results": 0.9, "subagent_files": 0.66,
                "reasons_given": 0.95}


# ---------------------------------------------------------------- subagents (briefer, segmenter, critic, analyst, evolver)

def only_file_tools(r: RunRecord) -> dict:
    """A helper subagent should read and write files, never drive the simulation."""
    bad = [c.name for c in r.traj.calls if c.name not in FILE_TOOLS]
    return res("only_file_tools", not bad, f"called director tools: {sorted(set(bad))}" if bad else "file tools only")


def read_before_write(r: RunRecord, must_read: tuple[str, ...], must_write: tuple[str, ...]) -> dict:
    """It read its inputs before writing its outputs (any of must_read, all of must_write)."""
    def touched(c: Call) -> str:
        return str(c.args.get("file_path") or c.args.get("path") or c.args.get("pattern") or "")
    reads = [c for c in r.traj.calls if c.name in ("read_file", "ls", "glob", "grep") and any(p in touched(c) for p in must_read)]
    writes = {p: next((c for c in r.traj.calls if c.name in ("write_file", "edit_file") and touched(c).endswith(p)), None) for p in must_write}
    problems = [] if reads else [f"never read {must_read}"]
    problems += [f"never wrote {p}" for p, c in writes.items() if not c]
    if reads and any(c and c.i < reads[0].i for c in writes.values()):
        problems.append("wrote before reading its input")
    return res("read_before_write", 0 if problems else 1, "; ".join(problems) or "read, then wrote")


def reply_length(r: RunRecord, max_words: int) -> dict:
    n = len(r.traj.final_text.split())
    return res("reply_length", 1 if 0 < n <= max_words else (0 if n == 0 else max_words / n), f"{n} words (max {max_words})")


def spawn_line(r: RunRecord) -> dict:
    lines = [l.strip() for l in r.traj.final_text.strip().splitlines() if l.strip()]
    spawn = [l for l in lines if l.startswith("SPAWN:")]
    ok = bool(spawn) and lines[-1].startswith("SPAWN:")
    return res("spawn_line", ok, f"SPAWN lines: {spawn}" if spawn else "no 'SPAWN:' line")


def segments_valid(r: RunRecord) -> dict:
    seg = r.files.get("segments.md", "")
    found = [a for a in ARCHETYPES if a in seg.lower()]
    m = re.search(r"\b([1-9])\s*personas?\b|\bn\s*[=:]\s*([1-9])\b", seg + "\n" + r.traj.final_text, re.I)
    n = int(m.group(1) or m.group(2)) if m else None
    problems = ([] if found else ["no known archetype in /segments.md"]) + \
               ([f"proposed n={n}, rule 3-8"] if n is not None and not 3 <= n <= 8 else []) + \
               (["no persona count proposed"] if n is None else [])
    return res("segments_valid", 0 if problems else 1, "; ".join(problems) or f"n={n}, archetypes {found}")


def evolver_memory(r: RunRecord, ids: list[str], business_name: str, archetypes: list[str]) -> dict:
    """Per persona: /memories/business/<id>.md with 2-6 tagged bullets; archetype memory <= 6 bullets, never names the business."""
    problems = []
    tag = re.compile(r"^- \((session|eval|owner)\)")
    for pid in ids:
        text = r.files.get(f"memories/business/{pid}.md", "")
        bullets = [l for l in text.splitlines() if l.strip().startswith("- ")]
        if not 2 <= len(bullets) <= 6:
            problems.append(f"{pid}: {len(bullets)} bullets (want 2-6)")
        if untagged := [b for b in bullets if not tag.match(b.strip())]:
            problems.append(f"{pid}: {len(untagged)} bullet(s) without a (session)/(eval)/(owner) tag")
    for a in archetypes:
        text = r.files.get(f"memories/{a.replace(' ', '-')}.md", "")
        bullets = [l for l in text.splitlines() if l.strip().startswith(("- ", "* "))]
        if not bullets:
            problems.append(f"archetype memory {a} not written")
        elif len(bullets) > 6:
            problems.append(f"archetype memory {a}: {len(bullets)} bullets (max 6)")
        if business_name.lower() in text.lower():
            problems.append(f"archetype memory {a} names the business")
    total = 2 * len(ids) + 2 * len(archetypes)
    return res("evolver_memory", max(0.0, 1 - len(problems) / total), "; ".join(problems) or "all memory files well-formed")


# ---------------------------------------------------------------- customer subagent

def opens_site_first(r: RunRecord) -> dict:
    first = r.traj.calls[0].name if r.traj.calls else "(none)"
    return res("opens_site_first", first == "open_site", f"first tool: {first}")


def decided_with_tool(r: RunRecord) -> dict:
    """It ended its own visit with decide (not stopped and decided for afterwards)."""
    forced = r.meta.get("forced")
    accepted = [c for c in r.traj.of("decide") if c.result.startswith("Recorded")]
    return res("decided_with_tool", bool(accepted) and not forced,
               "forced decision afterwards" if forced else f"decide called {len(r.traj.of('decide'))}x, accepted {len(accepted)}x")


def _visible(text: str) -> list[str]:
    m = re.search(r"Visible links and buttons: (.*)", text)
    return [t.strip() for t in m.group(1).split(",")] if m else []


def clicks_visible_targets(r: RunRecord) -> dict:
    """Every click names something that was on the page it was looking at (no invented buttons)."""
    seen: list[str] = []
    clicks, bad = 0, []
    for c in r.traj.calls:
        if c.name == "click":
            clicks += 1
            t = str(c.args.get("target", "")).strip().lower()
            if not any(t == v.lower() or t in v.lower() or v.lower() in t for v in seen if v):
                bad.append(f"{c.args.get('target')!r} not in {seen[:6]}")
        if c.result and (v := _visible(c.result)):
            seen = v
    return _frac("clicks_visible_targets", clicks - len(bad), clicks, bad, "no clicks")


def moves_well_formed(r: RunRecord, max_steps: int = 10) -> dict:
    moves = [c for c in r.traj.calls if c.name in ("click", "click_at", "scroll", "back", "search")]
    problems = [f"{c.name}#{c.i}: thought {len(str(c.args.get('thought', '')).split())} words" for c in moves
                if not 1 <= len(str(c.args.get("thought", "")).split()) <= 35]
    if len(moves) > max_steps:
        problems.append(f"{len(moves)} moves, cap {max_steps}")
    decided = next((c.i for c in r.traj.of("decide") if c.result.startswith("Recorded")), INF)
    if after := [c.name for c in r.traj.calls if c.i > decided]:
        problems.append(f"kept calling tools after deciding: {after}")
    return _frac("moves_well_formed", len(moves) + 1 - len(problems), len(moves) + 1, problems)


def decision_follows_visit(r: RunRecord) -> dict:
    """The final decision doesn't contradict what it did (session.contradiction); a corrected one counts half."""
    from b2a import session
    d = r.meta.get("decision") or {}
    if not d:
        return res("decision_follows_visit", 0, "no decision")
    fields = {k: v for k, v in d.items() if k in session.Decision.model_fields}
    why = session.contradiction(session.Decision(**fields), r.meta.get("steps") or [], r.meta.get("can_order", False))
    if why:
        return res("decision_follows_visit", 0, why)
    if d.get("reconsidered"):
        return res("decision_follows_visit", 0.5, f"first decision contradicted the visit ({d['reconsidered'][:80]}), then fixed")
    return res("decision_follows_visit", 1, "consistent")


def expected_outcome(r: RunRecord) -> dict | None:
    want = r.meta.get("expect_outcomes")
    if not want:
        return None
    got = (r.meta.get("decision") or {}).get("outcome")
    return res("expected_outcome", got in want, f"outcome {got}, expected one of {sorted(want)}")


CUSTOMER_CHECKS = [opens_site_first, decided_with_tool, clicks_visible_targets, moves_well_formed, decision_follows_visit,
                   no_corrective_results, expected_outcome]
CUSTOMER_MIN = {"clicks_visible_targets": 0.8, "moves_well_formed": 0.8, "decision_follows_visit": 0.5, "no_corrective_results": 0.8}
