"""Customers as deepagents subagents: each customer (a persona, or an AI shopping agent on a user's errand) is an agent with
its own model, its own browser and its own tools, and it shops by itself until it decides.

    director (create_deep_agent)
      └─ task("p1-tomas")  ─►  Tomás: subagent(model=his family, system_prompt=who he is, tools=[open_site, click, scroll,
                                       back, search, decide], permissions=read-only /memories/)

The director registers one subagent spec per customer (customer_subagent) and runs them with deepagents' `task` tool, several
at once. The default pipeline runs the same customer without a director (run_standalone, used by session.browse).

Every action records one `live` step exactly as before (thought, feeling, action, target, screenshot), so the map, the
persona page and the summary don't change. `decide` checks the decision against the visit (session.contradiction) and works
out the outcome (b2a/outcome.py): placing the order is buying.
"""
from __future__ import annotations

import base64
import os
import queue
import threading
from pathlib import Path
from typing import Literal

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import Field

from . import outcome, session
from .models import fast, persona as persona_model

Feeling = Literal["delighted", "interested", "neutral", "confused", "annoyed", "skeptical"]
MAX_STEPS = 10
_BROWSERS = threading.Semaphore(int(os.getenv("MAX_BROWSERS") or "4"))  # never more real browsers at once

SEARCH_BOX = ("input[type=search], input[name*=search i], input[placeholder*=search i], input[aria-label*=search i], "
              "input[name=q], input[name=s]")

CUSTOMER = """You are {name}, {age}, {occupation}. You are a {archetype} customer. {voice}
Your goal: {goal}. Your budget: {budget}.{instructions}
The world right now: {world}
What the business says changed: {context}

You are visiting {site} as this person. Shop with your tools, like a real person with limited patience:
- Start with open_site: it shows you the page and what you remember from past visits. Your memory files are also readable
  with read_file: {memory_files}.
- Move around with click, scroll, back and search. Use search, filters or menus instead of scrolling long lists. Every move
  needs your thought (first person, in your voice, max 30 words) and how you feel. You see a screenshot before every move:
  look at it like a real person would.
- If you find something that fits and you want it, buy it like a real customer: pick the size/option, add it to the cart,
  go to checkout, and place the order if the site lets you without payment details. Never enter payment details: if the
  site asks for them, stop there and decide.
- If the site clearly isn't for you, decide early. You have at most {max_steps} moves.
- Finish with decide. Your decision must follow from what you thought, felt and did on THIS visit, especially at the end,
  not from who you are in general. If you placed the order, you bought it ("buy", or "would complain" if something went
  wrong after). If you could have placed the order and didn't, you did not buy.
- If a page was blocked by an automated bot check, real customers would not see it: don't hold it against the business.
Stay in character. After decide, reply with one line: what you did and why."""

DECIDE_TOOL = """Finish your visit with your decision, as a real shopper on this visit, not a reviewer.
First name the moment that settled it and its step number (as shown in your page results: "Step N done", or the step
you are deciding at). Your decision must follow from your own
thoughts and feelings on this visit, especially the last steps. If you placed the order, say "buy" (or "would complain").
Real people buy without perfect information: if something fit your goal and budget and nothing put you off, you buy.
"Maybe later" only if something specific stopped you today. "Not buy" if it doesn't fit you, "would complain" if something
went wrong. Then write as yourself: first impression, an honest review, liked and disliked, what you'd really pay, and 1-3
suggestions, each naming the page it applies to."""


class DecideArgs(session.Decision):
    last_thought: str = Field(description="your last thought before deciding, first person, max 30 words")


# ---------------------------------------------------------------- the browser (Playwright on its own thread)

class BrowserSession:
    """Playwright's sync API only works on the thread that started it, and tools may run on any thread, so every browser
    command is sent to this session's own thread and waited for."""

    def __init__(self):
        self.q: queue.Queue = queue.Queue()
        self.ready = threading.Event()
        self.err: Exception | None = None
        self.pg = self.ctx = None
        threading.Thread(target=self._run, daemon=True).start()
        self.ready.wait(90)
        if self.err:
            raise self.err

    def _run(self):
        from playwright.sync_api import sync_playwright
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(args=["--disable-gpu", "--use-gl=swiftshader", "--disable-dev-shm-usage"])
                self.ctx = b.new_context(viewport={"width": 1280, "height": 800})
                self.pg = self.ctx.new_page()
                self.ready.set()
                while (item := self.q.get()) is not None:
                    fn, args, box = item
                    try:
                        box["v"] = fn(*args)
                    except Exception as e:
                        box["e"] = e
                    box["done"].set()
                b.close()
        except Exception as e:
            self.err = e
            self.ready.set()

    def do(self, fn, *args, timeout: float = 120):
        box = {"done": threading.Event()}
        self.q.put((fn, args, box))
        if not box["done"].wait(timeout):
            raise TimeoutError("the browser didn't respond")
        if "e" in box:
            raise box["e"]
        return box.get("v")

    def close(self):
        self.q.put(None)

    # ---- run on the browser thread
    def goto(self, url: str):
        try:
            self.pg.goto(url, timeout=30000, wait_until="domcontentloaded")
        except Exception:
            pass
        self.pg.wait_for_timeout(1500)
        self.pg.keyboard.press("Escape")  # close the signup popup a real person would dismiss

    def look(self, shot: Path) -> dict:
        self.pg.wait_for_timeout(900)
        try:
            jpg = self.pg.screenshot(type="jpeg", quality=55, timeout=15000)
            shot.write_bytes(jpg)
        except Exception:
            jpg = b""
        try:
            found = self.pg.evaluate(session.VISIBLE_LINKS)
            targets = {f["t"]: f["href"] for f in found}
            text = self.pg.inner_text("body", timeout=5000)[:2500]
        except Exception:
            targets, text = {}, ""
        title = self.pg.title()
        return {"url": self.pg.url, "title": title, "targets": targets, "text": text, "jpg": jpg,
                "blocked": session.is_bot_wall(text, title), "order_done": outcome.order_confirmed(text, outcome.order_possible(self.pg.url))}  # only our store takes orders

    def disabled(self, t: str) -> bool:
        return session.is_disabled(self.pg, t)

    def click(self, t: str, targets: dict) -> dict:
        was = self.pg.url
        href = targets.get(t) or next((h for k, h in targets.items() if k.lower() == t.lower()), None) \
            or next((h for k, h in targets.items() if t.lower() in k.lower() or k.lower() in t.lower()), None)
        if href and href.startswith("http"):
            self.pg.goto(href, timeout=30000, wait_until="domcontentloaded")  # a link: go where it points
        else:
            before = len(self.ctx.pages)
            session.click_text(self.pg, t)
            self.pg.wait_for_timeout(1200)
            if len(self.ctx.pages) > before:  # opened a new tab: follow it like a real person would
                self.pg = self.ctx.pages[-1]
            self.pg.wait_for_load_state("domcontentloaded", timeout=15000)
        return {"unchanged": self.pg.url == was and not href}

    def scroll(self):
        self.pg.mouse.wheel(0, 900)

    def back(self, home: str):
        self.pg.go_back(timeout=10000)
        if not self.pg.url.startswith("http"):  # went back past the landing page
            self.pg.goto(home, timeout=30000, wait_until="domcontentloaded")

    def search(self, query: str) -> bool:
        box = self.pg.locator(SEARCH_BOX).locator("visible=true").first
        if not box.count():
            return False
        box.fill(query, timeout=5000)
        box.press("Enter")
        self.pg.wait_for_load_state("domcontentloaded", timeout=15000)
        return True


# ---------------------------------------------------------------- one customer's visit

class Visit:
    """One customer, one visit: the browser, every recorded step, and the decision."""

    def __init__(self, persona: dict, url: str, out_dir: Path, on_step, max_steps: int = MAX_STEPS, shot_prefix: str = ""):
        self.p, self.url, self.out_dir, self.on_step, self.max_steps, self.prefix = persona, url, out_dir, on_step, max_steps, shot_prefix
        self.cid = persona["id"]
        out_dir.mkdir(parents=True, exist_ok=True)
        self.steps: list[dict] = []
        self.notes: list[str] = []          # the visit so far, as the old loop's history (for the forced decision)
        self.prompts: list[dict] = []       # what the customer saw at each step (persona page)
        self.n = self.k = 0
        self.cur: dict | None = None
        self.can_order = outcome.order_possible(url)
        self.ordered_at = 0
        self.decision: dict | None = None
        self.bounced = ""
        self.fallbacks = {"n": 0, "why": ""}
        self.decide_prompt = ""
        self.browser: BrowserSession | None = None
        self._slot = False
        self.on_done = None  # the host's callback with result() once the decision is in

    # ---- seeing the page
    def _look(self) -> dict:
        self.k += 1
        shot = self.out_dir / f"{self.cid}_{self.k}.jpg"
        obs = self.browser.do(self.browser.look, shot)
        obs["shot"] = self.prefix + shot.name if obs["jpg"] else None
        if obs["blocked"]:
            # our automated browser hit a bot check: real customers wouldn't see it, so it's recorded and skipped
            self.n += 1
            step = {"n": self.n, "url": obs["url"], "title": obs["title"], "shot": obs["shot"], "blocked": True,
                    "thought": "(A security check blocked our test browser here. Real customers wouldn't see this, so it doesn't count.)",
                    "feeling": "neutral", "action": "back", "target": ""}
            self.steps.append(step)
            self.notes.append(f"step {self.n} [{obs['url']}] BLOCKED by an automated bot check that real customers would not see.")
            self.on_step(self.cid, step)
            try:
                self.browser.do(self.browser.back, self.url)
            except Exception:
                pass
            self.k += 1
            shot = self.out_dir / f"{self.cid}_{self.k}.jpg"
            obs = self.browser.do(self.browser.look, shot)
            obs["shot"] = self.prefix + shot.name if obs["jpg"] else None
            obs["note"] = "(A bot check blocked our test browser on the last page; you were taken back. Don't hold it against the business.)"
        self.cur = obs
        return obs

    def page_text(self, obs: dict, notes: list[str] = ()) -> str:
        left = self.max_steps - self.n
        head = f"Step {self.n} done. " if self.n else ""
        out = (f"{head}You are on {obs['url']} ({obs['title']}). Your next move will be step {self.n + 1}.\n"
               f"Visible links and buttons: {', '.join(obs['targets']) or '(none)'}\n"
               f"Page text (excerpt): {obs['text']}\n" + "".join(f"{x}\n" for x in [*notes, obs.get("note", "")] if x))
        if obs.get("order_done"):
            out += "The confirmation page says your order went through: you placed the order.\n"
        out += f"Moves left: {left}." + (" That was your last move: call decide now." if left <= 0 else "")
        self.prompts.append({"n": self.n + 1, "prompt": out, "with_screenshot": bool(obs.get("jpg"))})
        return out

    def open(self, memory: str) -> str:
        _BROWSERS.acquire()  # held until the visit closes: caps parallel customers, with or without a director
        self._slot = True
        self.browser = BrowserSession()
        self.browser.do(self.browser.goto, self.url)
        obs = self._look()
        mem = f"What you remember from past visits:\n{memory}\n\n" if memory.strip() else "You have no memories of past visits yet.\n\n"
        text = mem + self.page_text(obs)
        self.prompts[-1]["prompt"] = text
        return text

    # ---- moving
    def _record(self, action: str, target: str, thought: str, feeling: str) -> dict:
        self.n += 1
        c = self.cur or {}
        step = {"n": self.n, "url": c.get("url", self.url), "title": c.get("title", ""), "shot": c.get("shot"),
                "thought": thought, "feeling": feeling, "action": action, "target": target}
        if c.get("order_done") and not self.ordered_at:  # they're on the confirmation page: the order went through
            step["ordered"], self.ordered_at = True, self.n
            self.notes.append(f"(step {self.n}: the confirmation page says your order went through. You placed the order: you bought it.)")
        self.steps.append(step)
        self.notes.append(f"step {self.n} [{step['url']}] thought: {thought} ({feeling}) → {action} {target}".strip())
        self.on_step(self.cid, step)
        return step

    def act(self, action: str, target: str, thought: str, feeling: str) -> str:
        if self.decision:
            return "You already decided. Reply with one line about your visit."
        if self.n >= self.max_steps:
            return "You have no moves left: call decide now."
        step = self._record(action, target, thought, feeling)
        notes: list[str] = []
        try:
            if action == "click":
                r = self.browser.do(self.browser.click, target.strip(), (self.cur or {}).get("targets", {}))
                if session.CART.search(target):
                    step["cart"] = True
                    self.on_step(self.cid, None)
                    notes.append("(You clicked '%s'. On this store checkout needs no payment: the purchase is done when you place the order.)" % target
                                 if self.can_order else
                                 "(You clicked '%s': you chose to buy. Test browsers are often blocked at the cart, so if the cart looks empty or an "
                                 "error shows after this, that is our test setup, not the business.)" % target)
                elif r["unchanged"]:
                    notes.append(f"(clicked '{target}': the page stayed the same, maybe a menu opened)")
            elif action == "scroll":
                self.browser.do(self.browser.scroll)
            elif action == "back":
                self.browser.do(self.browser.back, self.url)
            elif action == "search":
                if not self.browser.do(self.browser.search, target):
                    notes.append("(There is no search box on this page.)")
        except Exception as e:
            greyed = False
            if action == "click" and target:
                try:
                    greyed = self.browser.do(self.browser.disabled, target.strip(), timeout=10)
                except Exception:
                    pass
            if greyed:  # configurators (Apple: storage unlocks after color) grey out a choice until the one before it is made
                notes.append(f"(tried to click '{target}' but it is greyed out: on this page it unlocks only after an earlier choice "
                             "is made. Pick the first unanswered option above it (for example a model or color) first.)")
            else:
                notes.append(f"(tried to {action} '{target}' but it didn't work: {type(e).__name__})")
        self.notes += notes
        return self.page_text(self._look(), notes)

    # ---- deciding
    def did(self) -> str:
        carted = next((x["n"] for x in self.steps if x.get("cart")), 0)
        return (f"you placed the order at step {self.ordered_at}." if self.ordered_at else
                f"you could have placed the order here (no payment needed) but did not{f'; you added it to the cart at step {carted}' if carted else ''}." if self.can_order else
                f"you clicked to buy at step {carted}; on this site our test browser can't pay, so that is as far as a purchase could go." if carted else
                "you did not click to buy anything.")

    def decide(self, args: dict) -> str:
        if self.decision:
            return "You already decided. Reply with one line about your visit."
        last, feeling = args.pop("last_thought", ""), args.get("feeling", "neutral")
        d = session.Decision(**args)
        on_confirmation = bool((self.cur or {}).get("order_done")) and not self.ordered_at
        probe = self.steps + ([{"ordered": True, "feeling": feeling, "thought": last}] if on_confirmation else [{"feeling": feeling, "thought": last}])
        why = session.contradiction(d, probe, self.can_order)
        if why and not self.bounced:
            self.bounced = why
            return (f"Your decision contradicts your own visit: {why}. Look at what you thought, felt and did again and call "
                    "decide with what actually follows from it (change the decision, the rating, or both).")
        self._record("decide", "", last, feeling)
        self.finish(d.model_dump())
        o = self.decision["outcome"]
        return f"Recorded: {o.replace('_', ' ')}. Now reply with one line: what you did and why."

    def finish(self, decision: dict):
        decision["outcome"] = outcome.decide(decision, self.steps, self.can_order)
        decision["ordered_step"], decision["order_possible"] = self.ordered_at, self.can_order
        if self.bounced:
            decision["reconsidered"] = self.bounced  # a corrected decision is never hidden
        self.decision = decision
        self.decide_prompt = DECIDE_TOOL + f"\nWhat you actually did: {self.did()}"
        self.close()
        if self.on_done:
            self.on_done(self.result())

    def force_decision(self):
        """The customer stopped without calling decide (step cap, a weak tool-caller): decide from the recorded visit."""
        if self.decision:
            return
        q = session.DECIDE.format(**{**self.p, "memory": self.p.get("memory") or "nothing yet", "instructions": session.instructions(self.p)},
                                  world="", product=self.url, history="\n".join(self.notes) or "(nothing)", did=self.did())
        try:
            d = persona_model(self.p.get("model")).with_structured_output(session.Decision).invoke(q)
        except Exception as e:
            self.fallbacks["n"] += 1
            self.fallbacks["why"] = self.fallbacks["why"] or f"{type(e).__name__}: {str(e)[:120]}"
            d = fast().with_structured_output(session.Decision).invoke(q)
        self.decide_prompt = q
        self.finish(d.model_dump())
        self.decide_prompt = q

    def close(self):
        if self.browser:
            self.browser.close()
            self.browser = None
        if self._slot:
            self._slot = False
            _BROWSERS.release()

    def result(self) -> dict:
        """The same shape session.browse() always returned."""
        return {"persona": self.cid, **session.agent_tags(self.p), "steps": self.steps, "decision": self.decision,
                "fallbacks": self.fallbacks["n"], "fallback_reason": self.fallbacks["why"], "prompts": self.prompts,
                "decide_prompt": self.decide_prompt}


# ---------------------------------------------------------------- tools + middleware for one customer

class Host:
    """Who a customer shops for: the director job (b2a/director.py) or a standalone run (run_standalone)."""

    url = ""
    world = ""
    context = ""

    def begin(self, cid: str) -> Visit | str:  # a new visit, or why it can't start
        raise NotImplementedError

    def visit(self, cid: str) -> Visit | None:
        raise NotImplementedError

    def memory(self, cid: str) -> str:
        return ""


def tools_for(host: Host, cid: str) -> list:
    def current() -> Visit | str:
        v = host.visit(cid)
        return v if v and v.browser else "Call open_site first."

    def open_site() -> str:
        """Open the business's website. Call this first: it shows you the page and what you remember from past visits."""
        v = host.visit(cid)
        if v and v.browser:
            return v.page_text(v.cur)
        if v and v.decision:
            return "You already finished this visit. Reply with one line about it."
        v = host.begin(cid)
        if isinstance(v, str):
            return v
        return v.open(host.memory(cid))

    def click(target: str, thought: str, feeling: Feeling) -> str:
        """Click a visible link or button by its exact text (as listed on the page)."""
        v = current()
        return v if isinstance(v, str) else v.act("click", target, thought, feeling)

    def scroll(thought: str, feeling: Feeling) -> str:
        """Scroll down the page."""
        v = current()
        return v if isinstance(v, str) else v.act("scroll", "", thought, feeling)

    def back(thought: str, feeling: Feeling) -> str:
        """Go back to the previous page."""
        v = current()
        return v if isinstance(v, str) else v.act("back", "", thought, feeling)

    def search(query: str, thought: str, feeling: Feeling) -> str:
        """Type into the site's search box and search."""
        v = current()
        return v if isinstance(v, str) else v.act("search", query, thought, feeling)

    def decide(**kw) -> str:
        v = host.visit(cid)
        if not v:
            return "Call open_site first."
        return v.decide(kw)

    return [StructuredTool.from_function(f) for f in (open_site, click, scroll, back, search)] + [
        StructuredTool.from_function(decide, name="decide", description=DECIDE_TOOL, args_schema=DecideArgs)]


class CustomerMiddleware(AgentMiddleware):
    """Before every model call: show the customer the page as it looks right now (screenshot), keep older page text short so
    the visit doesn't grow without bound, and let Claude stand in if the customer's own model fails."""

    def __init__(self, host: Host, cid: str):
        super().__init__()
        self.host, self.cid = host, cid

    @property
    def name(self) -> str:
        return f"customer-{self.cid}"

    def wrap_model_call(self, request, handler):
        v = self.host.visit(self.cid)
        msgs = list(request.messages)
        last_tool = max((i for i, m in enumerate(msgs) if isinstance(m, ToolMessage)), default=-1)
        for i, m in enumerate(msgs):  # older pages: the first lines are enough to remember them
            if isinstance(m, ToolMessage) and i != last_tool and isinstance(m.content, str) and len(m.content) > 500:
                msgs[i] = m.model_copy(update={"content": m.content[:500] + " …"})
        if v and v.cur and v.cur.get("jpg") and not v.decision:
            msgs.append(HumanMessage(content=[
                {"type": "text", "text": "The page as you see it right now:"},
                {"type": "image", "source_type": "base64", "mime_type": "image/jpeg", "data": base64.b64encode(v.cur["jpg"]).decode()}]))
        req = request.override(messages=msgs)
        try:
            return handler(req)
        except Exception as e:  # e.g. Gemini free-tier quota: Claude stands in, and we say so
            if v:
                v.fallbacks["n"] += 1
                v.fallbacks["why"] = v.fallbacks["why"] or f"{type(e).__name__}: {str(e)[:120]}"
            return handler(req.override(model=fast()))


def system_prompt(p: dict, host: Host) -> str:
    files = (f"/memories/business/{p['id']}.md (your own past visits here) and /memories/{p['archetype'].replace(' ', '-')}.md "
             "(what customers like you learned on other sites)") if p.get("kind") != "agent" else "none (AI agents start fresh)"
    return CUSTOMER.format(**{**p, "instructions": session.instructions(p)}, world=host.world or "today, normal times",
                           context=host.context or "none", site=host.url, max_steps=MAX_STEPS, memory_files=files)


def description(p: dict) -> str:
    if p.get("kind") == "agent":
        return f"{p['name']}: an AI shopping agent acting for a user ({p.get('goal', '')[:120]}), played by {p.get('model')}."
    return (f"{p['name']}, {p.get('age')}: {p['archetype']} customer ({p.get('segment', '')}, {round((p.get('share') or 0) * 100)}% of "
            f"customers). Wants: {p.get('goal', '')[:120]} Budget: {p.get('budget', '')}. Played by {p.get('model')}.")


def subagent_name(p: dict) -> str:
    import re
    return f"{p['id']}-" + (re.sub(r"[^a-z0-9]+", "-", p["name"].lower()).strip("-") or "customer")


def customer_subagent(p: dict, host: Host) -> dict:
    """The deepagents SubAgent spec for one customer: its tendency, its own model, its own browser tools, read-only memory."""
    from deepagents.middleware.filesystem import FilesystemPermission
    return {"name": subagent_name(p), "description": description(p), "system_prompt": system_prompt(p, host),
            "model": persona_model(p.get("model")), "tools": tools_for(host, p["id"]),
            "middleware": [CustomerMiddleware(host, p["id"])],
            "permissions": [FilesystemPermission(operations=["write"], paths=["/**"], mode="deny")]}


# ---------------------------------------------------------------- standalone (the default pipeline, via session.browse)

class _OneCustomer(Host):
    def __init__(self, p, url, world, context, out_dir, on_step, max_steps, shot_prefix):
        self.p, self.url, self.world, self.context = p, url, world, context
        self.args = (out_dir, on_step, max_steps, shot_prefix)
        self.v: Visit | None = None

    def begin(self, cid):
        out_dir, on_step, max_steps, prefix = self.args
        self.v = Visit(self.p, self.url, out_dir, on_step, max_steps, prefix)
        return self.v

    def visit(self, cid):
        return self.v

    def memory(self, cid):
        return self.p.get("memory") or ""


def run_standalone(p: dict, url: str, world: str, context: str, out_dir: Path, on_step, max_steps: int = MAX_STEPS,
                   shot_prefix: str = "") -> dict:
    """One customer without a director: the same prompt, tools and middleware as its subagent spec."""
    from langchain.agents import create_agent
    host = _OneCustomer(p, url, world, context, out_dir, on_step, max_steps, shot_prefix)
    agent = create_agent(model=persona_model(p.get("model")), tools=tools_for(host, p["id"]), system_prompt=system_prompt(p, host),
                         middleware=[CustomerMiddleware(host, p["id"])])
    try:
        agent.invoke({"messages": [HumanMessage("Visit the site as yourself: open_site, shop, then decide.")]},
                     config={"recursion_limit": 4 * max_steps + 12, "run_name": f"customer:{p['name']}"})
    except Exception as e:
        if not host.v:
            raise
        host.v.notes.append(f"(the visit stopped early: {type(e).__name__})")
    if not host.v:
        host.begin(p["id"])
    host.v.force_decision()
    host.v.close()
    return host.v.result()
