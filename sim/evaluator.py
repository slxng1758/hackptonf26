"""The hidden evaluator. It is the only part of the system that knows the truth.

It reads a generation's archive and scores two things separately, because they can come apart:
  - belief: does the archive still carry the true cause?
  - practice: would people following this archive still do the thing that works?
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .models import evaluator_model
from .presets import PRESETS


class Score(BaseModel):
    belief: float = Field(ge=0, le=1, description="How much of the TRUE cause and mechanism survives, 0 = gone or replaced by a false cause, 1 = fully intact")
    practice: float = Field(ge=0, le=1, description="How likely people following this archive would still perform the practice that works, 0 = abandoned or replaced, 1 = clearly required")
    short: str = Field(default="", description="The current rule in at most 8 plain words, like a proverb or a sign on the wall")
    rule: str = Field(description="The community's current rule about this practice, quoted or closely paraphrased from the archive, max 25 words")
    reason: str = Field(description="The reason the archive gives for the rule, quoted or closely paraphrased, max 25 words")
    myth: float = Field(ge=0, le=1, description="How much the explanation has turned supernatural, ritual, authority-based or story-based instead of causal, 0 = purely causal, 1 = fully mythic")
    drift: str = Field(description="One sentence: what changed compared with the truth, in plain words")
    false_beliefs: list[str] = Field(default_factory=list, description="Specific claims in the archive that are false or unsupported, max 3, short")


PROMPT = """You are an evaluator outside a simulated civilization. You know the ground truth. The civilization does not.

GROUND TRUTH:
{truth}

THE CIVILIZATION'S ARCHIVE AFTER GENERATION {gen}:
{archive}

Score the archive. Be strict and literal. Judge only what is written, not what a smart reader could guess.
If the archive says nothing about the practice, practice is 0."""


def evaluate(preset_key: str, gen: int, archive: dict[str, str]) -> dict:
    text = "\n\n".join(f"--- {name} ---\n{body}" for name, body in archive.items()) or "(the archive is empty)"
    model = evaluator_model().with_structured_output(Score, method="json_schema")
    score: Score = model.invoke(PROMPT.format(truth=PRESETS[preset_key]["truth"], gen=gen, archive=text))
    return score.model_dump()
