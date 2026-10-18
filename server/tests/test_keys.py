import asyncio

from brain import keys, llm


def test_pool_and_rotation(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEYS", "a, b ,c")
    monkeypatch.setattr(keys, "_cool", {})
    monkeypatch.setattr(keys, "_turn", {})
    assert keys.pool("gemini") == ["a", "b", "c"]
    assert [keys.pick("gemini") for _ in range(4)] == ["a", "b", "c", "a"]
    keys.cooldown("gemini", "b")
    assert "b" not in keys.healthy("gemini")


def test_single_key_var_still_works(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEYS", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "solo")
    assert keys.pool("groq") == ["solo"]


def test_failover_across_keys_and_providers(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEYS", "g1,g2")
    monkeypatch.setenv("GROQ_API_KEYS", "q1")
    monkeypatch.setattr(keys, "_cool", {})
    monkeypatch.setattr(keys, "_turn", {})
    calls = []

    async def gem(system, msgs, key):
        calls.append(key)
        raise RuntimeError("429 RESOURCE_EXHAUSTED quota")

    async def grq(system, msgs, key):
        calls.append(key)
        return "hello from groq"

    out = asyncio.run(llm._try("gemini", {"gemini": gem, "groq": grq}, 1.0, "sys", []))
    assert out == "hello from groq" and calls == ["g1", "g2", "q1"]
    assert not keys.provider_healthy("gemini")
    # next call starts with the healthy provider
    calls.clear()
    asyncio.run(llm._try("gemini", {"gemini": gem, "groq": grq}, 1.0, "sys", []))
    assert calls[0] == "q1"


def test_non_rate_limit_error_does_not_rest_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEYS", "g1")
    monkeypatch.delenv("GROQ_API_KEYS", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(keys, "_cool", {})

    async def gem(system, msgs, key):
        raise ValueError("bad request")
    assert asyncio.run(llm._try("gemini", {"gemini": gem}, 1.0, "s", [])) is None
    assert keys.provider_healthy("gemini")
