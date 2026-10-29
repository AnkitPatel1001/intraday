"""Trade planner: setup, entry, stop, target, R:R, costs. Research only — not advice."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Optional

from app.core.calendar import SESSION_BARS, BAR_MIN, OPEN_MIN, bar_slot, slot_time
from app.core.primitives import BarSeries
from app.engine.indicators import atr as atr_fn, rsi as rsi_fn, ema as ema_fn, vwap as vwap_fn


# Indian trading costs (approximate, FY 2025-26)
# STT = Securities Transaction Tax, exc = exchange charges, st = stamp duty
BROKERAGE_INTRADAY_PCT = 0.03   # % of turnover (typical discount broker)
STT_INTRADAY_PCT = 0.025        # % of sell turnover
EXCHANGE_CHARGE_PCT = 0.00345   # NSE
GST_PCT = 18.0                  # on (brokerage + exchange + SEBI)
SEBI_FEES_PCT = 0.0001
STAMP_BUY_PCT = 0.015           # % of buy turnover
SLIPPAGE_PCT = 0.05             # estimated per side


@dataclass
class TradePlan:
    symbol: str
    side: str
    entry: float
    stop: float
    target: float
    entry_bar: int
    entry_time: str
    risk_per_share: float
    reward_per_share: float
    risk_reward: float
    setup: str
    stop_rule: str
    target_r: float
    invalidation: str
    max_holding_bars: int
    costs: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    label: str = "RESEARCH PLAN — not a buy/sell instruction"
    date: str = ""


def estimate_costs(entry: float, qty: int, side: str = "buy") -> dict:
    """Estimated round-trip costs in INR for an intraday trade."""
    turnover = entry * qty
    buy_turnover = turnover if side == "buy" else turnover
    sell_turnover = turnover
    brokerage = turnover * BROKERAGE_INTRADAY_PCT / 100
    stt = sell_turnover * STT_INTRADAY_PCT / 100
    exc = (buy_turnover + sell_turnover) * EXCHANGE_CHARGE_PCT / 100
    sebi = (buy_turnover + sell_turnover) * SEBI_FEES_PCT / 100
    stamp = buy_turnover * STAMP_BUY_PCT / 100
    gst = (brokerage + exc + sebi) * GST_PCT / 100
    slippage = entry * qty * SLIPPAGE_PCT / 100
    total = brokerage + stt + exc + sebi + stamp + gst + slippage
    return {
        "brokerage": round(brokerage, 2),
        "stt": round(stt, 2),
        "exchange_charges": round(exc, 2),
        "sebi_fees": round(sebi, 2),
        "stamp_duty": round(stamp, 2),
        "gst": round(gst, 2),
        "slippage_est": round(slippage, 2),
        "total_est": round(total, 2),
        "as_pct_of_turnover": round(100 * total / turnover, 4) if turnover else 0,
    }


def position_size(
    capital: float, risk_per_trade_pct: float, entry: float, stop: float,
    max_position_pct: Optional[float] = None,
) -> dict:
    """Whole-share position sizing from capital and risk limit.

    `max_position_pct`, if given, also caps the position so its cost never
    exceeds that percent of capital — without it, a tight stop (relative to
    risk_per_trade_pct) inflates the risk-budget share count past the plain
    capital limit, silently sizing a position close to 100% of capital.
    """
    risk_amount = capital * risk_per_trade_pct / 100
    risk_per_share = abs(entry - stop)
    if risk_per_share <= 0:
        return {"error": "risk per share must be positive", "shares": 0}
    shares = int(risk_amount / risk_per_share)
    cost = shares * entry
    if cost > capital:
        shares = int(capital / entry)
        cost = shares * entry
    if max_position_pct is not None:
        max_cost = capital * max_position_pct / 100
        if cost > max_cost:
            shares = int(max_cost / entry) if entry > 0 else 0
            cost = shares * entry
    actual_risk = shares * risk_per_share
    return {
        "shares": shares,
        "risk_amount": round(risk_amount, 2),
        "actual_risk": round(actual_risk, 2),
        "cost": round(cost, 2),
        "pct_of_capital": round(100 * cost / capital, 2) if capital else 0,
    }


def _slots_by_date(candles: list) -> dict[datetime.date, dict[int, object]]:
    """{date: {bar_slot: candle}}, keyed by time-of-day via bar_slot() — not
    by list position. A day with early gaps then can't be mis-indexed: a
    missing slot is simply absent from the dict instead of shifting every
    later bar one position to the left."""
    out: dict[datetime.date, dict[int, object]] = {}
    for c in candles:
        slot = bar_slot(c.ts.time())
        if slot is None:
            continue
        out.setdefault(c.ts.date(), {})[slot] = c
    return out


def _pick_date_with_bars(
    by_date: dict[datetime.date, dict[int, object]], entry_bar: int,
) -> datetime.date:
    """Most recent date with bars 0..entry_bar ALL present (by slot)."""
    needed = range(entry_bar + 1)
    for d in sorted(by_date, reverse=True):
        if all(i in by_date[d] for i in needed):
            return d
    raise ValueError(f"no session has bars 0..{entry_bar} complete")


def latest_entry_date(candles: list, entry_bar: int) -> datetime.date:
    """Most recent date in `candles` whose session has bars 0..entry_bar all
    present (matched by time-of-day, not position in the flat list — the
    old approach indexed straight into the whole fetch window, which always
    landed on the OLDEST day instead of the most recent usable session, and
    additionally mis-indexed any day with early gaps).
    """
    return _pick_date_with_bars(_slots_by_date(candles), entry_bar)


def build_plan(
    symbol: str,
    series: BarSeries,
    entry_bar: int,
    side: str = "buy",
    stop_rule: str = "or_mid",
    target_r: float = 2.0,
    or_minutes: int = 15,
    capital: float = 500000,
    risk_pct: float = 1.0,
) -> TradePlan:
    """Build a full trade plan from OHLCV data. Raises if data insufficient."""
    long = side == "buy"
    n = or_minutes // BAR_MIN
    if entry_bar < n or entry_bar >= SESSION_BARS:
        raise ValueError(f"entry_bar must be {n}..{SESSION_BARS-1}")

    # Get the most recent day that has bars 0..entry_bar all present (not
    # the oldest one in the fetch window, and not mis-indexed by a gap).
    by_date = _slots_by_date(series.candles)
    entry_date = _pick_date_with_bars(by_date, entry_bar)
    slots = by_date[entry_date]

    # Opening range
    or_bars = [slots[i] for i in range(n)]
    or_high = max(c.high for c in or_bars)
    or_low = min(c.low for c in or_bars)

    entry_candle = slots[entry_bar]
    entry = entry_candle.close

    if stop_rule == "or_mid":
        stop = round((or_high + or_low) / 2, 2)
    elif stop_rule == "or_low" and long:
        stop = or_low
    elif stop_rule == "or_high" and not long:
        stop = or_high
    else:
        stop = round(entry * 0.995, 2) if long else round(entry * 1.005, 2)

    if long and stop >= entry:
        stop = round(entry * 0.99, 2)
    if not long and stop <= entry:
        stop = round(entry * 1.01, 2)

    risk = abs(entry - stop)
    if risk <= 0:
        raise ValueError("zero risk")
    target = round(entry + target_r * risk, 2) if long else round(entry - target_r * risk, 2)
    reward = abs(target - entry)

    sizing = position_size(capital, risk_pct, entry, stop)
    costs = estimate_costs(entry, sizing.get("shares", 0), side)

    warnings = []
    if sizing.get("shares", 0) == 0:
        warnings.append("position size is zero — capital too small or risk too tight")
    if entry_bar > SESSION_BARS - 10:
        warnings.append("late-session entry — limited bars remaining")

    # Invalidation: close beyond stop on a closing basis
    invalidation = f"A 5-min close beyond ₹{stop} invalidates the setup"
    max_hold = SESSION_BARS - entry_bar - 1

    return TradePlan(
        symbol=symbol, side=side, entry=entry, stop=stop, target=target,
        entry_bar=entry_bar,
        entry_time=slot_time(entry_bar).strftime("%H:%M"),
        risk_per_share=round(risk, 2),
        reward_per_share=round(reward, 2),
        risk_reward=round(target_r, 2),
        setup="orb",
        stop_rule=stop_rule,
        target_r=round(target_r, 2),
        invalidation=invalidation,
        max_holding_bars=max_hold,
        costs=costs,
        warnings=warnings,
        date=entry_date.isoformat(),
    )
