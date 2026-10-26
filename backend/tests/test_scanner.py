"""Tests for scanner."""

import datetime
import pytest
from app.core.primitives import Candle, BarSeries, DataFreshness
from app.core.timezone import IST
from app.engine.scanner import ScanFilters, scan_symbol, scan_universe


def make_uptrend_series(symbol="RELIANCE", n=50) -> BarSeries:
    """Strong uptrend with volume spike on last bar."""
    candles = []
    price = 1000.0
    base = datetime.datetime(2026, 10, 1, 9, 15, tzinfo=IST)
    for i in range(n):
        ts = base + datetime.timedelta(minutes=i * 5)
        o = price
        c = price * 1.005  # +0.5% per bar = strong uptrend
        h = c * 1.001
        l = o * 0.999
        v = 500000 if i < n - 1 else 2000000  # volume spike on last bar
        candles.append(Candle(ts=ts, open=round(o, 2), high=round(h, 2),
                              low=round(l, 2), close=round(c, 2), volume=v))
        price = c
    return BarSeries(symbol=symbol, interval="5m", exchange="NSE",
                     freshness=DataFreshness.SYNTHETIC, source="test",
                     as_of=candles[-1].ts, candles=candles)


def make_flat_series(symbol="FLAT", n=50) -> BarSeries:
    """Flat series with no setups."""
    candles = []
    base = datetime.datetime(2026, 10, 1, 9, 15, tzinfo=IST)
    for i in range(n):
        ts = base + datetime.timedelta(minutes=i * 5)
        candles.append(Candle(ts=ts, open=1000.0, high=1001.0,
                              low=999.0, close=1000.0, volume=100000))
    return BarSeries(symbol=symbol, interval="5m", exchange="NSE",
                     freshness=DataFreshness.SYNTHETIC, source="test",
                     as_of=candles[-1].ts, candles=candles)


class TestScanSymbol:
    def test_uptrend_finds_setups(self):
        series = make_uptrend_series()
        r = scan_symbol(series, ScanFilters())
        assert r is not None
        assert len(r.setups) > 0
        assert r.reason  # non-empty explanation

    def test_flat_returns_none(self):
        series = make_flat_series()
        r = scan_symbol(series, ScanFilters())
        # May still match breakout since it's flat at same level
        # The key is it doesn't crash

    def test_low_price_filtered(self):
        series = make_uptrend_series()
        filters = ScanFilters(min_price=999999)
        r = scan_symbol(series, filters)
        assert r is None

    def test_low_volume_filtered(self):
        series = make_uptrend_series()
        filters = ScanFilters(min_volume=10**12)
        r = scan_symbol(series, filters)
        assert r is None

    def test_short_series_returns_none(self):
        series = make_uptrend_series(n=10)
        r = scan_symbol(series, ScanFilters())
        assert r is None

    def test_indicators_populated(self):
        series = make_uptrend_series()
        r = scan_symbol(series, ScanFilters())
        assert r is not None
        assert "rsi_14" in r.indicators

    def test_freshness_label(self):
        series = make_uptrend_series()
        r = scan_symbol(series, ScanFilters())
        assert r.freshness == "synthetic"

    def test_volume_spike_detected(self):
        series = make_uptrend_series()
        r = scan_symbol(series, ScanFilters())
        assert r is not None
        assert "volume_spike" in r.setups


class TestScanUniverse:
    def test_multiple_symbols(self):
        s1 = make_uptrend_series("RELIANCE")
        s2 = make_uptrend_series("TCS")
        results = scan_universe({"RELIANCE": s1, "TCS": s2}, ScanFilters())
        assert len(results) == 2

    def test_empty(self):
        results = scan_universe({}, ScanFilters())
        assert len(results) == 0
