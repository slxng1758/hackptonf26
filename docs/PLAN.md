# Two layers of AI customers + 2-person split (backend only, UI excluded)

## Context
The customers are AI agents, so they should vary by **model family** (OpenAI, Claude, Gemini, Grok, Meta/Llama), not only by persona. The product runs in two layers:

- **Layer 1 (base models):** each model family reacts to the product with no persona and no memory: "you're an AI shopping assistant / a typical customer." This shows how each lab's model sees the product by default.
- **Layer 2 (models + injected memory):** the same models, now given a customer's preferences through the LangChain deepagents harness (persona profile + long-term memory). The memory evolves from each run's feedback and from real outcomes. **This is where the agents evolve.**

Result: an overview, plus a click-through per agent (model × persona) showing its thought process, reactions, a written review and **suggestions**, not just buy / not buy. Comparing Layer 1 and Layer 2 shows how much memory changes behavior, and whether it moves predictions closer to real outcomes.

## What exists on `origin/main` (Candy's commits; `git pull` first)
- `b2a/models.py`: `persona_models()` builds Gemini, Claude, GPT, Grok and Llama (when keyed); `persona(name)` returns one.
- `b2a/session.py`: `cast()` assigns `persona["model"]` round-robin; `browse()` makes each persona browse the real site with its model; `Decision` = decision, rating, feeling, quote, reasons, missing.
- `b2a/sim.py`: cast → owner approves → browse → analyst + evolver subagents → `## Memory` per persona file, persona library, run-again loop, `persona_changes`, buy rate by model.
- `b2a/contract.py`: `EvalScore`, `PersonaChange`, `Social`. `docs/CONTRACT.md`.

---

## Shared changes (agree in the first 30 min, then split)
**Agent = (model family, persona or none, memory version).** Add to each session result: `layer: 1|2`, `model`, `persona_id | null`, `memory_version`.

**Richer `Decision`** (`b2a/session.py`, keep the old fields):
`first_impression`, `review` (3–5 sentences, in their voice), `liked[]`, `disliked[]`, `would_pay`, `suggestions[]` where `Suggestion = {change, why, where, impact: "would make me buy" | "nice to have"}`.

---

## Person A: the agents (layers, models, memory harness)
Owns `b2a/session.py`, `b2a/models.py`, `b2a/sim.py`.
1. **Model choice:** `GET /api/models` (keyed families); `SimIn.models: list[str]`; `cast()` uses only the chosen ones; per-persona model override on approval (already honored by `browse()`).
2. **Layer 1 run:** for each chosen model, one browse session with a neutral "base customer" prompt (no persona, no memory). Results are tagged `layer: 1`.
3. **Layer 2 run:** every persona × chosen model (or round-robin, if cost matters), with its memory injected.
4. **Memory through the deepagents harness:** move persona memory from appended `## Memory` text to deepagents long-term memory. Use `CompositeBackend` with a `StoreBackend` routed at `/memories/` (a LangGraph store, persisted across runs), one file per persona: `/memories/<persona_id>.md` (preferences, past experiences, lessons). The evolver subagent edits these files, and `browse()` loads the persona's memory file into the prompt. Track `memory_version` and write a `PersonaChange` on every edit.
5. **Evolution inputs:** the evolver updates memory from (a) this run's sessions, (b) owner corrections on the approval screen, (c) B's eval errors (missed real themes, rating error).
6. **Richer `Decision` + `DECIDE` prompt** (review + suggestions tied to pages they saw).

## Person B: measurement, comparison, data, sponsors
Owns new files: `b2a/evals.py`, `b2a/compare.py`, `b2a/network.py`, `data/`.
1. **Backtest dataset:** 1–2 products with real reviews (archived Wayback Machine page + reviews split into train/holdout).
2. **`evals.py`:** `score(sim, case) -> EvalScore` per layer and per memory version: rating error, theme recall/precision (LLM judge), distribution distance. LangSmith tracing + evals.
3. **`compare.py`: layer and model comparison.** `summary.by_model` (buy rate, rating, top complaint per family), `summary.layer_delta` (how decisions shift from Layer 1 to Layer 2 per model), **model disagreement** (where families split on the same persona), and accuracy of Layer 1 vs Layer 2 vs evolved Layer 2. Headline chart: *base models → + memory → + evolved memory*, error falling.
4. **`summary.top_suggestions`:** groups similar suggestions across all agents, with who asked (models + personas) and how many non-buyers said it would make them buy.
5. **Social layer** (`network.py`, Arlequin): agents post, reply and repost; graph + influencers. Cut first if behind.
6. **Peri visit** (real local business + evidence), MongoDB storage, Vultr deploy, domain, README, pitch.

**Workload:** about even. A has the trickier harness work; B has more breadth (data, scoring, Peri visit, shipping).

---

## Timeline (~36h from now)
| When | Person A | Person B |
|---|---|---|
| H0–1 | shared changes (together) | shared changes (together) |
| H1–8 | model picker, Layer 1 run, richer Decision | backtest dataset, `evals.py` v1, Peri visit |
| **H8 sync** | Layer 1 + Layer 2 run on backtest | first scores per layer and per model |
| H8–18 | StoreBackend `/memories/`, evolver from eval errors | `compare.py`, `top_suggestions`, LangSmith |
| **H18 sync** | 3 evolution rounds | chart: base → memory → evolved; is error falling? |
| H18–28 | Peri case end to end, prompt tuning | social layer, MongoDB |
| H28–36 | bug fixes, rehearse | deploy, domain, docs, deck, rehearse |

**Cut order:** Solana → social layer → Grok/Llama (keep 3 families) → per-persona × every-model (fall back to round-robin). **Don't cut:** Layer 1 vs Layer 2 comparison, the evolving memory, the accuracy chart, the Peri case.

## Verification
- `GET /api/models` lists keyed families; a sim with `models: ["Gemini","GPT","Claude"]` produces 3 Layer-1 sessions and Layer-2 sessions using only those.
- Every decision has `review` + `suggestions` that name pages the agent actually visited.
- `/memories/<persona_id>.md` persists across two separate sims, and the second run's prompt includes it.
- `compare.py` prints by-model results, the Layer 1 → 2 delta, and accuracy per layer on the backtest holdout.
