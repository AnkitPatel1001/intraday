"""Trade planning endpoints."""

from __future__ import annotations

import asyncio
import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.calendar import SESSION_BARS
from app.core.symbols import validate_symbol
from app.core.timezone import now_ist
from app.data.factory import get_provider
from app.engine.planner import build_plan, estimate_costs, position_size
from app.engine.timemachine import run_time_machine, normalize_plan, TimeMachineError

router = APIRouter()

# Cap concurrent Monte Carlo simulations so threadpool stays available
_SIM_SEMAPHORE = asyncio.Semaphore(2)


class PlanRequest(BaseModel):
    symbol: str
    side: str = "buy"
    entry_bar: int = 5
    stop_rule: str = "or_mid"
    target_r: float = Field(2.0, gt=0, le=50)
    or_minutes: int = Field(15, ge=5, le=60)
    capital: float = Field(500000, gt=0, le=1e12)
    risk_pct: float = Field(1.0, gt=0, le=100)
    interval: str = "5m"


class TimeMachineRequest(BaseModel):
    symbol: str
    side: str = "buy"
    date: str | None = None
    entry: float = Field(..., gt=0, le=1e9)
    stop: float = Field(..., gt=0, le=1e9)
    target: float = Field(..., gt=0, le=1e9)
    entry_bar: int = 5
    setup: str = "orb"
    or_minutes: int = Field(15, ge=5, le=60)
    stop_rule: str = "auto"
    replays: int = Field(10000, ge=1, le=1_000_000)
    seed: int = 19


class CostRequest(BaseModel):
    entry: float = Field(..., gt=0, le=1e9)
    qty: int = Field(..., gt=0, le=1_000_000)
    side: str = "buy"


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
        raise HTTPException(502, "data provider error")

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
        "label": "RESEARCH PLAN â€” simulated trade plan, not a buy/sell instruction",
        "data_label": series.label(),
    }


@router.post("/timemachine")
async def time_machine(req: TimeMachineRequest):
    """Replay a planned trade: N Monte Carlo simulations + historical rule replay."""
    try:
        sym = validate_symbol(req.symbol)
    except ValueError as e:
        raise HTTPException(400, str(e))

    plan_dict = {
        "symbol": sym, "side": req.side,
        "date": req.date or now_ist().date().isoformat(),
        "entry": req.entry, "stop": req.stop, "target": req.target,
        "entry_bar": req.entry_bar, "setup": req.setup,
        "opening_range": {"minutes": req.or_minutes},
        "stop_rule": req.stop_rule,
    }
    try:
        plan = normalize_plan(plan_dict)
    except TimeMachineError as e:
        raise HTTPException(400, str(e))

    provider = get_provider()
    end = datetime.date.fromisoformat(plan["date"])
    start = end - datetime.timedelta(days=90)
    try:
        series = await provider.get_bars(sym, "5m", start, end)
    except Exception as e:
        raise HTTPException(502, "data provider error")

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
