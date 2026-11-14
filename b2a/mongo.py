"""MongoDB Atlas: where the customers' memory and every simulation live.

Three jobs, all off when MONGODB_URI is unset (the app then uses JSON files in runs/, as before):

1. Long-term customer memory. Deep Agents writes /memories/<customer-type>.md through a LangGraph store; with Atlas
   that store is langgraph-store-mongodb's MongoDBStore (collection `customer_memory`), so what a price-sensitive
   customer learned testing a cafe is there when it tests a mask shop tomorrow, on any machine.

2. Atlas Vector Search over that memory. Each memory file is embedded with Gemini (gemini-embedding-001, 768 dims),
   so a new customer recalls lessons from the most *similar* past customers, not only its own type:
   "a budget grad student buying coffee" finds what price-sensitive and first-time customers learned elsewhere.

3. Every simulation, mirrored: `simulations` (one doc per run, with a flat `agents` array), `sessions` (each customer's
   browsing steps), `evals` (one doc per accuracy score). Aggregation pipelines answer cross-run questions:
   which model family's customers buy most, and does accuracy improve with each evolve round (insights()).

    MONGODB_URI=mongodb+srv://...      MONGODB_DB=hackpton (default)
"""
from __future__ import annotations

import json
import os
import queue
import threading
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIMS = ROOT / "runs" / "sims"
EMBED_MODEL = os.getenv("EMBED_MODEL", "gemini-embedding-001")
EMBED_DIMS = 768
from . import outcome as _outcome

BUYS = {"buy": 1.0, "would recommend": 1.0, "maybe later": 0.3, "not buy": 0.0, "would complain": 0.0}


def _env():
    from dotenv import load_dotenv
    load_dotenv()


def uri() -> str:
    _env()
    return os.getenv("MONGODB_URI", "").strip()


def enabled() -> bool:
    return bool(uri())


@lru_cache
def client():
    from pymongo import MongoClient
    return MongoClient(uri(), appname="customer-sim", serverSelectionTimeoutMS=8000)


def db():
    _env()
    return client()[os.getenv("MONGODB_DB", "hackpton")]


# ---------------------------------------------------------------- embeddings (Gemini)

def can_embed() -> bool:
    _env()
    return bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))


def embed(texts) -> list[list[float]]:
    """Gemini embeddings for the vector index (768 dims keeps Atlas M0 small and fast)."""
    from google.genai import types
    from .gemini import _client
    texts = [t if t.strip() else "(empty)" for t in texts]
    r = _client().models.embed_content(model=EMBED_MODEL, contents=texts,
                                       config=types.EmbedContentConfig(output_dimensionality=EMBED_DIMS))
    return [list(e.values) for e in r.embeddings]


def index_config(dims: int = EMBED_DIMS, fn=None):
    """Vector index over the memory files' text ("content"), for semantic recall."""
    from langgraph.store.mongodb import create_vector_index_config
    return create_vector_index_config(dims=dims, embed=fn or embed, fields=["content"], name="memory_vectors")


def memory_store(embed_fn=None):
    """The LangGraph store for /memories/ on Atlas, with Atlas Vector Search when Gemini embeddings are available."""
    from langgraph.store.mongodb import MongoDBStore
    return MongoDBStore(collection=db()["customer_memory"], index_config=index_config(fn=embed_fn) if can_embed() else None,
                        auto_index_timeout=30)


# ---------------------------------------------------------------- simulations

def agents_of(view: dict) -> list[dict]:
    """Flat per-customer rows: easy to $unwind and $group across every simulation."""
    decisions = view.get("decisions") or {}
    clicked = set((view.get("summary") or {}).get("clicked_buy") or [])
    out = []
    for p in view.get("personas") or []:
        d = decisions.get(p["id"])
        if not d:
            continue
        out.append({"persona_id": p["id"], "name": p.get("name", ""), "archetype": p.get("archetype", ""),
                    "model": p.get("model", ""), "layer": int(p.get("layer") or 2), "share": float(p.get("share") or 0),
                    "decision": d.get("decision", ""), "rating": d.get("rating"),
                    "bought": _outcome.bought(d, (view.get("live") or {}).get(p["id"])), "clicked_buy": p["id"] in clicked,
                    "outcome": _outcome.of(d, (view.get("live") or {}).get(p["id"])),
                    "inherited_memory": bool(p.get("inherited"))})
    return out


def sim_doc(view: dict) -> dict:
    i = view.get("input") or {}
    doc = {k: v for k, v in view.items() if k not in ("live",)}
    doc.update({"_id": view["id"], "agents": agents_of(view), "updated_at": datetime.now(timezone.utc),
                "product": i.get("name", ""), "round": int(view.get("round") or 0)})
    return doc


def save_sim(view: dict) -> None:
    """Upsert one simulation, its sessions and its eval scores."""
    d = db()
    d["simulations"].replace_one({"_id": view["id"]}, sim_doc(view), upsert=True)
    for pid, steps in (view.get("live") or {}).items():  # a few customers per run: plain upserts are plenty
        d["sessions"].replace_one({"_id": f"{view['id']}:{pid}"},
                                  {"_id": f"{view['id']}:{pid}", "sim_id": view["id"], "persona_id": pid, "steps": steps,
                                   "decision": (view.get("decisions") or {}).get(pid)}, upsert=True)
    for n, e in enumerate(view.get("evals") or []):
        d["evals"].replace_one({"_id": f"{view['id']}:{n}"},
                               {**e, "_id": f"{view['id']}:{n}", "sim_id": view["id"], "product": (view.get("input") or {}).get("name", ""),
                                "round": int(view.get("round") or 0)}, upsert=True)


# Writes happen in the background so a slow network never slows a simulation. Saves of the same sim are coalesced:
# only its latest state is written.
_q: queue.Queue = queue.Queue()
_pending: dict[str, dict] = {}
_plock = threading.Lock()
_worker: threading.Thread | None = None
last_error: str = ""


def _run():
    global last_error
    while True:
        sid = _q.get()
        with _plock:
            view = _pending.pop(sid, None)
        if view is None:
            continue
        try:
            save_sim(view)
            last_error = ""
        except Exception as e:  # never break a simulation because the database is unreachable
            last_error = f"{type(e).__name__}: {e}"[:300]


def mirror(view: dict) -> None:
    """Queue a simulation for Atlas. No-op without MONGODB_URI."""
    global _worker
    if not enabled() or not view.get("id"):
        return
    with _plock:
        first = view["id"] not in _pending
        _pending[view["id"]] = json.loads(json.dumps(view, default=str))  # snapshot: the job keeps changing
    if _worker is None or not _worker.is_alive():
        _worker = threading.Thread(target=_run, daemon=True, name="mongo-mirror")
        _worker.start()
    if first:
        _q.put(view["id"])


def backfill() -> int:
    """Copy every simulation already on disk into Atlas."""
    n = 0
    for f in sorted(SIMS.glob("*/sim.json")):
        try:
            save_sim(json.loads(f.read_text()))
            n += 1
        except Exception:
            pass
    return n


# ---------------------------------------------------------------- insights (aggregation pipelines)

BY_MODEL = [
    {"$unwind": "$agents"},
    {"$group": {"_id": {"model": "$agents.model", "layer": "$agents.layer"}, "customers": {"$sum": 1},
                "bought": {"$sum": {"$cond": ["$agents.bought", 1, 0]}}, "avg_rating": {"$avg": "$agents.rating"},
                "simulations": {"$addToSet": "$_id"}}},
    {"$project": {"_id": 0, "model": "$_id.model", "layer": "$_id.layer", "customers": 1, "bought": 1,
                  "buy_rate": {"$divide": ["$bought", "$customers"]}, "avg_rating": 1,
                  "simulations": {"$size": "$simulations"}}},
    {"$sort": {"layer": 1, "customers": -1}},
]

ACCURACY_BY_ROUND = [
    {"$group": {"_id": {"stage": {"$ifNull": ["$stage", "all"]}, "iteration": "$iteration"}, "scores": {"$sum": 1},
                "rating_error": {"$avg": "$rating_error"}, "theme_recall": {"$avg": "$theme_recall"},
                "products": {"$addToSet": "$product"}}},
    {"$project": {"_id": 0, "stage": "$_id.stage", "iteration": "$_id.iteration", "scores": 1,
                  "rating_error": 1, "theme_recall": 1,
                  "products": {"$size": "$products"}}},
    {"$sort": {"iteration": 1, "stage": 1}},
]

BY_ARCHETYPE = [
    {"$unwind": "$agents"}, {"$match": {"agents.layer": 2}},
    {"$group": {"_id": "$agents.archetype", "customers": {"$sum": 1}, "bought": {"$sum": {"$cond": ["$agents.bought", 1, 0]}},
                "avg_rating": {"$avg": "$agents.rating"}, "with_memory": {"$sum": {"$cond": ["$agents.inherited_memory", 1, 0]}}}},
    {"$project": {"_id": 0, "archetype": "$_id", "customers": 1, "with_memory": 1,
                  "buy_rate": {"$divide": ["$bought", "$customers"]}, "avg_rating": 1}},
    {"$sort": {"customers": -1}},
]


def _rounded(rows) -> list[dict]:
    return [{k: round(v, 3) if isinstance(v, float) else v for k, v in r.items()} for r in rows]


def insights() -> dict:
    """Across every simulation: customers by model family, accuracy by evolve round, customer types."""
    if enabled():
        d = db()
        return {"source": "mongodb", "simulations": d["simulations"].count_documents({}),
                "by_model": _rounded(d["simulations"].aggregate(BY_MODEL)),
                "accuracy_by_round": _rounded(d["evals"].aggregate(ACCURACY_BY_ROUND)),
                "by_archetype": _rounded(d["simulations"].aggregate(BY_ARCHETYPE))}
    return _insights_local()


def _insights_local() -> dict:
    """Same numbers from the JSON files, so the page works before Atlas is set up."""
    from collections import defaultdict
    views = []
    for f in SIMS.glob("*/sim.json"):
        try:
            views.append(json.loads(f.read_text()))
        except Exception:
            pass
    bm: dict = defaultdict(lambda: {"customers": 0, "bought": 0, "ratings": [], "sims": set()})
    ba: dict = defaultdict(lambda: {"customers": 0, "bought": 0, "ratings": [], "with_memory": 0})
    acc: dict = defaultdict(lambda: {"scores": 0, "err": [], "rec": [], "products": set()})
    for v in views:
        for a in agents_of(v):
            m = bm[(a["model"], a["layer"])]
            m["customers"] += 1; m["bought"] += a["bought"]; m["sims"].add(v["id"])
            if a["rating"] is not None:
                m["ratings"].append(a["rating"])
            if a["layer"] == 2:
                t = ba[a["archetype"]]
                t["customers"] += 1; t["bought"] += a["bought"]; t["with_memory"] += a["inherited_memory"]
                if a["rating"] is not None:
                    t["ratings"].append(a["rating"])
        for e in v.get("evals") or []:
            r = acc[(e.get("stage") or "all", e.get("iteration", 0))]
            r["scores"] += 1; r["err"].append(e["rating_error"]); r["rec"].append(e["theme_recall"])
            r["products"].add((v.get("input") or {}).get("name", ""))
    avg = lambda xs: round(sum(xs) / len(xs), 3) if xs else None
    return {"source": "local files", "simulations": len(views),
            "by_model": sorted([{"model": k[0], "layer": k[1], "customers": x["customers"], "bought": x["bought"],
                                 "buy_rate": round(x["bought"] / x["customers"], 3), "avg_rating": avg(x["ratings"]), "simulations": len(x["sims"])}
                                for k, x in bm.items()], key=lambda r: (r["layer"], -r["customers"])),
            "accuracy_by_round": sorted([{"stage": k[0], "iteration": k[1], "scores": x["scores"], "rating_error": avg(x["err"]),
                                          "theme_recall": avg(x["rec"]), "products": len(x["products"])} for k, x in acc.items()],
                                        key=lambda r: (r["iteration"], r["stage"])),
            "by_archetype": sorted([{"archetype": k, "customers": x["customers"], "with_memory": x["with_memory"],
                                     "buy_rate": round(x["bought"] / x["customers"], 3), "avg_rating": avg(x["ratings"])}
                                    for k, x in ba.items()], key=lambda r: -r["customers"])}


def status() -> dict:
    """For a quick check: GET /api/storage."""
    out = {"mongodb": enabled(), "vector_search": enabled() and can_embed(), "embed_model": EMBED_MODEL if can_embed() else None,
           "last_error": last_error}
    if enabled():
        try:
            client().admin.command("ping")
            d = db()
            out.update(database=d.name, connected=True,
                       counts={c: d[c].estimated_document_count() for c in ("simulations", "sessions", "evals", "customer_memory")})
        except Exception as e:
            out.update(connected=False, error=f"{type(e).__name__}: {e}"[:300])
    return out
