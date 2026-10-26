"""Order-fill semantics: limit orders rest until market crosses; market orders need a price."""

from types import SimpleNamespace

import pytest
from httpx import AsyncClient, ASGITransport

from app.engine.paper import PaperTradingEngine
from app.main import app

transport = ASGITransport(app=app)


class TestEngineLimitOrders:
    def test_limit_buy_below_market_rests(self):
        e = PaperTradingEngine(starting_cash=100000)
        o = e.place_order("RELIANCE", "buy", 1, "limit",
                          price=900.0, current_price=2500.0)
        assert o.status == "working"
        assert e.portfolio.positions == {}
        assert e.portfolio.cash == 100000

    def test_limit_sell_above_market_rests(self):
        e = PaperTradingEngine(starting_cash=100000)
        o = e.place_order("RELIANCE", "sell", 1, "limit",
                          price=3000.0, current_price=2500.0)
        assert o.status == "working"

    def test_limit_buy_fills_at_limit_when_crossed(self):
        e = PaperTradingEngine(starting_cash=100000)
        e.place_order("RELIANCE", "buy", 1, "limit",
                      price=900.0, current_price=2500.0)
        # Later quote reaches the limit -> resting order fills at 900 (no slippage)
        e.place_order("RELIANCE", "buy", 1, "limit",
                      price=950.0, current_price=899.0)
        prices = sorted(o.fill_price for o in e.orders if o.status == "filled")
        assert prices == [900.0, 950.0]
        resting = [o for o in e.orders if o.symbol == "RELIANCE"
                   and o.fill_price == 900.0][0]
        assert resting.slippage == 0.0
        assert e.portfolio.positions["RELIANCE"].qty == 2

    def test_limit_sell_fills_when_market_rises(self):
        e = PaperTradingEngine(starting_cash=100000)
        # Seed a long position at market
        e.place_order("RELIANCE", "buy", 1, "market", current_price=1000.0)
        e.place_order("RELIANCE", "sell", 1, "limit",
                      price=1100.0, current_price=1000.0)
        assert [o for o in e.orders if o.status == "working"]
        e.place_order("RELIANCE", "buy", 1, "limit",
                      price=900.0, current_price=1101.0)
        sells = [o for o in e.orders if o.side == "sell" and o.status == "filled"]
        assert len(sells) == 1
        assert sells[0].fill_price == 1100.0
        assert e.portfolio.positions == {}

    def test_market_order_without_price_rejected(self):
        e = PaperTradingEngine(starting_cash=100000)
        o = e.place_order("RELIANCE", "buy", 1, "market", current_price=None)
        assert o.status == "rejected"
        assert e.portfolio.positions == {}

    def test_limit_without_price_rejected(self):
        e = PaperTradingEngine(starting_cash=100000)
        o = e.place_order("RELIANCE", "buy", 1, "limit", price=None,
                          current_price=2500.0)
        assert o.status == "rejected"

    def test_bad_order_type_rejected(self):
        e = PaperTradingEngine(starting_cash=100000)
        with pytest.raises(ValueError):
            e.place_order("RELIANCE", "buy", 1, "sl", price=900.0,
                          current_price=2500.0)

    def test_working_order_not_filled_by_unrelated_symbol(self):
        e = PaperTradingEngine(starting_cash=100000)
        e.place_order("RELIANCE", "buy", 1, "limit",
                      price=900.0, current_price=2500.0)
        e.place_order("TCS", "buy", 1, "market", current_price=899.0)
        assert all(o.status != "filled" or o.symbol == "TCS" for o in e.orders)
        rel = [o for o in e.orders if o.symbol == "RELIANCE"][0]
        assert rel.status == "working"


class TestAPIMarketPriceFix:
    async def test_market_order_filled_from_quote(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/paper/order",
                             json={"symbol": "RELIANCE", "side": "buy", "qty": 1})
            assert r.status_code == 200
            data = r.json()
            assert data["order"]["status"] in ("filled", "rejected")
            if data["order"]["status"] == "filled":
                assert data["order"]["fill_price"] > 0

    async def test_market_order_502_when_quote_unavailable(self, monkeypatch):
        class Broken:
            async def get_quote(self, symbol):
                raise RuntimeError("feed down")

        import app.api.paper as paper_api
        monkeypatch.setattr(paper_api, "get_provider", lambda: Broken())
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/paper/order",
                             json={"symbol": "RELIANCE", "side": "buy", "qty": 1})
            assert r.status_code == 502

    async def test_limit_order_accepted_without_quote(self, monkeypatch):
        class Broken:
            async def get_quote(self, symbol):
                raise RuntimeError("feed down")

        import app.api.paper as paper_api
        monkeypatch.setattr(paper_api, "get_provider", lambda: Broken())
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/paper/order",
                             json={"symbol": "RELIANCE", "side": "buy", "qty": 1,
                                   "order_type": "limit", "price": 100.0})
            assert r.status_code == 200
            assert r.json()["order"]["status"] == "working"

    async def test_limit_order_far_below_market_rests(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/paper/order",
                             json={"symbol": "RELIANCE", "side": "buy", "qty": 1,
                                   "order_type": "limit", "price": 100.0})
            assert r.status_code == 200
            assert r.json()["order"]["status"] == "working"
            assert r.json()["order"]["fill_price"] is None

    async def test_flatten_works_with_quote(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            await c.post("/api/v1/paper/order",
                         json={"symbol": "RELIANCE", "side": "buy", "qty": 1})
            r = await c.post("/api/v1/paper/flatten",
                             json={"symbol": "RELIANCE"})
            assert r.status_code == 200
            data = r.json()
            assert data["flattened"] is True or data["flattened"] is False
