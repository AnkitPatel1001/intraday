"""Upstox market-data provider (REST historical + WebSocket quotes).

DATA_PROVIDER=upstox activates this provider. It talks to Upstox market-data
APIs only:

- historical candles: GET /v3/historical-candle (chunked, throttled, 429-aware)
- quotes: WebSocket LTPC feed first (zero REST), REST LTP as fallback

TOKENS: UPSTOX_ANALYTICS_TOKEN (long-lived, preferred) or the daily
UPSTOX_ACCESS_TOKEN. Both are read-only market-data credentials.

PAPER ONLY: no order/trade/account endpoints exist in this module — this app
never places live orders. REST calls are client-side throttled to stay well
below Upstox's 50 req/s quote cap so requests do not trip 429s.
"""

from __future__ import annotations

import asyncio
import datetime
import gzip
import json
import logging
import urllib.parse
from pathlib import Path
from typing import Optional

import httpx

from app.core.config import get_settings
from app.core.primitives import BarSeries, Candle, DataFreshness, Quote
from app.core.timezone import IST, now_ist
from app.data.provider import AuthError, DataError, MarketDataProvider, RateLimitError
from app.data.upstox_feed import get_feed

logger = logging.getLogger(__name__)

# Well-known NSE index instrument keys (equities come from the instrument file)
INDEX_KEYS = {
    "NIFTY50": "NSE_INDEX|NIFTY 50",
    "NIFTYNXT50": "NSE_INDEX|Nifty Next 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
    "FINNIFTY": "NSE_INDEX|Nifty Fin Service",
    "MIDCPNIFTY": "NSE_INDEX|Nifty Midcap Select",
    "INDIAVIX": "NSE_INDEX|India VIX",
}

# interval -> (unit, interval, intraday) for /v3/historical-candle
INTERVAL_MAP = {
    "1m": ("minutes", "1", True),
    "5m": ("minutes", "5", True),
    "15m": ("minutes", "15", True),
    "1d": ("days", "1", False),
}

# Upstox limits 1-15 minute intervals to ~1 month of data per request
INTRADAY_CHUNK_DAYS = 27

INSTRUMENT_FILE_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
CACHE_MAX_AGE_DAYS = 7


def _ist_from_ms(ms: int) -> datetime.datetime:
    if not ms:
        return now_ist()
    if ms > 10**12:  # milliseconds
        ms = ms // 1000
    return datetime.datetime.fromtimestamp(ms, tz=IST)


class UpstoxProvider(MarketDataProvider):
    name = "upstox"

    def __init__(self, transport: httpx.AsyncTransport | None = None):
        s = get_settings()
        self.base_url = s.upstox_base_url.rstrip("/")
        self.sandbox = s.upstox_sandbox
        self._transport = transport
        self._max_per_sec = max(1, s.upstox_rest_max_per_second)
        self._min_interval = 1.0 / self._max_per_sec
        self._last_call = 0.0
        self._throttle_lock = asyncio.Lock()
        self._instrument_map: dict[str, str] | None = None

    # -- auth -----------------------------------------------------------

    @property
    def token(self) -> str:
        s = get_settings()
        tok = s.upstox_analytics_token or s.upstox_access_token
        if not tok:
            raise AuthError(
                "Upstox token not configured: set UPSTOX_ANALYTICS_TOKEN "
                "(long-lived, recommended) or UPSTOX_ACCESS_TOKEN in .env — "
                "see README 'Free Upstox API key' (upstox.com/developer)"
            )
        return tok

    # -- HTTP with throttle + 429 backoff -------------------------------

    async def _throttle(self) -> None:
        async with self._throttle_lock:
            now = asyncio.get_event_loop().time()
            wait = self._last_call + self._min_interval - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = asyncio.get_event_loop().time()

    async def _request(self, path: str, params: dict | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        backoff = 0.5
        last_429 = None
        for attempt in range(4):
            await self._throttle()
            try:
                async with httpx.AsyncClient(
                    base_url=self.base_url, timeout=30.0,
                    transport=self._transport,
                ) as client:
                    r = await client.get(path, params=params, headers=headers)
            except httpx.HTTPError as e:
                raise DataError(f"upstox request failed: {e}") from e
            if r.status_code == 429:
                last_429 = r
                try:
                    wait = float(r.headers.get("Retry-After", backoff))
                except ValueError:
                    wait = backoff
                await asyncio.sleep(max(0.0, wait))
                backoff = min(backoff * 2, 8.0)
                continue
            if r.status_code in (401, 403):
                raise AuthError(
                    f"upstox auth failed ({r.status_code}): token expired or "
                    "invalid — regenerate UPSTOX_ACCESS_TOKEN / "
                    "UPSTOX_ANALYTICS_TOKEN"
                )
            if r.status_code >= 500:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 8.0)
                continue
            if r.status_code >= 400:
                raise DataError(f"upstox {path} -> HTTP {r.status_code}")
            try:
                return r.json()
            except ValueError as e:
                raise DataError("upstox returned non-JSON body") from e
        raise RateLimitError(
            f"upstox rate limited after retries (last HTTP {last_429.status_code})"
        )

    # -- instruments ----------------------------------------------------

    @staticmethod
    def _parse_instrument_master(raw: bytes) -> dict[str, str]:
        """gzip JSON instrument file -> {trading_symbol: instrument_key}."""
        data = json.loads(gzip.decompress(raw).decode("utf-8"))
        out: dict[str, str] = {}
        for row in data:
            sym = row.get("trading_symbol")
            key = row.get("instrument_key")
            if not sym or not key:
                continue
            if row.get("instrument_type") not in (None, "EQ"):
                continue
            out[sym.upper()] = key
        return out

    async def _download_instrument_map(self) -> dict[str, str]:
        try:
            async with httpx.AsyncClient(timeout=30.0,
                                         transport=self._transport) as client:
                r = await client.get(INSTRUMENT_FILE_URL)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise DataError(
                f"cannot download Upstox NSE instrument file: {e}"
            ) from e
        return self._parse_instrument_master(r.content)

    def _cache_path(self) -> Path:
        return Path(get_settings().upstox_instrument_cache)

    async def _load_instrument_map(self) -> dict[str, str]:
        if self._instrument_map is not None:
            return self._instrument_map
        path = self._cache_path()
        try:
            if path.exists():
                doc = json.loads(path.read_text(encoding="utf-8"))
                fetched = datetime.date.fromisoformat(doc.get("fetched_at", "2000-01-01"))
                age = (datetime.date.today() - fetched).days
                if 0 <= age <= CACHE_MAX_AGE_DAYS and doc.get("map"):
                    self._instrument_map = doc["map"]
                    return self._instrument_map
        except (ValueError, KeyError):
            pass
        self._instrument_map = await self._download_instrument_map()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "fetched_at": datetime.date.today().isoformat(),
                "map": self._instrument_map,
            }), encoding="utf-8")
        except OSError:
            logger.debug("could not persist upstox instrument cache", exc_info=True)
        return self._instrument_map

    async def resolve_instrument(self, symbol: str) -> str:
        """NSE symbol -> Upstox instrument key (e.g. 'NSE_EQ|INE002A01018')."""
        sym = symbol.upper()
        if sym in INDEX_KEYS:
            return INDEX_KEYS[sym]
        if sym.endswith(".NS"):
            sym = sym[: -len(".NS")]
        mapping = await self._load_instrument_map()
        key = mapping.get(sym)
        if not key:
            raise DataError(
                f"symbol {sym} not found in Upstox NSE instrument master"
            )
        return key

    # -- bars (REST historical, chunked) --------------------------------

    async def get_bars(self, symbol: str, interval: str,
                       start: datetime.date, end: datetime.date) -> BarSeries:
        if interval not in INTERVAL_MAP:
            raise DataError(f"unsupported interval: {interval}")
        unit, iv, intraday = INTERVAL_MAP[interval]
        key = await self.resolve_instrument(symbol)
        enc_key = urllib.parse.quote(key, safe="")

        windows: list[tuple[datetime.date, datetime.date]] = []
        if intraday:
            cur_from = start
            while cur_from <= end:
                cur_to = min(cur_from + datetime.timedelta(days=INTRADAY_CHUNK_DAYS - 1), end)
                windows.append((cur_from, cur_to))
                cur_from = cur_to + datetime.timedelta(days=1)
        else:
            windows.append((start, end))

        candles: list[Candle] = []
        seen: set[str] = set()
        for w_from, w_to in windows:
            path = f"/v3/historical-candle/{enc_key}/{unit}/{iv}/{w_to.isoformat()}/{w_from.isoformat()}"
            body = await self._request(path)
            rows = (body.get("data") or {}).get("candles") or []
            for row in rows:
                ts_raw = row[0]
                if ts_raw in seen:
                    continue
                seen.add(ts_raw)
                ts = datetime.datetime.fromisoformat(ts_raw)
                c = Candle(
                    ts=ts, open=float(row[1]), high=float(row[2]),
                    low=float(row[3]), close=float(row[4]),
                    volume=int(row[5] or 0),
                )
                try:
                    c.validate()
                except ValueError:
                    continue
                candles.append(c)

        if not candles:
            raise DataError(
                f"upstox returned no candles for {symbol} {interval} "
                f"{start}..{end}"
            )
        candles.sort(key=lambda c: c.ts)
        return BarSeries(
            symbol=symbol, interval=interval, exchange="NSE",
            freshness=DataFreshness.HISTORICAL, source="upstox",
            as_of=candles[-1].ts, candles=candles,
        )

    # -- quotes (WebSocket first, REST fallback) ------------------------

    def _quote_freshness(self) -> DataFreshness:
        from app.core.calendar import market_status_now
        return (DataFreshness.LIVE
                if market_status_now()["status"] == "open"
                else DataFreshness.DELAYED)

    async def get_quote(self, symbol: str) -> Quote:
        key = await self.resolve_instrument(symbol)
        quote = await self._quote_from_feed(symbol, [key])
        if quote is not None:
            return quote
        body = await self._request(
            "/v3/market-quote/ltp", {"instrumentKeys": key}
        )
        q = self._parse_ltp(symbol, key, body)
        if q is None:
            raise DataError(f"upstox returned no LTP for {symbol}")
        return q

    async def get_batch_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        keys: dict[str, str] = {}
        for sym in symbols:
            keys[sym] = await self.resolve_instrument(sym)
        out = await self._quotes_from_feed(symbols, keys)
        missing = [s for s in symbols if s not in out]
        if missing:
            joined = ",".join(keys[s] for s in missing)
            body = await self._request("/v3/market-quote/ltp", {"instrumentKeys": joined})
            for sym in missing:
                q = self._parse_ltp(sym, keys[sym], body)
                if q is not None:
                    out[sym] = q
        if not out:
            raise DataError("upstox returned no quotes for requested symbols")
        return out

    def _feed(self):
        s = get_settings()
        if not s.upstox_ws_enabled:
            return None
        return get_feed(lambda: s.upstox_analytics_token or s.upstox_access_token)

    async def _quote_from_feed(self, symbol: str, keys: list[str]) -> Optional[Quote]:
        got = await self._quotes_from_feed([symbol], {symbol: keys[0]})
        return got.get(symbol)

    async def _quotes_from_feed(self, symbols: list[str],
                                keys: dict[str, str]) -> dict[str, Quote]:
        feed = self._feed()
        if feed is None:
            return {}
        try:
            await feed.ensure_started()
            await feed.subscribe(list(keys.values()))
        except Exception:
            logger.debug("upstox feed start failed; using REST quotes",
                         exc_info=True)
            return {}
        out: dict[str, Quote] = {}
        freshness = self._quote_freshness()
        for sym in symbols:
            cached = feed.get_cached(keys[sym])
            if cached is None:
                continue
            ltp, _cp, ts_ms = cached
            out[sym] = Quote(
                symbol=sym, exchange="NSE", last_price=float(ltp), volume=0,
                ts=_ist_from_ms(ts_ms), freshness=freshness, source="upstox",
            )
        return out

    def _parse_ltp(self, symbol: str, key: str, body: dict) -> Optional[Quote]:
        data = body.get("data") or {}
        node = data.get(key) or {}
        ltp = node.get("ltp", node.get("last_price"))
        if ltp is None:
            return None
        ts_raw = node.get("ltt", node.get("last_update_time", 0))
        try:
            ts_ms = int(ts_raw) if ts_raw else 0
        except (TypeError, ValueError):
            ts_ms = 0
        try:
            vol = int(node.get("volume", node.get("total_traded_volume", 0)) or 0)
        except (TypeError, ValueError):
            vol = 0
        return Quote(
            symbol=symbol, exchange="NSE", last_price=float(ltp), volume=vol,
            ts=_ist_from_ms(ts_ms), freshness=self._quote_freshness(),
            source="upstox",
        )

    # -- health ---------------------------------------------------------

    async def health(self) -> dict:
        feed = self._feed()
        return {
            "provider": self.name,
            "healthy": True,
            "mode": "sandbox" if self.sandbox else "live",
            "order_endpoints": "none (paper trading only)",
            "ws_enabled": feed is not None,
            "ws_connected": bool(feed and feed.connected),
            "token_configured": bool(
                get_settings().upstox_analytics_token
                or get_settings().upstox_access_token
            ),
            "quotes_via": "websocket+rest-fallback" if feed else "rest",
        }
