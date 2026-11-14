# Pick persona models + per-persona thoughts & suggestions

## Context
The owner should (1) choose which model families play the customers (Gemini, Claude, GPT, …), and (2) get results at two levels: an overview, plus a click-through per persona showing its thought process, reactions and **its own thoughts and suggestions on the product**, not just buy / not buy.

Candy's commits on `main` already cover part of this:
- `b2a/models.py` `persona_models()` builds every family with a key (Gemini, Claude, GPT, Grok, Llama); `persona(name)` returns one.
- `b2a/session.py` `cast()` assigns `persona["model"]` round-robin across families; `browse()` uses `persona_model(persona.get("model"))`.
- Buy rate by model is computed and shown.
- `web/src/Simulate.tsx` `Replay` modal already shows one persona's browsing steps (screenshot, thought, feeling, action) + decision (quote, reasons, "would have changed my mind").
- Evolver + learning loop + `persona_changes` exist (commit 03fac04).

**Gaps:** the owner can't choose models, and the decision has no overall review or suggestions. The overview doesn't combine suggestions across personas.

These are Candy's files: agree with them who makes the edits before starting.

---

## 1. Owner picks the models
- `GET /api/models` → `list(persona_models())` (only families with keys) in `server.py`.
- `SimIn` gets `models: list[str] = []` (empty = all available). Store in `job.inp`.
- `cast()` in `b2a/session.py`: round-robin over `inp["models"] ∩ persona_models()` instead of all families.
- Approval screen: each persona card gets a small model dropdown. `approve` already accepts edited persona dicts, and `browse()` already reads `persona["model"]`, so no backend change.
- Optional "same personas, every model" toggle: duplicate each persona once per chosen model (id `p1-gemini`) to compare models on identical customers. Reuses the by-model buy rate.

## 2. Each persona gives a review and suggestions
Extend `Decision` in `b2a/session.py` (keep existing fields; the UI won't break):
```python
first_impression: str   # gut reaction in the first seconds, in their voice
review: str             # 3-5 sentences: what they think of the product overall, honest, in character
liked: list[str]        # 1-3, each tied to something they saw
disliked: list[str]     # 1-3, each tied to something they saw
suggestions: list[Suggestion]  # 1-3
would_pay: str          # what they'd actually pay, e.g. "$18, not $24"

class Suggestion(BaseModel):
    change: str          # concrete change to the product, page or pricing
    why: str             # why it matters to them
    where: str = ""      # page/section it applies to, from what they saw
    impact: Literal["would make me buy", "nice to have"]
```
Update the `DECIDE` prompt: "Write as yourself. Give your honest review, then suggestions you'd actually want, tied to what you saw." Mirror the fields in `Simulate.tsx`'s `Decision` interface and `docs/CONTRACT.md`.

## 3. Overview combines suggestions
In `SimJob._summarize()` (`b2a/sim.py`), one `fast()` structured call groups similar suggestions across personas:
`summary.top_suggestions: [{change, personas: [ids], models: [families], would_buy_count, where}]`, sorted by how many personas who didn't buy said it would make them buy. The analyst subagent already writes the narrative report and can read these too.

## 4. UI (UI teammate / Candy)
- **Overview:** headline (buy rate, rating), decisions by archetype and by model, **top suggestions** (with avatars of who asked), word-of-mouth, "were we right" chart.
- **Persona card → drill-down** (extend existing `Replay`): header with avatar, archetype, **model badge**; *Journey* (existing step replay); *Review* (first impression, review, liked/disliked); *Suggestions* (change, why, where, impact); *What I learned* (`persona_changes` / memory).

## Files
`server.py` (route + `SimIn.models`), `b2a/session.py` (`Decision`, `Suggestion`, `DECIDE`, `cast`), `b2a/sim.py` (`_summarize`), `web/src/Simulate.tsx` (model picker, drill-down sections, overview suggestions), `docs/CONTRACT.md`.

## Verification
- `GET /api/models` lists only keyed families; a sim with `models: ["Gemini","GPT"]` assigns only those; changing a persona's model on the approval screen changes which model produced `decisions[pid]` (logged).
- A finished sim has `review`, `liked`, `disliked`, `suggestions` for every persona, and suggestions name real pages they visited.
- `summary.top_suggestions` merges near-duplicates and its counts match the per-persona data.
- Click a persona in the UI: journey, review, suggestions and model badge all render; old sims without the new fields still open.
