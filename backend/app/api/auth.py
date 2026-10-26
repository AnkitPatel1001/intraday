"""Session authentication: issue/validate bearer sessions.

Sessions isolate paper-trading portfolios per client token.
No accounts, no passwords — tokens are opaque, expiring, in-memory.
"""

from __future__ import annotations

import secrets
import time

from fastapi import APIRouter, Request

from app.core.config import get_settings

# token -> expiry epoch seconds (in-memory; resets with server)
_sessions: dict[str, float] = {}

router = APIRouter()


def create_session() -> tuple[str, int]:
    settings = get_settings()
    ttl_seconds = int(settings.session_timeout_hours * 3600)
    token = secrets.token_urlsafe(24)
    _sessions[token] = time.time() + ttl_seconds
    return token, ttl_seconds


def validate_session(token: str | None) -> bool:
    if not token:
        return False
    _prune()
    expiry = _sessions.get(token)
    return expiry is not None and expiry > time.time()


def invalidate_session(token: str) -> None:
    _sessions.pop(token, None)
    from app.api.paper import drop_engine
    drop_engine(token)


def extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return request.headers.get("X-Session-Token") or None


def session_of(request: Request) -> str:
    """Token for current request; 'anonymous' when auth disabled."""
    return getattr(request.state, "session", "anonymous")


def _prune() -> None:
    now = time.time()
    expired = [t for t, exp in _sessions.items() if exp <= now]
    if expired:
        from app.api.paper import drop_engine
    for t in expired:
        _sessions.pop(t, None)
        drop_engine(t)  # session gone -> portfolio engine GC'd too


@router.post("/session")
async def issue_session():
    token, ttl = create_session()
    return {"token": token, "expires_in": ttl}


@router.get("/session")
async def session_status(request: Request):
    token = extract_token(request)
    valid = validate_session(token)
    out: dict = {"valid": valid}
    if valid and token:
        out["expires_in"] = int(_sessions[token] - time.time())
    return out


@router.delete("/session")
async def logout(request: Request):
    token = extract_token(request)
    if token:
        invalidate_session(token)
    return {"status": "logged_out"}
