"""Birbal HTTP API + static UI. Run: uv run uvicorn api:app --app-dir server --port 8000"""
import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse, PlainTextResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import AliasChoices, BaseModel, Field  # noqa: E402

from brain import keys, llm  # noqa: E402
from brain.prompts import OPENING_LINE, OPENING_LINES, TALKER_SYSTEM, talker_messages  # noqa: E402
from brain.cloud import make_store, open_github_issue  # noqa: E402
from brain.session import Session, SessionStore  # noqa: E402

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("birbal.api")
WEB = ROOT / "web"
EXPORTS = Path(os.getenv("BIRBAL_EXPORTS", ROOT / "exports"))

store = make_store(Path(os.getenv("BIRBAL_DATA", ROOT / "data" / "sessions")))
_replays: dict[str, asyncio.Task] = {}
_webrtc = None
VOICE_MAX_CONCURRENT = int(os.getenv("VOICE_MAX_CONCURRENT", "4"))
VOICE_MAX_SECONDS = float(os.getenv("VOICE_MAX_SECONDS", "900"))


@dataclass
class VoiceRun:
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None
    peer_id: str | None = None


_voice_runs: dict[str, VoiceRun] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    autosave = asyncio.create_task(store.autosave())
    try:
        yield
    finally:
        runs = list(_voice_runs.values())
        for run in runs:
            run.stop.set()
        replays = list(_replays.values())
        for task in [autosave, *replays]:
            task.cancel()
        await asyncio.gather(autosave, *replays, *(run.task for run in runs if run.task), return_exceptions=True)
        if _webrtc is not None:
            await _webrtc.close()


app = FastAPI(title="Birbal", lifespan=lifespan)

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


def _stop_voice(sid: str) -> None:
    if run := _voice_runs.get(sid):
        run.stop.set()


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
        _replays[sess.id] = asyncio.create_task(_replay(sess))
        await asyncio.sleep(0.05)
    return {"id": sess.id, **sess.state()}


async def _replay(sess: Session, pace: float = 1.0):
    try:
        await sess.replay(pace=pace)
        store.save(sess)
    finally:
        _replays.pop(sess.id, None)


@app.get("/api/state")
def state(s: str):
    return _get(s).state()


@app.post("/api/mode")
async def switch_mode(s: str, mode: Literal["text", "voice"]):
    """Switch mid-interview (e.g. mic fails -> keep going by typing). Same session, same transcript."""
    sess = _get(s)
    if sess.ended or sess.mode == "demo":
        raise HTTPException(409, "This interview cannot switch modes.")
    run = _voice_runs.get(s)
    if mode == "voice":
        if not run or not run.task or run.stop.is_set() or sess.status == "error":
            raise HTTPException(409, "Connect voice before switching to it.")
    elif sess.mode == "text" and not run:
        return sess.state()
    sess.mode = mode
    if mode == "text":
        _stop_voice(s)
        sess.status, sess.last_error, sess.interim = "listening", "", ""
        if not sess.ledger.transcript:
            sess.add_birbal(OPENING_LINES.get(sess.lang, OPENING_LINE))
        sess.dirty = True
    return sess.state()


@app.post("/api/turn")
async def turn(s: str, t: TurnIn):
    """Text mode: owner types, Birbal replies."""
    sess = _get(s)
    if sess.ended or sess.mode != "text":
        raise HTTPException(409, "Only an active text interview accepts typed answers.")
    run = _voice_runs.get(s)
    if sess.status == "thinking" or (run and not run.stop.is_set()):
        raise HTTPException(409, "Wait for the current reply or voice connection.")
    if not llm.available():
        raise HTTPException(503, "No LLM key configured. Add GOOGLE_API_KEY or GROQ_API_KEY to .env.")
    sess.add_owner(t.text)
    sess.status = "thinking"
    import bot
    reply = await llm.complete_text(TALKER_SYSTEM + bot.language_line(sess.lang),
                                    talker_messages(sess.ledger.transcript, sess.note()))
    if sess.ended:
        return sess.state()
    sess.status = "listening"
    if not reply:
        sess.retract_owner()  # the UI restores the text for a retry; don't record it twice
        raise HTTPException(502, "Birbal couldn't reply (LLM error or rate limit). Try again.")
    sess.add_birbal(reply)
    return sess.state()


@app.post("/api/end")
async def end(s: str):
    sess = _get(s)
    sess.finish()
    _stop_voice(s)
    if task := _replays.get(s):
        task.cancel()
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


async def _run_voice(connection, sess: Session, run: VoiceRun) -> None:
    import bot

    stop = asyncio.create_task(run.stop.wait())
    worker = asyncio.create_task(bot.run_bot(connection, sess))
    started = time.monotonic()
    outcome = "stopped"
    try:
        done, _ = await asyncio.wait(
            (worker, stop), timeout=VOICE_MAX_SECONDS, return_when=asyncio.FIRST_COMPLETED,
        )
        if worker in done:
            await worker
            outcome = "disconnected"
        elif not done:
            outcome = "time_limit"
    except Exception as exc:
        outcome = "pipeline_error"
        log.warning("Voice worker failed (%s)", type(exc).__name__)
    finally:
        stop.cancel()
        worker.cancel()
        try:
            await asyncio.wait_for(connection.disconnect(), timeout=5)
        except Exception as exc:
            log.warning("Voice peer cleanup failed (%s)", type(exc).__name__)
        await asyncio.gather(stop, worker, return_exceptions=True)
        if not sess.ended and sess.mode == "voice":
            sess.interim = ""
            if sess.status != "error":
                sess.status = "error"
                sess.last_error = ("Voice reached its time limit." if outcome == "time_limit"
                                   else "Voice disconnected.")
        _voice_runs.pop(sess.id, None)
        log.info("Voice session closed: outcome=%s duration_ms=%d", outcome, (time.monotonic() - started) * 1000)


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


class VoiceRequestData(BaseModel):
    session: str = Field(min_length=1, max_length=128)


class VoiceOffer(BaseModel):
    sdp: str = Field(min_length=1, max_length=65536)
    type: Literal["offer"]
    request_data: VoiceRequestData = Field(validation_alias=AliasChoices("request_data", "requestData"))
    pc_id: str | None = Field(default=None, max_length=128)
    restart_pc: bool = False


@app.post("/api/offer")
async def offer(body: VoiceOffer):
    import bot
    from pipecat.transports.smallwebrtc.request_handler import SmallWebRTCRequest
    sess = _get(body.request_data.session)
    if sess.ended or sess.mode == "demo" or (sess.status == "thinking" and sess.mode == "text"):
        raise HTTPException(409, "This interview cannot connect to voice right now.")
    ok, why = bot.voice_ready(sess.lang)
    if not ok:
        raise HTTPException(503, why)

    existing = _voice_runs.get(sess.id)
    if existing:
        if not body.pc_id or body.pc_id != existing.peer_id or existing.stop.is_set():
            raise HTTPException(409, "Voice is already connecting or active for this interview.")
        if body.restart_pc:
            # Pipecat's full peer replacement fires "disconnected" and stops this pipeline.
            existing.stop.set()
            raise HTTPException(409, "Voice connection lost. Continue by typing or start voice again.")
        run = existing
    else:
        if body.pc_id:
            raise HTTPException(404, "Voice connection no longer exists. Reconnect without the old peer.")
        if len(_voice_runs) >= VOICE_MAX_CONCURRENT:
            raise HTTPException(503, "Voice is busy. Continue by typing or try again shortly.")
        run = _voice_runs[sess.id] = VoiceRun()

    async def on_connection(connection):
        run.peer_id = connection.pc_id
        if not run.stop.is_set():
            sess.mode, sess.status, sess.last_error = "voice", "listening", ""
            sess.dirty = True
        run.task = asyncio.create_task(_run_voice(connection, sess, run))

    req = SmallWebRTCRequest(sdp=body.sdp, type=body.type, pc_id=body.pc_id,
                             request_data=body.request_data.model_dump())
    try:
        answer = await _handler().handle_web_request(request=req, webrtc_connection_callback=on_connection)
        if run.stop.is_set():
            raise HTTPException(409, "Voice was stopped before it connected.")
        if not answer or not run.task:
            raise HTTPException(502, "Voice could not start.")
        return answer
    except BaseException:
        if existing is None:
            if run.task:
                run.stop.set()
            else:
                _voice_runs.pop(sess.id, None)
        raise


class VoiceIceCandidate(BaseModel):
    candidate: str = Field(max_length=2048)
    sdp_mid: str | None = Field(max_length=128)
    sdp_mline_index: int | None = Field(ge=0)


class VoiceIcePatch(BaseModel):
    pc_id: str = Field(min_length=1, max_length=128)
    candidates: list[VoiceIceCandidate] = Field(max_length=64)


@app.patch("/api/offer")
async def ice(body: VoiceIcePatch):
    from pipecat.transports.smallwebrtc.request_handler import IceCandidate, SmallWebRTCPatchRequest
    await _handler().handle_patch_request(SmallWebRTCPatchRequest(
        pc_id=body.pc_id, candidates=[IceCandidate(**c.model_dump()) for c in body.candidates]))
    return {"status": "success"}


app.mount("/static", StaticFiles(directory=WEB), name="static")
