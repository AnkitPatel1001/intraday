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

    def test_null_values_forward_filled(self):
        # Yahoo regularly returns null-OHLC bars near close; carry last close
        # forward so sessions stay complete (else Time Machine finds 0 full sessions).
        t0 = int(datetime.datetime(2026, 10, 20, 3, 45,
                                   tzinfo=datetime.timezone.utc).timestamp())
        p = y.YahooProvider()
        series = p._parse_chart(
            self._payload(([t0, t0 + 300], [100.0, None], [101.0, None],
                           [99.5, None], [100.5, None])),
            "RELIANCE", "5m",
        )
        assert len(series.candles) == 2
        flat = series.candles[1]
        assert (flat.open, flat.high, flat.low, flat.close) == (100.5,) * 4

    def test_leading_null_still_skipped(self):
        t0 = int(datetime.datetime(2026, 10, 20, 3, 45,
                                   tzinfo=datetime.timezone.utc).timestamp())
        p = y.YahooProvider()
        series = p._parse_chart(
            self._payload(([t0, t0 + 300], [None, 101.0], [None, 102.0],
                           [None, 100.0], [None, 101.5])),
            "RELIANCE", "5m",
        )
        assert len(series.candles) == 1
        assert series.candles[0].open == 101.0

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

    def test_chart_url_index_mapped(self):
        url = y._chart_url("NIFTY50", "5m", y.HOSTS[0])
        assert "%5ENSEI" in url  # ^NSEI url-encoded
        assert "NIFTY50.NS" not in url

    def test_chart_url_banknifty_mapped(self):
        assert "%5ENSEBANK" in y._chart_url("BANKNIFTY", "1d", y.HOSTS[0])

    def test_chart_url_period_honors_start_end(self):
        start = datetime.date(2026, 9, 1)
        end = datetime.date(2026, 10, 24)
        url = y._chart_url("RELIANCE", "1d", y.HOSTS[0], start, end)
        assert "period1=" in url and "period2=" in url
        assert "range=" not in url

    def test_chart_url_period_clamped_to_60d_for_5m(self):
        start = datetime.date(2026, 1, 1)
        end = datetime.date(2026, 10, 24)
        url = y._chart_url("RELIANCE", "5m", y.HOSTS[0], start, end)
        p1 = int(url.split("period1=")[1].split("&")[0])
        p2 = int(url.split("period2=")[1].split("&")[0])
        span_days = (p2 - p1) / 86400
        assert span_days <= 60  # yahoo 5m hard limit (else HTTP 422)
        # lookback also measured from today, not from the requested end
        import datetime as dt
        from app.core.timezone import IST
        floor = dt.datetime.now(IST).date() - dt.timedelta(days=60)
        p1_date = dt.datetime.fromtimestamp(p1, IST).date()
        assert p1_date >= floor


class TestIndexMeta:
    def test_index_symbol_survives_parse(self):
        # meta.symbol is ^NSEI but consumers ask for NIFTY50 (valid NSE format)
        t0 = int(datetime.datetime(2026, 10, 20, 3, 45,
                                   tzinfo=datetime.timezone.utc).timestamp())
        payload = json.dumps({
            "chart": {"result": [{
                "meta": {"symbol": "^NSEI"},
                "timestamp": [t0],
                "indicators": {"quote": [{
                    "open": [22600.0], "high": [22650.0],
                    "low": [22550.0], "close": [22600.0],
                    "volume": [0],
                }]},
            }]},
        })
        p = y.YahooProvider()
        series = p._parse_chart(payload, "NIFTY50", "5m")
        assert series.symbol == "NIFTY50"
        assert series.candles[0].close == 22600.0
