"""Runs a civilization for N generations: genesis, then live, archive, prune, evaluate, inherit, repeat.

CLI:  python -m sim.runner --preset village --generations 8 --limit 1200
"""
from __future__ import annotations

import argparse
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from .evaluator import evaluate
from .generation import genesis_archive, run_generation
from .models import describe
from .presets import PRESETS
from .store import RUNS, get_store

load_dotenv()


def new_run(preset: str, generations: int, limit: int) -> dict:
    return {
        "id": datetime.now().strftime("%m%d-%H%M%S-") + uuid.uuid4().hex[:4],
        "preset": preset,
        "title": PRESETS[preset]["title"],
        "truth": PRESETS[preset]["truth"],
        "truth_short": PRESETS[preset]["truth_short"],
        "generations_planned": generations,
        "limit": limit,
        "models": describe(),
        "status": "running",
        "created": datetime.now(timezone.utc).isoformat(),
    }


def run(run: dict, store=None) -> dict:
    store = store or get_store()
    store.save_run(run)
    preset, limit = run["preset"], run["limit"]
    events = PRESETS[preset]["events"]

    # generation 0: the eyewitness account, scored so the chart starts at the truth
    archive = genesis_archive(preset)
    g0 = {"gen": 0, "event": "The original event", "summary": PRESETS[preset]["genesis"],
          "drafts": {}, "archive": archive, "chars_lost": 0, "trace": []}
    g0["score"] = evaluate(preset, 0, archive)
    store.save_generation(run["id"], g0)

    try:
        for gen in range(1, run["generations_planned"] + 1):
            t = time.time()
            event = events[(gen - 1) % len(events)]
            g = run_generation(RUNS / run["id"] / "world" / f"gen_{gen:03d}", gen, archive, event, preset, limit)
            g["score"] = evaluate(preset, gen, g["archive"])
            g["seconds"] = round(time.time() - t, 1)
            store.save_generation(run["id"], g)
            archive = g["archive"] or {"empty.md": "(nothing survived)"}
            print(f"gen {gen}: belief={g['score']['belief']:.2f} practice={g['score']['practice']:.2f} myth={g['score']['myth']:.2f} | {g['score']['rule']}")
        run["status"] = "done"
    except Exception as e:  # keep partial results; the UI shows how far it got
        run["status"] = "error"
        run["error"] = f"{type(e).__name__}: {e}"[:500]
        raise
    finally:
        store.save_run(run)
    return run


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", default="village", choices=list(PRESETS))
    ap.add_argument("--generations", type=int, default=8)
    ap.add_argument("--limit", type=int, default=1200, help="max characters the archive may keep")
    a = ap.parse_args()
    r = new_run(a.preset, a.generations, a.limit)
    print("run", r["id"])
    run(r)
