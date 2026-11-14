"""API for the UI.  uvicorn server:app --port 4620"""
from __future__ import annotations

import threading

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from sim.presets import PRESETS
from sim.runner import new_run, run
from sim.store import get_store

app = FastAPI(title="myth")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:4621", "http://127.0.0.1:4621"], allow_methods=["*"], allow_headers=["*"])
store = get_store()


class Start(BaseModel):
    preset: str = "village"
    generations: int = Field(8, ge=1, le=60)
    limit: int = Field(1200, ge=200, le=8000)


@app.get("/api/presets")
def presets():
    return {k: {"title": v["title"], "truth": v["truth"], "roles": list(v["roles"]) + ["archivist"], "events": v["events"]} for k, v in PRESETS.items()}


@app.get("/api/runs")
def runs():
    return store.list_runs()


@app.get("/api/runs/{run_id}")
def get(run_id: str):
    r = store.get_run(run_id)
    if not r:
        raise HTTPException(404, "no such run")
    return r


@app.post("/api/runs")
def start(body: Start):
    if body.preset not in PRESETS:
        raise HTTPException(400, "unknown preset")
    r = new_run(body.preset, body.generations, body.limit)

    def go():
        try:
            run(r, store)
        except Exception:
            pass  # status + error are saved on the run

    threading.Thread(target=go, daemon=True).start()
    return {"id": r["id"]}


# ---------- infodemic ----------
import json as _json
from pathlib import Path as _Path

_EPI = _Path(__file__).resolve().parent / "runs" / "epi"


@app.get("/api/epi")
def epi_list():
    if not _EPI.exists():
        return []
    out = []
    for p in sorted(_EPI.glob("*.json"), reverse=True):
        try:
            d = _json.loads(p.read_text())
            out.append({"id": d["id"], "scenario": d["scenario"], "ever_sick": d["ever_sick"], "population": d["population"], "variants": len(d["variants"])})
        except Exception:
            pass
    return out


@app.get("/api/epi/{run_id}")
def epi_get(run_id: str):
    p = _EPI / f"{_Path(run_id).name}.json"
    if not p.exists():
        raise HTTPException(404, "no such run")
    return _json.loads(p.read_text())


# ---------- message lab ----------
from sim import lab as _lab


class LabStart(BaseModel):
    message: str = Field(min_length=3, max_length=400)
    community: str = Field(min_length=3, max_length=600)


@app.post("/api/lab")
def lab_start(body: LabStart):
    return {"id": _lab.start(body.message, body.community).id}


@app.get("/api/lab")
def lab_list():
    return _lab.list_jobs()


@app.get("/api/lab/{job_id}")
def lab_get(job_id: str):
    d = _lab.get(job_id)
    if not d:
        raise HTTPException(404, "no such job")
    return d
