import asyncio
import json
import time
from types import SimpleNamespace
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

import api
from brain import llm, scribe
from brain.auth import COOKIE, SupabaseAuth, configured_auth
from brain.cloud import PilotStore
from brain.schema import ScribeOutput

ORIGIN = "https://birbal.example.test"
SUPABASE = "https://project.example.test"
ALICE, BOB = str(uuid4()), str(uuid4())


@pytest.fixture
def pilot(monkeypatch):
    auth = SupabaseAuth(SUPABASE, "publishable-fixture", ORIGIN)
    key = ec.generate_private_key(ec.SECP256R1())
    rows = {}
    state = SimpleNamespace(failing=False, rows=rows)
    monkeypatch.setattr(auth.keys, "get_signing_key_from_jwt", lambda _: key.public_key())

    def token(owner=ALICE, **overrides):
        claims = {"sub": owner, "iss": auth.issuer, "aud": "authenticated", "role": "authenticated",
                  "exp": int(time.time()) + 600, "iat": int(time.time())}
        return jwt.encode({**claims, **overrides}, key, algorithm="ES256", headers={"kid": "fixture"})

    def remote(request):
        if request.url.path.endswith("/otp"):
            assert json.loads(request.content)["create_user"] is False
            return httpx.Response(400)  # unknown and admitted addresses look the same to callers
        if request.url.path.endswith("/verify"):
            status = json.loads(request.content)["token"] == "123456"
            return httpx.Response(200 if status else 403, json={"access_token": token()} if status else {})
        assert request.url.path == "/rest/v1/pilot_interviews"
        assert "authorization" not in request.headers
        assert request.headers["apikey"] == "sb_secret_fixture"
        if state.failing:
            return httpx.Response(503)
        if request.method == "POST":
            assert request.url.params["on_conflict"] == "owner_id,id"
            assert request.headers["prefer"] == "resolution=merge-duplicates,return=minimal"
            row = json.loads(request.content)
            rows[(row["owner_id"], row["id"])] = row
            return httpx.Response(201)
        owner = request.url.params["owner_id"].removeprefix("eq.")
        if "id" in request.url.params:
            sid = request.url.params["id"].removeprefix("eq.")
            return httpx.Response(200, json=[rows[(owner, sid)]] if (owner, sid) in rows else [])
        return httpx.Response(200, json=[r for (uid, _), r in rows.items() if uid == owner])

    upstream = httpx.Client(transport=httpx.MockTransport(remote))
    monkeypatch.setattr(httpx, "request", upstream.request)
    monkeypatch.setattr(httpx, "post", upstream.post)
    monkeypatch.setattr(api, "auth", auth)
    monkeypatch.setattr(api, "store", PilotStore(SUPABASE, "sb_secret_fixture"))
    monkeypatch.setattr(llm, "available", lambda: True)

    async def model(*args):
        return "How often does this happen?"

    async def notes(*args):
        return ScribeOutput()

    async def extras(*args):
        return {}

    monkeypatch.setattr(llm, "complete_text", model)
    monkeypatch.setattr(scribe, "run", notes)
    monkeypatch.setattr(scribe, "extras", extras)

    def client(owner=None):
        return TestClient(api.app, base_url=ORIGIN, headers={"Origin": ORIGIN},
                          cookies={COOKIE: token(owner)} if owner else None)

    yield SimpleNamespace(client=client, token=token, remote=state)
    upstream.close()


def test_pilot_mode_fails_closed_when_incomplete(monkeypatch):
    monkeypatch.setenv("BIRBAL_AUTH_MODE", "pilot")
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SUPABASE_KEY"):
        configured_auth()


def test_login_sets_protected_cookie_and_logout_clears_it(pilot):
    client = pilot.client()
    assert client.get("/api/sessions").status_code == 401
    redirect = client.get("/start?s=fixture", follow_redirects=False)
    assert redirect.headers["location"] == "/login?next=%2Fstart%3Fs%3Dfixture"
    data = {"email": "fixture@example.test"}
    assert client.post("/api/auth/code", json=data).status_code == 204
    assert client.post("/api/auth/verify", json={**data, "code": "654321"}).status_code == 401
    reply = client.post("/api/auth/verify", json={**data, "code": "123456"})
    assert reply.status_code == 204
    assert all(setting in reply.headers["Set-Cookie"] for setting in ("HttpOnly", "Secure", "SameSite=lax"))
    assert reply.headers["Cache-Control"] == "no-store"
    assert client.get("/api/sessions").status_code == 200
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/sessions").status_code == 401


@pytest.mark.parametrize("claims", [
    {"iss": "https://other.example.test/auth/v1"}, {"aud": "anon"}, {"role": "service_role"},
    {"sub": "invalid"}, {"is_anonymous": True}, {"exp": 1},
])
def test_invalid_or_out_of_scope_signed_token_is_rejected(pilot, claims):
    client = pilot.client()
    client.cookies.set(COOKIE, pilot.token(**claims))
    assert client.get("/api/sessions").status_code == 401


def test_pilot_blocks_cross_origin_and_external_publication(pilot, monkeypatch, tmp_path):
    client = pilot.client(ALICE)
    monkeypatch.setattr(api, "EXPORTS", tmp_path / "exports")

    def unexpected(*args, **kwargs):
        pytest.fail("Private approval called a publisher")

    monkeypatch.setattr(api, "open_github_issue", unexpected)
    assert client.post("/api/start", headers={"Origin": "https://other.example.test"}).status_code == 403
    for path in ("/api/board", "/api/shared/old-token", "/b/old-token", "/board"):
        assert client.get(path).status_code == 404
    assert client.post("/api/offer", json={}).status_code == 404
    assert client.post("/api/start?mode=voice").status_code == 404
    sid = client.post("/api/start").json()["id"]
    assert client.post(f"/api/end?s={sid}").status_code == 200
    assert client.get(f"/api/export/me.json?s={sid}").status_code == 403
    assert client.get(f"/api/export/builders.md?s={sid}").status_code == 403
    approved = client.post(f"/api/approve?s={sid}").json()
    assert approved["share"] is None and approved["approved"]
    assert not api.EXPORTS.exists()
    assert client.get(f"/api/export/me.json?s={sid}").status_code == 403
    assert client.get(f"/api/export/builders.md?s={sid}").status_code == 200


def test_owner_scoped_routes_and_durable_resume(pilot, monkeypatch):
    owner, other = pilot.client(ALICE), pilot.client(BOB)
    sid = owner.post("/api/start").json()["id"]
    other_sid = other.post("/api/start").json()["id"]
    assert [row["id"] for row in owner.get("/api/sessions").json()] == [sid]
    assert [row["id"] for row in other.get("/api/sessions").json()] == [other_sid]
    answer = "Fictional merchants retry when a form resets."
    assert owner.post(f"/api/turn?s={sid}", json={"text": answer}).status_code == 200

    monkeypatch.setattr(api, "store", PilotStore(SUPABASE, "sb_secret_fixture"))
    for method, route, body in [
        ("GET", "state", None), ("GET", "brief", None), ("GET", "export/me.json", None),
        ("POST", "end", None), ("POST", "mode", None), ("POST", "approve", None),
        ("POST", "turn", {"text": "wrong owner"}),
        ("POST", "choice", {"span": "fictional", "choice": "remove"}),
        ("POST", "edit", {"audience": "me", "problem": "wrong owner"}),
    ]:
        query = "&mode=text" if route == "mode" else ""
        assert other.request(method, f"/api/{route}?s={sid}{query}", json=body).status_code == 404

    reply = owner.get(f"/api/state?s={sid}")
    assert reply.headers["Cache-Control"] == "no-store"
    assert [t["text"] for t in reply.json()["transcript"]][-2:] == [answer, "How often does this happen?"]
    assert other.get(f"/api/state?s={sid}").status_code == 404  # cached after the owner loaded it


def test_write_failure_is_visible_and_retried_without_duplicate_answer(pilot):
    client = pilot.client(ALICE)
    sid = client.post("/api/start").json()["id"]
    start = pilot.remote.rows[(ALICE, sid)]["data"]
    pilot.remote.failing = True
    assert client.post("/api/start").status_code == 503
    answer = "The sample form resets."
    result = client.post(f"/api/turn?s={sid}", json={"text": answer})
    assert result.status_code == 503 and result.headers["Birbal-Save-Pending"] == "1"
    assert pilot.remote.rows[(ALICE, sid)]["data"] == start
    assert client.get(f"/api/state?s={sid}").json()["save_pending"]
    assert client.post(f"/api/turn?s={sid}", json={"text": answer}).status_code == 409
    assert client.get("/api/sessions").status_code == 503
    pilot.remote.failing = False
    asyncio.run(api.store.flush_dirty())
    assert not client.get(f"/api/state?s={sid}").json()["save_pending"]
    assert [turn["text"] for turn in pilot.remote.rows[(ALICE, sid)]["data"]["ledger"]["transcript"]].count(answer) == 1
