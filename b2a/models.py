"""Model access. Shoppers are the real models people shop with; the brain runs the improve loop."""
from __future__ import annotations

import os
import subprocess
import time
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
    # The director rebuilds itself when it casts mid-run (new customer subagents -> new system prompt and tools), which
    # invalidates the thinking blocks already in its history: drop them instead of failing the request with a 400.
    return ChatAnthropic(model=(os.getenv("BRAIN_MODEL") or "claude-sonnet-5-5"), max_tokens=4096, timeout=90, max_retries=2,
                         betas=["thinking-binding-controls-2026-08-01"],
                         thinking={"type": "adaptive", "block_binding": {"prefix_mismatch_behavior": "drop_block"}})


@lru_cache
def fast():
    """Cheap model for persona work."""
    _anthropic_key()
    from langchain_anthropic import ChatAnthropic
    return ChatAnthropic(model=(os.getenv("FAST_MODEL") or "claude-haiku-5-5"), max_tokens=4096, timeout=60, max_retries=2)


@lru_cache
def shoppers() -> dict:
    """Every shopping agent we can run with the keys present."""
    out = {}
    if _anthropic_key():
        from langchain_anthropic import ChatAnthropic
        out["Claude"] = ChatAnthropic(model=(os.getenv("CLAUDE_SHOPPER") or "claude-haiku-5-5"), max_tokens=600, timeout=60, max_retries=2)
    if os.getenv("OPENAI_API_KEY"):
        from langchain_openai import ChatOpenAI
        out["GPT"] = ChatOpenAI(model=(os.getenv("GPT_SHOPPER") or "gpt-5.4-mini"), timeout=60, max_retries=2)
    if os.getenv("GOOGLE_API_KEY"):
        from langchain_google_genai import ChatGoogleGenerativeAI
        out["Gemini"] = ChatGoogleGenerativeAI(model=(os.getenv("GEMINI_SHOPPER") or "gemini-3.5-flash"), timeout=60, max_retries=2)
    return out


@lru_cache
def persona_models() -> dict:
    """Every model family we have a key for. Customers are spread across them, so no single lab's taste decides."""
    out = {}
    if os.getenv("GOOGLE_API_KEY"):
        from langchain_google_genai import ChatGoogleGenerativeAI
        out["Gemini"] = ChatGoogleGenerativeAI(model=(os.getenv("GEMINI_MODEL") or "gemini-3.5-flash"), timeout=60, max_retries=2)
    if _anthropic_key():
        out["Claude"] = fast()
    if os.getenv("OPENAI_API_KEY"):
        from langchain_openai import ChatOpenAI
        out["GPT"] = ChatOpenAI(model=(os.getenv("GPT_SHOPPER") or "gpt-5.4-mini"), timeout=60, max_retries=2)
    if os.getenv("AWS_ACCESS_KEY_ID") or os.getenv("AWS_PROFILE"):
        # Amazon Bedrock: Amazon's own Nova (the model family behind Amazon's shopping assistant) and Meta's Llama.
        from langchain_aws import ChatBedrockConverse
        region = (os.getenv("AWS_REGION") or "us-east-1")
        if os.getenv("NOVA_MODEL_ID"):
            out["Amazon Nova"] = ChatBedrockConverse(model=os.environ["NOVA_MODEL_ID"], region_name=region, max_tokens=1500)
        if os.getenv("LLAMA_BEDROCK_MODEL_ID"):
            out["Llama"] = ChatBedrockConverse(model=os.environ["LLAMA_BEDROCK_MODEL_ID"], region_name=region, max_tokens=1500)
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


RETRY_WAITS = (2, 6)  # seconds between tries when a customer's model fails


class ModelUnavailable(RuntimeError):
    """A customer's model kept failing (quota, outage). That customer is skipped: another model never stands in, so a run
    stays played by the one model the owner picked."""


def call_with_retry(fn, who: str = "", tries: int = 3):
    """fn() with retries and backoff; after the last failure, ModelUnavailable says which model failed and why."""
    last: Exception | None = None
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            last = e
            if i < tries - 1:
                time.sleep(RETRY_WAITS[min(i, len(RETRY_WAITS) - 1)])
    raise ModelUnavailable(f"{who or 'the model'} failed {tries} times: {type(last).__name__}: {str(last)[:160]}") from last
