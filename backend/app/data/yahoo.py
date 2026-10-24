"""Yahoo Finance adapter for NSE (.NS) and BSE (.BO) symbols.

Uses the unofficial v8 chart endpoint. Free, can lag, not an official API.
Freshness is DELAYED (Yahoo does not guarantee real-time for NSE).
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from app.core.primitives import BarSeries, Quote, Candle, DataFreshness
from app.core.symbols import to_yahoo_nse, from_yahoo, validate_symbol
from app.core.timezone import IST, epoch_to_ist
from app.data.provider import MarketDataProvider, DataError, RateLimitError

logger = logging.getLogger(__name__)

UA = "Mozilla/5.0 (compatible; market-intel/1.0)"
HOSTS = ("query2.finance.yahoo.com", "query1.finance.yahoo.com")
PAUSE = 0.3
BACKOFF = 5.0

_INTERVAL_MAP = {"1m": "1m", "5m": "5m", "15m": "15m", "1d": "1d", "1wk": "1wk"}
_RANGE_MAP = {"1m": "5d", "5m": "1mo", "15m": "3mo", "1d": "1y", "1wk": "5y"}


def _chart_url(symbol: str, interval: str, host: str) -> str:
    ysym = to_yahoo_nse(symbol) if not symbol.endswith((".NS", ".BO")) else symbol
    rng = _RANGE_MAP.get(interval, "1mo")
    iv = _INTERVAL_MAP.get(interval, "5m")
    return f"https://{host}/v8/finance/chart/{urllib.parse.quote(ysym)}?range={rng}&interval={iv}"


def _fetch_sync(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


class YahooProvider(MarketDataProvider):
    name = "yahoo"

    async def _get(self, url: str) -> str:
        last_err = None
        for host_idx in range(2):
            for attempt in range(2):
                try:
                    return await asyncio.to_thread(_fetch_sync, url)
                except urllib.error.HTTPError as e:
                    last_err = e
                    if e.code == 429:
                        if attempt == 0:
                            await asyncio.sleep(BACKOFF)
                            continue
                        raise RateLimitError(f"Yahoo rate limited (429) for {url}")
                    if e.code == 404:
                        raise DataError(f"Yahoo has no data (404) for {url}")
                    if e.code >= 500:
                        break  # try next host
                    raise DataError(f"Yahoo HTTP {e.code} for {url}")
                except (urllib.error.URLError, OSError) as e:
                    last_err = e
                    break
            if host_idx == 0:
                await asyncio.sleep(PAUSE)
        raise DataError(f"could not reach Yahoo: {last_err}")

    def _parse_chart(self, text: str, symbol: str, interval: str) -> BarSeries:
        try:
            doc = json.loads(text)
        except ValueError:
            raise DataError(f"Yahoo returned non-JSON for {symbol}")
        chart = doc.get("chart") if isinstance(doc, dict) else None
        if not isinstance(chart, dict):
            raise DataError(f"unexpected Yahoo response for {symbol}")
        res = chart.get("result")
        if not res:
            err = chart.get("error") or {}
            raise DataError(f"Yahoo has no data for {symbol}: {err.get('description', 'unknown')}")
        result = res[0]
        meta = result.get("meta") or {}
        timestamps = result.get("timestamp") or []
        q = ((result.get("indicators") or {}).get("quote") or [{}])[0] or {}
        cols = {k: (q.get(k) or []) for k in ("open", "high", "low", "close", "volume")}

        candles = []
        for i, ts in enumerate(timestamps):
            o = cols["open"][i] if i < len(cols["open"]) else None
            h = cols["high"][i] if i < len(cols["high"]) else None
            l = cols["low"][i] if i < len(cols["low"]) else None
            c = cols["close"][i] if i < len(cols["close"]) else None
            v = cols["volume"][i] if i < len(cols["volume"]) else 0
            if ts is None or None in (o, h, l, c):
                continue
            ist_dt = epoch_to_ist(int(ts))
            try:
                candle = Candle(ts=ist_dt, open=float(o), high=float(h),
                                low=float(l), close=float(c), volume=int(v or 0))
                candle.validate()
            except ValueError:
                continue
            candles.append(candle)

        nse_sym, _ = from_yahoo(str(meta.get("symbol", "")))
        as_of = candles[-1].ts if candles else datetime.datetime.now(IST)
        return BarSeries(
            symbol=validate_symbol(nse_sym or symbol),
            interval=interval,
            exchange="NSE",
            freshness=DataFreshness.DELAYED,
            source="yahoo",
            as_of=as_of,
            candles=candles,
        )

    async def get_bars(
        self, symbol: str, interval: str, start: datetime.date, end: datetime.date,
    ) -> BarSeries:
        url = _chart_url(symbol, interval, HOSTS[0])
        text = await self._get(url)
        return self._parse_chart(text, symbol, interval)

    async def get_quote(self, symbol: str) -> Quote:
        series = await self.get_bars(symbol, "5m", datetime.date.today(), datetime.date.today())
        if not series.candles:
            raise DataError(f"no bars for {symbol}")
        last = series.candles[-1]
        return Quote(
            symbol=symbol, exchange="NSE", last_price=last.close,
            volume=last.volume, ts=last.ts,
            freshness=DataFreshness.DELAYED, source="yahoo",
        )

    async def get_batch_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        out = {}
        for s in symbols:
            try:
                out[s] = await self.get_quote(s)
            except DataError as e:
                logger.warning("quote failed for %s: %s", s, e)
        return out
