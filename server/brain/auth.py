"""Invite-only Supabase Auth. Only the short-lived access token reaches the browser."""

import os
import time
from urllib.parse import urlsplit
from uuid import UUID

import httpx
import jwt
from fastapi import HTTPException

COOKIE = "birbal_session"


def https_origin(value: str) -> str:
    parts = urlsplit(value)
    local = parts.hostname in {"localhost", "127.0.0.1", "::1"}
    if not parts.hostname or parts.username or parts.password or parts.path or parts.query or parts.fragment:
        raise ValueError("Expected a bare origin without a trailing slash.")
    if parts.scheme != "https" and not (parts.scheme == "http" and local):
        raise ValueError("HTTPS is required except on localhost.")
    return value


class SupabaseAuth:
    def __init__(self, url: str, publishable: str, app_origin: str):
        self.issuer = https_origin(url.rstrip("/")) + "/auth/v1"
        self.origin = https_origin(app_origin.rstrip("/"))
        self.secure = self.origin.startswith("https://")
        self.headers = {"apikey": publishable}
        self.keys = jwt.PyJWKClient(self.issuer + "/.well-known/jwks.json", lifespan=300, timeout=3)

    def verify(self, token: str) -> tuple[str, int]:
        if not token or len(token) > 4096:
            raise jwt.InvalidTokenError("Invalid token length")
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg")
        if algorithm not in {"ES256", "RS256"} or not header.get("kid"):
            raise jwt.InvalidTokenError("An asymmetric signing key is required")
        key = self.keys.get_signing_key_from_jwt(token)
        claims = jwt.decode(token, key, algorithms=[algorithm], audience="authenticated",
                            issuer=self.issuer, options={"require": ["sub", "exp", "iat"]})
        if claims.get("role") != "authenticated" or claims.get("is_anonymous"):
            raise jwt.InvalidTokenError("Not an authenticated account")
        try:
            return str(UUID(claims["sub"])), max(0, int(claims["exp"] - time.time()))
        except (TypeError, ValueError) as exc:
            raise jwt.InvalidTokenError("Invalid account") from exc

    def _post(self, path: str, data: dict) -> httpx.Response:
        try:
            response = httpx.post(self.issuer + path, headers=self.headers, json=data, timeout=5)
        except httpx.RequestError as exc:
            raise HTTPException(503, "Sign-in is temporarily unavailable.") from exc
        if response.status_code >= 500:
            raise HTTPException(503, "Sign-in is temporarily unavailable.")
        return response

    def send_code(self, email: str) -> None:
        # The same response for admitted and unknown addresses prevents account enumeration.
        self._post("/otp", {"email": email, "create_user": False})

    def exchange(self, email: str, code: str) -> tuple[str, int]:
        response = self._post("/verify", {"email": email, "token": code, "type": "email"})
        if response.status_code == 429:
            raise HTTPException(429, "Too many sign-in attempts. Wait before trying again.")
        if not response.is_success:
            raise HTTPException(401, "That code is incorrect or expired.")
        try:
            token = response.json()["access_token"]
            _, lifetime = self.verify(token)
        except (ValueError, KeyError, TypeError, jwt.PyJWTError) as exc:
            raise HTTPException(503, "Sign-in is temporarily unavailable.") from exc
        return token, lifetime


def configured_auth() -> SupabaseAuth | None:
    mode = os.getenv("BIRBAL_AUTH_MODE", "demo")
    if mode == "demo":
        return None
    if mode != "pilot":
        raise RuntimeError("BIRBAL_AUTH_MODE must be demo or pilot.")
    names = ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "BIRBAL_APP_ORIGIN", "SUPABASE_KEY")
    if missing := [name for name in names if not os.getenv(name)]:
        raise RuntimeError("Private pilot configuration is incomplete: " + ", ".join(missing))
    return SupabaseAuth(*(os.environ[name] for name in names[:3]))
