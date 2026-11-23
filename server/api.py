"""Birbal HTTP API + static UI. Run: uv run uvicorn api:app --app-dir server --port 8000"""
import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

import jwt  # noqa: E402
from fastapi import FastAPI, HTTPException, Request, Response  # noqa: E402
from fastapi.concurrency import run_in_threadpool  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from brain import keys, llm  # noqa: E402
from brain.auth import COOKIE, configured_auth  # noqa: E402
from brain.prompts import OPENING_LINE, OPENING_LINES, TALKER_SYSTEM, talker_messages  # noqa: E402
from brain.cloud import PilotStorageError, PilotStore, make_store, open_github_issue  # noqa: E402
from brain.session import Session  # noqa: E402

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("birbal.api")
WEB = ROOT / "web"
EXPORTS = Path(os.getenv("BIRBAL_EXPORTS", ROOT / "exports"))

auth = configured_auth()
DATA = Path(os.getenv("BIRBAL_DATA", ROOT / "data" / "sessions"))
store = PilotStore(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"]) if auth else make_store(DATA)
if auth:
    logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    active_store = store
    stop_autosave = asyncio.Event()
    is_pilot = isinstance(active_store, PilotStore)
    autosave = asyncio.create_task(active_store.autosave(stop=stop_autosave) if is_pilot else active_store.autosave())
    try:
        yield
    finally:
        if is_pilot:
            stop_autosave.set()
            await autosave
            await active_store.drain()
        else:
            autosave.cancel()
            await asyncio.gather(autosave, return_exceptions=True)


app = FastAPI(title="Birbal", lifespan=lifespan)


@app.middleware("http")
async def private_pilot(request: Request, call_next):
    request.state.owner = None
    if auth is None:
        return await call_next(request)
    path = request.url.path
    if path.startswith(("/api/shared/", "/b/")) or path in {"/board", "/api/board"}:
        return JSONResponse({"detail": "Sharing is disabled in the private pilot."}, status_code=404)
    if path.startswith("/static/") and path not in {"/static/app.css", "/static/common.js", "/static/voice.js"}:
        return JSONResponse({"detail": "Not found."}, status_code=404)
    api_request = path.startswith("/api/")
    if api_request and request.method not in {"GET", "HEAD"} and request.headers.get("origin") != auth.origin:
        return JSONResponse({"detail": "This request must come from Birbal."}, status_code=403)
    public = {"/api/health", "/api/auth/code", "/api/auth/verify", "/api/auth/logout"}
    if path in {"/start", "/review"} or (api_request and path not in public):
        try:
            request.state.owner, _ = await run_in_threadpool(auth.verify, request.cookies.get(COOKIE, ""))
        except jwt.PyJWTError:
            if api_request:
                return JSONResponse({"detail": "Sign in to continue."}, status_code=401,
                                    headers={"Cache-Control": "no-store"})
            query = urlencode({"next": path + ("?" + request.url.query if request.url.query else "")})
            return RedirectResponse("/login?" + query, headers={"Cache-Control": "no-store"})
    if path == "/api/offer":
        return JSONResponse({"detail": "Voice is disabled in the private pilot."}, status_code=404)
    response = await call_next(request)
    if api_request or path in {"/start", "/review", "/login"}:
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "same-origin"
    return response


@app.exception_handler(PilotStorageError)
async def storage_unavailable(request: Request, error: PilotStorageError):
    return JSONResponse({"detail": "Interview storage is unavailable. Try again shortly."}, status_code=503)


_tasks: dict[str, asyncio.Task] = {}  # replay / voice task per session

Audience = Literal["me", "builders", "everyone"]


class TurnIn(BaseModel):
    text: str


class ChoiceIn(BaseModel):
    span: str
    choice: Literal["keep", "generalise", "remove"]


class EditIn(BaseModel):
    audience: Audience
    problem: str


async def _get(s: str, request: Request) -> Session:
    owner = request.state.owner
    sess = await run_in_threadpool(store.get_owned, s, owner) if auth else store.get(s)
    if sess is None or sess.owner_id != owner:
        raise HTTPException(404, "Interview not found. Start a new one.")
    return sess


async def _save(sess: Session, *, accepted_turn: bool = False) -> None:
    if not auth:
        store.save(sess)
        return
    try:
        await store.persist(sess)
    except PilotStorageError as exc:
        if accepted_turn:
            raise HTTPException(
                503, "Your answer has not been saved yet. Keep this interview open while Birbal retries.",
                headers={"Birbal-Save-Pending": "1"},
            ) from exc
        raise


def _cancel(sid: str) -> None:
    t = _tasks.pop(sid, None)
    if t and not t.done():
        t.cancel()


@app.get("/")
def landing():
    return RedirectResponse("/start") if auth else FileResponse(WEB / "landing.html")


class SignInEmail(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class SignInCode(SignInEmail):
    code: str = Field(pattern=r"^[0-9]{6,10}$")


@app.get("/login")
def login():
    return FileResponse(WEB / "login.html") if auth else RedirectResponse("/start")


@app.post("/api/auth/code", status_code=204)
def auth_code(body: SignInEmail):
    if auth is None:
        raise HTTPException(404)
    auth.send_code(body.email.strip().lower())


@app.post("/api/auth/verify", status_code=204)
def auth_verify(body: SignInCode, response: Response):
    if auth is None:
        raise HTTPException(404)
    token, lifetime = auth.exchange(body.email.strip().lower(), body.code)
    response.set_cookie(COOKIE, token, max_age=lifetime, httponly=True, secure=auth.secure, samesite="lax")


@app.post("/api/auth/logout", status_code=204)
def auth_logout(response: Response):
    response.delete_cookie(COOKIE, httponly=True, secure=bool(auth and auth.secure), samesite="lax")


@app.get("/api/auth/status")
def auth_status():
    return {"private": auth is not None}


@app.get("/start")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/review")
def review():
    return FileResponse(WEB / "review.html")


@app.get("/b/{token}")
def shared_page(token: str):
    return FileResponse(WEB / "review.html")


@app.get("/board")
def board_page():
    return FileResponse(WEB / "board.html")


@app.get("/api/board")
def board():
    """Approved, redacted problems: the public teaser plus a link to the builder brief."""
    rows = store.board() if hasattr(store, "board") else []
    return [{"id": r["id"], "posted": r["posted"], "teaser": r["teaser"], "link": f"/b/{r['share_token']}"} for r in rows]


@app.get("/api/shared/{token}")
async def shared(token: str):
    """Read-only view of an APPROVED brief: builder and public versions only. Never the owner version."""
    sess = store.by_token(token)
    if sess is None or not sess.approved:
        raise HTTPException(404, "This link is no longer valid. The owner may have changed the brief.")
    vs = await sess.brief()
    out = {a: _version_json(vs[a]) for a in ("builders", "everyone")}
    if not all(v["safe"] for v in out.values()):
        raise HTTPException(409, "This brief is being revised.")
    return {"versions": out, "approved": {"at": sess.approved["at"]}, "created": sess.created}


# --- interview -----------------------------------------------------------

@app.get("/api/health")
def health():
    if auth:
        return {"llm": llm.available(), "voice": False, "why": "Start by typing in the private pilot.",
                "model": "private pilot"}
    import bot
    voice, why = bot.voice_ready()
    return {"llm": llm.available(), "voice": voice, "why": why,
            "keys": {p: len(keys.pool(p)) for p in keys.ENV},
            "tts": os.getenv("TTS_PROVIDER", "aura"),
            "model": {"gemini": llm.GEMINI_TALKER_MODEL, "groq": llm.GROQ_MODEL, "alt": llm.ALT_MODEL}.get(llm.talker_provider(), "none")}


@app.get("/api/sessions")
def sessions(request: Request):
    return store.list_owned(request.state.owner) if auth else store.list()


Lang = Literal["auto", "en", "hi", "kn"]


@app.post("/api/start")
async def start(request: Request, mode: Literal["text", "voice", "demo"] = "text", lang: Lang = "auto"):
    if auth and mode != "text":
        raise HTTPException(404, "Only typing is enabled in the private pilot.")
    sess = store.create(request.state.owner) if auth else store.create()
    sess.start(mode, lang)
    if mode == "text":  # in voice mode the bot speaks the opening and records it itself
        sess.add_birbal(OPENING_LINES.get(lang, OPENING_LINE))
    if auth:
        try:
            await _save(sess)
        except PilotStorageError:
            store.live.pop(sess.id, None)
            raise
    if mode == "demo":
        _tasks[sess.id] = asyncio.create_task(_replay(sess))
        await asyncio.sleep(0.05)
    return {"id": sess.id, **sess.state()}


async def _replay(sess: Session, pace: float = 1.0):
    await sess.replay(pace=pace)
    store.save(sess)


@app.get("/api/state")
async def state(s: str, request: Request):
    sess = await _get(s, request)
    if sess.pre_turn_state is not None:
        return {**sess.pre_turn_state, "status": "thinking", "save_pending": sess.status != "thinking"}
    return {**sess.state(), "save_pending": sess.save_failed}


@app.post("/api/mode")
async def switch_mode(s: str, mode: Literal["text", "voice"], request: Request):
    """Switch mid-interview (e.g. mic fails -> keep going by typing). Same session, same transcript."""
    sess = await _get(s, request)  # the browser's pc.close() already stops the voice pipeline cleanly
    if auth and mode != "text":
        raise HTTPException(404, "Voice is disabled in the private pilot.")
    sess.mode = mode
    if sess.status == "error":
        sess.status, sess.last_error = "listening", ""
    return sess.state()


@app.post("/api/turn")
async def turn(s: str, t: TurnIn, request: Request):
    """Text mode: owner types, Birbal replies."""
    sess = await _get(s, request)
    if not llm.available():
        raise HTTPException(503, "No LLM key configured. Add GOOGLE_API_KEY or GROQ_API_KEY to .env.")
    if sess.ended:
        raise HTTPException(409, "This interview has ended. Start a new one.")
    if auth and (sess.status == "thinking" or sess.save_lock.locked() or sess.save_failed):
        raise HTTPException(409, "Wait for Birbal to finish saving or replying before sending another answer.")
    if auth:
        sess.pre_turn_state = sess.state()
    sess.add_owner(t.text)
    sess.status = "thinking"
    import bot
    reply = await llm.complete_text(TALKER_SYSTEM + bot.language_line(sess.lang),
                                    talker_messages(sess.ledger.transcript, sess.note()))
    sess.status = "listening"
    if not reply:
        sess.retract_owner()  # the UI restores the text for a retry; don't record it twice
        sess.pre_turn_state = None
        raise HTTPException(502, "Birbal couldn't reply (LLM error or rate limit). Try again.")
    sess.add_birbal(reply)
    if auth:
        await _save(sess, accepted_turn=True)
    return sess.state()


@app.post("/api/end")
async def end(s: str, request: Request):
    sess = await _get(s, request)
    if auth and (sess.status == "thinking" or sess.save_lock.locked()):
        raise HTTPException(409, "Wait for Birbal to finish replying or saving before ending the interview.")
    _cancel(s)
    sess.finish()
    await sess.settle()
    await _save(sess)
    return sess.state()


# --- brief ---------------------------------------------------------------

def _version_json(v) -> dict:
    return {"brief": v.brief.model_dump(), "leaks": [l.model_dump() for l in v.leaks], "safe": v.safe,
            "markdown": v.markdown}


async def _brief(sess: Session) -> dict:
    vs = await sess.brief()
    return {"id": sess.id, "share": f"/b/{sess.share_token}" if sess.share_token and not auth else None,
            "versions": {a: _version_json(v) for a, v in vs.items()},
            "private": [x.model_dump() for x in sess.ledger.sensitive],
            "approved": sess.approved, "created": sess.created, "elapsed": round(sess.minutes() * 60)}


@app.get("/api/brief")
async def brief(s: str, request: Request):
    sess = await _get(s, request)
    out = await _brief(sess)
    if sess.ended:
        await _save(sess)  # persist LLM extras once computed
    return out


@app.post("/api/choice")
async def choice(s: str, c: ChoiceIn, request: Request):
    sess = await _get(s, request)
    sess.set_choice(c.span, c.choice)
    if not auth and sess.approved and hasattr(store, "unpost_board"):
        store.unpost_board(sess)  # a changed brief leaves the board until re-approved
    sess.approved = None
    await _save(sess)
    return await _brief(sess)


@app.post("/api/edit")
async def edit(s: str, e: EditIn, request: Request):
    sess = await _get(s, request)
    if e.problem.strip():
        sess.overrides[e.audience] = e.problem.strip()
    else:  # empty = restore the generated statement
        sess.overrides.pop(e.audience, None)
    sess.approved, sess.share_token = None, None
    if auth:
        await _save(sess)
    return await _brief(sess)


@app.post("/api/approve")
async def approve(s: str, request: Request):
    sess = await _get(s, request)
    if auth and not sess.ended:
        raise HTTPException(409, "End the interview before approving the brief.")
    vs = await sess.brief()
    leaking = [a for a, v in vs.items() if a != "me" and not v.safe]
    if leaking:  # enforced server-side, not just by the disabled button
        raise HTTPException(409, f"Secret found in: {', '.join(leaking)}. Fix it before approving.")
    sess.approved = {"at": time.strftime("%Y-%m-%d %H:%M:%S"),
                     "private": {x.span: x.choice or "generalise" for x in sess.ledger.sensitive}}
    if auth:
        await _save(sess)
        return await _brief(sess)
    store.mint_share(sess)
    EXPORTS.mkdir(exist_ok=True)
    for a, v in vs.items():
        (EXPORTS / f"birbal-{sess.id}-{a}.md").write_text(v.markdown)
        (EXPORTS / f"birbal-{sess.id}-{a}.json").write_text(json.dumps(_version_json(v), indent=2))
    # The consequential actions, only after approval: post to the problem board, open a builder issue.
    teaser = vs["everyone"].brief.problem
    sess.approved["board"] = bool(getattr(store, "post_board", None)) and store.post_board(sess, teaser, vs["builders"].markdown)
    b = vs["builders"].brief
    body = vs["builders"].markdown + "\n\n---\n" + "\n".join(f"- [ ] {o.question}" for o in b.open_questions)
    sess.approved["issue"] = open_github_issue(f"Problem: {teaser[:90]}", body, ["birbal", "problem-brief"])
    store.save(sess)
    return await _brief(sess)


@app.get("/api/export/{audience}.{fmt}")
async def export(s: str, audience: Audience, fmt: Literal["md", "json"], request: Request):
    sess = await _get(s, request)
    if auth and audience == "me":
        raise HTTPException(403, "The private owner brief is view-only in the pilot.")
    if audience != "me" and not sess.approved:
        raise HTTPException(403, "Approve the brief before exporting shareable versions.")
    v = (await sess.brief())[audience]
    name = f"birbal-{sess.id}-{audience}.{fmt}"
    body = v.markdown if fmt == "md" else json.dumps(_version_json(v), indent=2)
    return PlainTextResponse(body, media_type="text/markdown" if fmt == "md" else "application/json",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


# --- voice (SmallWebRTC, same process so the bot shares the session) -------
_webrtc = None


def _ice_servers() -> list[dict]:
    """STUN always; TURN when configured (TURN_URLS comma-separated, TURN_USERNAME, TURN_CREDENTIAL).
    A cloud host can't receive WebRTC audio directly; a TURN relay carries it over TCP/TLS 443."""
    servers = [{"urls": "stun:stun.l.google.com:19302"}]
    urls = [u.strip() for u in os.getenv("TURN_URLS", "").split(",") if u.strip()]
    if urls:
        servers.append({"urls": urls, "username": os.getenv("TURN_USERNAME", ""),
                        "credential": os.getenv("TURN_CREDENTIAL", "")})
    return servers


def _handler():
    global _webrtc
    if _webrtc is None:
        from pipecat.transports.smallwebrtc.connection import IceServer
        from pipecat.transports.smallwebrtc.request_handler import SmallWebRTCRequestHandler
        _webrtc = SmallWebRTCRequestHandler(ice_servers=[IceServer(**s) for s in _ice_servers()])
    return _webrtc


@app.get("/api/voice")
def voice_status(lang: Lang = "auto"):
    if auth:
        return {"ready": False, "why": "Voice is disabled in the private pilot.", "ice": []}
    import bot
    ok, why = bot.voice_ready(lang)
    return {"ready": ok, "why": why, "ice": _ice_servers()}


@app.post("/api/offer")
async def offer(body: dict, request: Request):
    import bot
    from pipecat.transports.smallwebrtc.request_handler import SmallWebRTCRequest
    data = body.get("request_data") or {}
    sess = await _get(str(data.get("session", "")), request)
    ok, why = bot.voice_ready(sess.lang)
    if not ok:
        raise HTTPException(503, why)

    async def on_connection(connection):
        _cancel(sess.id)
        _tasks[sess.id] = asyncio.create_task(bot.run_bot(connection, sess))

    req = SmallWebRTCRequest(sdp=body["sdp"], type=body["type"], pc_id=body.get("pc_id"),
                             restart_pc=body.get("restart_pc"), request_data=data)
    return await _handler().handle_web_request(request=req, webrtc_connection_callback=on_connection)


@app.patch("/api/offer")
async def ice(body: dict):
    from pipecat.transports.smallwebrtc.request_handler import IceCandidate, SmallWebRTCPatchRequest
    await _handler().handle_patch_request(SmallWebRTCPatchRequest(
        pc_id=body["pc_id"], candidates=[IceCandidate(**c) for c in body.get("candidates", [])]))
    return {"status": "success"}


app.mount("/static", StaticFiles(directory=WEB), name="static")
