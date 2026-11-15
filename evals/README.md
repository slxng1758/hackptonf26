# Agent evals

Evals for the director deep agent, its subagents and the customer subagents. They use real models, so they cost money
and are kept out of the default `pytest` run (which only covers `tests/`).

```bash
uv pip install --python .venv/bin/python -r requirements-dev.txt     # agentevals + openevals, once
.venv/bin/python -m pytest evals -v                                    # everything (~10-15 min)
.venv/bin/python -m pytest evals/test_subagents.py -v -k critic        # one subagent (~30 s)
.venv/bin/python -m pytest evals/test_director.py -v -k happy          # one director scenario
.venv/bin/python -m pytest tests/test_eval_checks.py                   # the checks themselves, offline, free
```

Scores print as a table at the end and are saved to `runs/evals/<time>.json`. With `LANGSMITH_API_KEY` set, each run
is also an experiment in LangSmith (Datasets & Experiments → `hackpton-agent-evals`): one column per metric, the
judge's reasoning as a comment, and full traces of every agent, subagent and tool call.

## What runs

| file | agent under test | how |
|---|---|---|
| `test_director.py` | director deep agent, end to end | `DIRECTOR_STUB` mode: the director, briefer, segmenter and critic are real models making real decisions; browsing, scoring, social and evolving return fixtures. Scenarios: `happy`, `owner_corrects` (human-in-the-loop correction). |
| `test_subagents.py` | briefer, segmenter, critic, analyst, evolver | each one's **real compiled subagent graph**, taken out of the director's `task` tool (same prompt, inherited tools, middleware), on a fixture sim folder with known answers. The critic gets data with planted problems. |
| `test_customer.py` | customer subagent (p\*/a\*) | its real deepagents spec shopping a fake store (`FakeBrowser`, no Playwright). Scenarios: `fits` (should buy), `over_budget` (must not). |

## Two kinds of eval

**Tool calling** (`checks.py`, deterministic): each rule in the prompts is a check on the trajectory. Examples: brief,
then briefer, then segmenter, then cast, then approval (`setup_order`); one director tool per turn (`own_tools_serial`);
every customer of a round sent in ONE turn and the round closed (`round_protocol`); a skeptic in the cast, and
spawns of 1-2 (`cast_rules`); score → evolve → new round (`learning_loop`); stop after 2 flat loops (`loop_stop_rule`);
helper subagents never call director tools (`subagent_tool_scope`, `only_file_tools`); customers click only buttons that
were on the page (`clicks_visible_targets`). `reference_superset` is the agentevals trajectory match against a
reference run.

**LLM as judge** (`judges.py`, openevals / agentevals, judge = `EVAL_JUDGE_MODEL`): director judgment against its
decision rules (trajectory judge), the owner-facing `reason` sentences, the final reply against the summary numbers,
brief faithfulness to the site, segment plausibility, the critic catching planted problems, the analyst against known
facts, evolver memory grounded in sessions and feedback, customers staying in character.

Each eval has a minimum score (`DIRECTOR_MIN`, `CUSTOMER_MIN`, or in the test). Soft rules have low minimums and are
tracked rather than enforced.

## On LangSmith's Evaluators page (live traces)

The tool-calling checks that need only the agent's own messages also run as LangSmith **online code evaluators** on
every trace in `$LANGSMITH_PROJECT`, so real sims are scored too, not just the eval scenarios:

| evaluator | runs on | feedback keys |
|---|---|---|
| `hackpton: customer tool use` | `customer:*` runs and director customer subagents (`p3-maya`, `a1-claude-agent`) | `opens_site_first`, `decided_with_tool`, `clicks_visible_targets`, `moves_well_formed`, `no_corrective_results` |
| `hackpton: director tool use` | the `director` run that called `finish` (paused runs are skipped) | the director checks above, minus the ones that need the job view or files |
| `hackpton: helper subagent tool use` | `briefer`, `segmenter`, `critic`, `analyst`, `evolver` subagents | `only_file_tools`, `spawn_line` (critic) |

```bash
.venv/bin/python -m evals.langsmith_online                        # create or update them (run again after changing a check)
.venv/bin/python -m evals.langsmith_online --backfill 2026-11-15  # also score older traces
.venv/bin/python -m evals.langsmith_online --print director       # the code LangSmith runs
```

The evaluator code is generated from `checks.py` (the function source is copied in, with a parser for the message dicts
LangSmith stores), so each check exists once. `tests/test_langsmith_online.py` runs that code offline and checks it
scores the same as `checks.py`. The LLM judges stay in `pytest evals`: running them on LangSmith needs a model key stored
in the workspace.

## Adding one

A check is `def my_check(r: RunRecord) -> dict | None` returning `checks.res(key, score, comment)` (None = doesn't
apply). Add it to `DIRECTOR_CHECKS` / `CUSTOMER_CHECKS` and give it a planted-mistake test in `tests/test_eval_checks.py`.
A new scenario is one entry in `fixtures.py` (`DIRECTOR_SCENARIOS`, `CUSTOMER_SCENARIOS`).
