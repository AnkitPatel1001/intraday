"""Risk management. PASS/BLOCK every trade against user limits. Rejects on missing data."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RiskLimits:
    capital: float = 500000
    risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 3.0
    max_positions: int = 5
    min_risk_reward: float = 1.5
    max_position_pct: float = 25.0
    require_stop: bool = True
    max_trades_per_day: int = 10
    no_entries_after: str = "15:00"  # IST


@dataclass
class RiskCheck:
    passed: bool
    checks: list[dict] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    fingerprint: str = ""

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append({"name": name, "passed": ok, "detail": detail})
        if not ok:
            self.reasons.append(f"{name}: {detail}")
            self.passed = False


def check_trade(
    plan: dict,
    limits: RiskLimits,
    portfolio: Optional[dict] = None,
    daily_pnl: float = 0.0,
    trades_today: int = 0,
    now_ist: Optional[datetime.datetime] = None,
) -> RiskCheck:
    """Check a trade plan against risk limits. Returns RiskCheck with PASS/BLOCK."""
    import hashlib
    rc = RiskCheck(passed=True)
    portfolio = portfolio or {}

    entry = plan.get("entry")
    stop = plan.get("stop")
    target = plan.get("target")
    side = plan.get("side", "buy")
    symbol = plan.get("symbol", "")

    # Essential data present
    rc.add("has_entry", entry is not None and entry > 0, f"entry={entry}")
    rc.add("has_stop", stop is not None and stop > 0, f"stop={stop}")
    rc.add("has_target", target is not None and target > 0, f"target={target}")

    if not rc.passed:
        rc.fingerprint = hashlib.sha256(f"{symbol}:{entry}:{stop}".encode()).hexdigest()[:16]
        return rc

    long = side == "buy"

    # Stop / target sanity
    if long:
        rc.add("stop_below_entry", stop < entry, f"stop {stop} vs entry {entry}")
        rc.add("target_above_entry", target > entry, f"target {target} vs entry {entry}")
    else:
        rc.add("stop_above_entry", stop > entry, f"stop {stop} vs entry {entry}")
        rc.add("target_below_entry", target < entry, f"target {target} vs entry {entry}")

    # Risk / reward
    risk = abs(entry - stop)
    reward = abs(target - entry)
    rr = reward / risk if risk > 0 else 0
    rc.add("min_rr", rr >= limits.min_risk_reward,
           f"R:R {rr:.2f} < minimum {limits.min_risk_reward}")

    # Daily loss limit
    max_daily_loss = limits.capital * limits.max_daily_loss_pct / 100
    rc.add("daily_loss", daily_pnl > -max_daily_loss,
           f"daily P&L ₹{daily_pnl:.0f} vs limit ₹{-max_daily_loss:.0f}")

    # Trades per day
    rc.add("trades_per_day", trades_today < limits.max_trades_per_day,
           f"{trades_today} trades today vs limit {limits.max_trades_per_day}")

    # Max open positions
    open_positions = len(portfolio.get("positions", []))
    rc.add("max_positions", open_positions < limits.max_positions,
           f"{open_positions} open vs limit {limits.max_positions}")

    # Entry window
    if now_ist is not None:
        t = now_ist.time()
        from app.core.timezone import parse_clock
        try:
            cutoff = parse_clock(limits.no_entries_after)
            now_min = t.hour * 60 + t.minute
            rc.add("entry_window", now_min <= cutoff,
                   f"now {now_min//60:02d}:{now_min%60:02d} after cutoff {limits.no_entries_after}")
        except ValueError:
            pass

    # Position value vs capital
    shares = plan.get("shares", 0)
    pos_value = shares * entry if shares else 0
    max_pos_value = limits.capital * limits.max_position_pct / 100
    if shares:
        rc.add("position_size", pos_value <= max_pos_value,
               f"₹{pos_value:.0f} vs max ₹{max_pos_value:.0f}")

    # Liquidity warning (not a block, just a note)
    if shares and shares > 0:
        avg_volume = plan.get("avg_volume", 0)
        if avg_volume and shares > avg_volume * 0.01:
            rc.checks.append({
                "name": "liquidity_warning", "passed": True,
                "detail": f"position {shares} > 1% of avg volume {avg_volume}",
            })

    rc.fingerprint = hashlib.sha256(
        f"{symbol}:{entry}:{stop}:{target}:{datetime.date.today().isoformat()}".encode()
    ).hexdigest()[:16]
    return rc
