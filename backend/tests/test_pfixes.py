"""Retest suite for PENTEST_REPORT_2.md findings P-01..P-21 (TDD red->green)."""

import asyncio
import datetime
import json
import math

import pytest
from httpx import AsyncClient, ASGITransport

from app.core.config import get_settings
from app.core.primitives import BarSeries, Candle, DataFreshness
from app.core.ratelimit import limiter
from app.core.timezone import IST
from app.engine.backtest import run_backtest, orb_strategy
from app.main import app

transport = ASGITransport(app=app)


def _series(days: int = 20, step: float = 1.002) -> BarSeries:
    """Multi-day 5m up-trend series."""
    candles = []
    base = datetime.datetime(2026, 9, 1, 9, 15, tzinfo=IST)
    price = 1000.0
    for day in range(days + 10):
        d = base + datetime.timedelta(days=day)
        if d.weekday() >= 5:
            continue
        for slot in range(75):
            ts = d + datetime.timedelta(minutes=slot * 5)
            o = price
            c = price * step
            candles.append(Candle(ts=ts, open=round(o, 2), high=round(c * 1.001, 2),
                                  low=round(o * 0.999, 2), close=round(c, 2),
                                  volume=100000))
            price = c
    return BarSeries(symbol="RELIANCE", interval="5m", exchange="NSE",
                     freshness=DataFreshness.SYNTHETIC, source="synthetic",
                     as_of=candles[-1].ts, candles=candles)


class TestP01NoOvernight:
    def test_no_trades_cross_days(self):
        res = run_backtest(_series(), orb_strategy(15, "or_mid", 2.0), 500000, 1.0)
        assert res.trades, "expected some trades on up-trend series"
        overnight = [t for t in res.trades
                     if t.entry_time.date() != t.exit_time.date()]
        assert overnight == [], f"overnight trades leaked: {overnight[:3]}"

    def test_assumption_now_true(self):
        res = run_backtest(_series(), orb_strategy(15, "or_mid", 2.0), 500000, 1.0)
        assert any("Intraday only" in a for a in res.assumptions)


class TestP02TradeCount:
    async def test_roundtrip_counts_two_fills(self):
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            await c.post("/api/v1/paper/reset")
            await c.post("/api/v1/paper/order",
                         json={"symbol": "RELIANCE", "side": "buy", "qty": 1})
            await c.post("/api/v1/paper/order",
                         json={"symbol": "RELIANCE", "side": "sell", "qty": 1})
            perf = (await c.get("/api/v1/analytics/performance")).json()
            assert perf["trade_count"] == 2


class TestP03OutOfSession:
    async def test_weekend_order_rejected(self):
        s = get_settings()
        prev = s.paper_allow_off_hours
        s.paper_allow_off_hours = False
        try:
            now = datetime.datetime.now(IST)
            if now.weekday() < 5 and 9 <= now.hour < 16:
                pytest.skip("market currently open; weekend path not reachable")
            async with AsyncClient(transport=transport, base_url="http://t") as c:
                r = await c.post("/api/v1/paper/order",
                                 json={"symbol": "RELIANCE", "side": "buy", "qty": 1})
                assert r.status_code == 400
                assert "session" in r.json()["detail"].lower()
        finally:
            s.paper_allow_off_hours = prev

    def test_off_hours_allowed_flag_exists(self):
        s = get_settings()
        assert hasattr(s, "paper_allow_off_hours")


class TestP04FutureDates:
    async def test_future_date_400(self):
        future = datetime.date.today() + datetime.timedelta(days=14)
        while future.weekday() >= 5:
            future += datetime.timedelta(days=1)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.post("/api/v1/trades/timemachine", json={
                "symbol": "RELIANCE", "date": future.isoformat(),
                "entry": 2500, "stop": 2450, "target": 2600, "replays": 10,
            })
            assert r.status_code == 400
            assert "future" in r.json()["detail"].lower()


class TestP05StopTarget:
    async def test_stop_target_roundtrip(self):
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            await c.post("/api/v1/paper/reset")
            r = await c.post("/api/v1/paper/order", json={
                "symbol": "RELIANCE", "side": "buy", "qty": 1,
                "stop": 1.0, "target": 999999.0,
            })
            assert r.status_code == 200
            pf = (await c.get("/api/v1/paper/portfolio")).json()
            pos = pf["positions"][0]
            assert pos["stop"] == 1.0
            assert pos["target"] == 999999.0

    async def test_stop_triggers_auto_exit(self, monkeypatch):
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            await c.post("/api/v1/paper/reset")
            await c.post("/api/v1/paper/order", json={
                "symbol": "RELIANCE", "side": "buy", "qty": 1,
                "stop": 2650.0, "target": 999999.0,
            })
            # force a quote below the stop on the next order interaction
            import app.api.paper as paper_api

            class FakeQ:
                last_price = 2600.0

            class FakeP:
                async def get_quote(self, symbol):
                    return FakeQ()

            monkeypatch.setattr(paper_api, "get_provider", lambda: FakeP())
            r = await c.post("/api/v1/paper/order", json={
                "symbol": "RELIANCE", "side": "buy", "qty": 1,
            })
            assert r.status_code == 200
            pf = (await c.get("/api/v1/paper/portfolio")).json()
            # position auto-closed by stop before new order logic
            assert pf["positions"] == [] or pf["positions"][0]["qty"] >= 1
            orders = (await c.get("/api/v1/paper/orders")).json()["orders"]
            stop_exits = [o for o in orders if o.get("tag") == "stop_exit"]
            assert stop_exits, "expected stop_exit order in log"

    async def test_bad_stop_rejected(self):
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.post("/api/v1/paper/order", json={
                "symbol": "RELIANCE", "side": "buy", "qty": 1,
                "stop": 99999.0,
            })
            assert r.status_code == 400


class TestP06RateLimitPerToken:
    async def test_buckets_isolated_per_token(self):
        s = get_settings()
        s.rate_limit_per_minute = 2
        limiter.reset()
        try:
            async with AsyncClient(transport=transport, base_url="http://t") as c:
                tok_a = (await c.post("/api/v1/auth/session")).json()["token"]
                tok_b = (await c.post("/api/v1/auth/session")).json()["token"]
                ha = {"X-Session-Token": tok_a}
                hb = {"X-Session-Token": tok_b}
                assert (await c.get("/api/v1/paper/portfolio", headers=ha)).status_code == 200
                assert (await c.get("/api/v1/paper/portfolio", headers=ha)).status_code == 200
                assert (await c.get("/api/v1/paper/portfolio", headers=ha)).status_code == 429
                # token B unaffected by A's exhaustion
                assert (await c.get("/api/v1/paper/portfolio", headers=hb)).status_code == 200
        finally:
            s.rate_limit_per_minute = 0
            limiter.reset()


class TestP07ProfitFactorFinite:
    def test_all_win_series_finite_pf(self):
        res = run_backtest(_series(step=1.004), orb_strategy(15, "or_low", 80.0),
                           500000, 1.0)
        assert math.isfinite(res.profit_factor)
        assert res.profit_factor <= 999.99

    async def test_api_json_strict(self):
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.post("/api/v1/backtest/run", json={
                "symbol": "RELIANCE", "days": 60, "target_r": 80, "or_minutes": 15,
            })
        assert "Infinity" not in r.text
        assert "NaN" not in r.text


def _alt_series(days: int = 20) -> BarSeries:
    """Alternating up-day/down-day series: nonzero daily variance."""
    candles = []
    base = datetime.datetime(2026, 9, 1, 9, 15, tzinfo=IST)
    price = 1000.0
    for day in range(days + 10):
        d = base + datetime.timedelta(days=day)
        if d.weekday() >= 5:
            continue
        step = 1.001 if day % 2 == 0 else 0.999
        for slot in range(75):
            ts = d + datetime.timedelta(minutes=slot * 5)
            o = price
            c = price * step
            candles.append(Candle(ts=ts, open=round(o, 2), high=round(c * 1.001, 2),
                                  low=round(o * 0.999, 2), close=round(c, 2),
                                  volume=100000))
            price = c
    return BarSeries(symbol="RELIANCE", interval="5m", exchange="NSE",
                     freshness=DataFreshness.SYNTHETIC, source="synthetic",
                     as_of=candles[-1].ts, candles=candles)


class TestP08Sharpe:
    def test_sharpe_daily_annualization_reasonable(self):
        res = run_backtest(_alt_series(), orb_strategy(15, "or_mid", 2.0),
                           500000, 1.0)
        assert math.isfinite(res.sharpe)
        # daily equity, sqrt(252): alternated days => |sharpe| well under 50
        assert abs(res.sharpe) < 50


class TestP09ClosedQty:
    async def test_closed_qty_preserved(self):
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            await c.post("/api/v1/paper/reset")
            await c.post("/api/v1/paper/order",
                         json={"symbol": "RELIANCE", "side": "buy", "qty": 7})
            await c.post("/api/v1/paper/order",
                         json={"symbol": "RELIANCE", "side": "sell", "qty": 7})
            perf = (await c.get("/api/v1/analytics/performance")).json()
            assert perf["closed_trades"][0]["qty"] == 7
            csv = (await c.get("/api/v1/analytics/export")).text
            rows = [r for r in csv.splitlines() if "RELIANCE" in r]
            assert any(",7," in r for r in rows), csv


class TestP10CsvSchema:
    async def test_csv_matches_header(self):
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            await c.post("/api/v1/paper/reset")
            await c.post("/api/v1/paper/order",
                         json={"symbol": "RELIANCE", "side": "buy", "qty": 3})
            await c.post("/api/v1/paper/order",
                         json={"symbol": "RELIANCE", "side": "sell", "qty": 3})
            csv = (await c.get("/api/v1/analytics/export")).text
        lines = csv.splitlines()
        header = lines[0].split(",")
        assert header == ["order_id", "symbol", "side", "order_type", "qty",
                          "fill_price", "slippage", "fees", "status", "tag"]
        for ln in lines[1:]:
            assert len(ln.split(",")) == len(header)


class TestP11LabelFixed:
    async def test_no_mojibake(self):
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            perf = (await c.get("/api/v1/analytics/performance")).json()
        assert "â€" not in perf["label"]
        assert "—" in perf["label"] or "simulated" in perf["label"]


class TestP12SmallSampleWarning:
    async def test_replays_1_warned(self):
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.post("/api/v1/trades/timemachine", json={
                "symbol": "RELIANCE", "date": "2026-10-23",
                "entry": 2500, "stop": 2450, "target": 2600, "replays": 1,
            })
        assert r.status_code == 200
        notes = r.json().get("verdict_notes") or []
        assert any("small sample" in n.lower() for n in notes), notes


class TestP13Ttl:
    async def test_stale_working_order_cancelled(self):
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            await c.post("/api/v1/paper/reset")
            await c.post("/api/v1/paper/order", json={
                "symbol": "RELIANCE", "side": "buy", "qty": 1,
                "order_type": "limit", "price": 10.0,
            })
            # age the order to yesterday
            from app.api.paper import get_engine
            e = get_engine("anonymous")
            e.orders[-1].created_at = datetime.datetime.now(IST) - datetime.timedelta(days=2)
            await c.post("/api/v1/paper/order", json={
                "symbol": "RELIANCE", "side": "buy", "qty": 1,
            })
            orders = (await c.get("/api/v1/paper/orders")).json()["orders"]
            statuses = [o["status"] for o in orders if o.get("limit_price") == 10.0]
            assert "cancelled" in statuses, statuses


class TestP14Cancel:
    async def test_cancel_working(self):
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            await c.post("/api/v1/paper/reset")
            r = await c.post("/api/v1/paper/order", json={
                "symbol": "RELIANCE", "side": "buy", "qty": 1,
                "order_type": "limit", "price": 10.0,
            })
            oid = r.json()["order"]["id"]
            r2 = await c.delete(f"/api/v1/paper/orders/{oid}")
            assert r2.status_code == 200
            assert r2.json()["cancelled"] is True

    async def test_cancel_unknown_404(self):
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.delete("/api/v1/paper/orders/does-not-exist")
            assert r.status_code == 404


class TestP15BarsCap:
    async def test_1m_year_capped(self):
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.get("/api/v1/market/bars/RELIANCE?interval=1m&days=365")
            assert r.status_code == 422

    async def test_5m_month_ok(self):
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.get("/api/v1/market/bars/RELIANCE?interval=5m&days=30")
            assert r.status_code == 200


class TestP17Rejected400:
    async def test_sell_without_position_400(self):
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            await c.post("/api/v1/paper/reset")
            r = await c.post("/api/v1/paper/order",
                             json={"symbol": "RELIANCE", "side": "sell", "qty": 5})
            assert r.status_code == 400

    async def test_insufficient_cash_400(self):
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            await c.post("/api/v1/paper/reset?starting_cash=100")
            r = await c.post("/api/v1/paper/order",
                             json={"symbol": "RELIANCE", "side": "buy", "qty": 1000})
            assert r.status_code == 400


class TestP18Benchmark:
    def test_engine_benchmark_return(self):
        s = _series()
        bench_candles = [
            Candle(ts=c.ts, open=round(c.close * 0.9, 2),
                   high=round(c.close * 0.91, 2), low=round(c.close * 0.89, 2),
                   close=round(c.close, 2), volume=10)
            for c in s.candles[::75]  # daily-ish
        ]
        bench = BarSeries(symbol="NIFTY50", interval="1d", exchange="NSE",
                          freshness=DataFreshness.SYNTHETIC, source="synthetic",
                          as_of=bench_candles[-1].ts, candles=bench_candles)
        res = run_backtest(s, orb_strategy(15, "or_mid", 2.0), 500000, 1.0,
                           benchmark=bench)
        assert res.benchmark_return > 5  # series rises ~0.2%/bar daily compounding

    async def test_api_has_benchmark(self):
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.post("/api/v1/backtest/run",
                             json={"symbol": "RELIANCE", "days": 60})
        data = r.json()
        assert "benchmark_return_pct" in data
        assert isinstance(data["benchmark_return_pct"], (int, float))


class TestP19NoopRemoved:
    def test_source_has_no_noop_cash(self):
        import inspect
        import app.engine.backtest as bt
        src = inspect.getsource(bt.run_backtest)
        assert "cost * 0" not in src


class TestP21ServerHeader:
    async def test_server_header_stripped(self):
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.get("/health")
        assert "server" not in {k.lower() for k in r.headers}
