import asyncio

import pytest
from fastapi.testclient import TestClient

import api
from brain.session import SessionStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "store", SessionStore(tmp_path / "sessions"))
    monkeypatch.setattr(api, "EXPORTS", tmp_path / "exports")
    return TestClient(api.app)


def replayed(c):
    sid = c.post("/api/start?mode=text").json()["id"]
    asyncio.run(api.store.get(sid).replay(pace=0))
    c.post(f"/api/end?s={sid}")
    return sid


def test_brief_and_approve_flow(client, tmp_path):
    sid = replayed(client)
    b = client.get(f"/api/brief?s={sid}").json()
    assert b["versions"]["builders"]["safe"]
    assert client.get(f"/api/export/builders.md?s={sid}").status_code == 403
    assert client.post(f"/api/approve?s={sid}").status_code == 200
    r = client.get(f"/api/export/builders.md?s={sid}")
    assert r.status_code == 200 and "Kaveri" not in r.text
    assert any(p.name.endswith("builders.md") for p in (tmp_path / "exports").iterdir())


def test_handtyped_secret_blocks_approve(client):
    sid = replayed(client)
    r = client.post(f"/api/edit?s={sid}", json={"audience": "builders", "problem": "Kaveri Bank verification hangs"}).json()
    assert not r["versions"]["builders"]["safe"]
    assert client.post(f"/api/approve?s={sid}").status_code == 409
    r = client.post(f"/api/edit?s={sid}", json={"audience": "builders", "problem": ""}).json()
    assert r["versions"]["builders"]["safe"]


def test_choice_keep_shares_name(client):
    sid = replayed(client)
    r = client.post(f"/api/choice?s={sid}", json={"span": "Kaveri Bank", "choice": "keep"}).json()
    assert "Kaveri Bank" in r["versions"]["builders"]["markdown"] and r["versions"]["builders"]["safe"]


def test_sessions_are_isolated_and_persist(client, tmp_path):
    a, b = replayed(client), client.post("/api/start?mode=text").json()["id"]
    assert a != b
    assert client.get(f"/api/state?s={b}").json()["clear"] == 0
    client.post(f"/api/choice?s={a}", json={"span": "Ravi", "choice": "remove"})
    fresh = SessionStore(tmp_path / "sessions")  # simulates a server restart
    s = fresh.get(a)
    assert s.ended and {x.span: x.choice for x in s.ledger.sensitive}["Ravi"] == "remove"
    v = asyncio.run(s.brief())
    assert v["builders"].safe and "Ravi" not in v["builders"].markdown
    listed = client.get("/api/sessions").json()
    assert [x["id"] for x in listed] == [a] and "Kaveri" not in listed[0]["title"]


def test_unknown_or_malicious_session_id(client):
    assert client.get("/api/state?s=nope").status_code == 404
    assert client.get("/api/state?s=../../etc").status_code == 404


def test_turn_without_key_is_clear_error(client, monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    sid = client.post("/api/start?mode=text").json()["id"]
    assert client.post(f"/api/turn?s={sid}", json={"text": "hello"}).status_code == 503


def test_text_turn_appends_note_and_runs_scribe(client, monkeypatch):
    from brain import llm, scribe
    from brain.schema import Claim, ScribeOutput
    seen = {}

    async def fake_text(system, messages, timeout=10.0):
        seen["last"] = messages[-1]["content"]
        return "Got it. Walk me through the last time that happened."

    async def fake_scribe(ledger, asked, said):
        return ScribeOutput(claims=[Claim(dimension="who", value="merchants", kind="inferred")])

    monkeypatch.setenv("GOOGLE_API_KEY", "x")
    monkeypatch.setattr(llm, "complete_text", fake_text)
    monkeypatch.setattr(scribe, "run", fake_scribe)
    sid = client.post("/api/start?mode=text").json()["id"]
    st = client.post(f"/api/turn?s={sid}", json={"text": "Merchants drop off a lot"}).json()
    assert "[controller]" in seen["last"] and seen["last"].startswith("Merchants drop off a lot")
    assert st["transcript"][-1]["role"] == "birbal"
    asyncio.run(api.store.get(sid).settle())
    assert any(r["key"] == "who" and r["score"] == 1 for r in client.get(f"/api/state?s={sid}").json()["rows"])


def test_share_link_is_read_only_and_revocable(client):
    sid = replayed(client)
    assert client.post(f"/api/approve?s={sid}").status_code == 200
    share = client.get(f"/api/brief?s={sid}").json()["share"]
    token = share.split("/")[-1]
    r = client.get(f"/api/shared/{token}").json()
    assert set(r["versions"]) == {"builders", "everyone"}
    assert "Kaveri" not in str(r) and "private" not in r
    assert client.get(f"/b/{token}").status_code == 200
    client.post(f"/api/choice?s={sid}", json={"span": "Ravi", "choice": "remove"})
    assert client.get(f"/api/shared/{token}").status_code == 404
    assert client.get("/api/shared/short").status_code == 404


def test_in_progress_interview_survives_restart(client, tmp_path):
    sid = client.post("/api/start?mode=text").json()["id"]
    api.store.get(sid).add_owner("Merchants drop off", scribe_out=__import__("brain.schema", fromlist=["x"]).ScribeOutput())
    assert api.store.save_dirty() == 1
    fresh = SessionStore(tmp_path / "sessions")
    s = fresh.get(sid)
    assert not s.ended and s.ledger.transcript[-1].text == "Merchants drop off"


def test_failed_turn_is_not_recorded_twice(client, monkeypatch):
    from brain import llm

    async def boom(system, messages, timeout=10.0):
        return None
    monkeypatch.setenv("GOOGLE_API_KEY", "x")
    monkeypatch.setattr(llm, "complete_text", boom)
    sid = client.post("/api/start?mode=text").json()["id"]
    assert client.post(f"/api/turn?s={sid}", json={"text": "hello"}).status_code == 502
    assert [t.role for t in api.store.get(sid).ledger.transcript] == ["birbal"]
