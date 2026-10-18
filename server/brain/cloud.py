"""Supabase session store + problem board + GitHub issue. Each is a thin REST call with the local file store as
fallback, so a dead network never breaks an interview."""
import json
import logging
import os
from pathlib import Path
from typing import Optional

import httpx

from .session import Session, SessionStore

log = logging.getLogger("birbal.cloud")


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
