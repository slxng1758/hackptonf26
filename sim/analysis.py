"""Content x connectivity: which messages broke, and where in the network they were born.

Works on any run in the epi format (simulated now; a real propagation dataset can be mapped to the same shape).
  content      = what a variant says: did it keep the protective action (practice), did its reason turn to myth
  connectivity = where its author sits: betweenness (bridges between groups), degree, and how many groups it reached
The insight is the interaction: harmful variants born on bridges travel further than harmful variants born inside a group.
"""
from __future__ import annotations

import json
import statistics
from collections import deque
from pathlib import Path

EPI = Path(__file__).resolve().parent.parent / "runs" / "epi"


def betweenness(n: int, edges: list[list[int]]) -> list[float]:
    """Brandes' algorithm, unweighted. O(V*E): fine for a few hundred people."""
    adj = [[] for _ in range(n)]
    for a, b in edges:
        adj[a].append(b)
        adj[b].append(a)
    cb = [0.0] * n
    for s in range(n):
        stack, pred = [], [[] for _ in range(n)]
        sigma, dist = [0] * n, [-1] * n
        sigma[s], dist[s] = 1, 0
        q = deque([s])
        while q:
            v = q.popleft()
            stack.append(v)
            for w in adj[v]:
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    q.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)
        delta = [0.0] * n
        while stack:
            w = stack.pop()
            for v in pred[w]:
                delta[v] += sigma[v] / sigma[w] * (1 + delta[w])
            if w != s:
                cb[w] += delta[w]
    top = max(cb) or 1
    return [c / top for c in cb]


def analyze(run: dict) -> dict:
    people, edges, variants, frames = run["people"], run["edges"], run["variants"], run["frames"]
    n = len(people)
    bet = betweenness(n, edges)
    deg = [0] * n
    for a, b in edges:
        deg[a] += 1
        deg[b] += 1

    # reach of each variant: peak believers, and how many groups it touched
    peak = [0] * len(variants)
    groups = [set() for _ in variants]
    for f in frames:
        counts = {}
        for i, v in enumerate(f["b"]):
            if v is None:
                continue
            counts[v] = counts.get(v, 0) + 1
            groups[v].add(people[i]["village"])
        for v, c in counts.items():
            peak[v] = max(peak[v], c)

    rows = []
    for v in variants:
        if v["parent"] is None or v["person"] is None or v["person"] < 0:
            continue
        p = v["person"]
        rows.append({
            "id": v["id"], "text": v["text"], "role": v["role"], "day": v["day"],
            "harmful": v["practice"] < 0.6 or v["myth"] >= 0.5,
            "practice": v["practice"], "myth": v["myth"],
            "betweenness": round(bet[p], 3), "degree": deg[p],
            "reach": peak[v["id"]], "groups": len([g for g in groups[v["id"]] if g >= 0]),
        })

    def avg(xs):
        return round(statistics.mean(xs), 2) if xs else 0.0

    bridge_cut = sorted(bet, reverse=True)[max(0, n // 10 - 1)]  # top 10% of people by betweenness = "bridges"
    on_bridge = [r for r in rows if r["betweenness"] >= bridge_cut]
    off_bridge = [r for r in rows if r["betweenness"] < bridge_cut]
    harm = [r for r in rows if r["harmful"]]
    cells = {
        "harmful_bridge": avg([r["reach"] for r in on_bridge if r["harmful"]]),
        "harmful_inside": avg([r["reach"] for r in off_bridge if r["harmful"]]),
        "safe_bridge": avg([r["reach"] for r in on_bridge if not r["harmful"]]),
        "safe_inside": avg([r["reach"] for r in off_bridge if not r["harmful"]]),
    }
    by_role = {}
    for r in rows:
        d = by_role.setdefault(r["role"], {"variants": 0, "harmful": 0, "betweenness": []})
        d["variants"] += 1
        d["harmful"] += int(r["harmful"])
        d["betweenness"].append(r["betweenness"])
    roles = sorted(({"role": k, "variants": d["variants"], "harmful": d["harmful"], "betweenness": avg(d["betweenness"])} for k, d in by_role.items()),
                   key=lambda x: (-x["harmful"], -x["betweenness"]))

    findings = []
    if harm:
        worst = max(harm, key=lambda r: r["reach"])
        findings.append(f"The most-spread harmful version was told by a {worst['role']} (bridge score {worst['betweenness']}), "
                        f"reaching {worst['reach']} people across {worst['groups']} groups: \"{worst['text']}\"")
    if cells["harmful_bridge"] and cells["harmful_inside"]:
        ratio = cells["harmful_bridge"] / max(cells["harmful_inside"], 0.1)
        findings.append(f"Harmful versions born on bridges reached {cells['harmful_bridge']} people on average, "
                        f"versus {cells['harmful_inside']} when born inside one group ({ratio:.1f}x).")
    if roles:
        r0 = roles[0]
        findings.append(f"{r0['role']}s created {r0['harmful']} of {r0['variants']} of their versions in a harmful form.")

    return {
        "run": run["id"], "people": n, "variants": len(rows), "harmful": len(harm),
        "bridge_cut": round(bridge_cut, 3), "reach": cells, "roles": roles, "findings": findings,
        "rows": sorted(rows, key=lambda r: -r["reach"])[:40],
        "bridges": [i for i in range(n) if bet[i] >= bridge_cut],
    }


def analyze_id(run_id: str) -> dict | None:
    p = EPI / f"{Path(run_id).name}.json"
    return analyze(json.loads(p.read_text())) if p.exists() else None


if __name__ == "__main__":
    import sys
    out = analyze_id(sys.argv[1])
    print(json.dumps({k: v for k, v in out.items() if k not in ("rows", "bridges")}, indent=2))
