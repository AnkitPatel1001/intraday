"""Trade planning endpoints."""

from __future__ import annotations

import asyncio
import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.calendar import SESSION_BARS
from app.core.symbols import validate_symbol
from app.core.timezone import now_ist
from app.data.factory import get_provider
from app.api.provider_errors import provider_502
from app.engine.planner import build_plan, estimate_costs, position_size
from app.engine.timemachine import (
    run_time_machine, normalize_plan, resolve_entry_date, split_sessions,
    TimeMachineError,
)

router = APIRouter()

# Cap concurrent Monte Carlo simulations so threadpool stays available
_SIM_SEMAPHORE = asyncio.Semaphore(2)


class PlanRequest(BaseModel):
    symbol: str
    side: Literal["buy", "sell"] = "buy"
    entry_bar: int = 5
    stop_rule: Literal["or_mid", "or_low", "or_high", "pct"] = "or_mid"
    target_r: float = Field(2.0, gt=0, le=50)
    or_minutes: int = Field(15, ge=5, le=60)
    capital: float = Field(500000, gt=0, le=1e12)
    risk_pct: float = Field(1.0, gt=0, le=100)
    interval: Literal["1m", "5m", "15m", "1d"] = "5m"


class TimeMachineRequest(BaseModel):
    symbol: str
    side: str = "buy"
    date: str | None = None
    entry: float = Field(..., gt=0, le=1e9)
    stop: float = Field(..., gt=0, le=1e9)
    target: float = Field(..., gt=0, le=1e9)
    entry_bar: int = 5
    entry_time: str | None = None  # e.g. "09:45" (bar close, IST); overrides entry_bar
    setup: str = "orb"
    or_minutes: int = Field(15, ge=5, le=60)
    stop_rule: str = "auto"
    replays: int = Field(10000, ge=1, le=100_000)
    seed: int = 19


class CostRequest(BaseModel):
    entry: float = Field(..., gt=0, le=1e9)
    qty: int = Field(..., gt=0, le=1_000_000)
    side: Literal["buy", "sell"] = "buy"


class SizeRequest(BaseModel):
    capital: float = Field(..., gt=0, le=1e12)
    risk_pct: float = Field(..., gt=0, le=100)
    entry: float = Field(..., gt=0, le=1e9)
    stop: float = Field(..., gt=0, le=1e9)


@router.post("/plan")
async def create_plan(req: PlanRequest):
    try:
        sym = validate_symbol(req.symbol)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not 0 <= req.entry_bar < SESSION_BARS:
        raise HTTPException(400, f"entry_bar must be 0..{SESSION_BARS-1}")

    provider = get_provider()
    end = now_ist().date()
    start = end - datetime.timedelta(days=30)
    try:
        series = await provider.get_bars(sym, req.interval, start, end)
    except Exception as e:
        raise provider_502(sym, e) from e

    try:
        plan = build_plan(
            sym, series, req.entry_bar, req.side,
            req.stop_rule, req.target_r, req.or_minutes,
            req.capital, req.risk_pct,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {
        "plan": plan.__dict__,
        "label": "RESEARCH PLAN — simulated trade plan, not a buy/sell instruction",
        "data_label": series.label(),
    }


@router.post("/timemachine")
async def time_machine(req: TimeMachineRequest):
    """Replay a planned trade: N Monte Carlo simulations + historical rule replay."""
    try:
        sym = validate_symbol(req.symbol)
    except ValueError as e:
        raise HTTPException(400, str(e))

    today = now_ist().date()
    plan_dict: dict = {
        "symbol": sym, "side": req.side,
        "entry": req.entry, "stop": req.stop, "target": req.target,
        "setup": req.setup,
        "opening_range": {"minutes": req.or_minutes},
        "stop_rule": req.stop_rule,
    }
    if req.entry_time:
        plan_dict["entry_time"] = req.entry_time
        if "entry_bar" in req.model_fields_set:
            plan_dict["entry_bar"] = req.entry_bar
    else:
        plan_dict["entry_bar"] = req.entry_bar

    # Fast validation (ordering, bar grid) before any network call.
    try:
        plan = normalize_plan({**plan_dict, "date": (req.date or today.isoformat())})
    except TimeMachineError as e:
        raise HTTPException(400, str(e))
    if datetime.date.fromisoformat(plan["date"]) > today:
        raise HTTPException(400, "date cannot be in the future")

    provider = get_provider()
    if req.date is None:
        # Default date = today (skill behaviour), but fall back to the latest
        # session that actually has the entry bar — pre-market/weekend/holiday
        # would otherwise 400 with no way to run.
        try:
            series = await provider.get_bars(
                sym, "5m", today - datetime.timedelta(days=90), today)
        except Exception as e:
            raise provider_502(sym, e) from e
        resolved = resolve_entry_date(split_sessions(series.candles),
                                      plan["entry_bar"])
        if resolved is None:
            raise HTTPException(
                400, f"entry bar {plan['entry_bar']} not found in the last "
                     "90 days — no complete 5-min bar")
        try:
            plan = normalize_plan({**plan_dict, "date": resolved})
        except TimeMachineError as e:
            raise HTTPException(400, str(e))
    else:
        end = datetime.date.fromisoformat(plan["date"])
        try:
            series = await provider.get_bars(
                sym, "5m", end - datetime.timedelta(days=90), end)
        except Exception as e:
            raise provider_502(sym, e) from e

    try:
        # CPU-bound simulation runs off the event loop; concurrency capped.
        async with _SIM_SEMAPHORE:
            result = await asyncio.to_thread(
                run_time_machine, series, plan, replays=req.replays, seed=req.seed
            )
    except TimeMachineError as e:
        raise HTTPException(400, str(e))

    # Slim: remove sample_paths for API response
    mc = result["mc"]
    slim_mc = {k: v for k, v in mc.items() if k not in ("sample_paths", "bands")}
    result["mc"] = slim_mc
    return result


@router.post("/costs")
async def costs(req: CostRequest):
    return estimate_costs(req.entry, req.qty, req.side)


@router.post("/size")
async def size(req: SizeRequest):
    result = position_size(req.capital, req.risk_pct, req.entry, req.stop)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result
