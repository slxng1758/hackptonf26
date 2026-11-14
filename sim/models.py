"""Model selection. Villagers are cheap and many (Gemini if available), the evaluator is strong and rare."""
import os
import subprocess
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _ensure_anthropic_key() -> None:
    # Local dev convenience: read the key from the macOS Keychain if it isn't in the env. Never printed.
    if os.getenv("ANTHROPIC_API_KEY"):
        return
    try:
        key = subprocess.run(
            ["security", "find-generic-password", "-s", "anthropic-api-key", "-w"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if key:
            os.environ["ANTHROPIC_API_KEY"] = key
    except Exception:
        pass


def _claude(model: str):
    _ensure_anthropic_key()
    from langchain_anthropic import ChatAnthropic
    # Current Claude models reject `temperature`; drift comes from roles + the storage limit, not sampling.
    return ChatAnthropic(model=model, max_tokens=4096, timeout=60, max_retries=2)


@lru_cache
def villager_model():
    choice = os.getenv("VILLAGER_MODEL") or ("gemini" if os.getenv("GOOGLE_API_KEY") else "claude-haiku-5-5")
    if choice == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"), temperature=0.9)
    return _claude(choice)


@lru_cache
def evaluator_model():
    return _claude(os.getenv("EVALUATOR_MODEL", "claude-sonnet-5-5"))


def describe() -> dict:
    v = os.getenv("VILLAGER_MODEL") or ("gemini" if os.getenv("GOOGLE_API_KEY") else "claude-haiku-5-5")
    return {"villagers": os.getenv("GEMINI_MODEL", "gemini-2.5-flash") if v == "gemini" else v,
            "evaluator": os.getenv("EVALUATOR_MODEL", "claude-sonnet-5-5")}
