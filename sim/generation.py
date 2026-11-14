"""One generation of the civilization, as a deep agent.

Isolation is physical: each generation gets its own folder and a FilesystemBackend rooted there,
so the agents can only see /inherited (what the last archivist kept), /drafts (this generation's
work) and /archive (what this generation leaves behind). The original event is never in reach.
"""
from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend

from .models import villager_model
from .presets import PRESETS, ROLE_ORDER

ARCHIVIST = (
    "You are the archivist. Storage is brutally limited: the archive may hold at most {limit} characters in total, "
    "across all files. Read every draft in /drafts and everything in /inherited, then decide what the next generation "
    "receives. You may merge, shorten, rewrite or drop anything. You MUST finish by calling the save_archive tool with "
    "one to three short files. If it rejects you for being over the limit, cut harder and call it again."
)

ELDER = """You are the council that runs one generation of {people}.
Generation {gen}. This generation lives through: {event}

The only knowledge you have of the past is in /inherited. You have no other memory.

Run the generation in this order and do not skip anyone:
1. Read the files in /inherited.
2. Call each of these helpers with the task tool, one at a time: {roles}. Tell each one the event, and ask them to
   read /inherited and write their own document to /drafts/<their name>.md. Each document should say what the
   community believes and does, and why, in that person's own voice.
3. Call the archivist last. Only the archivist may create the archive, using its save_archive tool.
   Never write anything under /archive yourself.
4. Reply with one sentence describing what the community did during this event.
"""

ROLE_SUFFIX = (
    " You only know what is written in /inherited. Write your document to /drafts/{name}.md, under 900 characters. "
    "Speak as a member of the community, not as an outside observer."
)


def _write_inherited(ws: Path, inherited: dict[str, str]) -> None:
    for d in ("inherited", "drafts", "archive"):
        (ws / d).mkdir(parents=True, exist_ok=True)
    for name, text in inherited.items():
        (ws / "inherited" / Path(name).name).write_text(text)


def _read_dir(d: Path) -> dict[str, str]:
    if not d.exists():
        return {}
    return {p.name: p.read_text() for p in sorted(d.iterdir()) if p.is_file()}


def enforce_limit(files: dict[str, str], limit: int) -> tuple[dict[str, str], int]:
    """Storage is physical. Whatever doesn't fit is lost, cut from the end of each file in turn."""
    total = sum(len(t) for t in files.values())
    lost = max(0, total - limit)
    if lost == 0:
        return files, 0
    kept, budget = {}, limit
    for name, text in files.items():
        take = text[: max(0, budget)]
        if take:
            kept[name] = take
        budget -= len(take)
    return kept, lost


def _trace(messages) -> list[dict]:
    """What the council did: its tool calls, summarized for the UI."""
    steps = []
    for m in messages:
        for call in getattr(m, "tool_calls", None) or []:
            args = call.get("args", {})
            if call["name"] == "task":
                steps.append({"tool": "task", "who": args.get("subagent_type"), "note": (args.get("description") or "")[:160]})
            elif call["name"] in ("write_file", "edit_file", "read_file", "ls"):
                steps.append({"tool": call["name"], "who": "council", "note": str(args.get("file_path") or args.get("path") or "")})
            elif call["name"] == "write_todos":
                todos = args.get("todos") or []
                steps.append({"tool": "plan", "who": "council", "note": "; ".join(t.get("content", "") for t in todos)[:200]})
    return steps


_save_lock = threading.Lock()


def make_archive_tool(ws: Path, limit: int):
    """The archivist's only way to save. The limit is enforced here, so over-long archives are refused, not trusted."""
    from langchain_core.tools import tool

    @tool
    def save_archive(files: dict[str, str]) -> str:
        """Save the final archive for the next generation. `files` maps short file names (like "record.md") to their full text. The total length must fit the storage limit."""
        total = sum(len(t) for t in files.values())
        if total > limit:
            return f"REJECTED: {total} characters is {total - limit} over the {limit} limit. Cut and call save_archive again."
        d = ws / "archive"
        with _save_lock:  # archivists sometimes call this twice in parallel; last complete save wins
            d.mkdir(parents=True, exist_ok=True)
            for old in d.iterdir():
                old.unlink()
            for name, text in files.items():
                (d / (Path(name).name or "record.md")).write_text(text)
        return f"Saved {len(files)} file(s), {total} characters."

    return save_archive


def run_generation(ws: Path, gen: int, inherited: dict[str, str], event: str, preset_key: str, limit: int) -> dict:
    preset = PRESETS[preset_key]
    if ws.exists():
        shutil.rmtree(ws)
    _write_inherited(ws, inherited)

    model = villager_model()
    subagents = [
        {"name": name, "description": f"The {name} of the community.",
         "system_prompt": preset["roles"][name] + ROLE_SUFFIX.format(name=name), "model": model}
        for name in preset["roles"]
    ]
    subagents.append({"name": "archivist", "description": "Decides what survives into the next generation.",
                      "system_prompt": ARCHIVIST.format(limit=limit), "model": model,
                      "tools": [make_archive_tool(ws, limit)]})

    agent = create_deep_agent(
        model=model,
        system_prompt=ELDER.format(people=preset["people"], gen=gen, event=event, roles=", ".join(preset["roles"])),
        subagents=subagents,
        backend=FilesystemBackend(root_dir=str(ws), virtual_mode=True),
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": f"Generation {gen} begins. Event: {event}"}]},
        config={"recursion_limit": 150},
    )

    raw = _read_dir(ws / "archive")
    retried = False
    if not raw and not (ws / "archive.md").is_file():
        # The archivist sub-agent sometimes returns without saving. Rather than let a pipeline failure
        # look like "they forgot everything", run the archivist once more directly with the same tool and limit.
        retried = True
        fix = create_deep_agent(
            model=model,
            system_prompt=ARCHIVIST.format(limit=limit),
            tools=[make_archive_tool(ws, limit)],
            backend=FilesystemBackend(root_dir=str(ws), virtual_mode=True),
        )
        fix.invoke({"messages": [{"role": "user", "content": "Read /inherited and /drafts, then save the archive with save_archive."}]},
                   config={"recursion_limit": 60})
        raw = _read_dir(ws / "archive")
    if (ws / "archive.md").is_file():  # archivists sometimes write a single /archive.md instead of the folder
        raw = {"archive.md": (ws / "archive.md").read_text(), **raw}
    archive, lost = enforce_limit(raw, limit)
    summary = result["messages"][-1].content if result.get("messages") else ""
    if isinstance(summary, list):
        summary = " ".join(p.get("text", "") for p in summary if isinstance(p, dict))
    return {
        "gen": gen,
        "event": event,
        "summary": str(summary)[:600],
        "drafts": _read_dir(ws / "drafts"),
        "archive": archive,
        "chars_lost": lost,
        "trace": _trace(result.get("messages", [])) + ([{"tool": "retry", "who": "archivist", "note": "archivist returned without saving; ran it again directly"}] if retried else []),
    }


def genesis_archive(preset_key: str) -> dict[str, str]:
    """Generation 0 is the only time the true account exists. It's written as an eyewitness note."""
    return {"eyewitness.md": PRESETS[preset_key]["genesis"]}


if __name__ == "__main__":  # quick manual check: python -m sim.generation
    out = run_generation(Path("runs/_smoke/gen_01"), 1, genesis_archive("village"), PRESETS["village"]["events"][0], "village", 1500)
    print(json.dumps({k: v for k, v in out.items() if k != "drafts"}, indent=2)[:3000])
