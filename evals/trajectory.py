"""An agent's message history as a flat list of tool calls (with their results) that checks can reason about."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

CUSTOMER_NAME = re.compile(r"^[ap]\d+-")  # director subagents that are customers: p3-maya, a1-claude-agent


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content
                        if not isinstance(b, dict) or b.get("type") == "text")
    return json.dumps(content) if content is not None else ""


@dataclass
class Call:
    name: str
    args: dict
    id: str
    i: int             # position among all tool calls
    turn: int          # which AI message made it (calls in one turn run in parallel)
    result: str = ""
    error: bool = False

    @property
    def label(self) -> str:
        """`task` calls are labelled by the subagent they start: task:critic, task:p3-maya."""
        return f"task:{self.args.get('subagent_type', '?')}" if self.name == "task" else self.name

    @property
    def to_customer(self) -> bool:
        return self.name == "task" and bool(CUSTOMER_NAME.match(str(self.args.get("subagent_type", ""))))


@dataclass
class Trajectory:
    messages: list[BaseMessage]
    calls: list[Call] = field(default_factory=list)
    turns: list[list[Call]] = field(default_factory=list)  # one entry per AI message
    final_text: str = ""
    tokens: dict = field(default_factory=lambda: {"input": 0, "output": 0})

    @classmethod
    def from_messages(cls, messages: list[BaseMessage]) -> "Trajectory":
        t = cls(messages=list(messages))
        by_id: dict[str, Call] = {}
        for m in messages:
            if isinstance(m, AIMessage):
                turn = []
                for tc in m.tool_calls or []:
                    c = Call(tc["name"], dict(tc.get("args") or {}), tc.get("id") or "", len(t.calls), len(t.turns))
                    t.calls.append(c)
                    turn.append(c)
                    by_id[c.id] = c
                t.turns.append(turn)
                u = getattr(m, "usage_metadata", None) or {}
                t.tokens["input"] += u.get("input_tokens", 0)
                t.tokens["output"] += u.get("output_tokens", 0)
                if text_of(m.content).strip() and not m.tool_calls:
                    t.final_text = text_of(m.content).strip()
            elif isinstance(m, ToolMessage) and m.tool_call_id in by_id:
                c = by_id[m.tool_call_id]
                c.result = text_of(m.content)
                c.error = getattr(m, "status", "success") == "error"
        return t

    def of(self, *names: str) -> list[Call]:
        """Calls by tool name or label (e.g. "score", "task:critic")."""
        return [c for c in self.calls if c.name in names or c.label in names]

    def first(self, name: str) -> Call | None:
        return next(iter(self.of(name)), None)

    def labels(self, names: tuple[str, ...] | None = None) -> list[str]:
        return [c.label for c in self.calls if names is None or c.name in names]

    def compact_messages(self, limit: int = 400) -> list[BaseMessage]:
        """The same trajectory with long texts cut, for a trajectory judge (keeps tool calls and their pairing)."""
        out = []
        for m in self.messages:
            if isinstance(m, AIMessage):
                calls = [{**tc, "args": {k: v for k, v in (tc.get("args") or {}).items() if k != "todos"}} for tc in m.tool_calls or []]
                out.append(AIMessage(content=text_of(m.content)[:limit], tool_calls=calls, id=m.id))
            elif isinstance(m, ToolMessage):
                out.append(ToolMessage(content=" ".join(text_of(m.content).split())[:limit], tool_call_id=m.tool_call_id, name=m.name))
            elif getattr(m, "type", "") == "human":
                out.append(m)
        return out

    def compact(self, limit: int = 300) -> str:
        """A readable transcript for an LLM judge: every tool call with its args and (truncated) result."""
        out = []
        for c in self.calls:
            args = {k: v for k, v in c.args.items() if k not in ("todos",)}
            res = " ".join(c.result.split())[:limit]
            out.append(f"[{c.i}] (turn {c.turn}) {c.label} {json.dumps(args, default=str)[:400]}\n     -> {res}")
        if self.final_text:
            out.append(f"FINAL REPLY: {self.final_text[:600]}")
        return "\n".join(out)


@dataclass
class RunRecord:
    """What a check gets: the trajectory, plus what the run left behind (job view, files written)."""
    traj: Trajectory
    view: dict = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)
    meta: dict = field(default_factory=dict)  # scenario facts the checks need (owner feedback given, persona, ...)
