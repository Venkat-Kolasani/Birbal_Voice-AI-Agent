"""Thin JSON-completion client: Gemini first, Groq fallback. Returns None when no key or on failure."""
import asyncio
import json
import logging
import os
import re

from . import keys

log = logging.getLogger("birbal.llm")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")  # Scribe + brief extras (off the hot path)
# Talker: measured 2026-10-18 on the free tier: flash-lite 0.9 s, 3.6-flash 2.8 s, 3.8-flash 28 s per reply.
GEMINI_TALKER_MODEL = os.getenv("GEMINI_TALKER_MODEL", "gemini-flash-lite-latest")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
# Talker defaults to Gemini: voice resends the whole conversation each turn (~4k tokens by minute 6, 4-5 calls/min),
# far above Groq's published 8K TPM for gpt-oss-120b. Groq stays as failover. Switch only if the dashboard shows
# >= 30K TPM. Scribe is off the hot path.
SCRIBE_PROVIDER = os.getenv("SCRIBE_PROVIDER", "gemini")
TALKER_PROVIDER = os.getenv("TALKER_PROVIDER", "gemini")
TALKER_TEMPERATURE = float(os.getenv("TALKER_TEMPERATURE", "0.4"))
GROQ_REASONING = os.getenv("GROQ_REASONING_EFFORT", "low")  # gpt-oss reasons before answering; keep voice turns fast
# Third leg: any OpenAI-compatible endpoint (Mistral free plan by default: no card, phone verification). One provider's
# daily cap (Gemini: 20/day on 3.x-flash; flash-lite exhausted after ~100 calls on 2026-10-18) must never end the demo.
ALT_MODEL = os.getenv("ALT_LLM_MODEL", "gpt-5.6-luna")
ALT_BASE = os.getenv("ALT_LLM_BASE", "https://api.commandcode.ai/provider/v1")


def _order(prefer: str, table: dict) -> list:
    """Providers with keys, preferred first; a provider whose keys are all resting goes to the back."""
    names = [prefer] + [n for n in table if n != prefer]
    names = list(dict.fromkeys(names))
    names = [n for n in names if n in table and keys.has(n)]
    return sorted(names, key=lambda n: not keys.provider_healthy(n))


def talker_provider() -> str:
    """Which provider the Talker will use right now (picked per voice interview)."""
    order = _order(TALKER_PROVIDER, {"gemini": None, "groq": None, "alt": None})
    return order[0] if order else ""


async def _try(prefer: str, table: dict, timeout: float, *args):
    """Every key of every provider, in order, until one answers. Rate-limited keys rest for 60 s."""
    for name in _order(prefer, table):
        for key in keys.healthy(name):
            try:
                out = await asyncio.wait_for(table[name](*args, key), timeout)
                if out:
                    return out
            except Exception as e:  # never crash the call; try the next key/provider
                if keys.is_rate_limit(e):
                    keys.cooldown(name, key)
                log.warning("%s key …%s failed: %.160s", name, key[-4:], e)
    return None


def _parse(text: str) -> dict | None:
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        log.warning("LLM returned non-JSON: %.200s", text)
        return None


async def _gemini(system: str, user: str, key: str) -> dict | None:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=key)
    r = await client.aio.models.generate_content(
        model=GEMINI_MODEL, contents=user,
        config=types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json",
                                           temperature=0.2))
    return _parse(r.text)


async def _groq(system: str, user: str, key: str) -> dict | None:
    from groq import AsyncGroq
    r = await AsyncGroq(api_key=key, max_retries=0).chat.completions.create(
        model=GROQ_MODEL, temperature=0.2, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    return _parse(r.choices[0].message.content)


async def _alt(system: str, user: str, key: str) -> dict | None:
    from openai import AsyncOpenAI
    r = await AsyncOpenAI(api_key=key, base_url=ALT_BASE, max_retries=0).chat.completions.create(
        model=ALT_MODEL, temperature=0.2, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    return _parse(r.choices[0].message.content)


def available() -> bool:
    return keys.has("gemini") or keys.has("groq") or keys.has("alt")


async def complete_json(system: str, user: str, timeout: float = 15.0) -> dict | None:
    return await _try(SCRIBE_PROVIDER, {"gemini": _gemini, "groq": _groq, "alt": _alt}, timeout, system, user)


async def _gemini_text(system: str, messages: list[dict], key: str) -> str:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=key)
    contents = [types.Content(role="model" if m["role"] == "assistant" else "user",
                              parts=[types.Part(text=m["content"])]) for m in messages]
    r = await client.aio.models.generate_content(
        model=GEMINI_TALKER_MODEL, contents=contents,
        config=types.GenerateContentConfig(system_instruction=system, temperature=TALKER_TEMPERATURE))
    return (r.text or "").strip()


async def _groq_text(system: str, messages: list[dict], key: str) -> str:
    from groq import AsyncGroq
    r = await AsyncGroq(api_key=key, max_retries=0).chat.completions.create(
        model=GROQ_MODEL, temperature=TALKER_TEMPERATURE, messages=[{"role": "system", "content": system}, *messages],
        **({"reasoning_effort": GROQ_REASONING} if "gpt-oss" in GROQ_MODEL else {}))
    return (r.choices[0].message.content or "").strip()


async def _alt_text(system: str, messages: list[dict], key: str) -> str:
    from openai import AsyncOpenAI
    r = await AsyncOpenAI(api_key=key, base_url=ALT_BASE, max_retries=0).chat.completions.create(
        model=ALT_MODEL, temperature=TALKER_TEMPERATURE, messages=[{"role": "system", "content": system}, *messages],
        **({"reasoning_effort": GROQ_REASONING} if "gpt-oss" in ALT_MODEL else {}))
    return (r.choices[0].message.content or "").strip()


async def complete_text(system: str, messages: list[dict], timeout: float = 10.0) -> str | None:
    """Talker reply for text mode. messages: [{"role": "user"|"assistant", "content": str}]."""
    return await _try(TALKER_PROVIDER, {"gemini": _gemini_text, "groq": _groq_text, "alt": _alt_text}, timeout, system, messages)
