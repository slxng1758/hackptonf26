"""API.  .venv/bin/uvicorn server:app --port 4620"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from b2a import agent, personas, scan as scanner, sim
from b2a.models import shoppers
from b2a.presets import PRESETS

app = FastAPI(title="b2a")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:4621", "http://127.0.0.1:4621"], allow_methods=["*"], allow_headers=["*"])

from b2a.product_page import router as product_router  # description mode: browsable pages for products without a website
app.include_router(product_router)


class Start(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=160)
    listing: str = Field(min_length=5, max_length=1500)
    facts: list[str] = Field(min_length=1, max_length=40)
    competitors: list[str] = Field(min_length=1, max_length=8)
    customers: str = Field(min_length=5, max_length=20000, description="plain description or CSV text")
    customers_csv: bool = False
    competitor_meta: list[dict] | None = None


class ScanIn(BaseModel):
    query: str = Field(min_length=3, max_length=300)


@app.post("/api/scan")
def scan(body: ScanIn):
    try:
        return scanner.scan(body.query)
    except Exception as e:
        raise HTTPException(502, f"Couldn't read that business: {type(e).__name__}. Try the website URL, or a demo.")


@app.get("/api/presets")
def presets():
    return PRESETS


@app.get("/api/shoppers")
def list_shoppers():
    return list(shoppers().keys())


@app.post("/api/jobs")
def start(body: Start):
    inp = body.model_dump()
    if inp.pop("customers_csv"):
        inp["customers"] = personas.summarize_csv(inp["customers"])
    return {"id": agent.start(inp).id}


@app.get("/api/jobs")
def jobs():
    return agent.list_jobs()


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    d = agent.get(job_id)
    if not d:
        raise HTTPException(404, "no such job")
    return d


@app.get("/api/lessons")
def lessons():
    return agent.lessons()


# ---------- customer simulation (personas browse the real product) ----------
from fastapi.staticfiles import StaticFiles

sim.SIMS.mkdir(parents=True, exist_ok=True)
app.mount("/api/shots", StaticFiles(directory=str(sim.SIMS)), name="shots")
(sim.RUNS / "amazon" / "pages").mkdir(parents=True, exist_ok=True)
app.mount("/api/product", StaticFiles(directory=str(sim.RUNS / "amazon" / "pages")), name="product")  # Amazon eval product pages


class SimIn(BaseModel):
    description: str = Field("", max_length=8000, description="the product, as the owner describes it; we turn it into a page the customers browse")
    url: str = Field("", max_length=500, description="optional: a real website instead of a description")
    name: str = Field("", max_length=120)
    price: str = Field("", max_length=60)
    category: str = Field("", max_length=200)
    customers: str = Field("", max_length=20000)
    context: str = Field("", max_length=1000, description="what changed about the product")
    world: str = Field("", max_length=300, description="the world the customers live in")
    models: list[str] = Field(default_factory=list, description="model families to play customers (GET /api/models); empty = all keyed")
    world_preset: str | None = Field(None, description="a key of GET /api/worlds")
    case_id: str | None = Field(None, description="backtest case in data/ to score against (b2a/evals.py)")
    director: bool = Field(False, description="the director agent runs the simulation (also on with DIRECTOR=1)")
    stub: bool = Field(False, description="director stub mode: no browsers, fixture results")


@app.get("/api/models")
def list_models():
    """Model families that can play customers (only those with an API key)."""
    from b2a.models import persona_models
    return list(persona_models().keys())


@app.get("/api/worlds")
def list_worlds():
    """One-click world presets for the director (put the key in world_preset)."""
    from b2a.director import WORLDS
    return WORLDS


def _name_from(description: str) -> str:
    """Name for a described product when the owner gave none: its first sentence if short, else the first few words."""
    import re
    first = re.split(r"(?<=[.!?:])\s|\n", description.strip(), maxsplit=1)[0].strip(" .!?:-#*")
    return first if len(first) <= 60 else " ".join(first.split()[:6])


@app.post("/api/sims")
def sim_start(body: SimIn):
    d = body.model_dump()
    if len(d["description"].strip()) >= 10:
        # description mode: render the owner's own words as a product page (b2a/product_page.py); customers browse that
        from b2a import product_page
        d["name"] = d["name"] or _name_from(d["description"])
        page = product_page.create(product_page.Product(name=d["name"], description=d["description"], price=d["price"], changes=d["context"]))
        d["url"], d["product_id"], d["offer"] = page["url"], page["id"], d["description"][:2000]
    elif len(d["url"].strip()) >= 4:
        if not d["url"].startswith("http"):
            d["url"] = ("http://" if d["url"].startswith(("localhost", "127.0.0.1")) else "https://") + d["url"]
    else:
        raise HTTPException(422, "Describe your product (or give a website).")
    # "localhost" can reach a different server over IPv6 on this machine; our own pages live on 127.0.0.1
    d["url"] = d["url"].replace("://localhost:", "://127.0.0.1:")
    return {"id": sim.start(d).id}


@app.get("/api/sims")
def sim_list(host: str | None = None):
    return sim.list_sims(host)


@app.get("/api/sims/{sim_id}")
def sim_get(sim_id: str):
    d = sim.get(sim_id)
    if not d:
        raise HTTPException(404, "no such simulation")
    return d


class Approve(BaseModel):
    personas: list[dict] | None = None


@app.post("/api/sims/{sim_id}/approve")
def sim_approve(sim_id: str, body: Approve):
    if not sim.approve(sim_id, body.personas):
        raise HTTPException(409, "This simulation isn't waiting for approval.")
    return {"ok": True}


class Recast(BaseModel):
    feedback: str = Field(min_length=2, max_length=500)


@app.post("/api/sims/{sim_id}/recast")
def sim_recast(sim_id: str, body: Recast):
    if not sim.recast(sim_id, body.feedback):
        raise HTTPException(409, "This simulation isn't waiting for approval.")
    return {"ok": True}


class Teach(BaseModel):
    truth: str = Field(min_length=3, max_length=2000, description="what real customers actually did or said")


@app.post("/api/sims/{sim_id}/teach")
def sim_teach(sim_id: str, body: Teach):
    out = sim.teach(sim_id, body.truth)
    if out is None:
        raise HTTPException(409, "Only a finished simulation can learn.")
    return {"changes": out}


class Rerun(BaseModel):
    change: str = Field("", max_length=500, description="what the owner changed on the site since this run")


@app.post("/api/sims/{sim_id}/rerun")
def sim_rerun(sim_id: str, body: Rerun | None = None):
    job = sim.rerun(sim_id, (body.change if body else "").strip())
    if not job:
        raise HTTPException(409, "Only a finished simulation can run again.")
    return {"id": job.id}


@app.post("/api/sims/{sim_id}/evals")
def sim_add_eval(sim_id: str, body: dict):
    """Attach an accuracy score (b2a/contract.py EvalScore)."""
    from b2a.contract import EvalScore
    if not sim.add_eval(sim_id, EvalScore(**body).model_dump()):
        raise HTTPException(404, "no such simulation")
    return {"ok": True}


@app.post("/api/sims/{sim_id}/social")
def sim_set_social(sim_id: str, body: dict):
    """Attach the social layer (b2a/contract.py Social)."""
    from b2a.contract import Social
    if not sim.set_social(sim_id, Social(**body).model_dump()):
        raise HTTPException(404, "no such simulation")
    return {"ok": True}


@app.get("/api/insights")
def insights():
    """Across every simulation (MongoDB aggregation pipelines when Atlas is connected): buy rate by model family,
    accuracy by evolve round, customer types."""
    from b2a import mongo
    return mongo.insights()


@app.get("/api/storage")
def storage():
    """Is MongoDB Atlas connected, is vector search on, and how much is stored."""
    from b2a import mongo
    return mongo.status()


@app.get("/api/memory/search")
def memory_search(q: str):
    """Vector search over long-term customer memory: which past customers learned something relevant to this one."""
    from b2a import memory
    return memory.similar(q, k=5, min_score=0.0)


@app.get("/api/memory")
def long_term_memory():
    """What each type of customer has learned across every business tested."""
    from b2a import memory
    return memory.everything()


# ---------- Gemini: UX lens on the customers' screenshots, and a researched world (b2a/gemini.py) ----------

@app.post("/api/sims/{sim_id}/lens")
def sim_lens(sim_id: str):
    """Gemini boxes the spots on each page that confused or lost customers, then groups them into hotspots."""
    from b2a import gemini
    d = sim.get(sim_id)
    if not d:
        raise HTTPException(404, "no such simulation")
    if d.get("status") != "done":
        raise HTTPException(409, "Run the lens after the simulation is done.")
    try:
        return gemini.run_lens(sim_id, d).model_dump()
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@app.get("/api/sims/{sim_id}/lens")
def sim_lens_get(sim_id: str):
    from b2a import gemini
    d = gemini.saved_lens(sim_id)
    if d is None:
        raise HTTPException(404, "no lens yet: POST to this route to run it")
    return d


class WorldIn(BaseModel):
    world: str = Field(min_length=3, max_length=300)
    product: str = Field("", max_length=300)


@app.post("/api/world")
def world(body: WorldIn):
    """Gemini + Google Search: what the chosen world was really like, with sources. Put `text` in the sim's world field."""
    from b2a import gemini
    try:
        g = gemini.ground_world(body.world, body.product or "this product")
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    return {**g.model_dump(), "text": gemini.world_text(g)}


@app.get("/api/fixtures/extras")
def extras_fixture():
    """Sarah's example data for evals / persona_changes / social, so the UI can be built before the backend exists."""
    import json
    from pathlib import Path
    return json.loads((Path(__file__).parent / "fixtures" / "sim_extras_example.json").read_text())


# ---------- production: serve the built web app from the same server (Docker / Vultr). Must stay last. ----------
from pathlib import Path as _Path

_WEB = _Path(__file__).resolve().parent / "web" / "dist"
if _WEB.is_dir():
    app.mount("/", StaticFiles(directory=str(_WEB), html=True), name="web")
