"""Contract tests for the Yahoo adapter: HTTP error mapping, parse failures, fixtures."""

import datetime
import io
import json
import urllib.error

import pytest

from app.data import yahoo as y
from app.data.provider import DataError, RateLimitError
from app.core.primitives import DataFreshness


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://example", code, "err", {}, io.BytesIO(b""))


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    monkeypatch.setattr(y, "BACKOFF", 0)
    monkeypatch.setattr(y, "PAUSE", 0)


class TestHTTPErrorMapping:
    async def test_404_data_error(self, monkeypatch):
        def boom(url):
            raise _http_error(404)
        monkeypatch.setattr(y, "_fetch_sync", boom)
        p = y.YahooProvider()
        with pytest.raises(DataError):
            await p._get("http://x")

    async def test_429_rate_limit_error(self, monkeypatch):
        def boom(url):
            raise _http_error(429)
        monkeypatch.setattr(y, "_fetch_sync", boom)
        p = y.YahooProvider()
        with pytest.raises(RateLimitError):
            await p._get("http://x")

    async def test_500_falls_through_to_data_error(self, monkeypatch):
        calls = []

        def boom(url):
            calls.append(url)
            raise _http_error(503)
        monkeypatch.setattr(y, "_fetch_sync", boom)
        p = y.YahooProvider()
        with pytest.raises(DataError):
            await p._get("http://x")
        assert len(calls) >= 1

    async def test_403_data_error(self, monkeypatch):
        def boom(url):
            raise _http_error(403)
        monkeypatch.setattr(y, "_fetch_sync", boom)
        p = y.YahooProvider()
        with pytest.raises(DataError):
            await p._get("http://x")

    async def test_network_error_data_error(self, monkeypatch):
        def boom(url):
            raise urllib.error.URLError("no dns")
        monkeypatch.setattr(y, "_fetch_sync", boom)
        p = y.YahooProvider()
        with pytest.raises(DataError):
            await p._get("http://x")

    async def test_success_returns_body(self, monkeypatch):
        monkeypatch.setattr(y, "_fetch_sync", lambda url: '{"ok":1}')
        p = y.YahooProvider()
        assert await p._get("http://x") == '{"ok":1}'


class TestParseChart:
    def test_non_json(self):
        p = y.YahooProvider()
        with pytest.raises(DataError):
            p._parse_chart("not json at all", "RELIANCE", "5m")

    def test_missing_chart_key(self):
        p = y.YahooProvider()
        with pytest.raises(DataError):
            p._parse_chart(json.dumps({"foo": 1}), "RELIANCE", "5m")

    def test_empty_result_with_error(self):
        p = y.YahooProvider()
        payload = json.dumps({"chart": {"result": [], "error": {"description": "nope"}}})
        with pytest.raises(DataError) as ei:
            p._parse_chart(payload, "RELIANCE", "5m")
        assert "nope" in str(ei.value)

    def _payload(self, rows):
        ts, o, h, l, c = rows
        return json.dumps({
            "chart": {"result": [{
                "meta": {"symbol": "RELIANCE.NS"},
                "timestamp": ts,
                "indicators": {"quote": [{
                    "open": o, "high": h, "low": l, "close": c,
                    "volume": [1000] * len(ts),
                }]},
            }]},
        })

    def test_valid_payload(self):
        # 2026-10-20 09:15 IST == 2026-10-20 03:45 UTC
        t0 = int(datetime.datetime(2026, 10, 20, 3, 45,
                                   tzinfo=datetime.timezone.utc).timestamp())
        p = y.YahooProvider()
        series = p._parse_chart(
            self._payload(([t0, t0 + 300], [100.0, 101.0], [101.0, 102.0],
                           [99.5, 100.5], [100.5, 101.5])),
            "RELIANCE", "5m",
        )
        assert len(series.candles) == 2
        assert series.symbol == "RELIANCE"
        assert series.source == "yahoo"
        assert series.freshness == DataFreshness.DELAYED
        assert series.candles[0].open == 100.0

    def test_null_values_skipped(self):
        t0 = int(datetime.datetime(2026, 10, 20, 3, 45,
                                   tzinfo=datetime.timezone.utc).timestamp())
        p = y.YahooProvider()
        series = p._parse_chart(
            self._payload(([t0, t0 + 300], [100.0, None], [101.0, None],
                           [99.5, None], [100.5, None])),
            "RELIANCE", "5m",
        )
        assert len(series.candles) == 1

    def test_invalid_ohlc_skipped(self):
        t0 = int(datetime.datetime(2026, 10, 20, 3, 45,
                                   tzinfo=datetime.timezone.utc).timestamp())
        p = y.YahooProvider()
        # high < low -> row 1 invalid; row 2 valid (o,c within [l,h])
        series = p._parse_chart(
            self._payload(([t0, t0 + 300], [100.0, 107.0], [90.0, 110.0],
                           [95.0, 105.0], [100.0, 108.0])),
            "RELIANCE", "5m",
        )
        assert len(series.candles) == 1


class TestURL:
    def test_chart_url_nse_symbol(self):
        url = y._chart_url("RELIANCE", "5m", y.HOSTS[0])
        assert "RELIANCE.NS" in url
        assert "interval=5m" in url
        assert "query2.finance.yahoo.com" in url

    def test_chart_url_bse_passthrough(self):
        url = y._chart_url("RELIANCE.BO", "1d", y.HOSTS[0])
        assert "RELIANCE.BO" in url
        assert "interval=1d" in url

    def test_chart_url_intervals(self):
        for iv in ("1m", "5m", "15m", "1d", "1wk"):
            assert f"interval={iv}" in y._chart_url("TCS", iv, y.HOSTS[0])
