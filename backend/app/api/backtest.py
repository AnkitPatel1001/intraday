"""Backtesting endpoints."""

from __future__ import annotations

import asyncio
import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.symbols import validate_symbol
from app.core.timezone import now_ist
from app.data.factory import get_provider
from app.engine.backtest import run_backtest, orb_strategy

router = APIRouter()


class BacktestRequest(BaseModel):
    symbol: str
    strategy: str = "orb"
    interval: str = "5m"
    days: int = Field(90, ge=1, le=365)
    capital: float = Field(500000, gt=0, le=1e12)
    risk_pct: float = Field(1.0, gt=0, le=100)
    or_minutes: int = Field(15, ge=5, le=60)
    target_r: float = Field(2.0, gt=0, le=50)


@router.post("/run")
async def run(req: BacktestRequest):
    try:
        sym = validate_symbol(req.symbol)
    except ValueError as e:
        raise HTTPException(400, str(e))

    provider = get_provider()
    end = now_ist().date()
    start = end - datetime.timedelta(days=req.days)
    try:
        series = await provider.get_bars(sym, req.interval, start, end)
    except Exception as e:
        raise HTTPException(502, "data provider error")

    if len(series.candles) < 30:
        raise HTTPException(400, f"insufficient data: {len(series.candles)} bars")

    if req.strategy == "orb":
        strat = orb_strategy(req.or_minutes, "or_mid", req.target_r)
    else:
        raise HTTPException(400, f"unknown strategy: {req.strategy}")

    result = await asyncio.to_thread(
        run_backtest, series, strat, req.capital, req.risk_pct
    )
    return {
        "symbol": sym,
        "strategy": req.strategy,
        "bars": len(series.candles),
        "total_return_pct": result.total_return,
        "max_drawdown_pct": result.max_drawdown,
        "sharpe": result.sharpe,
        "win_rate_pct": result.win_rate,
        "profit_factor": result.profit_factor,
        "trade_count": result.trade_count,
        "avg_win": result.avg_win,
        "avg_loss": result.avg_loss,
        "benchmark_return_pct": result.benchmark_return,
        "assumptions": result.assumptions,
        "warnings": result.warnings,
        "equity_curve": result.equity_curve,
        "trades": [
            {
                "entry_time": t.entry_time.isoformat(),
                "exit_time": t.exit_time.isoformat(),
                "entry": t.entry_price, "exit": t.exit_price,
                "qty": t.qty, "side": t.side,
                "pnl": t.pnl, "fees": t.fees,
                "r": t.r_multiple, "reason": t.reason,
            }
            for t in result.trades[:100]
        ],
        "data_label": series.label(),
        "note": "Backtest results are simulations, not guarantees. Past performance does not indicate future results.",
    }
