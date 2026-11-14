"""Long-term customer memory, shared across every business we test.

Deep Agents mounts it at /memories/ through a CompositeBackend: the agents' own files (personas, sessions, report) live
in the simulation folder, and anything written under /memories/ goes to a LangGraph store that outlives the run.
One file per customer type, e.g. /memories/price-sensitive.md: what that kind of customer has learned on every site so
far. A new simulation for a different business starts its price-sensitive persona from that file.

Storage: a LangGraph InMemoryStore saved to runs/memory_store.json (MongoDB Atlas when MONGODB_URI is set, see TODO).
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


def store() -> InMemoryStore:
    global _store
    with _lock:
        if _store is None:
            _store = InMemoryStore()
            if FILE.exists():
                for key, value in json.loads(FILE.read_text()).items():
                    _store.put(NS, key, value)
        return _store


def persist():
    """Write the store to disk after a run (the in-memory store would forget on restart)."""
    s = store()
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
