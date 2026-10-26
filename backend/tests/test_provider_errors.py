"""provider_502: helpful 502 detail for provider failures (unknown symbol etc.)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.provider_errors import provider_502
from app.data.provider import AuthError, DataError, RateLimitError


def test_data_error_names_symbol_and_hint():
    e = provider_502("BONFIGLIOLI", DataError("Yahoo has no data (404)"))
    assert e.status_code == 502
    assert "BONFIGLIOLI" in e.detail
    assert "not the company name" in e.detail


def test_auth_error_passes_instructions_verbatim():
    msg = "UPSTOX token missing: see README setup"
    e = provider_502("RELIANCE", AuthError(msg))
    assert e.status_code == 502
    assert msg in e.detail


def test_rate_limit_passes_through():
    msg = "rate limited, retry later"
    e = provider_502("TCS", RateLimitError(msg))
    assert e.status_code == 502
    assert msg in e.detail


def test_unexpected_exception_stays_generic():
    e = provider_502("TCS", RuntimeError("internal traceback detail"))
    assert e.status_code == 502
    assert e.detail == "data provider error"
    assert "traceback" not in e.detail


async def test_api_bars_502_detail_includes_symbol(monkeypatch):
    from httpx import AsyncClient, ASGITransport

    from app.api import market
    from app.main import app

    class BoomProvider:
        name = "boom"

        async def get_bars(self, *a, **k):
            raise DataError("Yahoo has no data (404)")

        async def get_quote(self, *a, **k):
            raise DataError("Yahoo has no data (404)")

        async def get_batch_quotes(self, *a, **k):
            return {}

    monkeypatch.setattr(market, "get_provider", lambda: BoomProvider())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/v1/market/bars/BONFIGLIOLI?interval=5m&days=5")
    assert r.status_code == 502
    detail = r.json()["detail"]
    assert "BONFIGLIOLI" in detail
    assert "company name" in detail
