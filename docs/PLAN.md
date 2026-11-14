# Plan: an agent-directed customer simulation + 2-person split (backend only, UI excluded)

## Context
AI customer agents try a small business's product, react (thoughts, feelings, buy / not buy / complain), review it, suggest changes, talk about it on a simulated social feed, are scored against real outcomes, and evolve.

Three ideas shape the system:
- **A director agent runs everything.** One deepagents orchestrator decides which subagents to call, which personas to create, which models play them, how many evolve loops and social rounds to run, and when to stop. It gives a reason for every decision.
- **Agents vary by model family** (OpenAI, Claude, Gemini, Grok, Meta/Llama, Bedrock Nova), not only by persona.
- **Two layers:**
  - **Layer 1 (base models):** each model family reacts with no persona and no memory.
  - **Layer 2 (models + injected memory):** the same models, given a customer's preferences and memories through the deepagents harness. The memory evolves from feedback and real outcomes. **This is where the agents evolve.**

**Result:** an overview, plus a click-through per agent (model × persona) showing its thought process, reactions, review and suggestions. Comparing Layer 1, Layer 2 and evolved Layer 2 shows whether memory moves predictions closer to reality.

Related docs: [overall.md](overall.md) (idea + prizes), [varyagent.md](varyagent.md) (model picking + per-persona review and suggestions), [CONTRACT.md](CONTRACT.md) (API + data shapes).

## What exists on `main` (mostly Candy's work; `git pull` first)
- `b2a/models.py`: `persona_models()` (Gemini, Claude, GPT, Grok, Llama, Bedrock Nova/Llama when keyed); `persona(name)`; `brain()`, `fast()`.
- `b2a/session.py`: `read_site()`, `cast()` (assigns `persona["model"]` round-robin), `browse()` (one persona browses the real site in Playwright with its model; screenshot → thought, feeling, action), `run_all()`, `Decision`.
- `b2a/sim.py` `SimJob`: `cast()` → `awaiting_approval` → `approve()` → `_run()` (browse all) → `_summarize()` (buy rate, rating, by model) → `_analyze()` (deep agent with `analyst` + `evolver` subagents on `FilesystemBackend`) → `_record_changes()` (`persona_changes`). Also `teach()` (owner says what real customers did → memory), `recast()`, `rerun()` (same customers, changed product), and the persona library in `runs/persona_library/`.
- `server.py`: `/api/sims` (create, list, get), `/approve`, `/recast`, `/teach`, `/rerun`, `/api/fixtures/extras`.
- `b2a/contract.py` + `fixtures/sim_extras_example.json`: `EvalScore`, `PersonaChange`, `Social`.

**Gap:** the steps run in a fixed order in plain Python. `create_deep_agent` is only used at the end, for analysis. The director below makes the deep agent the thing that runs the whole simulation.

---

# The director agent (Person A's main task)

## What it is
A single `create_deep_agent` in a new file `b2a/director.py`. It receives the owner's input (product URL or description, what changed, world context, chosen models, optional backtest case or real outcome) and runs the simulation by calling **tools** and **subagents**. It plans with `write_todos`, and the plan is shown live.

Heavy, repeatable work (browsing, scoring) is done in **tools**: plain Python, reliable and capped. Judgment calls (who to cast, whether to continue, what the results mean) are made by the **director and its subagents**.

## Setup
```python
agent = create_deep_agent(
    model=brain(),                         # Claude Sonnet; strongest model plans
    system_prompt=DIRECTOR.format(...),    # goals, decision rules (below), budget, director memory
    tools=[brief_product, cast_personas, request_approval, run_base_models, run_personas,
           run_social_round, score, evolve, summarize, finish],
    subagents=[BRIEFER, SEGMENTER, ANALYST, EVOLVER, CRITIC],
    backend=CompositeBackend(
        default=FilesystemBackend(root_dir=job_dir, virtual_mode=True),   # this run: /product.md, /personas, /sessions, /report.md
        routes={"/memories/": StoreBackend(...)},                          # across runs: persona memories + director lessons
    ),
    interrupt_on={"request_approval": True},   # deepagents human-in-the-loop: pauses for the owner
    checkpointer=...,                          # needed for interrupt/resume (MemorySaver is fine for the hackathon)
)
```
Check the installed `deepagents` version for exact argument names (`interrupt_on`, backend classes). Owner approval resumes the paused graph: `POST /api/sims/{id}/approve` sends the approved/edited personas as the resume value.

## Tools (all in `b2a/director.py`, wrapping existing code)
Every tool takes a required **`reason: str`** argument. The tool logs it as a `decision` step `{t, tool, reason, args_summary}`, so the trace shows *why* the director did each thing. Every tool returns a **short summary plus the remaining budget**. Full data goes to files the subagents can read.

| Tool | Wraps | Does | Returns (short) |
|---|---|---|---|
| `brief_product(reason)` | `session.read_site()` + BRIEFER | Reads the URL or the uploaded description and writes `/product.md` + `/world.md`. If there is no URL, Person B's `product_page.py` renders a browsable page (see B4). | name, category, key features, what changed |
| `cast_personas(n, archetypes, models, reason)` | SEGMENTER + `session.cast()` | Creates `n` personas with the given archetype mix and model assignment; writes `/personas/<id>.md`; loads each one's memory from `/memories/personas/` if it exists. | ids, names, archetypes, shares, models |
| `request_approval(reason)` | old `awaiting_approval` state | **Interrupt.** The owner sees the cast, edits, adds or removes personas, changes models, adds notes ("my customers are older"). Resumes with the final cast. | final cast + owner notes |
| `run_base_models(models, reason)` | `session.browse()` with a neutral prompt | **Layer 1:** one session per model, no persona, no memory. | buy/not per model, ratings, top complaint |
| `run_personas(persona_ids, reason)` | `session.run_all()` | **Layer 2:** chosen personas browse with memory injected. Can run a subset, e.g. only new personas. | decisions, ratings, confidence, which segments disagree |
| `run_social_round(round, reason)` | `b2a/social.py` (A7) | Round 0: everyone posts. Later rounds: read the feed, then reply / repost / ignore. | posts this round, new replies + reposts count |
| `score(reason)` | Person B's `evals.score()` | Compares the latest results with real outcomes (backtest holdout, owner's `teach` input, or Peri poll). Appends an `EvalScore`. | rating error, theme recall, missed themes, change since last loop |
| `evolve(persona_ids, focus, reason)` | EVOLVER + `_record_changes()` | Updates those personas' memory files using sessions + eval errors + owner truths; bumps `memory_version`; records `PersonaChange`. | which personas changed, one-line lessons |
| `summarize(reason)` | `_summarize()` + B's `compare.py` + `network.py` | Buy rate, by model, by layer, top suggestions, social graph. | headline numbers |
| `finish(reason)` | `_analyze()` report part | ANALYST writes `/report.md`; director writes a lesson to `/memories/director.md`; status `done`. | — |

## Subagents (own context, read/write the job files)
- **BRIEFER (the "helper agent"):** turns a URL or description + "what changed" + world into a plain product brief customers would understand. Flags anything unclear.
- **SEGMENTER:** decides how many customer types exist and which archetypes fit this product: price-sensitive, quality-first, brand-loyal, function-first, first-time user, skeptic, enthusiast/"agreer", plus product-specific types like "gift buyer". Proposes `n` + shares + model spread. The director can accept or adjust.
- **ANALYST:** reads every session; finds where people got stuck, what convinced buyers, whether the claimed change was visible; writes the report.
- **EVOLVER:** edits `/memories/personas/<id>.md` with concrete lessons; never removes the persona's core identity.
- **CRITIC:** checks whether the simulation is trustworthy: personas too similar, too positive (sycophancy), a model family dominating, or a segment with too few agents. Its findings feed the director's next decision.

## Decision rules (in the director's system prompt)
**Casting**
- Default 5 personas; range 3–8. Fewer for simple products, more when the customer description lists many distinct groups.
- Always include at least one skeptic; include a first-time user only if the product needs learning or navigating.
- Spread the owner's chosen models evenly across personas; no family plays more than ~40% of personas.

**Layer 1**
- Always run base models once before personas: it's the baseline for the layer comparison.

**Spawning more personas**
- After a run, if a segment's agents split (e.g. 1 buy, 1 not) or average confidence < 0.5, or CRITIC flags a gap, cast 1–2 more personas in that segment and run only those.

**Evolve loops**
- With real outcomes (backtest or Peri): loop `score → evolve → run_personas` while rating error improves by ≥ 0.1 **or** theme recall improves by ≥ 0.1; stop after 2 loops with no improvement, or at the budget cap.
- Without real outcomes: evolve once from the sessions, rerun, and stop when the buy rate changes by < 5 points between runs.
- Only evolve personas that were wrong or uncertain (`evolve(persona_ids=…)`), not all of them.

**Social rounds**
- Round 0 always. Continue while the last round produced ≥ 2 new replies/reposts; max 3 rounds.

**Finishing**
- Write the report, then save one lesson to `/memories/director.md` (e.g. "for cafés, 5 personas were enough; price-sensitive segment needed 2 loops").

## Budget (enforced in tools, not just the prompt)
`Budget(max_personas=8, max_sessions=40, max_evolve_loops=4, max_social_rounds=3, max_minutes=20)`, like `MAX_TESTS` in `b2a/agent.py`. A tool past its cap does nothing and returns "budget used: here are the results so far; finish now." Every tool result includes the remaining budget so the director can plan with it.

## Memory (deepagents long-term memory)
- `/memories/personas/<persona_id>.md`: preferences, past experiences, lessons, tagged by source (session / eval / owner / real people). Loaded into the persona's prompt in `browse()` and social rounds. This replaces copying files into `runs/persona_library/`; keep the library as a fallback until the StoreBackend works.
- `/memories/director.md`: the director's own lessons about running simulations, loaded into its system prompt.
- `memory_version` per persona; every edit records a `PersonaChange` (before / after / lesson).

## What the owner and the UI see
- `status` comes from the tool currently running: `briefing`, `casting`, `awaiting_approval`, `base_models`, `browsing`, `scoring`, `evolving`, `social`, `analyzing`, `done`.
- `steps[]` keeps the existing trace; new `decisions[]` = `{t, tool, reason, args_summary, result_summary}`. A demo trace reads like:
  - "Casting 5: café customers split into students, remote workers, neighbors; adding a skeptic."
  - "Students split 1–1 on price: casting 1 more student."
  - "Loop 2: theme recall 0.5 → 0.7, running another loop."
  - "Loop 3: +0.02 only, stopping."
  - "Social round 2 had 0 new replies, stopping."
- `todos` (from `write_todos`) shown live.

## Migration (keep the app working the whole time)
1. Wrap the existing `SimJob` methods as tools **without changing their logic**. Start with `cast_personas`, `run_personas`, `evolve`, `finish`.
2. Add `b2a/director.py` and run it behind a flag (`DIRECTOR=1`); the old fixed `_run()` stays the default until the director is reliable.
3. **Stub mode for cheap testing:** `DIRECTOR_STUB=1` makes the browse/score tools return fixture data instantly, so the decision logic can be tested in seconds without browsers or API cost.
4. Add `request_approval` via `interrupt_on` + checkpointer; point `/approve` at the resume.
5. Add `run_base_models`, `run_social_round`, `score` as their pieces land.
6. Flip the default to the director once a backtest run completes end to end.

---

## Shared changes (agree in the first 30 min, then split)
- **Agent = (model family, persona or none, memory version).** Each session result gets `layer: 1|2`, `model`, `persona_id | null`, `memory_version`.
- **Richer `Decision`** (`b2a/session.py`, keep old fields): `first_impression`, `review` (3–5 sentences, in their voice), `liked[]`, `disliked[]`, `would_pay`, `suggestions[]` with `Suggestion = {change, why, where, impact: "would make me buy" | "nice to have"}`.
- **`decisions[]`** on the sim view (the director's reasons), plus `evals`, `persona_changes`, `social` from `b2a/contract.py`.
- **Input:** `SimIn` gets `description: str` (url becomes optional, but one is required), `models: list[str]`, `world_preset: str | None`, `case_id: str | None`.

---

## Person A: the agents (owns `b2a/director.py`, `b2a/session.py`, `b2a/models.py`, `b2a/sim.py`, `b2a/social.py`)
1. **Director agent** (everything in the section above). Top priority.
2. **Model choice:** `GET /api/models` (keyed families); `SimIn.models`; `cast()` uses only those; per-persona override on approval.
3. **Layer 1 run:** neutral "base customer" browse prompt; results tagged `layer: 1`.
4. **Layer 2 run with memory injection** from `/memories/personas/` (StoreBackend).
5. **Evolution inputs:** sessions, owner corrections (`teach`, approval notes), and B's eval errors (missed real themes, rating error).
6. **Richer `Decision` + `DECIDE` prompt:** review + suggestions tied to pages they saw.
7. **Social posts (Arlequin, half 1)**, `b2a/social.py`, called by the director's `run_social_round`:
   - Round 0: each agent posts about the product in its own voice, from its session and decision.
   - Rounds 1–2: each agent sees the feed and chooses reply / repost / ignore, with a one-line reason.
   - Output: `social.posts` (`SocialPost` in `b2a/contract.py`). Layer 1 agents post too, so the layers can be compared.
8. **World presets:** 2–3 one-click options (pre-COVID 2019 / COVID 2020; "previous version" / "new version") mapped to `world` text.

## Person B: truth, measurement, data, sponsors (owns new files: `b2a/evals.py`, `b2a/compare.py`, `b2a/network.py`, `b2a/product_page.py`, `data/`)
1. **Backtest dataset:** 1–2 products with real reviews. `data/<case>/{product.md, context.md, wayback_url.txt, reviews_train.json, reviews_holdout.json}` + real top themes + star distribution.
2. **`evals.py`:** `score(sim_view, truth) -> EvalScore` per layer and per memory version: rating error, buy-rate error if known, theme recall/precision (LLM judge), distribution distance. LangSmith tracing + evals. Must be fast (the director calls it every loop) and return the **missed themes** so the evolver knows what to fix.
3. **`compare.py`:**
   - `summary.by_model`, `summary.layer_delta` (Layer 1 → 2 per model), model disagreement.
   - Accuracy of base → + memory → + evolved memory (headline chart).
   - `summary.top_suggestions`: grouped suggestions, who asked, how many non-buyers said it would make them buy.
4. **Description mode (`product_page.py`):** turns the BRIEFER's brief into a simple, browsable HTML product page served at `/api/products/{id}/`, so `browse()` works unchanged for products with no website (and for old backtest products when the Wayback page is broken).
5. **Social network analysis (Arlequin, half 2)**, `b2a/network.py`. Reads `social.posts` only.
   - Graph (networkx) → nodes, edges; influencers (PageRank), communities, cascades, sentiment by community.
   - Content + connectivity: cluster posts by theme, show which themes travel across communities.
   - Compare model families and layers: who spreads what, does memory change the influencer.
   - Builds against `fixtures/sim_extras_example.json` until real posts exist.
6. **Real results for the Peri business**, so `score()` has a truth to compare with:
   - Before the visit, write 5–8 questions that match the simulation's outputs (would you buy at $X, what would stop you, what would you tell a friend, 1–5 rating).
   - At the business: get the owner's real decision + past records (sales, reviews), and poll 5–10 real customers with those questions (with permission). Record the business name, the person consulted + role, and a photo/quote (required for Peri).
   - Store as `data/peri_<business>/` in the same format as the backtest, so the director can `score` against it.
7. **Sponsors and shipping:**
   - **Gemini:** make it visible beyond being one persona model, e.g. the vision model that reads screenshots or the BRIEFER.
   - **MongoDB Atlas:** sims, sessions, posts, eval scores.
   - **Tiger Data (if time):** time series of `memory_version`, eval score per loop, sentiment per social round.
   - **Vultr** deploy, **GoDaddy** domain, README, pitch deck, **DEV** post after the event. **Solana** only if everything else is done.

**Workload:** A is now heavier (the director is the biggest single piece). B took description mode and the Peri truth plan to balance. **If A falls behind, B takes `social.py` (A7) back.**

---

## Timeline (~36h from now)
| When | Person A | Person B |
|---|---|---|
| H0–1 | shared changes (together) | shared changes (together) |
| H1–6 | director skeleton in **stub mode**: tools wrap existing code, `decisions[]` logged, casting + evolve rules | backtest dataset; `evals.py` v1 (works on fixture) |
| H6–10 | richer Decision; model picker; Layer 1 run; `interrupt_on` approval | Peri visit + real poll; `product_page.py` |
| **H10 sync** | director runs the backtest case end to end (real browse) | `score()` plugged into director; first accuracy number |
| H10–20 | StoreBackend `/memories/`; evolve loop rules tuned on backtest; CRITIC + spawn-more rule | `compare.py`, `top_suggestions`, LangSmith |
| **H20 sync** | director decides loops on its own: is error falling and does it stop sensibly? | headline chart: base → memory → evolved |
| H20–28 | `social.py` rounds; Peri case through the director; flip default to director | `network.py`, MongoDB |
| H28–36 | bug fixes, prompt tuning, rehearse | deploy, domain, docs, deck, rehearse |

**Cut order:** Solana → Tiger Data → Grok/Llama/Nova (keep 3 families) → CRITIC subagent → social rounds 1–2 (keep round 0 + graph) → StoreBackend (fall back to `runs/persona_library/`).
**Don't cut:** the director making the decisions (with reasons), Layer 1 vs Layer 2 comparison, evolving memory, the accuracy chart, the Peri case with real answers, a working social graph.

## Verification
- **Director (stub mode):** with fixture tools, a run produces todos, `decisions[]` with reasons, casts within 3–8, stops the evolve loop when improvement < 0.1, and never exceeds the budget.
- **Director (real):** on the backtest case, it pauses for approval (interrupt), resumes after `/approve`, runs Layer 1 then Layer 2, chooses its own loop count, and writes the report + a director lesson.
- **Spawn rule:** a forced 1–1 split in a segment makes it cast and run one extra persona in that segment only.
- `GET /api/models` lists keyed families; a sim with `models: ["Gemini","GPT","Claude"]` uses only those.
- Every decision has `review` + `suggestions` naming pages the agent visited.
- `/memories/personas/<id>.md` persists across two sims; the second run's prompts include it.
- Description mode: a sim with only `description` (no URL) browses the generated page.
- Social: `social.posts` from every agent; `network.py` returns nodes matching agent ids, a top influencer, and which complaint spread through whom.
- `compare.py` prints by-model, the Layer 1 → 2 delta, and accuracy per layer on the backtest holdout and the Peri poll.
