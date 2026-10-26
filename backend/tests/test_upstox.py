"""Tests for the Upstox market-data provider + WebSocket quote feed.

All offline: httpx.MockTransport for REST, hand-encoded protobuf for the feed.
PAPER-ONLY guarantee is asserted by source scan (no order endpoints).
"""

import datetime
import gzip
import json
import struct

import httpx
import pytest

from app.core.config import get_settings
from app.core.primitives import DataFreshness
from app.data.provider import AuthError, DataError, RateLimitError
from app.data.upstox import (
    INDEX_KEYS, INTERVAL_MAP, UpstoxProvider,
)
from app.data.upstox_feed import (
    UpstoxQuoteFeed, build_subscribe_payload, decode_feed_response, reset_feed,
)


# ------------------------------------------------- hand-rolled protobuf

def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
        if not n:
            return bytes(out)


def _len_field(no: int, payload: bytes) -> bytes:
    return _varint((no << 3) | 2) + _varint(len(payload)) + payload


def _var_field(no: int, n: int) -> bytes:
    return _varint((no << 3) | 0) + _varint(n)


def _dbl_field(no: int, x: float) -> bytes:
    return _varint((no << 3) | 1) + struct.pack("<d", x)


def encode_ltpc(ltp: float, ltt: int, ltq: int, cp: float) -> bytes:
    return (_dbl_field(1, ltp) + _var_field(2, ltt)
            + _var_field(3, ltq) + _dbl_field(4, cp))


def encode_feed_response(feeds: dict[str, bytes], current_ts: int = 1761420000000) -> bytes:
    out = bytearray()
    out += _var_field(1, 1)  # type = live_feed
    for key, feed in feeds.items():
        entry = _len_field(1, key.encode()) + _len_field(2, feed)
        out += _len_field(2, entry)
    out += _var_field(3, current_ts)
    return bytes(out)


def golden_response() -> bytes:
    """FeedResponse{feeds: {'NSE_EQ|INE002A01018': Feed{ltpc{...}}} + junk field}."""
    ltpc = encode_ltpc(2645.55, 1761420000000, 25, 2630.10)
    feed = _len_field(1, ltpc)
    entry = _len_field(1, b"NSE_EQ|INE002A01018") + _len_field(2, feed)
    out = bytearray()
    out += _var_field(1, 1)
    out += _len_field(2, entry)
    out += _var_field(3, 1761420000123)
    out += _len_field(99, b"future-field")  # unknown field must be skipped
    return bytes(out)


@pytest.fixture(autouse=True)
def _clean_feed():
    reset_feed()
    yield
    reset_feed()


@pytest.fixture
def settings():
    s = get_settings()
    prev = (s.upstox_analytics_token, s.upstox_access_token, s.upstox_ws_enabled,
            s.upstox_instrument_cache, s.upstox_base_url, s.upstox_rest_max_per_second)
    yield s
    (s.upstox_analytics_token, s.upstox_access_token, s.upstox_ws_enabled,
     s.upstox_instrument_cache, s.upstox_base_url, s.upstox_rest_max_per_second) = prev


@pytest.fixture
def with_token(settings):
    settings.upstox_analytics_token = "test-analytics-token"
    settings.upstox_access_token = ""
    return settings


@pytest.fixture
def map_cache(tmp_path, settings):
    """Write a fresh on-disk instrument map (no network)."""
    path = tmp_path / "instruments.json"
    path.write_text(json.dumps({
        "fetched_at": datetime.date.today().isoformat(),
        "map": {"RELIANCE": "NSE_EQ|INE002A01016", "TCS": "NSE_EQ|INE467B01029"},
    }), encoding="utf-8")
    settings.upstox_instrument_cache = str(path)
    return path


# ------------------------------------------------- protobuf feed wire

class TestFeedWire:
    def test_decode_golden_ltpc(self):
        msg = decode_feed_response(golden_response())
        assert msg["type"] == 1
        assert msg["currentTs"] == 1761420000123
        ltpc = msg["feeds"]["NSE_EQ|INE002A01018"]
        assert ltpc["ltp"] == pytest.approx(2645.55)
        assert ltpc["cp"] == pytest.approx(2630.10)
        assert ltpc["ltt"] == 1761420000000
        assert ltpc["ltq"] == 25

    def test_decode_rejects_garbage(self):
        with pytest.raises(ValueError):
            decode_feed_response(b"\x0e\x01")  # wire type 6 invalid

    def test_subscribe_payload_shape(self):
        raw = build_subscribe_payload(["NSE_INDEX|NIFTY 50"], mode="ltpc",
                                      guid="fixed-guid")
        doc = json.loads(raw.decode("utf-8"))
        assert doc == {
            "guid": "fixed-guid", "method": "sub",
            "data": {"instrumentKeys": ["NSE_INDEX|NIFTY 50"], "mode": "ltpc"},
        }

    def test_feed_cache_updates_from_message(self):
        feed = UpstoxQuoteFeed(lambda: "tok")
        feed._handle_message(golden_response())
        cached = feed.get_cached("NSE_EQ|INE002A01018")
        assert cached is not None
        ltp, cp, ts_ms = cached
        assert ltp == pytest.approx(2645.55)
        assert cp == pytest.approx(2630.10)
        assert ts_ms == 1761420000000


# ------------------------------------------------- auth

class TestAuth:
    async def test_missing_token_raises_with_instructions(self, settings, map_cache):
        settings.upstox_analytics_token = ""
        settings.upstox_access_token = ""
        p = UpstoxProvider()
        with pytest.raises(AuthError) as e:
            await p.get_quote("RELIANCE")
        assert "UPSTOX_ANALYTICS_TOKEN" in str(e.value)

    async def test_401_maps_to_auth_error(self, with_token, map_cache):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "expired"})
        p = UpstoxProvider(transport=httpx.MockTransport(handler))
        with pytest.raises(AuthError):
            await p.get_bars("RELIANCE", "5m",
                             datetime.date(2026, 10, 1), datetime.date(2026, 10, 20))


# ------------------------------------------------- bars

def _candle_row(day: int, price: float = 100.0) -> list:
    return [f"2026-10-{day:02d}T09:15:00+05:30", price, price + 1,
            price - 1, price + 0.5, 10000, 0]


class TestBars:
    async def test_daily_single_request_and_shape(self, with_token, map_cache):
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            rows = [_candle_row(d) for d in range(1, 6)]
            return httpx.Response(200, json={"status": "success",
                                             "data": {"candles": rows}})
        p = UpstoxProvider(transport=httpx.MockTransport(handler))
        s = await p.get_bars("RELIANCE", "1d",
                             datetime.date(2026, 10, 1), datetime.date(2026, 10, 5))
        assert len(seen) == 1
        assert "/v3/historical-candle/NSE_EQ%7CINE002A01016/days/1/" in seen[0]
        assert s.source == "upstox"
        assert s.freshness == DataFreshness.HISTORICAL
        assert len(s.candles) == 5
        assert s.candles[0].ts < s.candles[-1].ts  # ascending
        assert s.as_of == s.candles[-1].ts

    async def test_intraday_90d_chunks_into_4(self, with_token, map_cache):
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            return httpx.Response(200, json={
                "status": "success",
                "data": {"candles": [_candle_row(1)]}})
        p = UpstoxProvider(transport=httpx.MockTransport(handler))
        await p.get_bars("RELIANCE", "5m",
                         datetime.date(2026, 7, 28), datetime.date(2026, 10, 25))
        # 90 days / 27-day chunks = 4 windows
        assert len(seen) == 4
        assert all("/minutes/5/" in u for u in seen)

    async def test_interval_mapping(self, with_token, map_cache):
        want = {"1m": "minutes/1", "5m": "minutes/5",
                "15m": "minutes/15", "1d": "days/1"}
        for iv, seg in want.items():
            assert INTERVAL_MAP[iv][:2] == tuple(seg.split("/"))

    async def test_empty_response_raises(self, with_token, map_cache):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"status": "success",
                                             "data": {"candles": []}})
        p = UpstoxProvider(transport=httpx.MockTransport(handler))
        with pytest.raises(DataError):
            await p.get_bars("RELIANCE", "1d",
                             datetime.date(2026, 10, 1), datetime.date(2026, 10, 5))

    async def test_index_symbol_uses_static_key_no_master(self, with_token, settings):
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            return httpx.Response(200, json={
                "status": "success", "data": {"candles": [_candle_row(1)]}})
        p = UpstoxProvider(transport=httpx.MockTransport(handler))
        s = await p.get_bars("NIFTY50", "1d",
                             datetime.date(2026, 10, 1), datetime.date(2026, 10, 5))
        assert "NSE_INDEX%7CNIFTY%2050" in seen[0]
        assert len(s) == 1


# ------------------------------------------------- rate limits

class TestRateLimit:
    async def test_429_then_success(self, with_token, map_cache):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(429, headers={"Retry-After": "0"},
                                      json={"detail": "slow down"})
            return httpx.Response(200, json={
                "status": "success", "data": {"candles": [_candle_row(1)]}})
        p = UpstoxProvider(transport=httpx.MockTransport(handler))
        s = await p.get_bars("RELIANCE", "1d",
                             datetime.date(2026, 10, 1), datetime.date(2026, 10, 5))
        assert len(s) == 1
        assert calls["n"] == 2

    async def test_persistent_429_raises_rate_limit_error(self, with_token, map_cache):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"Retry-After": "0"},
                                  json={"detail": "slow down"})
        p = UpstoxProvider(transport=httpx.MockTransport(handler))
        with pytest.raises(RateLimitError):
            await p.get_bars("RELIANCE", "1d",
                             datetime.date(2026, 10, 1), datetime.date(2026, 10, 5))


# ------------------------------------------------- quotes

class TestQuotes:
    async def test_rest_fallback_parses_ltp(self, with_token, map_cache, settings):
        settings.upstox_ws_enabled = False
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            return httpx.Response(200, json={"status": "success", "data": {
                "NSE_EQ|INE002A01016": {"ltp": 2641.5, "ltt": "1761420000000",
                                        "volume": 12345}}})
        p = UpstoxProvider(transport=httpx.MockTransport(handler))
        q = await p.get_quote("RELIANCE")
        assert q.last_price == 2641.5
        assert q.source == "upstox"
        assert q.volume == 12345
        assert q.ts.tzinfo is not None
        assert "/v3/market-quote/ltp" in seen[0]
        assert q.freshness in (DataFreshness.LIVE, DataFreshness.DELAYED)

    async def test_feed_cache_hit_makes_no_rest_call(self, with_token, map_cache):
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("REST must not be called on feed cache hit")
        p = UpstoxProvider(transport=httpx.MockTransport(handler))

        # fake a running feed with cached price (bypass real websockets)
        class FakeFeed:
            connected = True
            async def ensure_started(self): return None
            async def subscribe(self, keys): return None
            def get_cached(self, key):
                if key == "NSE_EQ|INE002A01016":
                    return (2650.0, 2640.0, 1761420000000)
                return None

        import app.data.upstox as up
        monkey_feed = FakeFeed()
        orig = p._feed
        p._feed = lambda: monkey_feed
        try:
            q = await p.get_quote("RELIANCE")
        finally:
            p._feed = orig
        assert q.last_price == 2650.0
        assert q.source == "upstox"

    async def test_batch_quotes_single_rest_call(self, with_token, map_cache, settings):
        settings.upstox_ws_enabled = False
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            return httpx.Response(200, json={"status": "success", "data": {
                "NSE_EQ|INE002A01016": {"ltp": 100.0},
                "NSE_EQ|INE467B01029": {"ltp": 200.0}}})
        p = UpstoxProvider(transport=httpx.MockTransport(handler))
        out = await p.get_batch_quotes(["RELIANCE", "TCS"])
        assert len(seen) == 1
        assert out["RELIANCE"].last_price == 100.0
        assert out["TCS"].last_price == 200.0

    async def test_no_quote_node_raises(self, with_token, map_cache, settings):
        settings.upstox_ws_enabled = False

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"status": "success", "data": {}})
        p = UpstoxProvider(transport=httpx.MockTransport(handler))
        with pytest.raises(DataError):
            await p.get_quote("RELIANCE")


# ------------------------------------------------- instruments

class TestInstruments:
    async def test_index_static_map(self, with_token, settings):
        settings.upstox_ws_enabled = False
        p = UpstoxProvider()
        assert await p.resolve_instrument("NIFTY50") == INDEX_KEYS["NIFTY50"]

    async def test_equity_from_disk_cache(self, with_token, map_cache):
        p = UpstoxProvider()
        assert await p.resolve_instrument("RELIANCE") == "NSE_EQ|INE002A01016"

    async def test_unknown_symbol_raises(self, with_token, map_cache):
        p = UpstoxProvider()
        with pytest.raises(DataError) as e:
            await p.resolve_instrument("NOSUCHCO")
        assert "not found" in str(e.value)

    def test_parse_instrument_master(self):
        rows = [
            {"trading_symbol": "RELIANCE", "instrument_key": "NSE_EQ|X",
             "instrument_type": "EQ"},
            {"trading_symbol": "NIFTY26OCTFUT", "instrument_key": "NSE_FO|Y",
             "instrument_type": "FUT"},
            {"trading_symbol": "ODD", "instrument_key": "NSE_EQ|Z"},
        ]
        raw = gzip.compress(json.dumps(rows).encode())
        out = UpstoxProvider._parse_instrument_master(raw)
        assert out == {"RELIANCE": "NSE_EQ|X", "ODD": "NSE_EQ|Z"}


# ------------------------------------------------- factory + config

class TestFactory:
    def test_factory_routes_upstox(self):
        from app.data.factory import _cache, get_provider
        _cache.pop("upstox", None)
        try:
            p = get_provider("upstox")
            assert isinstance(p, UpstoxProvider)
        finally:
            _cache.pop("upstox", None)

    def test_default_stays_demo(self):
        from app.data.factory import get_provider
        from app.data.synthetic import SyntheticProvider
        s = get_settings()
        prev = s.data_provider
        s.data_provider = "demo"
        try:
            p = get_provider()
            assert isinstance(p, SyntheticProvider)
        finally:
            s.data_provider = prev

    def test_config_fields_exist(self):
        s = get_settings()
        for attr in ("upstox_api_key", "upstox_api_secret", "upstox_access_token",
                     "upstox_analytics_token", "upstox_ws_enabled",
                     "upstox_base_url", "upstox_rest_max_per_second",
                     "upstox_instrument_cache"):
            assert hasattr(s, attr)


# ------------------------------------------------- paper-only guarantee

class TestPaperOnly:
    def test_no_order_endpoints_in_upstox_modules(self):
        for path in ("app/data/upstox.py", "app/data/upstox_feed.py"):
            src = open(path, encoding="utf-8").read()
            lowered = src.lower()
            for banned in ("/v2/order", "/v3/order", "place_order",
                           "gtt", "/v2/portfolio", "/v2/user"):
                assert banned not in lowered, f"{path} contains {banned}"
