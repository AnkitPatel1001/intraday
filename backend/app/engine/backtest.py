"""Backtesting engine. Chronological, no look-ahead, realistic costs."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Callable, Optional

from app.core.primitives import BarSeries, Candle
from app.engine.planner import estimate_costs


@dataclass
class Trade:
    entry_time: datetime.datetime
    exit_time: datetime.datetime
    entry_price: float
    exit_price: float
    qty: int
    side: str
    pnl: float
    fees: float
    r_multiple: float
    reason: str  # 'target', 'stop', 'eod'


@dataclass
class BacktestResult:
    trades: list[Trade]
    total_return: float
    max_drawdown: float
    sharpe: float
    win_rate: float
    profit_factor: float
    trade_count: int
    avg_win: float
    avg_loss: float
    benchmark_return: float
    assumptions: list[str]
    warnings: list[str]
    equity_curve: list[float] = field(default_factory=list)


def run_backtest(
    series: BarSeries,
    strategy: Callable[[list[Candle], int], Optional[dict]],
    capital: float = 500000,
    risk_pct: float = 1.0,
    benchmark: Optional[BarSeries] = None,
) -> BacktestResult:
    """Run a strategy over historical bars.

    strategy(candles, i) -> dict with 'side', 'stop', 'target', 'qty' or None.
    Chronological: at bar i, only bars[0..i] are visible to the strategy.
    """
    candles = series.candles
    trades: list[Trade] = []
    equity = [capital]
    peak = capital
    max_dd = 0.0

    assumptions = [
        "Intraday only: all positions closed by session end",
        "Brokerage, STT, exchange charges, GST, stamp duty, and slippage included",
        "Whole shares only (Indian market constraint)",
        "No look-ahead: strategy sees only completed bars at decision time",
        "Synthetic/demo data unless provider is live",
    ]
    warnings = []

    cash = capital
    position = None  # dict: side, entry, stop, target, qty, entry_idx

    for i in range(1, len(candles)):
        bar = candles[i]
        prev = candles[i - 1]

        # Check exit on open position first (stop/target checked on this bar)
        if position is not None:
            exit_price = None
            reason = ""
            exit_ts = bar.ts
            # Intraday rule: never hold across sessions. Close at previous
            # session's last close as soon as a new trading day starts.
            if bar.ts.date() != position["entry_time"].date():
                exit_price = prev.close
                reason = "eod"
                exit_ts = prev.ts
            elif position["side"] == "buy":
                if bar.low <= position["stop"]:
                    exit_price = position["stop"]
                    reason = "stop"
                elif bar.high >= position["target"]:
                    exit_price = position["target"]
                    reason = "target"
            else:
                if bar.high >= position["stop"]:
                    exit_price = position["stop"]
                    reason = "stop"
                elif bar.low <= position["target"]:
                    exit_price = position["target"]
                    reason = "target"

            # EOD exit at last bar
            if exit_price is None and i == len(candles) - 1:
                exit_price = bar.close
                reason = "eod"

            if exit_price is not None:
                costs = estimate_costs(position["entry"], position["qty"], position["side"])
                if position["side"] == "buy":
                    gross = (exit_price - position["entry"]) * position["qty"]
                else:
                    gross = (position["entry"] - exit_price) * position["qty"]
                pnl = gross - costs["total_est"]
                cash += pnl
                risk = abs(position["entry"] - position["stop"])
                r_mult = pnl / (risk * position["qty"]) if risk > 0 else 0
                trades.append(Trade(
                    entry_time=position["entry_time"],
                    exit_time=exit_ts,
                    entry_price=position["entry"],
                    exit_price=exit_price,
                    qty=position["qty"],
                    side=position["side"],
                    pnl=round(pnl, 2),
                    fees=costs["total_est"],
                    r_multiple=round(r_mult, 2),
                    reason=reason,
                ))
                position = None

        # Enter new position if flat
        if position is None and i < len(candles) - 1:
            sig = strategy(candles[: i + 1], i)
            if sig:
                side = sig.get("side", "buy")
                stop = sig["stop"]
                target = sig["target"]
                entry = bar.close
                risk = abs(entry - stop)
                if risk > 0:
                    risk_amount = cash * risk_pct / 100
                    qty = max(0, int(risk_amount / risk))
                    cost = qty * entry
                    if qty > 0 and cost <= cash:
                        position = {
                            "side": side, "entry": entry, "stop": stop,
                            "target": target, "qty": qty,
                            "entry_time": bar.ts,
                        }

        # Track equity
        unrealized = 0.0
        if position is not None:
            if position["side"] == "buy":
                unrealized = (bar.close - position["entry"]) * position["qty"]
            else:
                unrealized = (position["entry"] - bar.close) * position["qty"]
        eq = cash + unrealized
        equity.append(eq)
        peak = max(peak, eq)
        dd = (peak - eq) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)

    # Metrics
    total_return = (equity[-1] - capital) / capital * 100 if capital else 0
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0
    gross_win = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    if gross_loss > 0:
        profit_factor = round(gross_win / gross_loss, 2)
    elif gross_win > 0:
        profit_factor = 999.99
        warnings.append("profit_factor capped at 999.99 (no losing trades)")
    else:
        profit_factor = 0.0

    # Sharpe: annualized from daily closes of the equity curve (252 trading days)
    daily_equity: dict[datetime.date, float] = {}
    for k in range(1, len(equity)):
        daily_equity[candles[k - 1].ts.date()] = equity[k]
    daily_rets = []
    prev_eq = capital
    for d in sorted(daily_equity):
        eq = daily_equity[d]
        if prev_eq > 0:
            daily_rets.append((eq - prev_eq) / prev_eq)
        prev_eq = eq
    if len(daily_rets) > 1:
        mean_r = sum(daily_rets) / len(daily_rets)
        var = sum((r - mean_r) ** 2 for r in daily_rets) / len(daily_rets)
        std = var ** 0.5
        sharpe = (mean_r / std * (252 ** 0.5)) if std > 0 else 0
    else:
        sharpe = 0

    # Benchmark
    benchmark_return = 0.0
    if benchmark and len(benchmark.candles) >= 2:
        b0 = benchmark.candles[0].close
        b1 = benchmark.candles[-1].close
        benchmark_return = (b1 - b0) / b0 * 100 if b0 else 0

    if len(trades) < 10:
        warnings.append(f"small sample: only {len(trades)} trades — results not statistically reliable")

    return BacktestResult(
        trades=trades,
        total_return=round(total_return, 2),
        max_drawdown=round(max_dd * 100, 2),
        sharpe=round(sharpe, 2),
        win_rate=round(win_rate, 1),
        profit_factor=round(profit_factor, 2),
        trade_count=len(trades),
        avg_win=round(avg_win, 2),
        avg_loss=round(avg_loss, 2),
        benchmark_return=round(benchmark_return, 2),
        assumptions=assumptions,
        warnings=warnings,
        equity_curve=[round(e, 2) for e in equity[:: max(1, len(equity) // 500)]],
    )


# Pre-built strategies

def orb_strategy(or_minutes: int = 15, stop_rule: str = "or_mid", target_r: float = 2.0):
    """Opening-range breakout strategy factory."""
    from app.core.calendar import BAR_MIN
    n = or_minutes // BAR_MIN

    def strategy(candles: list[Candle], i: int) -> Optional[dict]:
        if i < n:
            return None
        day = candles[i].ts.date()
        day_bars = [c for c in candles if c.ts.date() == day]
        if len(day_bars) < n + 1:
            return None
        or_bars = day_bars[:n]
        or_high = max(c.high for c in or_bars)
        or_low = min(c.low for c in or_bars)
        # Only trigger on the first bar that closes above the range
        for j in range(n, len(day_bars)):
            if day_bars[j].close > or_high and day_bars[j].ts == candles[i].ts:
                entry = candles[i].close
                stop = round((or_high + or_low) / 2, 2) if stop_rule == "or_mid" else or_low
                if stop >= entry:
                    return None
                risk = entry - stop
                target = round(entry + target_r * risk, 2)
                return {"side": "buy", "stop": stop, "target": target}
        return None

    return strategy
