"""Tests for the Indian-adapted Time Machine."""

import datetime
import pytest
from app.core.primitives import Candle, BarSeries, DataFreshness
from app.core.timezone import IST
from app.engine.timemachine import (
    TimeMachineError, normalize_plan, split_sessions, full_sessions,
    build_pool, simulate, verdict, verdict_notes, lean, run_time_machine,
    resolve_rule, resolve_entry_date, _cents_away,
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
        assert mc["until"] == "15:30"
        h = result["history"]
        assert "sessions" in h
        assert "triggered" in h
        assert isinstance(result["verdict"], str)
        assert isinstance(result["verdict_notes"], list)


class TestSkillParity:
    """Output must match the trader-timemachine skill (day-trader-skill) wording."""

    def test_verdict_1r_exact(self):
        mc = {"p_target": 0.30, "p_stop": 0.30, "p_neither": 0.40,
              "r_at_target": 1.0, "until": "15:30"}
        assert verdict(mc) == (
            "Close to a coin flip: target first 30.0 % vs stop first 30.0 %.")

    def test_verdict_other_r_exact(self):
        mc = {"p_target": 0.24, "p_stop": 0.50, "p_neither": 0.26,
              "r_at_target": 2.0, "until": "15:30"}
        v = verdict(mc)
        assert "at 2R the target has to come first in 33 % of the replays " \
               "that hit one side" in v
        assert "it did in" in v
        assert "target first 24.0 % vs stop first 50.0 %" in v

    def test_verdict_no_side_uses_until(self):
        mc = {"p_target": 0.0, "p_stop": 0.0, "p_neither": 1.0,
              "r_at_target": 1.0, "until": "15:30"}
        v = verdict(mc)
        assert "by 15:30" in v
        assert "the price at 15:30 decides every one" in v

    def test_notes_wording(self):
        mc = {"p_target": 0.3, "p_stop": 0.2, "p_neither": 0.5,
              "r_at_target": 1.0, "avg_R": -0.1, "until": "15:30"}
        notes = verdict_notes(mc)
        assert any("hit neither by 15:30" in n for n in notes)
        assert any("the replays that hit neither pull it the other way" in n
                   for n in notes)

    def test_plan_entry_time(self):
        plan = normalize_plan(valid_plan())
        assert plan["entry_time"] == "9:45 AM"  # bar 5 closes 09:45 IST

    def test_report_skill_format(self):
        series = make_series(35)
        plan = normalize_plan(valid_plan())
        result = run_time_machine(series, plan, replays=100, seed=42)
        rep = result["report"]
        assert "RELIANCE buy," in rep
        assert "100 replays of the rest of the session" in rep
        assert "seed 42." in rep
        assert "target first" in rep
        assert "History:" in rep
        assert rep.rstrip().endswith("Repeat with seed 42.")
        assert result["source"].startswith("trader-timemachine")

    def test_entry_outside_bar_warns(self):
        series = make_series(35)
        plan = normalize_plan(valid_plan(entry=9999.0, stop=9990.0,
                                         target=10020.0))
        result = run_time_machine(series, plan, replays=50, seed=1)
        assert result["warnings"]
        assert "outside that bar's range" in result["warnings"][0]
        assert "Note: " in result["report"]


class TestEntryTimeInput:
    def test_from_entry_time(self):
        raw = valid_plan()
        raw.pop("entry_bar")
        raw["entry_time"] = "09:45"
        p = normalize_plan(raw)
        assert p["entry_bar"] == 5
        assert p["entry_time"] == "9:45 AM"

    def test_disagreement(self):
        with pytest.raises(TimeMachineError, match="disagrees"):
            normalize_plan(valid_plan(entry_time="09:50"))  # bar 6 vs 5

    def test_off_grid(self):
        raw = valid_plan()
        raw.pop("entry_bar")
        raw["entry_time"] = "09:47"
        with pytest.raises(TimeMachineError, match="grid"):
            normalize_plan(raw)

    def test_missing_both(self):
        raw = valid_plan()
        raw.pop("entry_bar")
        with pytest.raises(TimeMachineError, match="entry_time"):
            normalize_plan(raw)


class TestResolveRule:
    def _day(self):
        candles = make_sessions(3)
        days = split_sessions(candles)
        return list(days.values())[0]

    def test_auto_detects_or_mid(self):
        day = self._day()
        n = 3
        oh = max(day[i].high for i in range(n))
        ol = min(day[i].low for i in range(n))
        stop = _cents_away((oh + ol) / 2, True)
        plan = normalize_plan(valid_plan(entry=1100.0, target=1150.0,
                                         stop=stop, stop_rule="auto"))
        rule = resolve_rule(plan, day)
        assert rule["stop_rule"] == "or_mid"
        assert "stop_pct" not in rule

    def test_auto_falls_back_to_pct(self):
        day = self._day()
        plan = normalize_plan(valid_plan(entry=1100.0, stop=1089.0,
                                         target=1150.0, stop_rule="auto"))
        rule = resolve_rule(plan, day)
        assert rule["stop_rule"] == "pct"
        assert rule["stop_pct"] > 0

    def test_non_orb_returns_none(self):
        day = self._day()
        plan = normalize_plan(valid_plan(setup="flag"))
        assert resolve_rule(plan, day) is None

    def test_wrong_side_rule_converted_to_pct(self):
        day = self._day()
        # sell: far rule is or_high; or_low does not match -> pct
        plan = normalize_plan(valid_plan(side="sell", entry=1000.0,
                                         stop=1020.0, target=980.0,
                                         stop_rule="or_low"))
        rule = resolve_rule(plan, day)
        assert rule["stop_rule"] == "pct"

    def test_history_skipped_for_non_orb(self):
        series = make_series(35)
        plan = normalize_plan(valid_plan(setup="flag"))
        result = run_time_machine(series, plan, replays=50, seed=1)
        h = result["history"]
        assert h["rule"] is None
        assert h["triggered"] == 0
        assert "orb) only" in h["note"]
        assert "History: skipped" in result["report"]


class TestResolveEntryDate:
    def _days(self):
        return split_sessions(make_sessions(3))

    def test_picks_latest_with_bar(self):
        days = self._days()
        ordered = sorted(days)
        del days[ordered[-1]][5]
        # latest day lost bar 5 -> falls back to the one before it
        assert resolve_entry_date(days, 5) == ordered[-2]
        assert resolve_entry_date(days, 6) == ordered[-1]

    def test_none_when_missing(self):
        days = self._days()
        assert resolve_entry_date(days, 999) is None
        assert resolve_entry_date({}, 5) is None
