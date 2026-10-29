"""Tests for trade planner and cost estimation."""

import pytest
from app.engine.planner import build_plan, estimate_costs, latest_entry_date, position_size, TradePlan


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

    def test_max_position_pct_caps_a_tight_stop(self):
        # risk_pct=1%, stop=0.5% of entry -> risk-budget sizing alone wants
        # ~2x capital; max_position_pct=25 must cap the cost to 25% of it.
        entry, stop = 2850.0, 2835.75
        r = position_size(500000, 1.0, entry, stop, max_position_pct=25.0)
        assert r["cost"] <= 500000 * 0.25 + 1e-6

    def test_max_position_pct_is_opt_in(self):
        # Omitting it must reproduce the old (uncapped-by-concentration) behaviour.
        a = position_size(500000, 1.0, 2850.0, 2835.75)
        b = position_size(500000, 1.0, 2850.0, 2835.75, max_position_pct=None)
        assert a == b


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
        assert p.date == ""


class TestLatestEntryDate:
    def test_picks_most_recent_day_with_enough_bars(self):
        import datetime
        from app.core.timezone import IST
        from app.core.primitives import Candle

        candles = []
        for d in (1, 2, 3):
            day = datetime.date(2026, 10, d)
            for slot in range(8):
                ts = datetime.datetime.combine(day, datetime.time(9, 15), tzinfo=IST) \
                    + datetime.timedelta(minutes=5 * slot)
                candles.append(Candle(ts=ts, open=100, high=101, low=99, close=100, volume=1))
        assert latest_entry_date(candles, 5) == datetime.date(2026, 10, 3)

    def test_raises_when_no_session_has_enough_bars(self):
        with pytest.raises(ValueError):
            latest_entry_date([], 5)

    def test_skips_a_day_with_an_early_gap(self):
        """Regression: picking a day by bar COUNT alone (not by matching
        bar_slot to time-of-day) could land on a day missing early bars —
        e.g. bars 0..4 absent but 6 later bars present (count=6 >= entry_bar+1
        for entry_bar=5) — and then silently index the wrong candle. The
        slot-matched picker must skip that day and fall back to an earlier,
        complete one."""
        import datetime
        from app.core.timezone import IST
        from app.core.primitives import Candle

        candles = []
        # Day 1 (older): a clean, complete session for the first 8 bars.
        day1 = datetime.date(2026, 10, 1)
        for slot in range(8):
            ts = datetime.datetime.combine(day1, datetime.time(9, 15), tzinfo=IST) \
                + datetime.timedelta(minutes=5 * slot)
            candles.append(Candle(ts=ts, open=100, high=101, low=99, close=100, volume=1))
        # Day 2 (most recent): bars 0..4 missing, only slots 5..10 present.
        day2 = datetime.date(2026, 10, 2)
        for slot in range(5, 11):
            ts = datetime.datetime.combine(day2, datetime.time(9, 15), tzinfo=IST) \
                + datetime.timedelta(minutes=5 * slot)
            candles.append(Candle(ts=ts, open=200, high=201, low=199, close=200, volume=1))

        # entry_bar=5 needs slots 0..5 — day 2 only has 6 bars by COUNT but
        # is missing slots 0..4, so it must be skipped in favour of day 1.
        assert latest_entry_date(candles, 5) == day1


class TestBuildPlanDateSelection:
    def test_uses_most_recent_session_not_oldest(self):
        """Regression: build_plan used to index entry_bar into the whole
        flat candle list, which always landed on the OLDEST day in the
        fetch window instead of the most recent usable session."""
        import asyncio
        import datetime
        from app.data.synthetic import SyntheticProvider

        series = asyncio.run(SyntheticProvider().get_bars(
            "RELIANCE", "5m", datetime.date(2026, 9, 1), datetime.date(2026, 10, 24)
        ))
        plan = build_plan("RELIANCE", series, entry_bar=10, side="buy")
        dates = sorted({c.ts.date() for c in series.candles})
        assert plan.date == dates[-1].isoformat()
        assert plan.date != dates[0].isoformat()
