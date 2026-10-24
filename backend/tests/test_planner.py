"""Tests for trade planner and cost estimation."""

import pytest
from app.engine.planner import estimate_costs, position_size, TradePlan


class TestCosts:
    def test_basic(self):
        c = estimate_costs(1000, 10, "buy")
        assert c["brokerage"] > 0
        assert c["stt"] > 0
        assert c["exchange_charges"] > 0
        assert c["gst"] > 0
        assert c["stamp_duty"] > 0
        assert c["total_est"] > 0

    def test_total_is_sum(self):
        c = estimate_costs(1000, 10, "buy")
        components = (c["brokerage"] + c["stt"] + c["exchange_charges"] +
                      c["sebi_fees"] + c["stamp_duty"] + c["gst"])
        assert abs(c["total_est"] - components - c["slippage_est"]) < 0.1

    def test_scales_with_qty(self):
        c1 = estimate_costs(1000, 10)
        c2 = estimate_costs(1000, 20)
        assert c2["total_est"] > c1["total_est"]

    def test_as_pct(self):
        c = estimate_costs(1000, 10)
        assert c["as_pct_of_turnover"] > 0
        assert c["as_pct_of_turnover"] < 1  # should be < 1% for intraday


class TestPositionSize:
    def test_basic(self):
        r = position_size(500000, 1.0, 100, 95)
        # risk_amount = 500000 * 1% = 5000, risk/share = 5, shares = 1000
        assert r["shares"] == 1000
        assert r["risk_amount"] == 5000

    def test_capital_limited(self):
        r = position_size(10000, 1.0, 5000, 4950)
        # risk_amount=100, risk/share=50, shares=2, cost=10000
        # cost > capital? 10000 <= 10000 so ok
        assert r["shares"] == 2

    def test_capital_hard_limit(self):
        r = position_size(5000, 10.0, 4000, 3800)
        # risk_amount=500, risk/share=200, shares=2, cost=8000 > 5000
        # so shares = int(5000/4000) = 1
        assert r["shares"] == 1

    def test_zero_risk(self):
        r = position_size(500000, 1.0, 100, 100)
        assert "error" in r

    def test_pct_of_capital(self):
        r = position_size(500000, 1.0, 100, 95)
        assert r["pct_of_capital"] > 0


class TestTradePlan:
    def test_fields(self):
        p = TradePlan(
            symbol="RELIANCE", side="buy", entry=100, stop=95, target=110,
            entry_bar=5, entry_time="09:40", risk_per_share=5, reward_per_share=10,
            risk_reward=2.0, setup="orb", stop_rule="or_mid", target_r=2.0,
            invalidation="close below 95", max_holding_bars=70,
        )
        assert p.symbol == "RELIANCE"
        assert p.risk_reward == 2.0
        assert "RESEARCH" in p.label
