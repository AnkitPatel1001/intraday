"""Tests for technical indicators against known fixtures."""

import pytest
from app.engine.indicators import sma, ema, rsi, macd, atr, vwap, bollinger, stochastic


class TestSMA:
    def test_basic(self):
        result = sma([1, 2, 3, 4, 5], 3)
        assert result[0] is None
        assert result[1] is None
        assert result[2] == 2.0  # (1+2+3)/3
        assert result[3] == 3.0  # (2+3+4)/3
        assert result[4] == 4.0  # (3+4+5)/3

    def test_insufficient(self):
        result = sma([1, 2], 5)
        assert all(v is None for v in result)

    def test_window_equals_length(self):
        result = sma([2, 4, 6], 3)
        assert result[2] == 4.0

    def test_invalid_n(self):
        with pytest.raises(ValueError):
            sma([1, 2, 3], 0)


class TestEMA:
    def test_basic(self):
        result = ema([1, 2, 3, 4, 5], 3)
        assert result[0] is None
        assert result[1] is None
        # first EMA = SMA of first 3 = 2.0
        assert result[2] == 2.0
        # k = 2/(3+1) = 0.5; ema[3] = 4*0.5 + 2*0.5 = 3.0
        assert result[3] == 3.0

    def test_insufficient(self):
        result = ema([1], 5)
        assert all(v is None for v in result)


class TestRSI:
    def test_all_up(self):
        closes = list(range(1, 30))
        result = rsi(closes, 14)
        assert result[-1] is not None
        assert result[-1] > 90  # all gains, no losses

    def test_all_down(self):
        closes = list(range(30, 1, -1))
        result = rsi(closes, 14)
        assert result[-1] is not None
        assert result[-1] < 10  # all losses

    def test_known_fixture(self):
        # RSI-14 on a well-known series
        closes = [
            44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
            45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00,
            46.03, 46.41, 46.22, 45.64,
        ]
        result = rsi(closes, 14)
        # First RSI at index 14 should be ~70.46 (Wilder's RSI-14)
        assert result[14] is not None
        assert 65 < result[14] < 80

    def test_insufficient(self):
        result = rsi([1, 2, 3], 14)
        assert all(v is None for v in result)

    def test_range(self):
        closes = [100, 101, 102, 101, 103, 102, 104, 103, 105, 104, 106, 105, 107, 106, 108, 107, 109, 108, 110, 109, 111, 110, 112, 111, 113, 112, 114, 113, 115, 114]
        result = rsi(closes, 14)
        for v in result:
            if v is not None:
                assert 0 <= v <= 100


class TestMACD:
    def test_shapes(self):
        closes = list(range(50, 100))
        line, sig, hist = macd(closes)
        assert len(line) == len(closes)
        assert len(sig) == len(closes)
        assert len(hist) == len(closes)

    def test_none_early(self):
        closes = list(range(50))
        line, _, _ = macd(closes)
        # fast=12, slow=26: first slow EMA at index 25, so line[24] is None, line[25] has value
        assert line[24] is None
        assert line[25] is not None


class TestATR:
    def test_positive(self):
        highs = [10, 11, 12, 11, 13, 12, 14, 13, 15, 14, 16, 15, 17, 16, 18, 17]
        lows = [9, 10, 11, 9, 11, 10, 12, 11, 13, 12, 14, 13, 15, 14, 16, 15]
        closes = [9.5, 10.5, 11.5, 10.5, 12.5, 11.5, 13.5, 12.5, 14.5, 13.5, 15.5, 14.5, 16.5, 15.5, 17.5, 16.5]
        result = atr(highs, lows, closes, 14)
        assert result[-1] is not None
        assert result[-1] > 0

    def test_insufficient(self):
        result = atr([10], [9], [9.5], 14)
        assert all(v is None for v in result)


class TestVWAP:
    def test_basic(self):
        result = vwap([10, 11], [9, 10], [9.5, 10.5], [100, 200])
        assert len(result) == 2
        assert result[0] > 0
        # second should be weighted average
        assert result[1] > result[0]


class TestBollinger:
    def test_bands_order(self):
        closes = list(range(100, 130))
        upper, mid, lower = bollinger(closes, 20)
        assert upper[-1] > mid[-1] > lower[-1]

    def test_none_early(self):
        closes = list(range(10))
        upper, _, _ = bollinger(closes, 20)
        assert all(v is None for v in upper)


class TestStochastic:
    def test_range(self):
        highs = list(range(110, 140))
        lows = list(range(100, 130))
        closes = list(range(105, 135))
        k, d = stochastic(highs, lows, closes)
        for v in k:
            if v is not None:
                assert 0 <= v <= 100
