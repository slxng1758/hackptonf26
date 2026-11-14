# Customer simulation API

Backend: `http://localhost:4620` (`server.py`, engine in `b2a/sim.py` + `b2a/session.py`).

## Routes (live now)

| Method | Route | Body | Returns |
|---|---|---|---|
| POST | `/api/sims` | `{ url, name?, category?, customers?, context?, world? }` | `{ id }` |
| GET | `/api/sims` | | `[{ id, name, status, buy_rate }]` |
| GET | `/api/sims/{id}` | | the simulation (below). Poll while running |
| POST | `/api/sims/{id}/approve` | `{ personas?: Persona[] }` | `{ ok: true }`, or 409 if not awaiting approval |
| GET | `/api/shots/{id}/shots/{file}` | | screenshot JPEG from a browsing step |

`context` = what changed about the product. `world` = the world customers live in (e.g. "spring 2020, COVID, masks required in stores").

**Status:** `casting → awaiting_approval → browsing → analyzing → done` (or `error`).

## Simulation object (live now)

```
id, input, status, error
personas[]   { id: "p1", name, age, occupation, archetype, segment, share, goal, budget, voice, avatar: { seed } }
live         { [persona_id]: Step[] }      Step = { n, url, title, shot, blocked?, thought, feeling, action, target }
decisions    { [persona_id]: { decision, rating, feeling, quote, reasons[], missing } }
summary      { buy_rate, rating, decisions: { [decision]: count }, missing: [{ persona, text }] }
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
