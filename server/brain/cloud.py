"""Supabase session store + problem board + GitHub issue. Each is a thin REST call with the local file store as
fallback, so a dead network never breaks an interview."""
import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

import httpx

from .session import Session, SessionStore

log = logging.getLogger("birbal.cloud")


class PilotStorageError(Exception):
    pass


class PilotStore:
    """Private pilot rows have no file fallback and are keyed by authenticated owner."""

    def __init__(self, url: str, key: str):
        self.base = url.rstrip("/") + "/rest/v1/pilot_interviews"
        self.headers = {"apikey": key}
        # Only legacy JWT service-role keys are used as bearer tokens, not sb_secret_* keys.
        if not key.startswith("sb_secret_"):
            self.headers["Authorization"] = f"Bearer {key}"
        self.live: dict[str, Session] = {}

    def create(self, owner: str) -> Session:
        session = Session(uuid4().hex, owner)
        self.live[session.id] = session
        return session

    def _rows(self, method: str, *, params: dict, **kwargs):
        try:
            headers = {**self.headers, "Prefer": "resolution=merge-duplicates,return=minimal"} if method == "POST" else self.headers
            response = httpx.request(method, self.base, headers=headers, params=params, timeout=5, **kwargs)
            response.raise_for_status()
            if method == "GET":
                rows = response.json()
                if not isinstance(rows, list):
                    raise ValueError("Expected rows")
                return rows
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("Private interview storage failed (%s %s)", method, type(exc).__name__)
            raise PilotStorageError from exc

    @staticmethod
    def _restore(row: dict) -> Session:
        return Session.from_dict({**row["data"], "id": row["id"], "owner_id": row["owner_id"]})

    def get_owned(self, sid: str, owner: str) -> Session | None:
        if len(sid) != 32 or any(ch not in "0123456789abcdef" for ch in sid):
            return None
        if live := self.live.get(sid):
            return live if live.owner_id == owner else None
        rows = self._rows("GET", params={"owner_id": f"eq.{owner}", "id": f"eq.{sid}",
                                         "select": "id,owner_id,data"})
        if not rows or rows[0]["owner_id"] != owner or rows[0]["id"] != sid:
            return None
        return self.live.setdefault(sid, self._restore(rows[0]))

    def list_owned(self, owner: str, limit: int = 8) -> list[dict]:
        rows = self._rows("GET", params={"owner_id": f"eq.{owner}", "select": "id,owner_id,data",
                                         "order": "updated_at.desc,id", "limit": str(limit)})
        return [self._restore(row).summary() for row in rows if row["owner_id"] == owner]

    async def persist(self, session: Session) -> None:
        if not session.owner_id:
            raise PilotStorageError
        async with session.save_lock:
            data = session.to_dict()
            data.pop("owner_id")
            session.dirty = False
            try:
                await asyncio.to_thread(
                    self._rows, "POST", params={"on_conflict": "owner_id,id"},
                    json={"id": session.id, "owner_id": session.owner_id,
                          "updated_at": datetime.now(UTC).isoformat(), "data": data},
                )
            except (PilotStorageError, asyncio.CancelledError):
                session.dirty = session.save_failed = True
                raise
            session.save_failed = False
            session.pre_turn_state = None

    async def autosave(self, *, stop: asyncio.Event, every: float = 5.0) -> None:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=every)
            except TimeoutError:
                await self.flush_dirty(stop=stop)

    async def flush_dirty(self, *, stop: asyncio.Event | None = None) -> None:
        for session in list(self.live.values()):
            if stop and stop.is_set():
                break
            if session.dirty and session.status != "thinking":
                try:
                    await self.persist(session)
                except PilotStorageError:
                    pass

    async def drain(self) -> None:
        await asyncio.gather(*(session.settle(timeout=3) for session in self.live.values()))
        try:
            async with asyncio.timeout(10):
                await self.flush_dirty()
        except TimeoutError:
            log.warning("Private pilot shutdown reached the save deadline.")
        if any(session.dirty for session in self.live.values()):
            log.warning("Private pilot shutdown left unsaved changes.")


class SupabaseStore(SessionStore):
    """Files stay as the write-through cache; Supabase is the durable copy and the source for recent briefs."""

    def __init__(self, root: Path, url: str, key: str):
        super().__init__(root)
        self.base = url.rstrip("/") + "/rest/v1"
        self.headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json",
                        "Prefer": "resolution=merge-duplicates,return=minimal"}
        self.ok = True  # flips off after a failure; retried on the next save

    def _req(self, method: str, path: str, **kw) -> Optional[httpx.Response]:
        try:
            r = httpx.request(method, self.base + path, headers=self.headers, timeout=6, **kw)
            r.raise_for_status()
            self.ok = True
            return r
        except Exception as e:
            log.warning("supabase %s %s failed: %.120s", method, path, e)
            self.ok = False
            return None

    def save(self, s: Session) -> None:
        super().save(s)
        d = s.to_dict()
        self._req("POST", "/sessions", json={"id": s.id, "ended": s.ended, "approved": bool(s.approved),
                                               "share_token": s.share_token, "updated": "now()", "data": d})

    def get(self, sid: str) -> Optional[Session]:
        s = super().get(sid)
        if s is not None or not sid.isalnum():
            return s
        r = self._req("GET", f"/sessions?id=eq.{sid}&select=data")
        rows = r.json() if r is not None else []
        if not rows:
            return None
        s = Session.from_dict(rows[0]["data"])
        self.live[sid] = s
        return s

    def by_token(self, token: str) -> Optional[Session]:
        s = super().by_token(token)
        if s is not None or not token or len(token) < 16:
            return s
        r = self._req("GET", f"/sessions?share_token=eq.{token}&select=data")
        rows = r.json() if r is not None else []
        return self.get(rows[0]["data"]["id"]) if rows else None

    def list(self, limit: int = 8) -> "list[dict]":
        r = self._req("GET", f"/sessions?select=data&order=updated.desc&limit={limit}")
        if r is None:
            return super().list(limit)
        out = []
        for row in r.json():
            try:
                s = self.live.get(row["data"]["id"]) or Session.from_dict(row["data"])
                if s.ledger.claims:
                    out.append(s.summary())
            except Exception:
                log.warning("skipping unreadable cloud session")
        return out

    # --- problem board -----------------------------------------------------
    def post_board(self, s: Session, teaser: str, builder_md: str) -> bool:
        r = self._req("POST", "/board", json={"id": s.id, "teaser": teaser, "builder_md": builder_md,
                                              "share_token": s.share_token, "posted": "now()"})
        return r is not None

    def unpost_board(self, s: Session) -> None:
        self._req("DELETE", f"/board?id=eq.{s.id}")

    def board(self, limit: int = 50) -> "list[dict]":
        r = self._req("GET", f"/board?select=id,posted,teaser,share_token&order=posted.desc&limit={limit}")
        return r.json() if r is not None else []


def make_store(root: Path) -> SessionStore:
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY")
    if url and key:
        return SupabaseStore(root, url, key)
    return SessionStore(root)


# --- GitHub issue on approve ------------------------------------------------

def open_github_issue(title: str, body: str, labels: list[str]) -> Optional[str]:
    """Create an issue in GITHUB_REPO; returns its URL, or None if not configured / failed. Never raises."""
    token, repo = os.getenv("GITHUB_TOKEN"), os.getenv("GITHUB_REPO")
    if not token or not repo:
        return None
    try:
        r = httpx.post(f"https://api.github.com/repos/{repo}/issues", timeout=10,
                       headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                       json={"title": title[:120], "body": body, "labels": labels})
        r.raise_for_status()
        return r.json().get("html_url")
    except Exception as e:
        log.warning("github issue failed: %.160s", e)
        return None
