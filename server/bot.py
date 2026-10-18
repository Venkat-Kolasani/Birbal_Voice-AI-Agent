"""Birbal voice pipeline (Pipecat 1.12): mic -> VAD -> Deepgram STT -> Talker LLM -> TTS -> speaker.

Wiring found in pipecat 1.12.0 source/examples; see docs/DECISIONS.md D-008. The Scribe runs off the
hot path via Session.add_owner (asyncio task); the controller note is injected per turn by ControllerNote.
"""
import os
import time

from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.turns.user_start import MinWordsUserTurnStartStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.frames.frames import (BotStartedSpeakingFrame, BotStoppedSpeakingFrame, InterimTranscriptionFrame,
                                   LLMContextFrame, LLMMessagesAppendFrame, TranscriptionFrame, TTSSpeakFrame,
                                   UserStartedSpeakingFrame)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair, LLMUserAggregatorParams
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.workers.runner import WorkerRunner

from brain import keys
from brain.llm import GEMINI_TALKER_MODEL, GROQ_MODEL, TALKER_TEMPERATURE, talker_provider
from brain.prompts import OPENING_LINE, OPENING_LINES, TALKER_SYSTEM
from brain.session import Session

NOTE_PREFIX = "[controller]"


# Voice resends the whole context every turn. Keeping only the recent turns holds a call near ~1.2k tokens, which
# fits Groq's 8K TPM; older facts reach the Talker through the controller note's "Last noted" / "Already clear".
MAX_CONTEXT_MESSAGES = int(os.getenv("MAX_CONTEXT_MESSAGES", "10"))


def rewrite(msgs: list[dict], note: str, last: str | None, keep: int = MAX_CONTEXT_MESSAGES) -> list[dict]:
    """Attach this turn's controller note to the last user message, removing last turn's note; keep recent turns only.

    The note rides on a user message (exactly like text mode's talker_messages) rather than a "developer" message:
    Pipecat sends "developer" as-is to Groq (supports_developer_role=True), which may reject it.
    """
    suffix = lambda n: "\n\n" + n  # noqa: E731
    role = lambda m: m.get("role") if isinstance(m, dict) else None  # noqa: E731
    out = []
    for m in msgs:
        # Pipecat may store provider-specific objects (LLMSpecificMessage, e.g. Gemini thought signatures) in the
        # context. They are not dicts; keep them exactly as they are.
        c = m.get("content") if isinstance(m, dict) else None
        if last is not None and isinstance(c, str) and c.endswith(suffix(last)):
            m = {**m, "content": c[: -len(suffix(last))]}
        out.append(m)
    if keep and len(out) > keep:
        out = out[-keep:]
        while out and role(out[0]) != "user":  # never start the window on a model turn
            out = out[1:]
    for i in range(len(out) - 1, -1, -1):
        if role(out[i]) == "user" and isinstance(out[i].get("content"), str):
            out[i] = {**out[i], "content": out[i]["content"] + suffix(note)}
            return out
    return out + [{"role": "user", "content": note}]  # no user turn yet


class ControllerNote(FrameProcessor):
    """Before each Talker run, swap last turn's controller note for a fresh one (keeps context small)."""

    def __init__(self, session: Session):
        super().__init__()
        self.session = session
        self._last: str | None = None

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMContextFrame) and direction == FrameDirection.DOWNSTREAM:
            note = self.session.note()
            frame.context.set_messages(rewrite(frame.context.messages, note, self._last))
            self._last = note
        await self.push_frame(frame, direction)


class StatusTap(FrameProcessor):
    """Mirror speaking state into the session for the UI orb."""

    def __init__(self, session: Session):
        super().__init__()
        self.session = session

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, BotStartedSpeakingFrame):
            self.session.status = "speaking"
        elif isinstance(frame, (BotStoppedSpeakingFrame, UserStartedSpeakingFrame)):
            self.session.status = "listening"
        await self.push_frame(frame, direction)


LANGS = {  # code -> (name for the LLM, TTS/STT locale)
    # Mid-interview switching: follow the owner, but keep Roman script so the en-IN voice (Hinglish-native) stays natural.
    "auto": ("the owner's language. If they switch language mid-way (say, to Hindi), switch with them, but write it in "
             "Roman script, Hinglish style, so the voice stays natural. English if unsure", "en-IN"),
    "en": ("English", "en-IN"),
    "hi": ("Hindi (write it in Devanagari script; technical words may stay in English)", "hi-IN"),
    "kn": ("Kannada (write it in Kannada script; technical words may stay in English)", "kn-IN"),
}


def language_line(lang: str) -> str:
    return f"\nConduct the interview in {LANGS.get(lang, LANGS['auto'])[0]}. The owner may mix in English."


class TranscriptTap(FrameProcessor):
    """Live partial transcript for the UI, so the owner sees Birbal hearing them while they speak."""

    def __init__(self, session: Session):
        super().__init__()
        self.session = session
        self._final = ""

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, InterimTranscriptionFrame):
            self.session.interim = (self._final + " " + frame.text).strip()
            self.session.status = "listening"
        elif isinstance(frame, TranscriptionFrame):
            self._final = (self._final + " " + frame.text).strip()
            self.session.interim = self._final
        elif isinstance(frame, BotStartedSpeakingFrame):
            self._final = ""
        await self.push_frame(frame, direction)


def make_stt(lang: str):
    if os.getenv("STT_PROVIDER", "deepgram") == "sarvam" or lang == "kn":
        from pipecat.services.sarvam.stt import SarvamSTTService
        # codemix keeps Hinglish as spoken (no translation), so evidence quotes stay verbatim.
        return SarvamSTTService(api_key=keys.pick("sarvam"), mode=os.getenv("SARVAM_STT_MODE", "codemix"),
                                settings=SarvamSTTService.Settings(model=os.getenv("SARVAM_STT_MODEL", "saaras:v3")))
    from pipecat.services.deepgram.stt import DeepgramSTTService
    return DeepgramSTTService(api_key=keys.pick("deepgram"), settings=DeepgramSTTService.Settings(
        model=os.getenv("DEEPGRAM_MODEL", "nova-3"),
        language=os.getenv("DEEPGRAM_LANGUAGE", "multi")))  # multi = Hindi/English code-switching


def make_llm(lang: str):
    system = TALKER_SYSTEM + language_line(lang)
    if talker_provider() == "gemini":
        from pipecat.services.google.llm import GoogleLLMService
        return GoogleLLMService(api_key=keys.pick("gemini"), settings=GoogleLLMService.Settings(
            model=GEMINI_TALKER_MODEL, system_instruction=system, temperature=TALKER_TEMPERATURE))
    if talker_provider() == "alt":
        from pipecat.services.openai.llm import OpenAILLMService
        from brain.llm import ALT_BASE, ALT_MODEL
        return OpenAILLMService(api_key=keys.pick("alt"), base_url=ALT_BASE, settings=OpenAILLMService.Settings(
            model=ALT_MODEL, system_instruction=system, temperature=TALKER_TEMPERATURE))
    from pipecat.services.groq.llm import GroqLLMService
    return GroqLLMService(api_key=keys.pick("groq"), settings=GroqLLMService.Settings(
        model=GROQ_MODEL, system_instruction=system, temperature=TALKER_TEMPERATURE,
        **({"reasoning_effort": os.getenv("GROQ_REASONING_EFFORT", "low")} if "gpt-oss" in GROQ_MODEL else {})))


def tts_provider(lang: str) -> str:
    p = os.getenv("TTS_PROVIDER", "aura")
    # Aura speaks English only; Hindi/Kannada need Sarvam.
    return "sarvam" if lang in ("hi", "kn") and p == "aura" and keys.has("sarvam") else p


def make_tts(lang: str):
    provider = tts_provider(lang)
    if provider == "sarvam":
        from pipecat.services.sarvam.tts import SarvamTTSService
        locale = LANGS.get(lang, LANGS["auto"])[1] if lang != "auto" else os.getenv("SARVAM_LANGUAGE", "en-IN")
        return SarvamTTSService(api_key=keys.pick("sarvam"), settings=SarvamTTSService.Settings(
            model="bulbul:v3", voice=os.getenv("SARVAM_VOICE", "shubh"), language=locale,
            pace=float(os.getenv("SARVAM_PACE", "1.0"))))
    if provider == "elevenlabs":
        from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
        return ElevenLabsTTSService(api_key=keys.pick("elevenlabs"), settings=ElevenLabsTTSService.Settings(
            model="eleven_flash_v2_5", voice=os.environ["ELEVENLABS_VOICE_ID"]))
    from pipecat.services.deepgram.tts import DeepgramTTSService
    return DeepgramTTSService(api_key=keys.pick("deepgram"), settings=DeepgramTTSService.Settings(
        voice=os.getenv("AURA_VOICE", "aura-2-helena-en")))


def voice_ready(lang: str = "auto") -> tuple[bool, str]:
    stt = "sarvam" if os.getenv("STT_PROVIDER", "deepgram") == "sarvam" or lang == "kn" else "deepgram"
    if not keys.has(stt):
        extra = " (Kannada speech needs Sarvam)" if lang == "kn" else ""
        return False, f"Add {keys.ENV[stt]} to .env for voice{extra}."
    if not (keys.has("gemini") or keys.has("groq") or keys.has("alt")):
        return False, "Add GOOGLE_API_KEY, GROQ_API_KEY or ALT_LLM_KEY to .env for voice."
    tts = tts_provider(lang)
    if lang in ("hi", "kn") and tts == "aura":
        return False, "Hindi/Kannada voice needs SARVAM_API_KEY (Aura speaks English only)."
    if not keys.has({"aura": "deepgram"}.get(tts, tts)):
        return False, f"TTS_PROVIDER={tts} needs {keys.ENV[{'aura': 'deepgram'}.get(tts, tts)]} in .env."
    return True, ""


async def run_bot(connection, session: Session) -> None:
    transport = SmallWebRTCTransport(params=TransportParams(audio_in_enabled=True, audio_out_enabled=True),
                                     webrtc_connection=connection)
    # Resuming a session (back from typing, or after a refresh): give the Talker the recent conversation.
    history = [{"role": "assistant" if t.role == "birbal" else "user", "content": t.text}
               for t in session.ledger.transcript[-MAX_CONTEXT_MESSAGES:]]
    while history and history[0]["role"] != "user":
        history = history[1:]
    context = LLMContext(messages=history or None)
    resuming = any(t.role == "owner" for t in session.ledger.transcript)
    # Turn-taking: Pipecat's default stop strategy is the bundled smart-turn model (judges whether the sentence is
    # finished), so VAD only needs a short pause (Pipecat default 0.2 s; we use 0.4 s for people who pause to think).
    # Barge-in needs a few real words, so venue noise or a cough doesn't cut Birbal off.
    vad = SileroVADAnalyzer(params=VADParams(stop_secs=float(os.getenv("VAD_STOP_SECS", "0.4"))))
    user_agg, assistant_agg = LLMContextAggregatorPair(context, user_params=LLMUserAggregatorParams(
        vad_analyzer=vad, user_idle_timeout=float(os.getenv("IDLE_NUDGE_SECS", "8")),
        user_turn_strategies=UserTurnStrategies(
            start=[MinWordsUserTurnStartStrategy(min_words=int(os.getenv("BARGE_IN_MIN_WORDS", "2")))])))

    pipeline = Pipeline([
        transport.input(), make_stt(session.lang), TranscriptTap(session), user_agg, ControllerNote(session), make_llm(session.lang),
        make_tts(session.lang),
        transport.output(), StatusTap(session), assistant_agg,
    ])
    worker = PipelineWorker(pipeline, params=PipelineParams(enable_metrics=True, enable_usage_metrics=True))
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    idle_nudged = False

    recent_errors: list[float] = []

    @worker.event_handler("on_pipeline_error")
    async def on_error(worker, frame):
        # A fatal error, or 2 errors within 10 s, means voice is broken: the UI then switches to typing in the same
        # interview. A single transient hiccup is only logged. Text mode has its own key/provider failover.
        err = str(getattr(frame, "error", "voice error"))[:200]
        logger.error(f"voice pipeline error: {err}")
        now = time.monotonic()
        recent_errors[:] = [t for t in recent_errors if now - t < 10] + [now]
        if getattr(frame, "fatal", False) or len(recent_errors) >= 2:
            session.status, session.last_error = "error", err

    @transport.event_handler("on_client_connected")
    async def on_connected(transport, client):
        logger.info("voice client connected")
        # Deterministic opening, no LLM call. TTSSpeakFrame appends the spoken text to context by default.
        if resuming:
            last_q = session.last_birbal() or "Where were we?"
            await worker.queue_frames([TTSSpeakFrame(f"I'm back. {last_q}")])
        else:
            await worker.queue_frames([TTSSpeakFrame(OPENING_LINES.get(session.lang, OPENING_LINE))])

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(transport, client):
        logger.info("voice client disconnected")
        # Disconnect is not the end: "Type instead" and page refresh both close the connection mid-interview.
        # Ending stays the owner's explicit act (/api/end).
        if not session.ended:
            session.status = "listening"
        await runner.cancel()

    @user_agg.event_handler("on_user_turn_stopped")
    async def on_user_turn(aggregator, strategy, message):
        nonlocal idle_nudged
        idle_nudged = False
        if message.content:
            session.status = "thinking"
            session.add_owner(message.content)

    @assistant_agg.event_handler("on_assistant_turn_stopped")
    async def on_assistant_turn(aggregator, message):
        if message.content:
            session.add_birbal(message.content)

    @user_agg.event_handler("on_user_turn_idle")
    async def on_idle(aggregator):
        nonlocal idle_nudged
        if idle_nudged or session.ended:
            return
        idle_nudged = True
        await aggregator.push_frame(LLMMessagesAppendFrame([{
            "role": "user",
            "content": f"{NOTE_PREFIX} The owner has been quiet for a while. Gently say: take your time, or we can skip this one."}],
            run_llm=True))

    await runner.run()
    logger.info("voice pipeline finished")
