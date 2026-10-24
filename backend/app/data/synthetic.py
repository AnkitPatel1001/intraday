"""Synthetic data provider for demo mode and tests.

Generates reproducible OHLCV series from a seeded RNG. EVERY BarSeries from
this provider is labeled DataFreshness.SYNTHETIC with source='synthetic'.
Never used in production mode without explicit DATA_PROVIDER=demo.
"""

from __future__ import annotations

import datetime
import hashlib
import math
import random

from app.core.calendar import (
    OPEN_MIN, SESSION_BARS, BAR_MIN, is_trading_day, bar_slot, slot_time,
)
from app.core.primitives import BarSeries, Quote, Candle, DataFreshness
from app.core.timezone import IST
from app.data.provider import MarketDataProvider

# Base prices roughly approximate real NSE levels (NOT live, for demo only).
_BASE_PRICES: dict[str, float] = {
    "RELIANCE": 2850, "TCS": 4100, "HDFCBANK": 1680, "ICICIBANK": 1240,
    "INFY": 1850, "SBIN": 820, "BHARTIARTL": 1580, "ITC": 460,
    "KOTAKBANK": 1750, "LT": 3580, "AXISBANK": 1180, "ASIANPAINT": 2900,
    "MARUTI": 12500, "HINDUNILVR": 2400, "BAJFINANCE": 6800, "HCLTECH": 1720,
    "WIPRO": 520, "SUNPHARMA": 1680, "TITAN": 3400, "ULTRACEMCO": 11500,
    "NESTLEIND": 2200, "NTPC": 360, "POWERGRID": 320, "M&M": 2900,
    "TATAMOTORS": 980, "TATASTEEL": 140, "JSWSTEEL": 950, "COALINDIA": 420,
    "BAJAJ-AUTO": 9200, "TECHM": 1600, "INDUSINDBK": 1400, "GRASIM": 2600,
    "HINDALCO": 650, "DRREDDY": 6200, "CIPLA": 1450, "BAJAJFINSV": 1650,
    "NIFTY50": 24500, "BANKNIFTY": 52000, "FINNIFTY": 23800,
    "NIFTYMIDCAP": 58000,
}


def _seed_for(symbol: str, date: datetime.date) -> int:
    h = hashlib.md5(f"{symbol}:{date.isoformat()}".encode()).hexdigest()
    return int(h[:8], 16)


def _daily_close(symbol: str, date: datetime.date) -> float:
    base = _BASE_PRICES.get(symbol, 1000.0)
    seed = _seed_for(symbol, date)
    rng = random.Random(seed)
    # Random walk drift over ~2000 trading days anchored to today
    day_num = date.toordinal()
    anchor = datetime.date(2026, 10, 24).toordinal()
    days_offset = day_num - anchor
    # Deterministic pseudo-trend
    trend = math.sin(day_num * 0.017 + seed % 100) * 0.08
    noise = rng.gauss(0, 0.012)
    return round(base * (1 + trend + noise + days_offset * 0.0001), 2)


def _session_candles(
    symbol: str, date: datetime.date, prev_close: float
) -> list[Candle]:
    """Generate 75 synthetic 5-min candles for one NSE session."""
    seed = _seed_for(symbol, date) ^ 0x5EED
    rng = random.Random(seed)
    target_close = _daily_close(symbol, date)
    # gap from prev close
    gap = rng.gauss(0, 0.004)
    open_price = round(prev_close * (1 + gap), 2)

    # build 75 bars: random walk toward target_close
    candles = []
    price = open_price
    for slot in range(SESSION_BARS):
        mins = OPEN_MIN + slot * BAR_MIN
        hour, minute = divmod(mins, 60)
        ts = datetime.datetime.combine(date, datetime.time(hour, minute), tzinfo=IST)

        drift = (target_close - price) / max(1, SESSION_BARS - slot) * 0.6
        ret = rng.gauss(0, 0.0015) + drift / max(price, 1)
        o = price
        c = round(price * (1 + ret), 2)
        # wick
        wick = abs(rng.gauss(0, 0.0008)) * price
        h = round(max(o, c) + wick, 2)
        l = round(min(o, c) - wick, 2)
        if l <= 0:
            l = round(min(o, c) * 0.999, 2)
        v = int(abs(rng.gauss(150000, 80000)) * (2.0 if slot < 6 or slot > 66 else 1.0))

        candles.append(Candle(ts=ts, open=o, high=h, low=l, close=c, volume=v))
        price = c
    # force last close toward target for consistency across days
    if candles:
        last = candles[-1]
        candles[-1] = Candle(
            ts=last.ts, open=last.open, high=max(last.high, target_close),
            low=min(last.low, target_close), close=target_close, volume=last.volume,
        )
    return candles


class SyntheticProvider(MarketDataProvider):
    """Demo-mode provider. All data SYNTHETIC, labeled as such."""

    name = "synthetic"

    def _trading_days(self, start: datetime.date, end: datetime.date) -> list[datetime.date]:
        days = []
        d = start
        while d <= end:
            if is_trading_day(d):
                days.append(d)
            d += datetime.timedelta(days=1)
        return days

    async def get_bars(
        self,
        symbol: str,
        interval: str,
        start: datetime.date,
        end: datetime.date,
    ) -> BarSeries:
        days = self._trading_days(start, end)
        all_candles: list[Candle] = []

        if interval == "1d":
            prev = _daily_close(symbol, start - datetime.timedelta(days=7))
            for d in days:
                c = _daily_close(symbol, d)
                o = prev
                h = max(o, c) * 1.008
                l = min(o, c) * 0.992
                ts = datetime.datetime.combine(d, datetime.time(15, 30), tzinfo=IST)
                rng = random.Random(_seed_for(symbol, d) ^ 0xD)
                v = int(abs(rng.gauss(3_000_000, 1_000_000)))
                all_candles.append(
                    Candle(ts=ts, open=round(o, 2), high=round(h, 2),
                           low=round(l, 2), close=round(c, 2), volume=v)
                )
                prev = c
        elif interval in ("5m", "1m"):
            # For 5m: generate full sessions. For 1m: subdivide 5m.
            prev = _daily_close(symbol, start - datetime.timedelta(days=7))
            for d in days:
                sess = _session_candles(symbol, d, prev)
                if interval == "5m":
                    all_candles.extend(sess)
                else:
                    # subdivide each 5m into five 1m bars
                    for sc in sess:
                        rng = random.Random(_seed_for(symbol, d) ^ int(sc.ts.timestamp()))
                        step = (sc.close - sc.open) / 5.0
                        p = sc.open
                        for m in range(5):
                            o = p
                            c = round(p + step + rng.gauss(0, sc.close * 0.0003), 2)
                            wick = abs(rng.gauss(0, sc.close * 0.0002))
                            h = round(max(o, c) + wick, 2)
                            l = round(min(o, c) - wick, 2)
                            ts = sc.ts + datetime.timedelta(minutes=m)
                            all_candles.append(
                                Candle(ts=ts, open=o, high=h, low=l, close=c,
                                       volume=sc.volume // 5)
                            )
                            p = c
                prev = _daily_close(symbol, d)
        else:
            raise ValueError(f"unsupported interval: {interval}")

        as_of = all_candles[-1].ts if all_candles else datetime.datetime.now(IST)
        return BarSeries(
            symbol=symbol,
            interval=interval,
            exchange="NSE",
            freshness=DataFreshness.SYNTHETIC,
            source="synthetic",
            as_of=as_of,
            candles=all_candles,
        )

    async def get_quote(self, symbol: str) -> Quote:
        today = datetime.date.today()
        # walk back to last trading day
        while not is_trading_day(today):
            today -= datetime.timedelta(days=1)
        c = _daily_close(symbol, today)
        return Quote(
            symbol=symbol, exchange="NSE", last_price=c,
            volume=500000, ts=datetime.datetime.now(IST),
            freshness=DataFreshness.SYNTHETIC, source="synthetic",
        )

    async def get_batch_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        return {s: await self.get_quote(s) for s in symbols}
