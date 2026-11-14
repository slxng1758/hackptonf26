# Inheritance

<!-- Hook + why it matters: the team writes this part. -->

A simulated community lives through generations. Each generation can read only what the previous
generation's archivist chose to keep, under a hard storage limit. A hidden evaluator, the only part
of the system that knows what really happened, scores every generation on two things that can come apart:

- **belief**: does the archive still carry the true cause?
- **practice**: would people following the archive still do the thing that works?

plus **myth**: how far the explanation has drifted toward ritual, authority or the supernatural.

Two worlds ship with it: **The Well** (a village learns to boil contaminated water) and
**The Runbook** (a company learns to flush a stale cache after a bad deploy).

## Run it

```bash
# backend (Python 3.12, uv)
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python deepagents langchain-anthropic langchain-google-genai fastapi uvicorn pymongo python-dotenv
cp .env.example .env          # add ANTHROPIC_API_KEY (and optionally GOOGLE_API_KEY, MONGODB_URI)
.venv/bin/uvicorn server:app --port 4620

# frontend
cd web && npm install && npm run dev     # http://localhost:4621
```

Run a civilization without the UI:

```bash
.venv/bin/python -m sim.runner --preset village --generations 8 --limit 1200
```

## How it works

```
generation N folder (agents can't see outside it)
├── inherited/   what generation N-1's archivist kept      (read)
├── drafts/      physician, storyteller, ruler, skeptic     (write)
└── archive/     archivist's cut, hard-capped in characters (write → becomes N+1's inherited/)
```

- **Each generation is one deepagents agent** (the council) with five sub-agents: physician,
  storyteller, ruler, skeptic and archivist. Each has its own goals and its own isolated context.
- **Isolation is physical.** Every generation runs on a `FilesystemBackend` rooted at its own folder,
  so the original event is never reachable after generation 0.
- **Storage is enforced in code** (`sim/generation.py: enforce_limit`). Whatever the archivist leaves
  over the limit is cut, not just discouraged.
- **The evaluator** (`sim/evaluator.py`) reads each archive against the hidden ground truth and returns
  structured scores, the current rule, its stated reason, and specific false beliefs.
- **Storage:** MongoDB Atlas when `MONGODB_URI` is set (one document per run and per generation),
  JSON files in `runs/` otherwise.

| File | What it does |
|---|---|
| `sim/presets.py` | Worlds: hidden truth, eyewitness account, roles, events |
| `sim/generation.py` | One generation as a deep agent with sub-agents |
| `sim/evaluator.py` | Hidden evaluator with structured output |
| `sim/runner.py` | The generation loop (CLI) |
| `sim/store.py` | MongoDB Atlas or JSON storage |
| `server.py` | FastAPI for the UI |
| `web/` | React timeline UI |

## Models

Villagers make many calls, so they use a cheap model: Gemini if `GOOGLE_API_KEY` is set, otherwise
Claude Haiku. The evaluator makes one call per generation and uses a stronger model (Claude Sonnet).

## Prior work

LLMs have been studied in transmission-chain experiments, where a story is passed along and retold.
<!-- TODO: add the verified citation(s) before publishing. -->

## Credits

Idea: Jayden. Built at HackPrinceton Fall 2026.
