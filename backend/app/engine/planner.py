"""Trade planner: setup, entry, stop, target, R:R, costs. Research only — not advice."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Optional

from app.core.calendar import SESSION_BARS, BAR_MIN, OPEN_MIN, slot_time
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
) -> dict:
    """Whole-share position sizing from capital and risk limit."""
    risk_amount = capital * risk_per_trade_pct / 100
    risk_per_share = abs(entry - stop)
    if risk_per_share <= 0:
        return {"error": "risk per share must be positive", "shares": 0}
    shares = int(risk_amount / risk_per_share)
    cost = shares * entry
    if cost > capital:
        shares = int(capital / entry)
        cost = shares * entry
    actual_risk = shares * risk_per_share
    return {
        "shares": shares,
        "risk_amount": round(risk_amount, 2),
        "actual_risk": round(actual_risk, 2),
        "cost": round(cost, 2),
        "pct_of_capital": round(100 * cost / capital, 2) if capital else 0,
    }


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

    candles = series.candles
    # Get the entry day's candles
    entry_date = candles[entry_bar].ts.date()
    day_candles = [c for c in candles if c.ts.date() == entry_date]
    if len(day_candles) < entry_bar + 1:
        raise ValueError("insufficient bars for the entry day")

    # Opening range
    or_bars = day_candles[:n]
    or_high = max(c.high for c in or_bars)
    or_low = min(c.low for c in or_bars)

    entry_candle = day_candles[entry_bar]
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
    )
