"""Shared test fixtures."""

import datetime
import pytest
from app.core.primitives import Candle, BarSeries, DataFreshness
from app.core.timezone import IST
from app.data.synthetic import SyntheticProvider


@pytest.fixture(autouse=True)
def _open_test_env():
    """Disable auth + rate limiting for the general suite.

    Dedicated security tests (tests/test_security.py) re-enable these
    explicitly to assert enforcement behavior.
    """
    from app.core.config import get_settings
    from app.core.ratelimit import limiter

    s = get_settings()
    prev_auth, prev_rl = s.auth_enabled, s.rate_limit_per_minute
    s.auth_enabled = False
    s.rate_limit_per_minute = 0
    limiter.reset()
    yield
    s.auth_enabled, s.rate_limit_per_minute = prev_auth, prev_rl
    limiter.reset()


@pytest.fixture
def provider():
    return SyntheticProvider()


@pytest.fixture
def sample_candles():
    """100 synthetic candles across 2 days."""
    candles = []
    base = datetime.datetime(2026, 10, 20, 9, 15, tzinfo=IST)
    price = 1000.0
    for d in range(2):
        day = base + datetime.timedelta(days=d)
        for slot in range(75):
            ts = day + datetime.timedelta(minutes=slot * 5)
            o = price
            c = price * (1.001 if slot % 2 == 0 else 0.999)
            h = max(o, c) * 1.001
            l = min(o, c) * 0.999
            candles.append(Candle(ts=ts, open=round(o, 2), high=round(h, 2),
                                  low=round(l, 2), close=round(c, 2), volume=100000))
            price = c
    return candles


@pytest.fixture
def series_5m():
    """30 sessions of 5-min bars via synthetic provider."""
    import asyncio
    p = SyntheticProvider()
    start = datetime.date(2026, 9, 1)
    end = datetime.date(2026, 10, 24)
    return asyncio.get_event_loop().run_until_complete(
        p.get_bars("RELIANCE", "5m", start, end)
    )
