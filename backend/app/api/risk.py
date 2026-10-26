"""Risk management endpoints."""

from __future__ import annotations

import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.timezone import now_ist
from app.engine.risk import RiskLimits, check_trade

router = APIRouter()


class RiskCheckRequest(BaseModel):
    symbol: str
    side: str = "buy"
    entry: float
    stop: float
    target: float
    shares: int = 0
    capital: float | None = None
    risk_per_trade_pct: float | None = None
    max_daily_loss_pct: float | None = None
    max_positions: int | None = None
    min_risk_reward: float | None = None
    daily_pnl: float = 0.0
    trades_today: int = 0
    open_positions: int = 0



@router.post("/check")
async def check(req: RiskCheckRequest):
    settings = get_settings()
    limits = RiskLimits(
        capital=req.capital or settings.default_capital,
        risk_per_trade_pct=req.risk_per_trade_pct or settings.default_risk_per_trade_pct,
        max_daily_loss_pct=req.max_daily_loss_pct or settings.default_max_daily_loss_pct,
        max_positions=req.max_positions or settings.default_max_positions,
        min_risk_reward=req.min_risk_reward or settings.default_min_risk_reward,
    )
    plan = {
        "symbol": req.symbol, "side": req.side,
        "entry": req.entry, "stop": req.stop, "target": req.target,
        "shares": req.shares,
    }
    portfolio = {"positions": [{"id": i} for i in range(req.open_positions)]}
    rc = check_trade(plan, limits, portfolio, req.daily_pnl, req.trades_today, now_ist())
    return {
        "passed": rc.passed,
        "verdict": "PASS" if rc.passed else "BLOCK",
        "checks": rc.checks,
        "reasons": rc.reasons,
        "fingerprint": rc.fingerprint,
        "label": "Risk check is a rules verification, not a recommendation.",
    }


@router.get("/limits")
async def get_limits():
    s = get_settings()
    return {
        "capital": s.default_capital,
        "risk_per_trade_pct": s.default_risk_per_trade_pct,
        "max_daily_loss_pct": s.default_max_daily_loss_pct,
        "max_positions": s.default_max_positions,
        "min_risk_reward": s.default_min_risk_reward,
        "paper_trading": True,
    }
