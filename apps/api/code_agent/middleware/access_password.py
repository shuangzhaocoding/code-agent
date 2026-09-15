"""Optional shared-secret access gate (not an account system)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from code_agent.config import settings
from code_agent.crypto import decrypt_secret, encrypt_secret

COOKIE_NAME = "ca_access"
HEADER_NAME = "X-Code-Agent-Password"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days

# Paths that remain reachable without unlocking (health + unlock + static).
_PUBLIC_PREFIXES = (
    "/api/health",
    "/api/auth/",
    "/assets/",
)
_PUBLIC_EXACT = {"/", "/favicon.ico", "/favicon.svg"}


def access_password_plain() -> str:
    """Return configured plaintext password, or empty if none stored."""
    raw = settings.get("server.access_password")
    if raw is None:
        return ""
    text = str(raw).strip()
    if not text:
        return ""
    # Prefer encrypted storage; fall back to legacy plaintext.
    if text.startswith("enc:"):
        return decrypt_secret(text[4:]) or ""
    return text


def access_password_flag() -> bool:
    """User toggle: whether the gate should be active (default off)."""
    raw = settings.get("server.access_password_enabled")
    if raw is None:
        return False
    return bool(raw)


def access_password_enabled() -> bool:
    """Gate is on only when the toggle is on AND a password is configured."""
    return access_password_flag() and bool(access_password_plain())


def store_access_password(plain: str) -> str:
    """Return value to persist in Setting (encrypted). Empty clears."""
    text = (plain or "").strip()
    if not text:
        return ""
    return "enc:" + encrypt_secret(text)


def _signing_key() -> bytes:
    # Derive from master fernet material path via a stable app salt + password.
    # Token binds to current password so changing it invalidates cookies.
    pwd = access_password_plain()
    material = f"code-agent-access|{pwd}".encode()
    return hashlib.sha256(material).digest()


def make_access_token() -> str:
    nonce = secrets.token_hex(8)
    sig = hmac.new(_signing_key(), nonce.encode(), hashlib.sha256).hexdigest()
    return f"{nonce}.{sig}"


def verify_access_token(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    nonce, sig = token.split(".", 1)
    if not nonce or not sig:
        return False
    expected = hmac.new(_signing_key(), nonce.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def verify_password_attempt(attempt: str) -> bool:
    plain = access_password_plain()
    if not plain:
        return True
    return hmac.compare_digest(plain, (attempt or "").strip())


def request_unlocked(request: Request) -> bool:
    if not access_password_enabled():
        return True
    header = request.headers.get(HEADER_NAME) or request.headers.get(HEADER_NAME.lower())
    if header and verify_password_attempt(header):
        return True
    cookie = request.cookies.get(COOKIE_NAME)
    if verify_access_token(cookie):
        return True
    # EventSource / some clients may pass ?access_token=
    token = request.query_params.get("access_token")
    if verify_access_token(token):
        return True
    return False


def _is_public(path: str) -> bool:
    if path in _PUBLIC_EXACT:
        return True
    for prefix in _PUBLIC_PREFIXES:
        if path.startswith(prefix):
            return True
    # SPA assets / index without /api
    if not path.startswith("/api"):
        return True
    return False


class AccessPasswordMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path or "/"
        if _is_public(path) or request.method == "OPTIONS":
            return await call_next(request)
        if not access_password_enabled():
            return await call_next(request)
        if request_unlocked(request):
            return await call_next(request)
        return JSONResponse(
            status_code=401,
            content={"detail": {"code": "auth.required", "message": "Access password required"}},
        )


def set_access_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )


def clear_access_cookie(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/")
