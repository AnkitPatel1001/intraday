"""Translate data-provider exceptions into helpful HTTP 502 errors.

Auth/rate-limit messages carry setup instructions, so they pass through
verbatim. DataError (unknown symbol, no coverage) gets a human-readable
hint. Anything unexpected stays generic.
"""

from __future__ import annotations

from fastapi import HTTPException

from app.data.provider import AuthError, DataError, RateLimitError


def provider_502(sym: str, exc: Exception) -> HTTPException:
    if isinstance(exc, (AuthError, RateLimitError)):
        return HTTPException(502, f"{sym}: {exc}")
    if isinstance(exc, DataError):
        return HTTPException(
            502,
            f"no data for {sym}: {exc}. Verify the NSE trading symbol "
            f"(not the company name) and that the provider covers it.",
        )
    return HTTPException(502, "data provider error")
