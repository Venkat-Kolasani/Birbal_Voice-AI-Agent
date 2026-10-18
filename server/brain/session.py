"""One interview session: transcript, ledger, gap report, brief. Transport-agnostic."""
import asyncio
import json
import logging
import secrets
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import llm, scribe
from .brief import Version, canonical, leak_check, redact, to_markdown, versions
from .controller import gap_report, merge
from .prompts import controller_note
from .schema import DIMENSION_LABELS, DIMENSIONS, KIND_LABELS, GapReport, Ledger, ScribeOutput, Turn

log = logging.getLogger("birbal.session")
FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


class Session:
    def __init__(self, sid: Optional[str] = None) -> None:
        self.id = sid or uuid.uuid4().hex[:10]
        self.created = datetime.now().isoformat(timespec="seconds")
        self.mode = "text"
        self.lang = "auto"
        self.last_error = ""
        self.interim = ""  # live partial transcript while the owner is speaking (voice)
        self.share_token: Optional[str] = None
        self.dirty = False  # unsaved changes (autosave picks these up)
        self.extras: dict = {}
        self._extras_turns = -1
        self._elapsed_offset = 0.0  # seconds, for sessions restored from disk
        self.ledger = Ledger()
        self.started: Optional[float] = None
        self.ended_at: Optional[float] = None
        self.status = "idle"  # idle | listening | thinking | speaking | ended
        self.ended = False
        self.approved: Optional[dict] = None
        self._tasks: set[asyncio.Task] = set()
        self._owner_turns = 0
        self._brief_cache: Optional[dict[str, Version]] = None
        self._lock = asyncio.Lock()
        self.overrides: dict[str, str] = {}  # audience -> hand-edited problem statement

    # --- timeline ---------------------------------------------------------
    def start(self, mode: str = "text", lang: str = "auto") -> None:
        self.__init__(self.id)
        self.mode, self.lang = mode, lang
        self.started = time.monotonic()
        self.status = "listening"

    def minutes(self) -> float:
        if not self.started:
            return self._elapsed_offset / 60
        return (self._elapsed_offset + (self.ended_at or time.monotonic()) - self.started) / 60

    def _t(self) -> float:
        return round(self.minutes() * 60, 1)

    def last_birbal(self) -> str:
        return next((t.text for t in reversed(self.ledger.transcript) if t.role == "birbal"), "")

    def add_birbal(self, text: str) -> None:
        # The resume line ("I'm back. <last question>") is said aloud but not recorded twice.
        if text.startswith("I'm back. ") and self.ledger.transcript and \
                text[len("I'm back. "):].strip() == self.last_birbal():
            return
        if text.strip():
            self.ledger.transcript.append(Turn(role="birbal", text=text.strip(), t=self._t()))
            self.dirty = True

    def add_owner(self, text: str, scribe_out: Optional[ScribeOutput] = None) -> None:
        """Record an owner turn and run the Scribe in the background (never blocks the Talker)."""
        if not text.strip():
            return
        asked = self.last_birbal()
        self.interim = ""
        self.dirty = True
        self.ledger.transcript.append(Turn(role="owner", text=text.strip(), t=self._t()))
        self._owner_turns += 1
        turn = self._owner_turns
        self._brief_cache = None
        if scribe_out is not None:
            merge(self.ledger, scribe_out, turn)
            return
        task = asyncio.create_task(self._scribe(asked, text, turn))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def retract_owner(self) -> None:
        """Undo the last owner turn after a failed Talker reply (the owner will resend it)."""
        if self.ledger.transcript and self.ledger.transcript[-1].role == "owner":
            self.ledger.transcript.pop()
            self.ledger.claims = [c for c in self.ledger.claims if c.turn != self._owner_turns]
            self._owner_turns -= 1
            self.dirty = True

    async def _scribe(self, asked: str, said: str, turn: int) -> None:
        try:
            out = await scribe.run(self.ledger, asked, said)
            async with self._lock:
                merge(self.ledger, out, turn)
                self.dirty = True
        except Exception:
            log.exception("scribe turn %s failed; skipped", turn)

    async def settle(self, timeout: float = 15.0) -> None:
        """Wait for in-flight Scribe calls (used before building the brief)."""
        if self._tasks:
            await asyncio.wait(list(self._tasks), timeout=timeout)

    # --- views ------------------------------------------------------------
    def gap(self) -> GapReport:
        # Consent is asked once. If the owner's next answer didn't settle it, default to hidden (fail closed) and
        # move on; the Review page can change it. Nagging three times costs the interview.
        for s in self.ledger.sensitive:
            if s.choice is None and s.asked_turn is not None and self._owner_turns > s.asked_turn:
                s.choice, s.auto, s.decided_turn = "generalise", True, self._owner_turns
                self.dirty = True
        return gap_report(self.ledger, self.minutes())

    def note(self) -> str:
        gr = self.gap()
        if gr.focus == "consent":
            gr.pending_consent[0].asked_turn = self._owner_turns
        return controller_note(gr, self.ledger)

    def state(self) -> dict:
        gr = self.gap()
        rows = []
        for d in DIMENSIONS:
            claims = [c for c in self.ledger.claims if c.dimension == d]
            best = max(claims, key=lambda c: (c.kind == "observed" and c.anchored, c.turn), default=None)
            rows.append({
                "key": d, "label": DIMENSION_LABELS[d], "score": gr.scores[d],
                "focus": gr.focus == d,
                "text": best.value if best else "",
                "kind": best.kind if best else "",
                "kind_label": KIND_LABELS[best.kind] if best else "",
                "quote": best.evidence_quote if best else "",
                "count": len(claims),
            })
        return {
            "status": self.status, "ended": self.ended, "mode": self.mode, "lang": self.lang, "error": self.last_error,
            "interim": self.interim,
            "elapsed": round(self.minutes() * 60),
            "focus": gr.focus, "why": gr.why, "ready_for_readback": gr.ready_for_readback,
            "clear": sum(1 for d in DIMENSIONS if gr.scores[d] == 2),
            "rows": rows,
            "private": [s.model_dump() for s in self.ledger.sensitive],
            "open": [u.model_dump() for u in self.ledger.unknowns],
            "contradictions": [c.model_dump() for c in self.ledger.contradictions],
            "parked": self.ledger.parked,
            "transcript": [t.model_dump() for t in self.ledger.transcript[-8:]],
            "llm": llm.available(),
        }

    async def brief(self) -> dict[str, Version]:
        if self._brief_cache is None:
            await self.settle()
            # Extras (LLM-written problem / where to start) only refresh when the interview itself changed.
            if llm.available() and self._extras_turns != self._owner_turns:
                b = redact(canonical(self.ledger), self.ledger.sensitive, "builders")
                self.extras = await scribe.extras([(l.label, l.kind, l.text) for l in b.lines]) or self.extras
                self._extras_turns = self._owner_turns
            self._brief_cache = versions(self.ledger, self.extras)
        out = {}
        for aud, v in self._brief_cache.items():
            if aud in self.overrides:
                b = v.brief.model_copy(deep=True)
                b.problem = self.overrides[aud]
                v = Version(brief=b, leaks=leak_check(b, self.ledger.sensitive),
                            markdown=to_markdown(b, self.ledger.sensitive))
            out[aud] = v
        return out

    def set_choice(self, span: str, choice: str) -> None:
        for s in self.ledger.sensitive:
            if s.span == span:
                s.choice, s.decided_turn = choice, self._owner_turns
        self._brief_cache = None
        self.share_token = None  # any change after approval invalidates the shared link
        self.overrides.clear()

    # --- persistence ------------------------------------------------------
    def to_dict(self) -> dict:
        return {"id": self.id, "created": self.created, "mode": self.mode, "lang": self.lang, "elapsed_s": round(self.minutes() * 60),
                "ended": self.ended, "approved": self.approved, "overrides": self.overrides, "extras": self.extras,
                "owner_turns": self._owner_turns, "share_token": self.share_token,
                "ledger": self.ledger.model_dump()}

    @classmethod
    def from_dict(cls, d: dict) -> "Session":
        s = cls(d["id"])
        s.created, s.mode, s.approved = d["created"], d.get("mode", "text"), d.get("approved")
        s.lang = d.get("lang", "auto")
        s.share_token = d.get("share_token")
        s.overrides, s.extras = d.get("overrides", {}), d.get("extras", {})
        s._owner_turns = s._extras_turns = d.get("owner_turns", 0)
        s.ledger = Ledger.model_validate(d["ledger"])
        s._elapsed_offset = d.get("elapsed_s", 0)
        if d.get("ended"):
            s.status, s.ended = "ended", True
        elif s.ledger.transcript:
            s.status = "listening"  # in-progress interview restored after a restart
        return s

    def summary(self) -> dict:
        # Shown on a shared screen, so use the redacted builder wording, never the owner's raw words.
        title = redact(canonical(self.ledger, self.extras), self.ledger.sensitive, "builders").problem
        return {"id": self.id, "created": self.created, "ended": self.ended, "approved": bool(self.approved),
                "elapsed": round(self.minutes() * 60), "title": title or "Untitled interview",
                "clear": self.state()["clear"], "private": len(self.ledger.sensitive)}

    # --- replay -----------------------------------------------------------
    async def replay(self, name: str = "demo_interview", pace: float = 1.0) -> None:
        """Play a fixture interview as if live. pace = seconds per word-ish unit (0 = instant)."""
        data = json.loads((FIXTURES / f"{name}.json").read_text())
        self.start()
        for turn in data["turns"]:
            self.status = "speaking"
            self.add_birbal(turn["birbal"])
            await asyncio.sleep(pace * min(4.0, len(turn["birbal"]) / 40))
            self.status = "listening"
            words = turn["owner"].split()
            for i in range(len(words)):  # simulate live transcription, word by word
                self.interim = " ".join(words[:i + 1])
                await asyncio.sleep(pace * min(3.0, len(turn["owner"]) / 50) / max(1, len(words)))
            self.add_owner(turn["owner"], ScribeOutput.model_validate(turn.get("scribe") or {}))
            self.status = "thinking"
            await asyncio.sleep(pace * 0.6)
        self.finish()

    def finish(self) -> None:
        self.status, self.ended = "ended", True
        self.ended_at = self.ended_at or time.monotonic()


class SessionStore:
    """Live sessions in memory, finished ones as JSON on disk (data/sessions/<id>.json)."""

    def __init__(self, root: Path):
        self.root = root
        self.live: dict[str, Session] = {}

    def create(self) -> Session:
        s = Session()
        self.live[s.id] = s
        return s

    def get(self, sid: str) -> Optional[Session]:
        if sid in self.live:
            return self.live[sid]
        f = self.root / f"{sid}.json"
        if not sid.isalnum() or not f.exists():  # isalnum: ids come from URLs, never allow path tricks
            return None
        s = Session.from_dict(json.loads(f.read_text()))
        self.live[sid] = s
        return s

    def mint_share(self, s: Session) -> str:
        s.share_token = secrets.token_urlsafe(16)
        self.save(s)
        return s.share_token

    def by_token(self, token: str) -> Optional[Session]:
        if not token or len(token) < 16:
            return None
        for s in self.live.values():
            if s.share_token and secrets.compare_digest(s.share_token, token):
                return s
        if self.root.exists():
            for f in self.root.glob("*.json"):
                try:
                    d = json.loads(f.read_text())
                except (OSError, json.JSONDecodeError):
                    continue
                if d.get("share_token") and secrets.compare_digest(d["share_token"], token):
                    return self.get(d["id"])
        return None

    def save_dirty(self) -> int:
        """Persist live sessions with unsaved changes (in-progress interviews survive a restart)."""
        n = 0
        for s in list(self.live.values()):
            if s.dirty and s.ledger.transcript:
                s.dirty = False
                self.save(s)
                n += 1
        return n

    async def autosave(self, every: float = 5.0) -> None:
        while True:
            await asyncio.sleep(every)
            try:
                self.save_dirty()
            except Exception:
                log.exception("autosave failed")

    def save(self, s: Session) -> None:
        s.dirty = False
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.root / f"{s.id}.json.tmp"
        tmp.write_text(json.dumps(s.to_dict(), indent=1))
        tmp.replace(self.root / f"{s.id}.json")  # atomic: never leave a half-written session

    def list(self, limit: int = 8) -> list[dict]:
        ids = {f.stem for f in self.root.glob("*.json")} if self.root.exists() else set()
        ids |= {i for i, s in self.live.items() if s.ledger.transcript}
        out = []
        for i in ids:
            try:
                s = self.get(i)
            except Exception:
                log.warning("skipping unreadable session %s", i)
                continue
            if s and s.ledger.claims:
                out.append(s.summary())
        return sorted(out, key=lambda x: x["created"], reverse=True)[:limit]
