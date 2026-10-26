"""Tests for risk management."""

import datetime
import pytest
from app.engine.risk import RiskLimits, RiskCheck, check_trade
from app.core.timezone import IST


def make_plan(**overrides):
    base = {
        "symbol": "RELIANCE", "side": "buy",
        "entry": 100.0, "stop": 95.0, "target": 110.0,
        "shares": 100,
    }
    base.update(overrides)
    return base


def default_limits():
    return RiskLimits(capital=500000, risk_per_trade_pct=1.0,
                      max_daily_loss_pct=3.0, max_positions=5,
                      min_risk_reward=1.5)


class TestRiskPass:
    def test_valid_trade_passes(self):
        rc = check_trade(make_plan(), default_limits())
        assert rc.passed
        assert rc.verdict == "PASS" if hasattr(rc, "verdict") else True
        assert len(rc.reasons) == 0

    def test_fingerprint_deterministic(self):
        rc1 = check_trade(make_plan(), default_limits())
        rc2 = check_trade(make_plan(), default_limits())
        # fingerprints include date, so same day = same fingerprint
        assert rc1.fingerprint == rc2.fingerprint


class TestRiskBlock:
    def test_stop_above_entry_blocks(self):
        rc = check_trade(make_plan(stop=105), default_limits())
        assert not rc.passed

    def test_low_rr_blocks(self):
        # entry=100, stop=99, target=101 -> R:R = 1.0 < 1.5
        rc = check_trade(make_plan(stop=99, target=101), default_limits())
        assert not rc.passed

    def test_daily_loss_blocks(self):
        rc = check_trade(make_plan(), default_limits(), daily_pnl=-20000)
        # max daily loss = 500000 * 3% = 15000; -20000 < -15000 -> block
        assert not rc.passed

    def test_too_many_trades_blocks(self):
        rc = check_trade(make_plan(), default_limits(), trades_today=10)
        assert not rc.passed

    def test_too_many_positions_blocks(self):
        portfolio = {"positions": [{"id": i} for i in range(5)]}
        rc = check_trade(make_plan(), default_limits(), portfolio=portfolio)
        assert not rc.passed

    def test_missing_entry_blocks(self):
        rc = check_trade(make_plan(entry=None), default_limits())
        assert not rc.passed

    def test_missing_stop_blocks(self):
        rc = check_trade(make_plan(stop=None), default_limits())
        assert not rc.passed

    def test_entry_window_blocks(self):
        late = datetime.datetime(2026, 10, 23, 15, 10, tzinfo=IST)
        rc = check_trade(make_plan(), default_limits(), now_ist=late)
        assert not rc.passed

    def test_reasons_populated(self):
        rc = check_trade(make_plan(stop=105), default_limits())
        assert len(rc.reasons) > 0


class TestRiskCheckClass:
    def test_add_pass(self):
        rc = RiskCheck(passed=True)
        rc.add("test", True, "ok")
        assert rc.passed
        assert len(rc.checks) == 1

    def test_add_fail(self):
        rc = RiskCheck(passed=True)
        rc.add("test", False, "bad")
        assert not rc.passed
        assert len(rc.reasons) == 1
