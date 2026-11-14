# Agent-ready

**Will AI shopping agents pick your business?**

More and more people ask an AI agent to find them a caterer, an insurer or a plumber. The agent reads a few listings and
chooses one. Agent-ready tests your business against those agents before your customers' agents decide for them.

1. **Your customers become segments.** Describe your customers in a sentence or upload a CSV. An agent splits them into
   segments and writes the requests each segment would actually type to its AI assistant.
2. **Real AI shoppers run those requests.** Claude and GPT (and Gemini when a key is set) each read your listing next to
   your competitors' and pick one, in shuffled order so position doesn't bias the result. Every square in the grid is one
   real model's decision.
3. **A deep agent fixes what lost.** A critic sub-agent reads why the shoppers chose competitors. A rewriter sub-agent
   rewrites your listing using **only the facts you confirmed**, never a competitor's claims. Then it re-tests.
4. **It remembers.** Lessons about what makes agents choose a listing are saved and loaded into every future test.

The shoppers are real models, not simulations: for business-to-agent (B2A) commerce, the agent is the customer.
The customer segments are a simulation, a cheap first pass before testing with people.

## Run it

```bash
# backend (Python 3.12)
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python deepagents langchain-anthropic langchain-openai langchain-google-genai fastapi uvicorn python-dotenv
cp .env.example .env        # ANTHROPIC_API_KEY, OPENAI_API_KEY, optional GOOGLE_API_KEY
.venv/bin/uvicorn server:app --port 4620

# frontend
cd web && npm install && npm run dev     # http://localhost:4621
```

Each key you add turns on one more shopper: `ANTHROPIC_API_KEY` → Claude, `OPENAI_API_KEY` → GPT, `GOOGLE_API_KEY` → Gemini.

## How it works

| File | What it does |
|---|---|
| `b2a/agent.py` | The deep agent: plans with a todo list, calls the tools below, delegates to `critic` and `rewriter` sub-agents, writes `/report.md` |
| `b2a/market.py` | The market test: every shopper × every customer request × shuffled orders, pick rate weighted by segment size |
| `b2a/personas.py` | Customer segments and their requests, from a description or a CSV (name, email, phone, address and ID columns are dropped first) |
| `b2a/models.py` | Which shoppers run, based on the keys present |
| `b2a/presets.py` | Two demo markets: commercial truck insurance and event catering. All businesses in them are fictional |
| `server.py` | FastAPI |
| `web/` | React UI: setup, live shopper grid, test cards with word-level diffs, agent trace, report |

**Deep Agents features in use:** planning (`write_todos`, shown live), sub-agents with separate contexts (`critic`,
`rewriter`), a filesystem per job (`/facts.md`, `/tests/*.json`, `/report.md`, read and written by the agent and its
sub-agents), and long-term memory across jobs (`runs/memory.md`).

## Honest limits

- A model's choice in a test is not a purchase. The pick rate tells you how readable and matchable your listing is to
  agents, under the requests we generated.
- Segments come from what you tell us about your customers. Garbage in, garbage out.
- The rewrite only uses facts you entered. "Worth adding if true" items in the report are things buyers asked for that
  you did not mention. They never go into the listing.

Built at HackPrinceton Fall 2026.
