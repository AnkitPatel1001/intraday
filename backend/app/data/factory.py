"""Data provider factory + validation helpers."""

from __future__ import annotations

import datetime
import logging

from app.core.config import get_settings
from app.core.primitives import BarSeries, Candle, DataFreshness
from app.data.provider import MarketDataProvider, DataError
from app.data.synthetic import SyntheticProvider
from app.data.yahoo import YahooProvider

logger = logging.getLogger(__name__)

_cache: dict[str, MarketDataProvider] = {}


def get_provider(name: str | None = None) -> MarketDataProvider:
    settings = get_settings()
    name = name or settings.data_provider
    if name not in _cache:
        if name == "demo":
            _cache[name] = SyntheticProvider()
        elif name == "yahoo":
            _cache[name] = YahooProvider()
        elif name == "upstox":
            from app.data.upstox import UpstoxProvider
            _cache[name] = UpstoxProvider()
        else:
            logger.warning("Unknown provider %r, falling back to demo", name)
            _cache[name] = SyntheticProvider()
    return _cache[name]



def staleness(series: BarSeries) -> dict:
    """Report data freshness for UI labels."""
    import datetime as dt
    from app.core.timezone import now_ist
    age = now_ist() - series.as_of
    return {
        "source": series.source,
        "freshness": series.freshness.value,
        "as_of": series.as_of.isoformat(),
        "age_minutes": int(age.total_seconds() // 60),
        "stale": age > dt.timedelta(minutes=30),
        "label": series.label(),
    }
