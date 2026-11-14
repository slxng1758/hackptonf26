"""Where runs live. MongoDB Atlas when MONGODB_URI is set, otherwise JSON files in runs/.

One document per run, one per generation, so archives can be queried across time.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

RUNS = Path(__file__).resolve().parent.parent / "runs"


class JsonStore:
    def _dir(self, run_id: str) -> Path:
        d = RUNS / run_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_run(self, run: dict) -> None:
        (self._dir(run["id"]) / "run.json").write_text(json.dumps(run, indent=2))

    def save_generation(self, run_id: str, g: dict) -> None:
        (self._dir(run_id) / f"gen_{g['gen']:03d}.json").write_text(json.dumps(g, indent=2))

    def list_runs(self) -> list[dict]:
        out = []
        for p in sorted(RUNS.glob("*/run.json"), reverse=True):
            try:
                out.append(json.loads(p.read_text()))
            except Exception:
                pass
        return sorted(out, key=lambda r: r.get("created", ""), reverse=True)

    def get_run(self, run_id: str) -> dict | None:
        p = RUNS / run_id / "run.json"
        if not p.exists():
            return None
        run = json.loads(p.read_text())
        run["generations"] = [json.loads(g.read_text()) for g in sorted((RUNS / run_id).glob("gen_*.json"))]
        return run


class MongoStore:
    def __init__(self, uri: str):
        from pymongo import MongoClient
        db = MongoClient(uri, serverSelectionTimeoutMS=5000)["myth"]
        self.runs, self.gens = db["runs"], db["generations"]
        self.gens.create_index([("run_id", 1), ("gen", 1)], unique=True)

    def save_run(self, run: dict) -> None:
        self.runs.replace_one({"_id": run["id"]}, {"_id": run["id"], **run}, upsert=True)

    def save_generation(self, run_id: str, g: dict) -> None:
        self.gens.replace_one({"run_id": run_id, "gen": g["gen"]}, {"run_id": run_id, **g}, upsert=True)

    def list_runs(self) -> list[dict]:
        return [{k: v for k, v in r.items() if k != "_id"} for r in self.runs.find().sort("created", -1)]

    def get_run(self, run_id: str) -> dict | None:
        r = self.runs.find_one({"_id": run_id})
        if not r:
            return None
        r.pop("_id", None)
        r["generations"] = [{k: v for k, v in g.items() if k not in ("_id", "run_id")} for g in self.gens.find({"run_id": run_id}).sort("gen", 1)]
        return r


def get_store():
    uri = os.getenv("MONGODB_URI")
    return MongoStore(uri) if uri else JsonStore()
