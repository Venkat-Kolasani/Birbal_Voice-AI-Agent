import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from pipecat.processors.frame_processor import FrameProcessor

import api
import bot
from brain.session import SessionStore


class Peer:
    def __init__(self, pc_id):
        self.pc_id = pc_id
        self.closed = False

    async def disconnect(self):
        self.closed = True


class Signaling:
    def __init__(self):
        self.peers = []
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()

    async def handle_web_request(self, *, request, webrtc_connection_callback):
        self.entered.set()
        await self.release.wait()
        peer = Peer(str(len(self.peers) + 1))
        self.peers.append(peer)
        await webrtc_connection_callback(peer)
        return {"type": "answer", "sdp": "fixture", "pc_id": peer.pc_id}


@pytest.fixture
def voice(monkeypatch, tmp_path):
    signaling = Signaling()
    monkeypatch.setattr(api, "store", SessionStore(tmp_path))
    monkeypatch.setattr(api, "_voice_runs", {})
    monkeypatch.setattr(api, "_handler", lambda: signaling)
    monkeypatch.setattr(bot, "voice_ready", lambda lang: (True, ""))

    async def wait_for_disconnect(peer, session):
        await asyncio.Event().wait()

    monkeypatch.setattr(bot, "run_bot", wait_for_disconnect)
    return signaling


def client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="http://test")


async def start(c, mode="voice"):
    return (await c.post("/api/start", params={"mode": mode})).json()["id"]


async def offer(c, sid):
    return await c.post("/api/offer", json={"type": "offer", "sdp": "fixture", "request_data": {"session": sid}})


def test_caps_voice_without_blocking_text_and_releases_slot_on_switch(voice, monkeypatch):
    monkeypatch.setattr(api, "VOICE_MAX_CONCURRENT", 1)

    async def check():
        async with client() as c:
            sid = await start(c)
            assert (await offer(c, sid)).status_code == 200
            run = api._voice_runs[sid]
            assert (await offer(c, sid)).status_code == 409
            other = await start(c, "text")
            assert (await offer(c, other)).status_code == 503
            sess = api.store.get(sid)
            sess.add_birbal("What happened?")
            before = list(sess.ledger.transcript)
            assert (await c.post(f"/api/mode?s={sid}&mode=text")).json()["mode"] == "text"
            await asyncio.wait_for(run.task, 1)
            assert voice.peers[0].closed and sid not in api._voice_runs
            assert sess.ledger.transcript == before
            assert (await offer(c, other)).status_code == 200
            next_run = api._voice_runs[other]
            await c.post(f"/api/end?s={other}")
            await asyncio.wait_for(next_run.task, 1)
            assert (await offer(c, other)).status_code == 409

    asyncio.run(check())


def test_switching_during_pending_offer_does_not_restart_voice(voice):
    voice.release.clear()

    async def check():
        async with client() as c:
            sid = await start(c)
            pending = asyncio.create_task(offer(c, sid))
            await asyncio.wait_for(voice.entered.wait(), 1)
            run = api._voice_runs[sid]
            assert (await c.post(f"/api/mode?s={sid}&mode=text")).json()["mode"] == "text"
            voice.release.set()
            assert (await pending).status_code == 409
            await asyncio.wait_for(run.task, 1)
            state = (await c.get(f"/api/state?s={sid}")).json()
            assert state["mode"] == "text" and state["status"] == "listening"
            assert len(state["transcript"]) == 1 and voice.peers[0].closed

    asyncio.run(check())


@pytest.mark.parametrize("cancel_resume", [False, True])
def test_immediate_resume_waits_for_previous_peer_cleanup(voice, monkeypatch, cancel_resume):
    monkeypatch.setattr(api, "VOICE_MAX_CONCURRENT", 1)

    async def check():
        async with client() as c:
            sid = await start(c)
            assert (await offer(c, sid)).status_code == 200
            old = api._voice_runs[sid]
            closing, finish = asyncio.Event(), asyncio.Event()
            disconnect = voice.peers[0].disconnect

            async def delayed_disconnect():
                closing.set()
                await finish.wait()
                await disconnect()

            voice.peers[0].disconnect = delayed_disconnect
            assert (await c.post(f"/api/mode?s={sid}&mode=text")).status_code == 200
            await asyncio.wait_for(closing.wait(), 1)
            resume = asyncio.create_task(offer(c, sid))
            await asyncio.sleep(0)
            assert not resume.done() and len(voice.peers) == 1
            if cancel_resume:
                assert (await c.post(f"/api/mode?s={sid}&mode=text")).status_code == 200
            finish.set()
            result = await asyncio.wait_for(resume, 1)
            if cancel_resume:
                assert result.status_code == 409 and "canceled" in result.json()["detail"]
                assert api.store.get(sid).mode == "text" and sid not in api._voice_runs
                return
            assert result.status_code == 200
            assert voice.peers[0].closed and api._voice_runs[sid] is not old
            new = api._voice_runs[sid]
            await c.post(f"/api/end?s={sid}")
            await asyncio.wait_for(new.task, 1)

    asyncio.run(check())


def test_offer_validation_and_failed_restart_release_the_peer(voice):
    async def check():
        async with client() as c:
            sid = await start(c)
            body = {"type": "offer", "sdp": "fixture", "requestData": {"session": sid}}
            assert (await c.post("/api/offer", json={**body, "requestData": {"session": []}})).status_code == 422
            assert not api._voice_runs
            assert (await c.post("/api/offer", json=body)).status_code == 200
            run = api._voice_runs[sid]
            retry = {**body, "pc_id": run.peer_id, "restart_pc": True}
            assert (await c.post("/api/offer", json=retry)).status_code == 409
            await asyncio.wait_for(run.task, 1)
            assert voice.peers[0].closed
            assert api.store.get(sid).status == "error"

    asyncio.run(check())


def test_rtvi_handshake_on_real_local_webrtc_peer(monkeypatch, tmp_path):
    class Passthrough(FrameProcessor):
        async def process_frame(self, frame, direction):
            await super().process_frame(frame, direction)
            await self.push_frame(frame, direction)

    monkeypatch.setattr(api, "store", SessionStore(tmp_path))
    monkeypatch.setattr(api, "_webrtc", None)
    monkeypatch.setattr(api, "_ice_servers", lambda: [])
    monkeypatch.setattr(api, "_voice_runs", {})
    monkeypatch.setattr(bot, "voice_ready", lambda lang: (True, ""))
    for name in ("make_stt", "make_llm", "make_tts"):
        monkeypatch.setattr(bot, name, lambda lang: Passthrough())

    async def check():
        async with api.lifespan(api.app), client() as c:
            sid = await start(c, "text")
            peer = RTCPeerConnection(configuration=RTCConfiguration(iceServers=[]))
            peer.addTransceiver("audio")
            channel = peer.createDataChannel("chat")
            ready = asyncio.Event()

            @channel.on("open")
            def client_ready():
                channel.send(json.dumps({
                    "label": "rtvi-ai", "type": "client-ready", "id": "ready",
                    "data": {"version": "2.2.0"},
                }))

            @channel.on("message")
            def bot_ready(message):
                if json.loads(message).get("type") == "bot-ready":
                    ready.set()

            try:
                await peer.setLocalDescription(await peer.createOffer())
                response = await c.post("/api/offer", json={
                    "type": "offer", "sdp": peer.localDescription.sdp, "requestData": {"session": sid},
                })
                assert response.status_code == 200
                answer = response.json()
                await peer.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))
                await asyncio.wait_for(ready.wait(), 5)
                run = api._voice_runs[sid]
                response = await c.post(f"/api/mode?s={sid}&mode=text")
                assert response.json()["mode"] == "text"
                await asyncio.wait_for(run.task, 5)
                assert sid not in api._voice_runs
            finally:
                await peer.close()

    asyncio.run(check())


@pytest.mark.parametrize("failed", [False, True])
def test_worker_timeout_or_failure_routes_to_text(voice, monkeypatch, caplog, failed):
    monkeypatch.setattr(api, "VOICE_MAX_SECONDS", 0.01)
    if failed:
        async def fail(peer, session):
            raise ValueError("synthetic provider input should not appear in logs")

        monkeypatch.setattr(bot, "run_bot", fail)

    async def check():
        async with client() as c:
            sid = await start(c)
            assert (await offer(c, sid)).status_code == 200
            run = api._voice_runs[sid]
            await asyncio.wait_for(run.task, 1)
            state = (await c.get(f"/api/state?s={sid}")).json()
            assert state["status"] == "error" and not state["ended"]
            assert voice.peers[0].closed and sid not in api._voice_runs
            if not failed:
                assert state["error"] == "Voice reached its time limit."
            state = (await c.post(f"/api/mode?s={sid}&mode=text")).json()
            assert state["status"] == "listening" and state["mode"] == "text"

    asyncio.run(check())
    assert "synthetic provider input" not in caplog.text


@pytest.mark.parametrize("audio_starts", [False, True])
def test_opening_audio_deadline(monkeypatch, audio_starts):
    class Events:
        def __init__(self):
            self.events = {}

        def event_handler(self, name):
            def register(callback):
                self.events[name] = callback
                return callback
            return register

    class Transport(Events):
        def input(self):
            return None

        def output(self):
            return None

    class Worker(Events):
        async def queue_frames(self, frames):
            if audio_starts:
                status_tap.clear_reply_timeout()

    class Runner:
        async def add_workers(self, worker):
            pass

        async def run(self):
            await transport.events["on_client_connected"](transport, None)
            await asyncio.sleep(0.03)

        async def cancel(self):
            pass

    transport, worker = Transport(), Worker()
    user, assistant = Events(), Events()
    status_tap = SimpleNamespace()
    monkeypatch.setattr(bot, "REPLY_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(bot, "SmallWebRTCTransport", lambda **kwargs: transport)
    monkeypatch.setattr(bot, "SileroVADAnalyzer", lambda **kwargs: None)
    monkeypatch.setattr(bot, "LLMContextAggregatorPair", lambda *args, **kwargs: (user, assistant))
    monkeypatch.setattr(bot, "Pipeline", lambda processors: processors)
    monkeypatch.setattr(bot, "PipelineWorker", lambda *args, **kwargs: worker)
    monkeypatch.setattr(bot, "WorkerRunner", lambda **kwargs: Runner())
    monkeypatch.setattr(bot, "StatusTap", lambda session, clear: setattr(status_tap, "clear_reply_timeout", clear))
    for name in ("make_stt", "make_llm", "make_tts"):
        monkeypatch.setattr(bot, name, lambda lang: None)
    session = api.Session()
    session.start(mode="voice")
    asyncio.run(bot.run_bot(None, session))
    assert session.status == ("listening" if audio_starts else "error")
