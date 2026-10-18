"""Birbal HTTP API + static UI. Run: uv run uvicorn api:app --app-dir server --port 8000"""
import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse, PlainTextResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from brain import keys, llm  # noqa: E402
from brain.prompts import OPENING_LINE, OPENING_LINES, TALKER_SYSTEM, talker_messages  # noqa: E402
from brain.cloud import make_store, open_github_issue  # noqa: E402
from brain.session import Session, SessionStore  # noqa: E402

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("birbal.api")
WEB = ROOT / "web"
EXPORTS = Path(os.getenv("BIRBAL_EXPORTS", ROOT / "exports"))

app = FastAPI(title="Birbal")


@app.on_event("startup")
async def _autosave():
    asyncio.create_task(store.autosave())
store = make_store(Path(os.getenv("BIRBAL_DATA", ROOT / "data" / "sessions")))
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


def _get(s: str) -> Session:
    sess = store.get(s)
    if sess is None:
        raise HTTPException(404, "Interview not found. Start a new one.")
    return sess


def _cancel(sid: str) -> None:
    t = _tasks.pop(sid, None)
    if t and not t.done():
        t.cancel()


@app.get("/")
def landing():
    return FileResponse(WEB / "landing.html")


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
    import bot
    voice, why = bot.voice_ready()
    return {"llm": llm.available(), "voice": voice, "why": why,
            "keys": {p: len(keys.pool(p)) for p in keys.ENV},
            "tts": os.getenv("TTS_PROVIDER", "aura"),
            "model": {"gemini": llm.GEMINI_TALKER_MODEL, "groq": llm.GROQ_MODEL, "alt": llm.ALT_MODEL}.get(llm.talker_provider(), "none")}


@app.get("/api/sessions")
def sessions():
    return store.list()


Lang = Literal["auto", "en", "hi", "kn"]


@app.post("/api/start")
async def start(mode: Literal["text", "voice", "demo"] = "text", lang: Lang = "auto"):
    sess = store.create()
    sess.start(mode, lang)
    if mode == "text":  # in voice mode the bot speaks the opening and records it itself
        sess.add_birbal(OPENING_LINES.get(lang, OPENING_LINE))
    if mode == "demo":
        _tasks[sess.id] = asyncio.create_task(_replay(sess))
        await asyncio.sleep(0.05)
    return {"id": sess.id, **sess.state()}


async def _replay(sess: Session, pace: float = 1.0):
    await sess.replay(pace=pace)
    store.save(sess)


@app.get("/api/state")
def state(s: str):
    return _get(s).state()


@app.post("/api/mode")
async def switch_mode(s: str, mode: Literal["text", "voice"]):
    """Switch mid-interview (e.g. mic fails -> keep going by typing). Same session, same transcript."""
    sess = _get(s)  # the browser's pc.close() already stops the voice pipeline cleanly
    sess.mode = mode
    if sess.status == "error":
        sess.status, sess.last_error = "listening", ""
    return sess.state()


@app.post("/api/turn")
async def turn(s: str, t: TurnIn):
    """Text mode: owner types, Birbal replies."""
    sess = _get(s)
    if not llm.available():
        raise HTTPException(503, "No LLM key configured. Add GOOGLE_API_KEY or GROQ_API_KEY to .env.")
    if sess.ended:
        raise HTTPException(409, "This interview has ended. Start a new one.")
    sess.add_owner(t.text)
    sess.status = "thinking"
    import bot
    reply = await llm.complete_text(TALKER_SYSTEM + bot.language_line(sess.lang),
                                    talker_messages(sess.ledger.transcript, sess.note()))
    sess.status = "listening"
    if not reply:
        sess.retract_owner()  # the UI restores the text for a retry; don't record it twice
        raise HTTPException(502, "Birbal couldn't reply (LLM error or rate limit). Try again.")
    sess.add_birbal(reply)
    return sess.state()


@app.post("/api/end")
async def end(s: str):
    sess = _get(s)
    _cancel(s)
    sess.finish()
    await sess.settle()
    store.save(sess)
    return sess.state()


# --- brief ---------------------------------------------------------------

def _version_json(v) -> dict:
    return {"brief": v.brief.model_dump(), "leaks": [l.model_dump() for l in v.leaks], "safe": v.safe,
            "markdown": v.markdown}


async def _brief(sess: Session) -> dict:
    vs = await sess.brief()
    return {"id": sess.id, "share": f"/b/{sess.share_token}" if sess.share_token else None,
            "versions": {a: _version_json(v) for a, v in vs.items()},
            "private": [x.model_dump() for x in sess.ledger.sensitive],
            "approved": sess.approved, "created": sess.created, "elapsed": round(sess.minutes() * 60)}


@app.get("/api/brief")
async def brief(s: str):
    sess = _get(s)
    out = await _brief(sess)
    if sess.ended:
        store.save(sess)  # persist LLM extras once computed
    return out


@app.post("/api/choice")
async def choice(s: str, c: ChoiceIn):
    sess = _get(s)
    sess.set_choice(c.span, c.choice)
    if sess.approved and hasattr(store, "unpost_board"):
        store.unpost_board(sess)  # a changed brief leaves the board until re-approved
    sess.approved = None
    store.save(sess)
    return await _brief(sess)


@app.post("/api/edit")
async def edit(s: str, e: EditIn):
    sess = _get(s)
    if e.problem.strip():
        sess.overrides[e.audience] = e.problem.strip()
    else:  # empty = restore the generated statement
        sess.overrides.pop(e.audience, None)
    sess.approved, sess.share_token = None, None
    return await _brief(sess)


@app.post("/api/approve")
async def approve(s: str):
    sess = _get(s)
    vs = await sess.brief()
    leaking = [a for a, v in vs.items() if a != "me" and not v.safe]
    if leaking:  # enforced server-side, not just by the disabled button
        raise HTTPException(409, f"Secret found in: {', '.join(leaking)}. Fix it before approving.")
    sess.approved = {"at": time.strftime("%Y-%m-%d %H:%M:%S"),
                     "private": {x.span: x.choice or "generalise" for x in sess.ledger.sensitive}}
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
async def export(s: str, audience: Audience, fmt: Literal["md", "json"]):
    sess = _get(s)
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
    import bot
    ok, why = bot.voice_ready(lang)
    return {"ready": ok, "why": why, "ice": _ice_servers()}


@app.post("/api/offer")
async def offer(body: dict):
    import bot
    from pipecat.transports.smallwebrtc.request_handler import SmallWebRTCRequest
    data = body.get("request_data") or {}
    sess = _get(str(data.get("session", "")))
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
