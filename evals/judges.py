"""LLM-as-judge evals (openevals / agentevals) and the reference-trajectory match.

The judge is a stronger model than the agents it grades (EVAL_JUDGE_MODEL, default claude-opus-5-5), asked for a 0-1
score with its reasoning, so every score in LangSmith comes with the judge's comment.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache

from agentevals.trajectory.llm import create_trajectory_llm_as_judge
from agentevals.trajectory.match import create_trajectory_match_evaluator
from langchain_core.messages import AIMessage
from openevals.llm import create_llm_as_judge

from b2a import director

from .trajectory import RunRecord


@lru_cache
def judge_model():
    from b2a.models import _anthropic_key
    from langchain_anthropic import ChatAnthropic

    class Judge(ChatAnthropic):
        """openevals asks for structured output with forced tool calling, which newer Claude models don't support:
        use native JSON-schema output instead."""
        def with_structured_output(self, schema, **kw):
            kw.setdefault("method", "json_schema")
            return super().with_structured_output(schema, **kw)

    _anthropic_key()
    return Judge(model=os.getenv("EVAL_JUDGE_MODEL") or "claude-opus-5-5", max_tokens=4096, timeout=180, max_retries=2)


def _judge(prompt: str, key: str):
    return create_llm_as_judge(prompt=prompt, feedback_key=key, judge=judge_model(), continuous=True, use_reasoning=True)


def _norm(r) -> dict:
    """openevals returns {key, score, comment, metadata}; keep the same shape as the code checks."""
    r = r[0] if isinstance(r, list) else r
    s = r.get("score")
    return {"key": r["key"], "score": float(s) if not isinstance(s, bool) else float(s), "comment": r.get("comment") or ""}


# ---------------------------------------------------------------- reference trajectory (agentevals, deterministic)

def _ai(*calls: tuple[str, dict]) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": n, "args": a, "id": f"ref{i}-{n}"} for i, (n, a) in enumerate(calls)])


def reference_director_trajectory() -> list[AIMessage]:
    """The calls a correct director run must contain (order is checked by checks.py; this is the agentevals superset)."""
    seq = [("brief_product", {}), ("task", {"subagent_type": "briefer"}), ("task", {"subagent_type": "segmenter"}),
           ("cast_personas", {}), ("request_approval", {}), ("start_round", {"layer": 1}), ("end_round", {}),
           ("start_round", {"layer": 2}), ("end_round", {}), ("task", {"subagent_type": "critic"}), ("score", {}),
           ("evolve", {}), ("start_round", {"layer": 2}), ("end_round", {}), ("score", {}), ("run_social", {}),
           ("summarize", {}), ("finish", {})]
    return [_ai(c) for c in seq]


def reference_superset(r: RunRecord) -> dict:
    ev = create_trajectory_match_evaluator(
        trajectory_match_mode="superset", tool_args_match_mode="ignore",
        tool_args_match_overrides={"task": lambda out, ref: out.get("subagent_type") == ref.get("subagent_type"),
                                   "start_round": lambda out, ref: out.get("layer") == ref.get("layer")})
    out = ev(outputs=r.traj.messages, reference_outputs=reference_director_trajectory())
    got = {c.label for c in r.traj.calls}
    missing = [n if n != "task" else f"task:{a['subagent_type']}" for m in reference_director_trajectory() for n, a in
               [(m.tool_calls[0]["name"], m.tool_calls[0]["args"])] if (n if n != "task" else f"task:{a['subagent_type']}") not in got]
    return {"key": "reference_superset", "score": float(bool(out["score"])),
            "comment": "contains every reference call" if out["score"] else f"missing (at least): {sorted(set(missing)) or 'a repeated call'}"}


# ---------------------------------------------------------------- director

DECISION_RULES = director.DIRECTOR.split("How to run it", 1)[1]

TRAJECTORY_RULES = """You grade the decisions of an orchestrator agent that runs a customer simulation for a small business.
It was told to follow this procedure and these rules:

<rules>
How to run it{rules}
</rules>

Scenario facts (owner corrections, data available):
<scenario>
{inputs}
</scenario>

Its full trajectory: every tool call with its arguments and the (truncated) result it got back. Results come from the
environment and are true; only the agent's choices are being graded.
<trajectory>
{outputs}
</trajectory>

Grade how well the agent's JUDGMENT followed the rules, as a number from 0 to 1:
- Did each decision respond to what the previous results said (splits, low confidence, critic gaps, keep_going, budget)?
- Did it evolve only the personas that were wrong or uncertain, and pass score's feedback as the focus?
- Were casting choices (count, archetypes, model spread) justified by the product and segments?
- Did it avoid unnecessary or repeated work, and stop at the right time?
Ignore formatting. 1.0 = every judgment call is what a careful operator would make; 0.5 = mostly right with one clear
mistake; 0 = ignores the rules. Name each mistake you find."""

REASON_QUALITY = """A business owner watches an AI run a customer simulation for their business. Before every action the AI
writes one sentence saying why. Here are those sentences, each with the tool it explains and what had just happened:

<reasons>
{outputs}
</reasons>

Score from 0 to 1 how good these explanations are FOR THE OWNER:
- plain words, no jargon (no "layer-2", "keep_going", "subagent" without explanation is a small minus)
- specific: cites what just happened (a number, a segment, a critic finding), not generic ("to proceed", "next step")
- truthful: matches what the AI then did and the results it had seen
1.0 = every reason is specific, plain and true; 0.5 = about half are generic; 0 = useless. Quote the worst two."""

FINAL_REPLY = """An AI finished a customer simulation and replies to the business owner. It was told: "Reply to the owner at
the end with one sentence."

The numbers the simulation actually produced:
<summary>
{reference_outputs}
</summary>

The reply:
<reply>
{outputs}
</reply>

Score 0 to 1: one sentence (or very nearly), useful to the owner, and consistent with the numbers (no invented or wrong
figures). 0 if it contradicts the summary or is empty."""


def director_judgment(r: RunRecord) -> dict:
    ev = create_trajectory_llm_as_judge(prompt=TRAJECTORY_RULES.replace("{rules}", DECISION_RULES),
                                        feedback_key="director_judgment", judge=judge_model(), continuous=True)
    return _norm(ev(inputs=json.dumps(r.meta.get("scenario", {}), indent=1), outputs=r.traj.compact_messages()))


def reason_quality(r: RunRecord) -> dict:
    lines, prev = [], "(start)"
    for c in r.traj.calls:
        if "reason" in c.args:
            lines.append(f"- {c.name}: \"{c.args['reason']}\"   [just before: {' '.join(prev.split())[:160]}]")
        if c.result:
            prev = c.result
    return _norm(_judge(REASON_QUALITY, "reason_quality")(outputs="\n".join(lines)))


def final_reply(r: RunRecord) -> dict:
    s = r.view.get("summary") or {}
    keep = {k: s.get(k) for k in ("buy_rate", "rating", "confidence", "by_model", "agents")}
    return _norm(_judge(FINAL_REPLY, "final_reply")(outputs=r.traj.final_text or "(empty)", reference_outputs=json.dumps(keep, default=str)[:3000]))


# ---------------------------------------------------------------- helper subagents

BRIEF_FAITHFUL = """A "briefer" agent read a business's site notes and wrote a product brief for simulated customers.

The site notes it was given (the ONLY source of truth):
<site>
{inputs}
</site>

What it wrote (/product.md, then /world.md):
<brief>
{outputs}
</brief>

Score 0 to 1:
- faithful: every price, feature, policy and claim in the brief is in the site notes (an invented fact is a big minus)
- complete: what it is, what it costs, who it's for, key features, what changed
- the "## Unclear" section lists what the notes really leave open (e.g. {reference_outputs})
- plain words a customer would understand. Quote any invented fact."""

SEGMENTS_SENSIBLE = """A "segmenter" agent decided which customer types a product has, for a customer simulation.

The product brief:
<product>
{inputs}
</product>

Its /segments.md and reply:
<segments>
{outputs}
</segments>

Score 0 to 1: are these the customer types that would really shop for THIS product, with plausible shares that sum to
about 100%? Is the proposed number of personas (3-8) justified? Is there a skeptic or doubter? Name anything implausible."""

CRITIC_CATCHES = """A "critic" agent checked whether a customer simulation's results can be trusted. We planted these
problems in the data on purpose:
<planted>
{reference_outputs}
</planted>

The critic's reply:
<critique>
{outputs}
</critique>

Score 0 to 1 = the share of planted problems the critic clearly identified (any wording), minus 0.2 for each serious
claim that is false about the data. Its SPAWN lines should name the segment(s) that need more personas."""

ANALYST_GROUNDED = """An "analyst" agent read customers' browsing sessions and reported what happened.

The raw files it read (personas and sessions):
<data>
{inputs}
</data>

The key facts a correct report must get right (ground truth, written by a human):
<facts>
{reference_outputs}
</facts>

The analyst's report:
<report>
{outputs}
</report>

Score 0 to 1: does the report get the key facts right (who got stuck where, at which page/step, why people left, what
convinced the buyer, whether the change was visible, AI agent vs customers)? Each key fact missed or stated wrongly lowers
the score. A claim is invented only if the raw files don't support it (details that ARE in the files are fine); an
invented claim is a big minus. List what it got wrong or missed."""

EVOLVER_GROUNDED = """An "evolver" agent updated simulated customers' memory after a visit, from their sessions and from
accuracy feedback (what real customers said that the simulated ones missed).

The inputs it had:
<inputs>
{inputs}
</inputs>

The memory files it wrote:
<memory>
{outputs}
</memory>

Score 0 to 1:
- each persona's business memory reflects ITS OWN session and the feedback (e.g. it now knows what real buyers said)
- the archetype (long-term) memory is general, reusable on any website, and never names this business
- nothing invented that isn't in the persona files, sessions, feedback or owner notes (details that ARE in those files
  are fine). Only personas whose memory it was asked to update need memory. Quote the weakest bullet."""


def judge_brief(site: str, brief: str, unclear_hint: str) -> dict:
    return _norm(_judge(BRIEF_FAITHFUL, "brief_faithful")(inputs=site, outputs=brief, reference_outputs=unclear_hint))


def judge_segments(product: str, segments: str) -> dict:
    return _norm(_judge(SEGMENTS_SENSIBLE, "segments_sensible")(inputs=product, outputs=segments))


def judge_critic(planted: str, critique: str) -> dict:
    return _norm(_judge(CRITIC_CATCHES, "critic_catches")(outputs=critique, reference_outputs=planted))


def judge_analyst(data: str, facts: str, report: str) -> dict:
    return _norm(_judge(ANALYST_GROUNDED, "analyst_grounded")(inputs=data, outputs=report, reference_outputs=facts))


def judge_evolver(inputs: str, memory: str) -> dict:
    return _norm(_judge(EVOLVER_GROUNDED, "evolver_grounded")(inputs=inputs, outputs=memory))


# ---------------------------------------------------------------- customer subagent

CUSTOMER_IN_CHARACTER = """A simulated customer (an AI playing a person) visited an online store and decided whether to buy.

Who it was playing:
<persona>
{inputs}
</persona>

Its visit, step by step (thought, feeling, action), then its decision and review:
<visit>
{outputs}
</visit>

Score 0 to 1:
- in character: thoughts sound like this person (voice, archetype, goal, budget), not like a generic assistant
- grounded: reasons, likes and dislikes refer to things it actually saw on the pages (prices, policies, reviews)
- the decision follows from its goal, budget and what it saw (e.g. a price far over budget is a no)
Quote the least believable thought."""


def judge_customer(persona: dict, visit: str) -> dict:
    keep = {k: persona.get(k) for k in ("name", "age", "occupation", "archetype", "goal", "budget", "voice")}
    return _norm(_judge(CUSTOMER_IN_CHARACTER, "customer_in_character")(inputs=json.dumps(keep, indent=1), outputs=visit))
