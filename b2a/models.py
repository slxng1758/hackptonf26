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
    return ChatAnthropic(model=os.getenv("FAST_MODEL", "claude-haiku-5-5"), max_tokens=4096, timeout=60, max_retries=2)


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


@lru_cache
def persona_models() -> dict:
    """Every model family we have a key for. Customers are spread across them, so no single lab's taste decides."""
    out = {}
    if os.getenv("GOOGLE_API_KEY"):
        from langchain_google_genai import ChatGoogleGenerativeAI
        out["Gemini"] = ChatGoogleGenerativeAI(model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"), timeout=60, max_retries=2)
    if _anthropic_key():
        out["Claude"] = fast()
    if os.getenv("OPENAI_API_KEY"):
        from langchain_openai import ChatOpenAI
        out["GPT"] = ChatOpenAI(model=os.getenv("GPT_SHOPPER", "gpt-5.4-mini"), timeout=60, max_retries=2)
    if os.getenv("XAI_API_KEY") and os.getenv("XAI_MODEL"):
        from langchain_openai import ChatOpenAI
        out["Grok"] = ChatOpenAI(model=os.environ["XAI_MODEL"], base_url="https://api.x.ai/v1", api_key=os.environ["XAI_API_KEY"], timeout=60, max_retries=2)
    if os.getenv("GROQ_API_KEY") and os.getenv("LLAMA_MODEL"):
        from langchain_openai import ChatOpenAI
        out["Llama"] = ChatOpenAI(model=os.environ["LLAMA_MODEL"], base_url="https://api.groq.com/openai/v1", api_key=os.environ["GROQ_API_KEY"], timeout=60, max_retries=2)
    return out


def persona(name: str | None = None):
    """The model that plays one customer (by family name); falls back to Claude Haiku."""
    ms = persona_models()
    return ms.get(name or "", None) or next(iter(ms.values()), None) or fast()
