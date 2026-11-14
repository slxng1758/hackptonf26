"""Long-term customer memory, shared across every business we test.

Deep Agents mounts it at /memories/ through a CompositeBackend: the agents' own files (personas, sessions, report) live
in the simulation folder, and anything written under /memories/ goes to a LangGraph store that outlives the run.
One file per customer type, e.g. /memories/price-sensitive.md: what that kind of customer has learned on every site so
far. A new simulation for a different business starts its price-sensitive persona from that file.

Storage: MongoDB Atlas (langgraph-store-mongodb, collection `customer_memory`) when MONGODB_URI is set, with Atlas
Vector Search over the memory text (Gemini embeddings). Otherwise a LangGraph InMemoryStore saved to
runs/memory_store.json. See b2a/mongo.py.

similar(): a new customer also recalls lessons from the most similar *other* customer types (vector search).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from deepagents.backends import CompositeBackend, FilesystemBackend, StoreBackend
from langgraph.store.memory import InMemoryStore

FILE = Path(__file__).resolve().parent.parent / "runs" / "memory_store.json"
NS = ("customer-memory",)
_lock = threading.Lock()
_store: InMemoryStore | None = None


def _safe_embed(texts):
    """Gemini embeddings; a neutral vector if Gemini fails, so a memory write never breaks a simulation."""
    from . import mongo
    try:
        return mongo.embed(texts)
    except Exception:
        return [[(1 / mongo.EMBED_DIMS) ** 0.5] * mongo.EMBED_DIMS for _ in texts]


def using_mongo() -> bool:
    from . import mongo
    return mongo.enabled()


def store():
    """Atlas (MongoDBStore) when MONGODB_URI is set, else an in-memory store loaded from runs/memory_store.json."""
    global _store
    with _lock:
        if _store is None:
            from . import mongo
            if mongo.enabled():
                try:
                    _store = mongo.memory_store(embed_fn=_safe_embed)
                    return _store
                except Exception as e:  # unreachable cluster: keep working from local files
                    print(f"[memory] MongoDB unavailable ({type(e).__name__}); using local memory file")
            index = {"dims": mongo.EMBED_DIMS, "embed": _safe_embed, "fields": ["content"]} if mongo.can_embed() else None
            _store = InMemoryStore(index=index) if index else InMemoryStore()
            if FILE.exists():
                for key, value in json.loads(FILE.read_text()).items():
                    _store.put(NS, key, value)
        return _store


def persist():
    """Write the store to disk after a run (the in-memory store would forget on restart). Atlas persists by itself."""
    s = store()
    if not isinstance(s, InMemoryStore):
        return
    items = {it.key: it.value for it in s.search(NS, limit=10_000)}
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(items, indent=2))


def _backend() -> StoreBackend:
    return StoreBackend(namespace=lambda _rt: NS, store=store())


def backend_for(sim_dir: Path) -> CompositeBackend:
    """What the Deep Agents orchestrator sees: the simulation's files, plus /memories/ for long-term memory."""
    return CompositeBackend(default=FilesystemBackend(root_dir=str(sim_dir), virtual_mode=True), routes={"/memories/": _backend()})


def _key(archetype: str) -> str:
    return "/" + archetype.replace(" ", "-") + ".md"


def for_archetype(archetype: str) -> str:
    """Everything this kind of customer has learned so far, across businesses ('' if nothing yet)."""
    r = _backend().read(_key(archetype))
    if r.error or not r.file_data:  # agents sometimes shorten the name ("first-time" for "first-time user")
        first = archetype.split()[0].split("-")[0].lower()
        alt = next((it.key for it in store().search(NS, limit=10_000) if it.key.strip("/").lower().startswith(first)), None)
        r = _backend().read(alt) if alt else r
    if r.error or not r.file_data:
        return ""
    from deepagents.backends.utils import file_data_to_string
    return file_data_to_string(r.file_data).strip()


def everything() -> dict[str, str]:
    out = {}
    for it in store().search(NS, limit=10_000):
        r = _backend().read(it.key)
        if not r.error and r.file_data:
            from deepagents.backends.utils import file_data_to_string
            out[it.key.strip("/").removesuffix(".md")] = file_data_to_string(r.file_data).strip()
    return out


def similar(description: str, exclude: str = "", k: int = 2, min_score: float = 0.65) -> list[dict]:
    """Vector search: memory files of other customer types most similar to this customer (Atlas Vector Search on
    MongoDB, in-memory vectors otherwise). [] when there are no embeddings or nothing is close enough."""
    from . import mongo
    if not mongo.can_embed():
        return []
    try:
        hits = store().search(NS, query=description, limit=k + 3)
    except Exception:
        return []
    # Scores are cosine similarity. Atlas reports cosine as (1 + cos) / 2, so convert it back. With Gemini embeddings,
    # related lessons score ~0.75 and unrelated ones ~0.5-0.6, hence the 0.65 cutoff.
    atlas = not isinstance(store(), InMemoryStore)
    out = []
    for h in hits:
        score = None if h.score is None else (2 * h.score - 1 if atlas else h.score)
        if h.key == _key(exclude) or (score is not None and score < min_score):
            continue
        text = (h.value or {}).get("content", "")
        lines = [l.strip() for l in (text if isinstance(text, str) else "\n".join(text)).splitlines() if l.strip().startswith(("-", "*"))]
        if lines:
            out.append({"type": h.key.strip("/").removesuffix(".md"), "score": round(score or 0, 3), "lessons": lines[:2]})
        if len(out) >= k:
            break
    return out


def for_persona(p: dict) -> str:
    """This customer's starting memory: what its own type learned, plus the closest lessons from similar customers."""
    own = for_archetype(p.get("archetype", ""))
    who = f"{p.get('archetype', '')} customer, {p.get('age', '')}, {p.get('occupation', '')}. Goal: {p.get('goal', '')}. Budget: {p.get('budget', '')}."
    near = similar(who, exclude=p.get("archetype", ""))
    if not near:
        return own
    extra = "\n".join(f"{l} (learned by a similar {n['type']} customer)" for n in near for l in n["lessons"])
    return (own + "\n" if own else "") + "From similar customers:\n" + extra
