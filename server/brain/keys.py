"""API key pools with cooldown. A provider can have several keys:
GOOGLE_API_KEYS=k1,k2 (or a single GOOGLE_API_KEY). A key that hits a rate limit is rested for a while
and the next healthy key (or the next provider) is used instead.
"""
import os
import time

ENV = {"gemini": "GOOGLE_API_KEY", "groq": "GROQ_API_KEY", "alt": "ALT_LLM_KEY", "deepgram": "DEEPGRAM_API_KEY",
       "sarvam": "SARVAM_API_KEY", "elevenlabs": "ELEVENLABS_API_KEY"}
_cool: dict[tuple[str, str], float] = {}  # (provider, key) -> resting until (monotonic)
_turn: dict[str, int] = {}  # round-robin cursor per provider

RATE_LIMIT_HINTS = ("429", "rate limit", "rate_limit", "resource_exhausted", "quota", "too many requests")


def pool(provider: str) -> list[str]:
    var = ENV[provider]
    raw = os.getenv(var + "S") or os.getenv(var) or ""
    return [k.strip() for k in raw.split(",") if k.strip()]


def has(provider: str) -> bool:
    return bool(pool(provider))


def healthy(provider: str) -> list[str]:
    """Keys not resting, starting from the round-robin cursor. Falls back to all keys if every one is resting."""
    keys = pool(provider)
    if not keys:
        return []
    i = _turn.get(provider, 0) % len(keys)
    keys = keys[i:] + keys[:i]
    now = time.monotonic()
    ok = [k for k in keys if _cool.get((provider, k), 0) <= now]
    return ok or keys


def pick(provider: str) -> str | None:
    keys = healthy(provider)
    if not keys:
        return None
    _turn[provider] = _turn.get(provider, 0) + 1  # spread load across keys
    return keys[0]


def cooldown(provider: str, key: str, secs: float = 60.0) -> None:
    _cool[(provider, key)] = time.monotonic() + secs


def is_rate_limit(err: Exception) -> bool:
    text = f"{type(err).__name__} {err}".lower()
    return any(h in text for h in RATE_LIMIT_HINTS)


def provider_healthy(provider: str) -> bool:
    now = time.monotonic()
    return any(_cool.get((provider, k), 0) <= now for k in pool(provider))
