"""The market test: real AI shopping agents choose between your listing and your competitors' for each buyer task.

Orders are shuffled per trial to cancel position bias. Wins are weighted by how much of the customer base each segment is.
"""
from __future__ import annotations

import random
import re
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel, Field

from .models import shoppers


class Choice(BaseModel):
    pick: int = Field(description="the number of the option you choose")
    reason: str = Field(description="one sentence: why this one")
    missing: str = Field(description="one sentence: what the options you rejected failed to tell you, if anything")


SHOP = """You are an AI shopping agent acting for a customer. The customer asked you:
"{task}"

These are the options you found:
{listings}

Choose the single best option for this customer, using only what the options say. Be decisive."""


def to_confirm(listing: str) -> list[str]:
    return [m.strip(" .;,") for m in re.findall(r"\[confirm\]\s*([^.\n\[]+)", listing)]


def clean(listing: str) -> str:
    return re.sub(r"\s*\[confirm\]\s*", " ", listing).strip()


def run(listing: str, competitors: list[str], segments: list[dict], orders: int = 2, seed: int = 0, on_result=None) -> dict:
    rng = random.Random(seed)
    models = shoppers()
    ours = clean(listing)
    jobs = []
    for si, seg in enumerate(segments):
        for ti, task in enumerate(seg["tasks"]):
            for _ in range(orders):
                for name in models:
                    items = [("ours", ours)] + [(f"c{i}", c) for i, c in enumerate(competitors)]
                    rng.shuffle(items)
                    jobs.append({"shopper": name, "segment": si, "task": task, "items": items})

    def one(j):
        listings = "\n".join(f"{i + 1}. {text}" for i, (_, text) in enumerate(j["items"]))
        try:
            c: Choice = models[j["shopper"]].with_structured_output(Choice).invoke(SHOP.format(task=j["task"], listings=listings))
            picked = j["items"][max(1, min(len(j["items"]), c.pick)) - 1][0]
            r = {"shopper": j["shopper"], "segment": j["segment"], "task": j["task"], "picked": picked, "reason": c.reason, "missing": c.missing}
        except Exception as e:
            r = {"shopper": j["shopper"], "segment": j["segment"], "task": j["task"], "picked": "error", "reason": type(e).__name__, "missing": ""}
        if on_result:
            on_result(r)
        return r

    with ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(one, jobs))

    ok = [r for r in results if r["picked"] != "error"]
    seg_rows = []
    weighted = 0.0
    for si, seg in enumerate(segments):
        rs = [r for r in ok if r["segment"] == si]
        rate = sum(r["picked"] == "ours" for r in rs) / max(1, len(rs))
        weighted += rate * seg["share"]
        seg_rows.append({"segment": seg["name"], "share": seg["share"], "rate": rate, "wins": sum(r["picked"] == "ours" for r in rs), "total": len(rs)})
    by_shopper = {n: {"wins": sum(1 for r in ok if r["shopper"] == n and r["picked"] == "ours"), "total": sum(1 for r in ok if r["shopper"] == n)} for n in models}
    lost_to: dict[str, int] = {}
    for r in ok:
        if r["picked"] != "ours":
            lost_to[r["picked"]] = lost_to.get(r["picked"], 0) + 1
    return {
        "listing": ours, "to_confirm": to_confirm(listing),
        "pick_rate": weighted, "raw_rate": sum(r["picked"] == "ours" for r in ok) / max(1, len(ok)),
        "wins": sum(r["picked"] == "ours" for r in ok), "total": len(ok), "errors": len(results) - len(ok),
        "by_segment": seg_rows, "by_shopper": by_shopper,
        "lost_to": sorted(({"competitor": int(k[1:]), "times": v} for k, v in lost_to.items()), key=lambda x: -x["times"]),
        "results": results,
    }
