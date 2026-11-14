"""Model access. Shoppers are the real models people shop with; the brain runs the improve loop."""
from __future__ import annotations

import os
import subprocess
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _anthropic_key() -> bool:
    # Local convenience: read the key from the macOS Keychain if it isn't in the env. Never printed.
    if not os.getenv("ANTHROPIC_API_KEY"):
        try:
            k = subprocess.run(["security", "find-generic-password", "-s", "anthropic-api-key", "-w"],
                               capture_output=True, text=True, timeout=5).stdout.strip()
            if k:
                os.environ["ANTHROPIC_API_KEY"] = k
        except Exception:
            pass
    return bool(os.getenv("ANTHROPIC_API_KEY"))


@lru_cache
def brain():
    """The deep agent and its sub-agents."""
    _anthropic_key()
    from langchain_anthropic import ChatAnthropic
    return ChatAnthropic(model=os.getenv("BRAIN_MODEL", "claude-sonnet-5-5"), max_tokens=4096, timeout=90, max_retries=2)


@lru_cache
def fast():
    """Cheap model for persona work."""
    _anthropic_key()
    from langchain_anthropic import ChatAnthropic
    return ChatAnthropic(model=os.getenv("FAST_MODEL", "claude-haiku-5-5"), max_tokens=2048, timeout=60, max_retries=2)


@lru_cache
def shoppers() -> dict:
    """Every shopping agent we can run with the keys present."""
    out = {}
    if _anthropic_key():
        from langchain_anthropic import ChatAnthropic
        out["Claude"] = ChatAnthropic(model=os.getenv("CLAUDE_SHOPPER", "claude-haiku-5-5"), max_tokens=600, timeout=60, max_retries=2)
    if os.getenv("OPENAI_API_KEY"):
        from langchain_openai import ChatOpenAI
        out["GPT"] = ChatOpenAI(model=os.getenv("GPT_SHOPPER", "gpt-5.4-mini"), timeout=60, max_retries=2)
    if os.getenv("GOOGLE_API_KEY"):
        from langchain_google_genai import ChatGoogleGenerativeAI
        out["Gemini"] = ChatGoogleGenerativeAI(model=os.getenv("GEMINI_SHOPPER", "gemini-2.5-flash"), timeout=60, max_retries=2)
    return out
