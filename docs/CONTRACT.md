# Customer simulation API

read from the 

Backend: `http://localhost:4620` (`server.py`, engine in `b2a/sim.py` + `b2a/session.py`).

## Routes (live now)

| Method | Route | Body | Returns |
|---|---|---|---|
| POST | `/api/sims` | `{ description, name?, price?, context?, world?, customers? }` (or `{ url, ... }` for a real website) | `{ id }`. A description of 10+ characters is turned into a product page (`/api/products/{id}/`) that the customers browse; `name` defaults to the description's first sentence. 422 if neither is given. |
| GET | `/api/sims` | | `[{ id, name, status, buy_rate }]` |
| GET | `/api/sims/{id}` | | the simulation (below). Poll while running |
| POST | `/api/sims/{id}/approve` | `{ personas?: Persona[] }` | `{ ok: true }`, or 409 if not awaiting approval |
| GET | `/api/shots/{id}/shots/{file}` | | screenshot JPEG from a browsing step |

`cart: true` on a step = the persona clicked add to cart / buy / download there. That counts as buying (`buy_rate` uses it), even if they later say "maybe later".

`input.offer` = what the site sells and its prices, filled in automatically when only `url` is sent.

`context` = what changed about the product. `world` = the world customers live in (e.g. "spring 2020, COVID, masks required in stores").

**Status:** `casting → awaiting_approval → browsing → analyzing → done` (or `error`).

## Simulation object (live now)

```
id, input, status, error
personas[]   { id: "p1", name, age, occupation, archetype, segment, share, goal, budget, voice, avatar: { seed } }
live         { [persona_id]: Step[] }      Step = { n, url, title, shot, blocked?, cart?, thought, feeling, action, target }
decisions    { [persona_id]: { decision, rating, feeling, quote, reasons[], missing } }
summary      { buy_rate, clicked_buy: persona_id[], rating, decisions: { [decision]: count }, missing: [{ persona, text }] }
report       markdown from the analyst agent
memory       { [persona_id]: "## Memory" text the evolver wrote }
steps[]      { t, kind, note }   agent trace
```

- archetype: `price-sensitive | quality-first | brand-loyal | function-first | first-time user | skeptic | enthusiast`
- feeling: `delighted | interested | neutral | confused | annoyed | skeptical`
- decision: `buy | not buy | maybe later | would complain | would recommend`

## Coming next: three new keys on the same object

Types: [`b2a/contract.py`](../b2a/contract.py), TS mirror [`web/src/sim-extras.ts`](../web/src/sim-extras.ts).
**Example data to build against now:** [`fixtures/sim_extras_example.json`](../fixtures/sim_extras_example.json).

| Key | What it's for | UI |
|---|---|---|
| `evals: EvalScore[]` | Accuracy against held-out real reviews, one entry per calibration iteration | Line chart of `rating_error` and `theme_recall` by `iteration`; latest `predicted_rating` vs `actual_rating`; matched vs missed themes |
| `persona_changes: PersonaChange[]` | What each persona learned per iteration (`before` / `after` memory + `lesson`) | Persona drill-down: "what I learned" |
| `social: Social \| null` | Personas posting about the product: `posts` (feed, by `round`), `nodes`/`edges` (who replied to or reposted whom), `top_influencers`, `summary` | Feed + network graph: node size = `centrality`, color = `sentiment`, edges by `kind` |

All persona references use the same ids as `personas[]` (`p1`, `p2`, …).

## Gemini: UX lens and researched world (`b2a/gemini.py`)

| Method | Route | Body | Returns |
|---|---|---|---|
| POST | `/api/sims/{id}/lens` | | `Lens`. Runs Gemini on the screenshots where customers were confused, annoyed, skeptical, went back, or left without buying. 409 until the sim is `done`; 503 without `GOOGLE_API_KEY`. Takes ~10–30 s. |
| GET | `/api/sims/{id}/lens` | | the saved `Lens`, or 404 |
| POST | `/api/world` | `{ world, product? }` | `GroundedWorld` + `text`. Gemini + Google Search: what that world was really like, with sources. Put `text` in the sim's `world` field. |
| POST | `/api/products` | `{ name, description, price?, changes?, features?, image_url? }` | `{ id, url }`: a browsable page for a product with no website. Use `url` as the sim's `url`. |

**Lens in the UI:** for each `LensShot`, show the screenshot (`/api/shots/{id}/shots/{shot}`) with its `boxes` drawn on top (box_2d is `[ymin, xmin, ymax, xmax]` on a 0–1000 scale: `top = ymin/10 %`, `left = xmin/10 %`, `height = (ymax−ymin)/10 %`, `width = (xmax−xmin)/10 %`), plus the customer's `thought`. `hotspots` is the owner's list: the same problem found by several customers, with who hit it and which models played them. Types: `web/src/sim-extras.ts`.

## MongoDB Atlas (`b2a/mongo.py`, `b2a/memory.py`)

Set `MONGODB_URI` (and optionally `MONGODB_DB`, default `hackpton`) in `.env`. Without it, everything below works from local JSON files.

| Method | Route | Returns |
|---|---|---|
| GET | `/api/storage` | `{ mongodb, vector_search, connected, database, counts: {simulations, sessions, evals, customer_memory}, last_error }` |
| GET | `/api/insights` | Across every simulation (aggregation pipelines on Atlas): `by_model` (buy rate and rating per model family and layer), `accuracy_by_round` (rating error and theme recall per evolve round), `by_archetype` (incl. how many started with inherited memory) |
| GET | `/api/memory/search?q=` | Atlas Vector Search over long-term customer memory: `[{ type, score, lessons }]` |

**Collections:** `customer_memory` (deepagents `/memories/` via `langgraph-store-mongodb`, with a vector index `memory_vectors` on Gemini embeddings), `simulations` (one doc per run, flat `agents` array), `sessions` (each customer's browsing steps), `evals` (one doc per accuracy score). Simulations are mirrored in the background on every save.

**New customers' memory:** `personas[].memory` now starts with their own type's lessons plus "From similar customers:" lessons found by vector search (cosine ≥ 0.65).

## Director mode (`b2a/director.py`)

One deep agent runs the whole simulation and logs a reason for every step. On with `"director": true` in `POST /api/sims`
(or `DIRECTOR=1`). The default pipeline is unchanged. New `POST /api/sims` fields: `models: string[]` (from
`GET /api/models`), `world_preset` (a key of `GET /api/worlds`), `case_id` (a `data/<case>` to score against with
`evals.score`), `director`, `stub` (no browsers, fixture results, for testing).

It uses the existing pieces: Layer 1 = `session.agent_shoppers` (`a1`, `a2`… now tagged `"layer": 1`, so
`evals`/`compare` see them), Layer 2 = personas starting from `memory.for_persona` plus their own memory at this
business, scoring = `evals.score` + `feedback_for_evolver` + `improvement`, word of mouth = `social.run` +
`network.analyze`, summary = `sim._summarize` + `compare.summary`.

New keys on the simulation object (all modes; empty unless the director ran):
```
runs[]       { n, layer, agents[], decisions{}, clicked_buy[], memory_versions{}, summary, status }   one per browsing pass
director[]   { t, tool, reason, args, result }   why the director did each thing
todos[]      the director's live plan (write_todos)
budget       { max_*, used counts, left }
```
`decisions[id]` also has `confidence, first_impression, review, liked[], disliked[], would_pay,
suggestions[{change, why, where, impact}]` (all modes), plus `layer, model, persona_id, memory_version` (director).
`personas[]` in director mode also carry `layer`, `memory_version`, `general_memory`.
`persona_changes[]` from the director carry `memory_version`.

**Status (director):** `briefing → casting → awaiting_approval → base_models → browsing → scoring → evolving → social →
summarizing → analyzing → done`. `/approve` and `/recast` resume the paused director, also after a server restart
(checkpoint in `runs/checkpoints.sqlite`). `/rerun` on a director sim starts a director round with the same customers.

**Memory, two more layers in the same store** (own namespaces, so `everything()` / `similar()` still list only customer types):
- `/memories/business/<persona_id>.md`: what one persona learned at this business (product-specific, tagged by source:
  session / eval / owner), scoped to the business + a lineage (rerun keeps it), with a `memory_version` per edit.
  The evolver writes it, and also updates the type's `/memories/<archetype>.md` as before.
- `/memories/director/lessons.md`: the director's lessons about running simulations, read into its prompt.
