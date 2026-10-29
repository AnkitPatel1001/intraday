"""Trade planning endpoints."""

from __future__ import annotations

import asyncio
import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.auth import session_of
from app.api.paper import OrderRequest as PaperOrderRequest, get_engine, place_order as paper_place_order
from app.core.calendar import SESSION_BARS
from app.core.config import get_settings
from app.core.symbols import validate_symbol
from app.core.timezone import now_ist
from app.data.factory import get_provider
from app.api.provider_errors import provider_502
from app.engine.autotrade import decide_auto_trade
from app.engine.planner import build_plan, estimate_costs, position_size
from app.engine.risk import RiskLimits, check_trade
from app.engine.timemachine import (
    run_time_machine, normalize_plan, resolve_entry_date, split_sessions,
    TimeMachineError,
)

router = APIRouter()

# Cap concurrent Monte Carlo simulations so threadpool stays available
_SIM_SEMAPHORE = asyncio.Semaphore(2)


async def _resolve_latest_session(provider, sym: str, plan_dict: dict, today: datetime.date):
    """Resolve a dateless plan_dict against the latest session (within the
    last 90 days) whose entry bar is complete. Shared by /timemachine's
    date=None path and /auto, which both want "today, or the most recent
    trading day that actually has this bar" instead of a hard failure on
    weekends/holidays/pre-market.

    Raises TimeMachineError for a bad bar grid or no matching session;
    provider fetch errors propagate unchanged for the caller to 502-wrap.
    """
    plan = normalize_plan({**plan_dict, "date": today.isoformat()})
    series = await provider.get_bars(
        sym, "5m", today - datetime.timedelta(days=90), today)
    resolved = resolve_entry_date(split_sessions(series.candles), plan["entry_bar"])
    if resolved is None:
        raise TimeMachineError(
            f"entry bar {plan['entry_bar']} not found in the last 90 days "
            "— no complete 5-min bar")
    plan = normalize_plan({**plan_dict, "date": resolved})
    return plan, series


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


class AutoTradeRequest(BaseModel):
    symbol: str
    side: Literal["buy", "sell"] = "buy"
    entry_bar: int = Field(5, ge=0, le=SESSION_BARS - 2)
    stop_pct: float = Field(0.5, gt=0, le=20)   # skill default: 0.5% stop distance
    target_r: float = Field(2.0, gt=0, le=50)   # skill default: 2R target
    capital: float = Field(500000, gt=0, le=1e12)
    risk_pct: float = Field(1.0, gt=0, le=100)
    replays: int = Field(10000, ge=1, le=100_000)
    seed: int = 19
    min_edge: float = Field(0.05, ge=0, le=1.0)
    qty: int | None = Field(None, gt=0, le=1_000_000)
    execute: bool = True  # False = decide only, never place the paper order
    tag: str = ""


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
            plan, series = await _resolve_latest_session(provider, sym, plan_dict, today)
        except TimeMachineError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise provider_502(sym, e) from e
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


@router.post("/auto")
async def auto_trade(req: AutoTradeRequest, request: Request):
    """Time-machine-gated automatic buy/sell. PAPER TRADING ONLY.

    Derives entry/stop/target from the live quote (skill defaults: 0.5%
    stop distance, target_r reward), risk-checks the plan against the
    account's limits/portfolio, and runs the Monte Carlo + historical
    rule replay on the symbol's own past sessions. The paper order is
    placed automatically — through the caller's own session portfolio —
    only when the risk check PASSes AND the replay's target-vs-stop edge
    is at or above `min_edge`. No live broker is ever touched; set
    `execute=false` to see the decision without placing an order.
    """
    try:
        sym = validate_symbol(req.symbol)
    except ValueError as e:
        raise HTTPException(400, str(e))

    provider = get_provider()
    try:
        q = await provider.get_quote(sym)
    except Exception as e:
        raise provider_502(sym, e) from e

    long = req.side == "buy"
    entry = round(q.last_price, 2)
    risk_per_share = max(round(entry * req.stop_pct / 100, 2), 0.01)
    reward_per_share = round(risk_per_share * req.target_r, 2)
    stop = round(entry - risk_per_share, 2) if long else round(entry + risk_per_share, 2)
    target = round(entry + reward_per_share, 2) if long else round(entry - reward_per_share, 2)

    settings = get_settings()
    limits = RiskLimits(
        capital=req.capital, risk_per_trade_pct=req.risk_pct,
        max_daily_loss_pct=settings.default_max_daily_loss_pct,
        max_positions=settings.default_max_positions,
        min_risk_reward=settings.default_min_risk_reward,
    )
    # max_position_pct passed through so a tight stop_pct (which inflates
    # the risk-budget share count) can't size a position that's pre-doomed
    # to BLOCK on the risk check's own concentration limit.
    sizing = position_size(req.capital, req.risk_pct, entry, stop,
                           max_position_pct=limits.max_position_pct)
    shares = req.qty if req.qty is not None else sizing.get("shares", 0)
    costs = estimate_costs(entry, max(shares, 0), req.side)

    engine = get_engine(session_of(request))
    portfolio = engine.snapshot()
    today = now_ist().date()
    trades_today = sum(
        1 for o in engine.orders
        if o.status == "filled" and o.created_at.date() == today
    )
    risk_plan = {
        "symbol": sym, "side": req.side,
        "entry": entry, "stop": stop, "target": target, "shares": shares,
    }
    rc = check_trade(risk_plan, limits, portfolio, portfolio["realized_pnl"],
                      trades_today, now_ist())

    # Resolve the latest session that actually has this entry bar, same as
    # /timemachine's auto-date behaviour, then replay it.
    tm_plan_dict: dict = {
        "symbol": sym, "side": req.side,
        "entry": entry, "stop": stop, "target": target,
        "setup": "orb", "opening_range": {"minutes": 15},
        "stop_rule": "auto", "entry_bar": req.entry_bar,
    }
    tm_result: dict | None = None
    time_machine_error: str | None = None
    try:
        plan, series = await _resolve_latest_session(provider, sym, tm_plan_dict, today)
    except TimeMachineError as e:
        plan, series, time_machine_error = None, None, str(e)
    except Exception as e:
        raise provider_502(sym, e) from e

    if plan is not None:
        try:
            async with _SIM_SEMAPHORE:
                tm_result = await asyncio.to_thread(
                    run_time_machine, series, plan,
                    replays=req.replays, seed=req.seed,
                )
        except TimeMachineError as e:
            time_machine_error = str(e)

    mc = tm_result["mc"] if tm_result else None
    decision = decide_auto_trade(mc, rc.passed, req.min_edge, shares)

    order_out = None
    order_error = None
    if decision["action"] == "enter" and req.execute:
        try:
            paper_req = PaperOrderRequest(
                symbol=sym, side=req.side, qty=shares, order_type="market",
                tag=req.tag or f"auto:timemachine:{decision['edge']:+.3f}",
                stop=stop, target=target,
            )
            result = await paper_place_order(paper_req, request)
            order_out = result["order"]
            portfolio = result["portfolio"]
        except HTTPException as e:
            order_error = e.detail

    time_machine_out = None
    if tm_result is not None:
        slim_mc = {k: v for k, v in tm_result["mc"].items() if k not in ("sample_paths", "bands")}
        time_machine_out = {
            "verdict": tm_result["verdict"],
            "verdict_notes": tm_result["verdict_notes"],
            "mc": slim_mc,
            "history": tm_result["history"],
            "plan_date": tm_result["plan"]["date"],
        }

    return {
        "label": (
            "PAPER TRADING AUTO-STRATEGY — time-machine-gated, simulated, "
            "no real money, not financial advice"
        ),
        "symbol": sym, "side": req.side,
        "live_price": q.last_price, "freshness": q.freshness.value,
        "plan": {
            "entry": entry, "stop": stop, "target": target,
            "risk_per_share": risk_per_share, "reward_per_share": reward_per_share,
            "target_r": req.target_r, "shares": shares, "costs": costs,
        },
        "risk": {
            "passed": rc.passed, "verdict": "PASS" if rc.passed else "BLOCK",
            "checks": rc.checks, "reasons": rc.reasons, "fingerprint": rc.fingerprint,
        },
        "time_machine": time_machine_out,
        "time_machine_error": time_machine_error,
        "decision": decision,
        "order": order_out,
        "order_error": order_error,
        "portfolio": portfolio,
    }
