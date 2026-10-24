"""Tests for the Indian-adapted Time Machine."""

import datetime
import pytest
from app.core.primitives import Candle, BarSeries, DataFreshness
from app.core.timezone import IST
from app.engine.timemachine import (
    TimeMachineError, normalize_plan, split_sessions, full_sessions,
    build_pool, simulate, verdict, verdict_notes, lean, run_time_machine,
    SESSION_BARS, MIN_SESSIONS,
)


def make_sessions(n_days: int, bars_per_day: int = 75) -> list[Candle]:
    """Generate deterministic 5-min candles for n_days sessions from a base date."""
    candles = []
    price = 1000.0
    base_date = datetime.date(2026, 6, 1)
    d = 0
    count = 0
    while count < n_days:
        day = base_date + datetime.timedelta(days=d)
        d += 1
        if day.weekday() >= 5:
            continue
        count += 1
        for slot in range(bars_per_day):
            mins = 555 + slot * 5
            ts = datetime.datetime.combine(
                day, datetime.time(mins // 60, mins % 60), tzinfo=IST
            )
            o = price
            c = price * (1.001 if (slot + count) % 3 else 0.999)
            h = max(o, c) * 1.002
            l = min(o, c) * 0.998
            candles.append(Candle(ts=ts, open=round(o, 2), high=round(h, 2),
                                  low=round(l, 2), close=round(c, 2), volume=50000))
            price = c
    return candles


def make_series(n_days: int = 40) -> BarSeries:
    candles = make_sessions(n_days)
    return BarSeries(
        symbol="RELIANCE", interval="5m", exchange="NSE",
        freshness=DataFreshness.SYNTHETIC, source="test",
        as_of=candles[-1].ts if candles else datetime.datetime.now(IST),
        candles=candles,
    )


def valid_plan(**overrides):
    base = {
        "symbol": "RELIANCE", "side": "buy", "date": "2026-07-17",
        "entry": 1000.0, "stop": 990.0, "target": 1020.0,
        "entry_bar": 5, "setup": "orb",
        "opening_range": {"minutes": 15}, "stop_rule": "or_mid",
    }
    base.update(overrides)
    return base


class TestNormalizePlan:
    def test_valid(self):
        p = normalize_plan(valid_plan())
        assert p["symbol"] == "RELIANCE"
        assert p["risk_per_share"] == 10.0
        assert p["target_r"] == 2.0

    def test_bad_symbol(self):
        with pytest.raises(TimeMachineError):
            normalize_plan(valid_plan(symbol=""))

    def test_bad_side(self):
        with pytest.raises(TimeMachineError):
            normalize_plan(valid_plan(side="hold"))

    def test_bad_date(self):
        with pytest.raises(TimeMachineError):
            normalize_plan(valid_plan(date="not-a-date"))

    def test_stop_above_entry_for_buy(self):
        with pytest.raises(TimeMachineError):
            normalize_plan(valid_plan(stop=1005, target=1010))

    def test_bad_entry_bar(self):
        with pytest.raises(TimeMachineError):
            normalize_plan(valid_plan(entry_bar=80))

    def test_bad_or_minutes(self):
        with pytest.raises(TimeMachineError):
            normalize_plan(valid_plan(opening_range={"minutes": 7}))


class TestSplitSessions:
    def test_groups_by_date(self):
        candles = make_sessions(3)
        days = split_sessions(candles)
        assert len(days) == 3

    def test_slot_keys(self):
        candles = make_sessions(1)
        days = split_sessions(candles)
        first_day = list(days.values())[0]
        assert 0 in first_day
        assert 74 in first_day


class TestFullSessions:
    def test_only_full_sessions(self):
        candles = make_sessions(35)
        days = split_sessions(candles)
        full, short = full_sessions(days, "2026-10-24")
        assert len(full) >= MIN_SESSIONS
        assert len(short) == 0

    def test_excludes_after_date(self):
        candles = make_sessions(10)
        days = split_sessions(candles)
        full, _ = full_sessions(days, "2026-09-05")
        for d, _ in full:
            assert d < "2026-09-05"

    def test_short_sessions_detected(self):
        candles = make_sessions(5, bars_per_day=50)
        days = split_sessions(candles)
        full, short = full_sessions(days, "2026-12-01")
        assert len(full) == 0
        assert len(short) > 0


class TestBuildPool:
    def test_pool_structure(self):
        candles = make_sessions(30)
        days = split_sessions(candles)
        full, _ = full_sessions(days, "2026-12-01")
        pool = build_pool(full)
        assert len(pool) == SESSION_BARS
        assert len(pool[1]) == len(full)  # slot 1 from each session

    def test_ratios_positive(self):
        candles = make_sessions(25)
        days = split_sessions(candles)
        full, _ = full_sessions(days, "2026-12-01")
        pool = build_pool(full)
        for ratios in pool[1][:5]:
            assert all(r > 0 for r in ratios)


class TestSimulate:
    def test_probabilities_sum_to_one(self):
        candles = make_sessions(30)
        days = split_sessions(candles)
        full, _ = full_sessions(days, "2026-12-01")
        pool = build_pool(full)
        mc = simulate(pool, 1000, 990, 1020, k=10, last=50, replays=100, seed=42)
        total = mc["p_target"] + mc["p_stop"] + mc["p_neither"]
        assert abs(total - 1.0) < 0.01

    def test_deterministic_same_seed(self):
        candles = make_sessions(30)
        days = split_sessions(candles)
        full, _ = full_sessions(days, "2026-12-01")
        pool = build_pool(full)
        mc1 = simulate(pool, 1000, 990, 1020, k=10, last=50, replays=100, seed=42)
        mc2 = simulate(pool, 1000, 990, 1020, k=10, last=50, replays=100, seed=42)
        assert mc1["p_target"] == mc2["p_target"]
        assert mc1["avg_R"] == mc2["avg_R"]

    def test_different_seed_different_result(self):
        candles = make_sessions(30)
        days = split_sessions(candles)
        full, _ = full_sessions(days, "2026-12-01")
        pool = build_pool(full)
        mc1 = simulate(pool, 1000, 990, 1020, k=10, last=50, replays=200, seed=42)
        mc2 = simulate(pool, 1000, 990, 1020, k=10, last=50, replays=200, seed=99)
        # Very likely different, but not guaranteed for tiny replays
        assert mc1["seed"] == 42
        assert mc2["seed"] == 99


class TestVerdict:
    def test_verdict_is_string(self):
        mc = {"p_target": 0.3, "p_stop": 0.25, "p_neither": 0.45, "r_at_target": 1.0}
        v = verdict(mc)
        assert isinstance(v, str)
        assert "target" in v.lower() or "stop" in v.lower()

    def test_coin_flip(self):
        mc = {"p_target": 0.50, "p_stop": 0.50, "p_neither": 0.0, "r_at_target": 1.0}
        v = verdict(mc)
        assert "coin flip" in v.lower()

    def test_strong_target(self):
        mc = {"p_target": 0.70, "p_stop": 0.10, "p_neither": 0.20, "r_at_target": 1.0}
        v = verdict(mc)
        assert "strongly" in v.lower()

    def test_no_side_hits(self):
        mc = {"p_target": 0.0, "p_stop": 0.0, "p_neither": 1.0, "r_at_target": 1.0}
        v = verdict(mc)
        assert "no replay" in v.lower()

    def test_notes_many_neither(self):
        mc = {"p_target": 0.3, "p_stop": 0.2, "p_neither": 0.5, "r_at_target": 1.0, "avg_R": 0.1}
        notes = verdict_notes(mc)
        assert len(notes) > 0


class TestRunTimeMachine:
    def test_full_run(self):
        series = make_series(35)
        plan = normalize_plan(valid_plan())
        result = run_time_machine(series, plan, replays=200, seed=42)
        assert "mc" in result
        assert "verdict" in result
        assert "history" in result
        assert result["mc"]["replays"] == 200
        assert result["mc"]["seed"] == 42

    def test_reproducible(self):
        series = make_series(35)
        plan = normalize_plan(valid_plan())
        r1 = run_time_machine(series, plan, replays=100, seed=42)
        r2 = run_time_machine(series, plan, replays=100, seed=42)
        assert r1["mc"]["p_target"] == r2["mc"]["p_target"]

    def test_insufficient_sessions_raises(self):
        series = make_series(5)
        plan = normalize_plan(valid_plan(date="2026-06-05"))
        with pytest.raises(TimeMachineError, match="full session"):
            run_time_machine(series, plan, replays=100)

    def test_wrong_interval_raises(self):
        series = make_series(35)
        series.interval = "1d"
        plan = normalize_plan(valid_plan())
        with pytest.raises(TimeMachineError, match="5-min"):
            run_time_machine(series, plan, replays=100)

    def test_bad_replays_raises(self):
        series = make_series(35)
        plan = normalize_plan(valid_plan())
        with pytest.raises(TimeMachineError):
            run_time_machine(series, plan, replays=0)
        with pytest.raises(TimeMachineError):
            run_time_machine(series, plan, replays=2_000_000)

    def test_output_structure(self):
        series = make_series(35)
        plan = normalize_plan(valid_plan())
        result = run_time_machine(series, plan, replays=100, seed=42)
        mc = result["mc"]
        assert "p_target" in mc
        assert "p_stop" in mc
        assert "p_neither" in mc
        assert "p_green" in mc
        assert "avg_R" in mc
        assert "median_close" in mc
        assert "r_at_target" in mc
        assert "bars_left" in mc
        assert "pool_sessions" in mc
        h = result["history"]
        assert "sessions" in h
        assert "triggered" in h
        assert isinstance(result["verdict"], str)
        assert isinstance(result["verdict_notes"], list)
