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


class SimIn(BaseModel):
    url: str = Field(min_length=4, max_length=500)
    name: str = Field("", max_length=120)
    category: str = Field("", max_length=200)
    customers: str = Field("", max_length=20000)
    context: str = Field("", max_length=1000, description="what changed about the product")
    world: str = Field("", max_length=300, description="the world the customers live in")


@app.post("/api/sims")
def sim_start(body: SimIn):
    d = body.model_dump()
    if not d["url"].startswith("http"):
        d["url"] = "https://" + d["url"]
    return {"id": sim.start(d).id}


@app.get("/api/sims")
def sim_list():
    return sim.list_sims()


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


@app.post("/api/sims/{sim_id}/rerun")
def sim_rerun(sim_id: str):
    job = sim.rerun(sim_id)
    if not job:
        raise HTTPException(409, "Only a finished simulation can run again.")
    return {"id": job.id}


@app.get("/api/fixtures/extras")
def extras_fixture():
    """Sarah's example data for evals / persona_changes / social, so the UI can be built before the backend exists."""
    import json
    from pathlib import Path
    return json.loads((Path(__file__).parent / "fixtures" / "sim_extras_example.json").read_text())
