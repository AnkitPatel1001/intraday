"""Tests for paper trading engine."""

import pytest
from app.engine.paper import PaperTradingEngine, Order, Position, Portfolio


class TestPaperEngine:
    def test_init(self):
        e = PaperTradingEngine(starting_cash=100000)
        assert e.portfolio.cash == 100000
        assert len(e.portfolio.positions) == 0

    def test_buy_market(self):
        e = PaperTradingEngine(100000)
        order = e.place_order("RELIANCE", "buy", 10, "market", current_price=1000)
        assert order.status == "filled"
        assert order.fill_price > 0
        assert "RELIANCE" in e.portfolio.positions
        assert e.portfolio.cash < 100000

    def test_buy_reduces_cash(self):
        e = PaperTradingEngine(100000)
        before = e.portfolio.cash
        e.place_order("RELIANCE", "buy", 10, "market", current_price=1000)
        assert e.portfolio.cash < before

    def test_sell_closes_position(self):
        e = PaperTradingEngine(100000)
        e.place_order("RELIANCE", "buy", 10, "market", current_price=1000)
        order = e.place_order("RELIANCE", "sell", 10, "market", current_price=1100)
        assert order.status == "filled"
        assert "RELIANCE" not in e.portfolio.positions
        assert e.portfolio.realized_pnl != 0

    def test_insufficient_cash_rejects(self):
        e = PaperTradingEngine(1000)
        order = e.place_order("RELIANCE", "buy", 100, "market", current_price=1000)
        assert order.status == "rejected"

    def test_sell_without_position_rejects(self):
        e = PaperTradingEngine(100000)
        order = e.place_order("RELIANCE", "sell", 10, "market", current_price=1000)
        assert order.status == "rejected"

    def test_invalid_qty(self):
        e = PaperTradingEngine(100000)
        with pytest.raises(ValueError):
            e.place_order("RELIANCE", "buy", 0, "market")

    def test_invalid_side(self):
        e = PaperTradingEngine(100000)
        with pytest.raises(ValueError):
            e.place_order("RELIANCE", "hold", 10, "market")

    def test_fees_deducted(self):
        e = PaperTradingEngine(100000)
        e.place_order("RELIANCE", "buy", 10, "market", current_price=1000)
        assert e.portfolio.total_fees > 0

    def test_flatten(self):
        e = PaperTradingEngine(100000)
        e.place_order("RELIANCE", "buy", 10, "market", current_price=1000)
        order = e.flatten("RELIANCE", 1100)
        assert order is not None
        assert "RELIANCE" not in e.portfolio.positions

    def test_flatten_empty(self):
        e = PaperTradingEngine(100000)
        assert e.flatten("RELIANCE", 1000) is None

    def test_snapshot(self):
        e = PaperTradingEngine(100000)
        snap = e.snapshot()
        assert snap["cash"] == 100000
        assert snap["label"] == "PAPER TRADING — simulated, no real money"

    def test_audit_log(self):
        e = PaperTradingEngine(100000)
        e.place_order("RELIANCE", "buy", 10, "market", current_price=1000)
        assert len(e.audit_log) > 0

    def test_avg_price_averaging(self):
        e = PaperTradingEngine(100000)
        e.place_order("RELIANCE", "buy", 10, "market", current_price=1000)
        e.place_order("RELIANCE", "buy", 10, "market", current_price=1100)
        pos = e.portfolio.positions["RELIANCE"]
        assert pos.qty == 20
        assert abs(pos.avg_price - 1050) < 1

    def test_partial_sell(self):
        e = PaperTradingEngine(100000)
        e.place_order("RELIANCE", "buy", 20, "market", current_price=1000)
        e.place_order("RELIANCE", "sell", 10, "market", current_price=1100)
        pos = e.portfolio.positions["RELIANCE"]
        assert pos.qty == 10

    def test_update_unrealized(self):
        e = PaperTradingEngine(100000)
        e.place_order("RELIANCE", "buy", 10, "market", current_price=1000)
        e.update_unrealized("RELIANCE", 1100)
        pos = e.portfolio.positions["RELIANCE"]
        assert pos.unrealized_pnl > 0
