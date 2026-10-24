"""Tests for FastAPI endpoints."""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


transport = ASGITransport(app=app)


async def client():
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestHealth:
    async def test_health(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/health")
            assert r.status_code == 200
            data = r.json()
            assert data["status"] == "ok"
            assert data["paper"] is True


class TestMarket:
    async def test_status(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/market/status")
            assert r.status_code == 200
            data = r.json()
            assert "status" in data
            assert data["timezone"] == "Asia/Kolkata"

    async def test_universe(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/market/universe")
            assert r.status_code == 200
            data = r.json()
            assert len(data["symbols"]) > 0

    async def test_quote_valid(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/market/quote/RELIANCE")
            assert r.status_code == 200
            data = r.json()
            assert data["symbol"] == "RELIANCE"
            assert data["freshness"] == "synthetic"

    async def test_quote_invalid(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/market/quote/!!!")
            assert r.status_code == 400

    async def test_bars(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/market/bars/RELIANCE?interval=5m&days=10")
            assert r.status_code == 200
            data = r.json()
            assert data["symbol"] == "RELIANCE"
            assert len(data["candles"]) > 0
            assert data["freshness"] == "synthetic"

    async def test_bars_invalid_symbol(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/market/bars/!!!")
            assert r.status_code == 400

    async def test_indices(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/market/indices")
            assert r.status_code == 200
            data = r.json()
            assert "indices" in data


class TestScanner:
    async def test_scan(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/scanner/scan?symbols=RELIANCE,TCS&interval=5m&days=30")
            assert r.status_code == 200
            data = r.json()
            assert "results" in data
            assert "note" in data

    async def test_presets(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/scanner/presets")
            assert r.status_code == 200
            assert len(r.json()["presets"]) > 0


class TestTrades:
    async def test_costs(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/trades/costs", json={"entry": 1000, "qty": 10, "side": "buy"})
            assert r.status_code == 200
            data = r.json()
            assert data["total_est"] > 0

    async def test_size(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/trades/size", json={
                "capital": 500000, "risk_pct": 1.0, "entry": 100, "stop": 95
            })
            assert r.status_code == 200
            data = r.json()
            assert data["shares"] == 1000

    async def test_timemachine_invalid_symbol(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/trades/timemachine", json={
                "symbol": "!!!", "entry": 100, "stop": 95, "target": 110,
            })
            assert r.status_code == 400


class TestRisk:
    async def test_check_pass(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/risk/check", json={
                "symbol": "RELIANCE", "side": "buy",
                "entry": 100, "stop": 95, "target": 110,
                "shares": 100, "capital": 500000,
            })
            assert r.status_code == 200
            data = r.json()
            assert data["verdict"] in ("PASS", "BLOCK")

    async def test_check_block(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/risk/check", json={
                "symbol": "RELIANCE", "side": "buy",
                "entry": 100, "stop": 105, "target": 110,
            })
            assert r.status_code == 200
            data = r.json()
            assert data["verdict"] == "BLOCK"

    async def test_limits(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/risk/limits")
            assert r.status_code == 200
            assert r.json()["paper_trading"] is True


class TestPaper:
    async def test_portfolio(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/paper/portfolio")
            assert r.status_code == 200
            data = r.json()
            assert "cash" in data
            assert "PAPER" in data["label"]

    async def test_place_order(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/paper/order", json={
                "symbol": "RELIANCE", "side": "buy", "qty": 5,
                "order_type": "market",
            })
            assert r.status_code == 200
            data = r.json()
            assert data["order"]["status"] in ("filled", "rejected")

    async def test_order_invalid(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/paper/order", json={
                "symbol": "RELIANCE", "side": "buy", "qty": 0,
            })
            assert r.status_code == 400

    async def test_orders_list(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/paper/orders")
            assert r.status_code == 200


class TestAnalytics:
    async def test_performance(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/analytics/performance")
            assert r.status_code == 200
            data = r.json()
            assert "realized_pnl" in data
            assert "PAPER" in data["label"]

    async def test_export(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/analytics/export")
            assert r.status_code == 200
            assert "text/csv" in r.headers["content-type"]


class TestBacktest:
    async def test_run(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/backtest/run", json={
                "symbol": "RELIANCE", "strategy": "orb",
                "interval": "5m", "days": 30,
            })
            assert r.status_code == 200
            data = r.json()
            assert "total_return_pct" in data
            assert "trade_count" in data
            assert "assumptions" in data
            assert "note" in data

    async def test_unknown_strategy(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/backtest/run", json={
                "symbol": "RELIANCE", "strategy": "unknown",
            })
            assert r.status_code == 400
