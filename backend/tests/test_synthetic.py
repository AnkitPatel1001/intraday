"""Tests for synthetic data provider."""

import asyncio
import datetime
import pytest
from app.core.primitives import DataFreshness
from app.data.synthetic import SyntheticProvider


def run(coro):
    return asyncio.run(coro)


class TestSyntheticProvider:
    @pytest.fixture
    def provider(self):
        return SyntheticProvider()

    def test_name(self, provider):
        assert provider.name == "synthetic"

    def test_get_bars_5m(self, provider):
        start = datetime.date(2026, 10, 1)
        end = datetime.date(2026, 10, 10)
        series = run(provider.get_bars("RELIANCE", "5m", start, end))
        assert series.freshness == DataFreshness.SYNTHETIC
        assert series.source == "synthetic"
        assert len(series.candles) > 0
        # ~8 trading days * 75 bars = ~600
        assert len(series.candles) >= 300

    def test_get_bars_1d(self, provider):
        start = datetime.date(2026, 10, 1)
        end = datetime.date(2026, 10, 10)
        series = run(provider.get_bars("RELIANCE", "1d", start, end))
        assert series.freshness == DataFreshness.SYNTHETIC
        # ~8 trading days
        assert 5 <= len(series.candles) <= 10

    def test_candles_valid(self, provider):
        start = datetime.date(2026, 10, 1)
        end = datetime.date(2026, 10, 3)
        series = run(provider.get_bars("TCS", "5m", start, end))
        for c in series.candles:
            assert c.high >= c.low
            assert c.high >= max(c.open, c.close)
            assert c.low <= min(c.open, c.close)
            assert c.volume >= 0

    def test_deterministic(self, provider):
        start = datetime.date(2026, 10, 1)
        end = datetime.date(2026, 10, 3)
        s1 = run(provider.get_bars("RELIANCE", "5m", start, end))
        s2 = run(provider.get_bars("RELIANCE", "5m", start, end))
        assert len(s1.candles) == len(s2.candles)
        for c1, c2 in zip(s1.candles, s2.candles):
            assert c1.close == c2.close

    def test_get_quote(self, provider):
        q = run(provider.get_quote("RELIANCE"))
        assert q.freshness == DataFreshness.SYNTHETIC
        assert q.last_price > 0
        assert q.symbol == "RELIANCE"

    def test_get_batch_quotes(self, provider):
        quotes = run(provider.get_batch_quotes(["RELIANCE", "TCS"]))
        assert "RELIANCE" in quotes
        assert "TCS" in quotes

    def test_different_symbols_different_prices(self, provider):
        q1 = run(provider.get_quote("RELIANCE"))
        q2 = run(provider.get_quote("TCS"))
        assert q1.last_price != q2.last_price

    def test_timestamps_ist(self, provider):
        start = datetime.date(2026, 10, 1)
        end = datetime.date(2026, 10, 1)
        series = run(provider.get_bars("INFY", "5m", start, end))
        for c in series.candles[:5]:
            assert c.ts.tzinfo is not None
            offset = c.ts.utcoffset()
            assert offset == datetime.timedelta(hours=5, minutes=30)
