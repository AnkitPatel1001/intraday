"""Input-validation bounds (422) and manual 400 checks."""

from httpx import AsyncClient, ASGITransport

from app.main import app

transport = ASGITransport(app=app)


async def post_json(url: str, payload: dict):
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.post(url, json=payload)


class TestCostsBounds:
    async def test_zero_entry_422(self):
        r = await post_json("/api/v1/trades/costs",
                            {"entry": 0, "qty": 100, "side": "buy"})
        assert r.status_code == 422

    async def test_negative_entry_422(self):
        r = await post_json("/api/v1/trades/costs",
                            {"entry": -10, "qty": 100, "side": "buy"})
        assert r.status_code == 422

    async def test_zero_qty_422(self):
        r = await post_json("/api/v1/trades/costs",
                            {"entry": 100, "qty": 0, "side": "buy"})
        assert r.status_code == 422

    async def test_huge_entry_422(self):
        r = await post_json("/api/v1/trades/costs",
                            {"entry": 1e12, "qty": 1, "side": "buy"})
        assert r.status_code == 422


class TestSizeBounds:
    async def test_zero_capital_422(self):
        r = await post_json("/api/v1/trades/size",
                            {"capital": 0, "risk_pct": 1, "entry": 100, "stop": 99})
        assert r.status_code == 422

    async def test_risk_over_100_422(self):
        r = await post_json("/api/v1/trades/size",
                            {"capital": 100000, "risk_pct": 101,
                             "entry": 100, "stop": 99})
        assert r.status_code == 422

    async def test_valid_returns_200(self):
        r = await post_json("/api/v1/trades/size",
                            {"capital": 100000, "risk_pct": 1,
                             "entry": 100, "stop": 95})
        assert r.status_code == 200
        assert "shares" in r.json() or "qty" in r.json()


class TestPlanBounds:
    async def test_zero_capital_422(self):
        r = await post_json("/api/v1/trades/plan",
                            {"symbol": "RELIANCE", "capital": 0})
        assert r.status_code == 422

    async def test_zero_target_r_422(self):
        r = await post_json("/api/v1/trades/plan",
                            {"symbol": "RELIANCE", "target_r": 0})
        assert r.status_code == 422

    async def test_risk_pct_over_100_422(self):
        r = await post_json("/api/v1/trades/plan",
                            {"symbol": "RELIANCE", "risk_pct": 101})
        assert r.status_code == 422

    async def test_bad_entry_bar_400(self):
        r = await post_json("/api/v1/trades/plan",
                            {"symbol": "RELIANCE", "entry_bar": 999})
        assert r.status_code == 400

    async def test_unknown_symbol_400(self):
        r = await post_json("/api/v1/trades/plan", {"symbol": "NOT A SYMBOL!"})
        assert r.status_code == 400


class TestTimeMachineBounds:
    async def test_zero_replays_422(self):
        r = await post_json("/api/v1/trades/timemachine",
                            {"symbol": "RELIANCE", "entry": 100, "stop": 95,
                             "target": 110, "replays": 0})
        assert r.status_code == 422

    async def test_negative_entry_422(self):
        r = await post_json("/api/v1/trades/timemachine",
                            {"symbol": "RELIANCE", "entry": -1, "stop": 95,
                             "target": 110})
        assert r.status_code == 422

    async def test_stop_above_entry_400(self):
        r = await post_json("/api/v1/trades/timemachine",
                            {"symbol": "RELIANCE", "entry": 100, "stop": 110,
                             "target": 120})
        assert r.status_code == 400


class TestBacktestBounds:
    async def test_zero_days_422(self):
        r = await post_json("/api/v1/backtest/run",
                            {"symbol": "RELIANCE", "days": 0})
        assert r.status_code == 422

    async def test_negative_capital_422(self):
        r = await post_json("/api/v1/backtest/run",
                            {"symbol": "RELIANCE", "capital": -1})
        assert r.status_code == 422

    async def test_unknown_strategy_400(self):
        r = await post_json("/api/v1/backtest/run",
                            {"symbol": "RELIANCE", "strategy": "magic"})
        assert r.status_code == 400


class TestScannerCap:
    async def test_101_symbols_422(self):
        syms = [f"SYM{i}" for i in range(101)]
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/scanner/scan", json={"symbols": syms})
        assert r.status_code == 422
        assert "100" in r.json()["detail"]

    async def test_100_symbols_accepted(self):
        from app.core.symbols import DEMO_UNIVERSE
        syms = (DEMO_UNIVERSE * 20)[:100]
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/scanner/scan", json={"symbols": syms})
        assert r.status_code == 200


class TestRiskBounds:
    """F-03: risk/check numeric bounds (was: unbounded list build + inf)."""

    async def test_huge_open_positions_422(self):
        r = await post_json("/api/v1/risk/check", {
            "symbol": "RELIANCE", "side": "buy",
            "entry": 100, "stop": 95, "target": 110,
            "open_positions": 5_000_000,
        })
        assert r.status_code == 422

    async def test_negative_shares_422(self):
        r = await post_json("/api/v1/risk/check", {
            "symbol": "RELIANCE", "side": "buy",
            "entry": 100, "stop": 95, "target": 110,
            "shares": -1,
        })
        assert r.status_code == 422

    async def test_zero_entry_422(self):
        r = await post_json("/api/v1/risk/check", {
            "symbol": "RELIANCE", "side": "buy",
            "entry": 0, "stop": 95, "target": 110,
        })
        assert r.status_code == 422

    async def test_negative_trades_today_422(self):
        r = await post_json("/api/v1/risk/check", {
            "symbol": "RELIANCE", "side": "buy",
            "entry": 100, "stop": 95, "target": 110,
            "trades_today": -1,
        })
        assert r.status_code == 422

    async def test_inf_entry_422(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post(
                "/api/v1/risk/check",
                content=b'{"symbol":"RELIANCE","side":"buy",'
                        b'"entry":1e400,"stop":95,"target":110}',
                headers={"content-type": "application/json"},
            )
        assert r.status_code == 422

    async def test_valid_check_still_200(self):
        r = await post_json("/api/v1/risk/check", {
            "symbol": "RELIANCE", "side": "buy",
            "entry": 100, "stop": 95, "target": 110,
            "shares": 100, "capital": 500000, "open_positions": 2,
        })
        assert r.status_code == 200


class TestPaperManualChecks:
    async def test_order_qty_zero_400(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/paper/order",
                             json={"symbol": "RELIANCE", "side": "buy", "qty": 0})
            assert r.status_code == 400

    async def test_order_bad_side_400(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/paper/order",
                             json={"symbol": "RELIANCE", "side": "short", "qty": 1})
            assert r.status_code == 400

    async def test_order_bad_type_400(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/paper/order",
                             json={"symbol": "RELIANCE", "side": "buy", "qty": 1,
                                   "order_type": "stop"})
            assert r.status_code == 400

    async def test_order_negative_price_400(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/paper/order",
                             json={"symbol": "RELIANCE", "side": "buy", "qty": 1,
                                   "order_type": "limit", "price": -5})
            assert r.status_code == 400

    async def test_order_limit_without_price_400(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/paper/order",
                             json={"symbol": "RELIANCE", "side": "buy", "qty": 1,
                                   "order_type": "limit"})
            assert r.status_code == 400

    async def test_order_huge_qty_400(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/paper/order",
                             json={"symbol": "RELIANCE", "side": "buy",
                                   "qty": 10_000_000})
            assert r.status_code == 400

    async def test_order_long_tag_400(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/paper/order",
                             json={"symbol": "RELIANCE", "side": "buy", "qty": 1,
                                   "tag": "x" * 201})
            assert r.status_code == 400

    async def test_reset_nonpositive_cash_400(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/paper/reset?starting_cash=0")
            assert r.status_code == 400
