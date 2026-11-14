"""Social network analysis of the agents' posts (Arlequin Track 2: content + connectivity).

Person A's social rounds produce posts (SocialPost: id, round, author, kind, target, text, sentiment). This module
turns them into who-reacted-to-whom, then combines what was said (themes) with how it travelled (graph):

  influencers   PageRank on reply/repost edges: whose posts drew the most reactions, weighted by who reacted
  communities   groups of agents that mostly react to each other (modularity)
  cascades      each original post's thread: size, depth, reach, how many other communities it reached
  themes        which topics stayed inside one community and which crossed between them
  by_model      do Claude / GPT / Gemini agents post, react and spread differently?

    from b2a import network
    social = network.analyze(view)   # -> b2a.contract.Social (dict via .model_dump())
"""
from __future__ import annotations

from collections import Counter, defaultdict

import networkx as nx
from pydantic import BaseModel, Field

from .contract import Cascade, Community, GraphEdge, GraphNode, Social, SocialPost, ThemeSpread
from .evals import _tokens


def _mean(xs: list[float]) -> float:
    return round(sum(xs) / len(xs), 3) if xs else 0.0


def pagerank(g: nx.DiGraph, alpha: float = 0.85, iters: int = 100, tol: float = 1e-10) -> dict[str, float]:
    """Weighted PageRank by power iteration. Pure Python (nx.pagerank needs numpy/scipy); our graphs are tiny."""
    nodes = list(g.nodes)
    n = len(nodes)
    if not n:
        return {}
    out_w = {u: sum(d.get("weight", 1) for _, _, d in g.out_edges(u, data=True)) for u in nodes}
    pr = {u: 1 / n for u in nodes}
    for _ in range(iters):
        dangling = alpha * sum(pr[u] for u in nodes if not out_w[u]) / n
        new = {u: (1 - alpha) / n + dangling for u in nodes}
        for u, v, d in g.edges(data=True):
            new[v] += alpha * pr[u] * d.get("weight", 1) / out_w[u]
        if sum(abs(new[u] - pr[u]) for u in nodes) < tol:
            return new
        pr = new
    return pr


# ---------------------------------------------------------------- threads

def _roots(posts: list[SocialPost]) -> dict[str, str]:
    """post id -> id of the original post its thread started from."""
    by_id = {p.id: p for p in posts}
    out = {}
    for p in posts:
        cur, seen = p, set()
        while cur.target and cur.target in by_id and cur.id not in seen:
            seen.add(cur.id)
            cur = by_id[cur.target]
        out[p.id] = cur.id
    return out


def _depths(posts: list[SocialPost]) -> dict[str, int]:
    by_id = {p.id: p for p in posts}
    out = {}
    for p in posts:
        d, cur, seen = 0, p, set()
        while cur.target and cur.target in by_id and cur.id not in seen:
            seen.add(cur.id)
            d += 1
            cur = by_id[cur.target]
        out[p.id] = d
    return out


# ---------------------------------------------------------------- themes (content)

class _Label(BaseModel):
    index: int
    theme: str = Field(description="2-6 words, concrete, e.g. 'shrinks in the dryer', 'worth it vs disposables'")


class _Labels(BaseModel):
    labels: list[_Label]


LABEL_PROMPT = """Give each social media post about a product a short theme label. Posts about the same point must get
exactly the same label. Use 2-6 concrete words.

{posts}"""


def label_themes(roots: list[SocialPost], judge: str = "auto") -> dict[str, str]:
    """Theme per original post (replies and reposts inherit their thread's theme)."""
    if not roots:
        return {}
    if judge in ("auto", "llm"):
        try:
            from .models import fast
            r: _Labels = fast().with_structured_output(_Labels).invoke(
                LABEL_PROMPT.format(posts="\n".join(f"{i}. {p.text}" for i, p in enumerate(roots))))
            got = {l.index: l.theme.strip().lower() for l in r.labels if 0 <= l.index < len(roots)}
            if len(got) == len(roots):
                return {roots[i].id: t for i, t in got.items()}
        except Exception:
            if judge == "llm":
                raise
    # keyword fallback: posts sharing half their content words get one theme, labelled by the first post's words
    out: dict[str, str] = {}
    reps: list[tuple[set[str], str]] = []
    for p in roots:
        t = _tokens(p.text)
        for rt, label in reps:
            if t and rt and len(t & rt) / min(len(t), len(rt)) >= 0.5:
                out[p.id] = label
                break
        else:
            label = " ".join(p.text.split()[:6]).strip(".,!?:;").lower()
            reps.append((t, label))
            out[p.id] = label
    return out


# ---------------------------------------------------------------- analysis

def analyze(view_or_posts: dict | list, personas: list[dict] | None = None, judge: str = "auto") -> Social:
    if isinstance(view_or_posts, dict):
        social = view_or_posts.get("social") or {}
        raw = social.get("posts") if isinstance(social, dict) else None
        raw = raw if raw is not None else view_or_posts.get("posts", [])
        personas = personas if personas is not None else view_or_posts.get("personas", [])
    else:
        raw = view_or_posts
    posts = [p if isinstance(p, SocialPost) else SocialPost(**p) for p in raw or []]
    info = {p["id"]: p for p in personas or []}
    by_id = {p.id: p for p in posts}
    authors = {p.author for p in posts}

    # graph: edge from the agent who reacted to the agent whose post they reacted to
    g = nx.DiGraph()
    for aid in set(info) | authors:
        g.add_node(aid)
    edge_kind: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for p in posts:
        if p.kind in ("reply", "repost") and p.target in by_id:
            src, dst = p.author, by_id[p.target].author
            if src == dst:
                continue
            w = g[src][dst]["weight"] + 1 if g.has_edge(src, dst) else 1
            g.add_edge(src, dst, weight=w)
            edge_kind[(src, dst)][p.kind] += 1

    pr = pagerank(g)
    und = g.to_undirected()
    comms = (list(nx.community.greedy_modularity_communities(und, weight="weight")) if und.number_of_edges()
             else [{n} for n in und.nodes])
    comm_of = {n: i for i, c in enumerate(sorted(comms, key=lambda c: (-len(c), sorted(c)))) for n in c}

    roots = _roots(posts)
    depth = _depths(posts)
    originals = [p for p in posts if roots[p.id] == p.id]
    theme_of_root = label_themes(originals, judge)
    theme = {p.id: theme_of_root.get(roots[p.id], "") for p in posts}

    sent_by: dict[str, list[float]] = defaultdict(list)
    for p in posts:
        sent_by[p.author].append(p.sentiment)
    received = Counter(by_id[p.target].author for p in posts if p.kind in ("reply", "repost") and p.target in by_id and by_id[p.target].author != p.author)
    written = Counter(p.author for p in posts)

    def name(aid: str) -> str:
        return info.get(aid, {}).get("name", aid)

    nodes = [GraphNode(id=n, label=name(n), archetype=info.get(n, {}).get("archetype", ""), sentiment=_mean(sent_by[n]),
                       centrality=round(pr.get(n, 0.0), 4), community=comm_of.get(n, 0), model=info.get(n, {}).get("model", ""),
                       layer=info.get(n, {}).get("layer"), posts=written[n], reactions_received=received[n])
             for n in sorted(g.nodes, key=lambda n: -pr.get(n, 0))]
    edges = [GraphEdge(source=s, target=t, kind=edge_kind[(s, t)].most_common(1)[0][0], weight=d["weight"]) for s, t, d in g.edges(data=True)]

    # cascades: one per original post
    thread: dict[str, list[SocialPost]] = defaultdict(list)
    for p in posts:
        thread[roots[p.id]].append(p)
    cascades = []
    for r in originals:
        rs = [p for p in thread[r.id] if p.id != r.id]
        reactors = {p.author for p in rs} - {r.author}
        cascades.append(Cascade(post_id=r.id, author=r.author, text=r.text, theme=theme[r.id], size=len(rs),
                                depth=max([depth[p.id] for p in rs], default=0), reach=len(reactors),
                                communities_reached=len({comm_of.get(a) for a in reactors} - {comm_of.get(r.author)}),
                                sentiment=_mean([p.sentiment for p in thread[r.id]])))
    cascades.sort(key=lambda c: (-c.size, -c.reach, -c.communities_reached))

    # themes: content x connectivity
    tposts: dict[str, list[SocialPost]] = defaultdict(list)
    for p in posts:
        if theme[p.id]:
            tposts[theme[p.id]].append(p)
    themes = []
    for t, ps in tposts.items():
        cs = {comm_of.get(p.author) for p in ps}
        themes.append(ThemeSpread(theme=t, posts=len(ps), agents=len({p.author for p in ps}), communities=len(cs),
                                  sentiment=_mean([p.sentiment for p in ps]), crosses_communities=len(cs) > 1))
    themes.sort(key=lambda x: (-x.communities, -x.posts))

    communities = []
    for i in sorted(set(comm_of.values())):
        mem = sorted(n for n, c in comm_of.items() if c == i)
        communities.append(Community(id=i, members=mem, sentiment=_mean([s for m in mem for s in sent_by[m]]),
                                     archetypes=sorted({info.get(m, {}).get("archetype", "") for m in mem} - {""}),
                                     models=sorted({info.get(m, {}).get("model", "") for m in mem} - {""})))

    by_model: dict[str, dict] = {}
    for n in nodes:
        if not n.model:
            continue
        m = by_model.setdefault(n.model, {"agents": 0, "posts": 0, "reactions_received": 0, "sentiments": []})
        m["agents"] += 1
        m["posts"] += n.posts
        m["reactions_received"] += n.reactions_received
        m["sentiments"] += sent_by[n.id]
    for m in by_model.values():
        m["sentiment"] = _mean(m.pop("sentiments"))

    top = [n.id for n in nodes if n.reactions_received > 0][:3] or [n.id for n in nodes[:1]]
    return Social(posts=posts, nodes=nodes, edges=edges, top_influencers=top,
                  summary=_summary(cascades, themes, nodes, communities, name),
                  cascades=cascades, themes=themes, communities=communities, by_model=by_model)


def _summary(cascades: list[Cascade], themes: list[ThemeSpread], nodes: list[GraphNode], communities: list[Community], name) -> str:
    if not cascades:
        return "No posts yet."
    out = []
    c = cascades[0]
    if c.size:
        where = f" across {c.communities_reached + 1} groups" if c.communities_reached else " within one group"
        tone = "negative" if c.sentiment < -0.15 else "positive" if c.sentiment > 0.15 else "mixed"
        out.append(f"{name(c.author)}'s post about \"{c.theme or c.text[:60]}\" spread furthest: {c.size} replies/reposts "
                   f"from {c.reach} customers{where} ({tone} overall).")
    else:
        out.append("Nobody reacted to anyone else's posts.")
    cross = [t.theme for t in themes if t.crosses_communities]
    stay = [t.theme for t in themes if not t.crosses_communities and t.posts > 1]
    if cross:
        out.append(f"Crossed between groups: {', '.join(cross[:3])}.")
    if stay:
        out.append(f"Stayed inside one group: {', '.join(stay[:3])}.")
    lead = next((n for n in nodes if n.reactions_received), None)
    if lead:
        out.append(f"Most influential: {lead.label}{f' ({lead.archetype})' if lead.archetype else ''}"
                   f"{f', played by {lead.model}' if lead.model else ''}.")
    return " ".join(out)
