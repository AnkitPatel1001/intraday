"""Risk management endpoints."""

from __future__ import annotations

import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.core.timezone import now_ist
from app.engine.risk import RiskLimits, check_trade

router = APIRouter()


class RiskCheckRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    symbol: str
    side: Literal["buy", "sell"] = "buy"
    entry: float = Field(..., gt=0, le=1e9)
    stop: float = Field(..., gt=0, le=1e9)
    target: float = Field(..., gt=0, le=1e9)
    shares: int = Field(0, ge=0, le=10_000_000)
    capital: float | None = Field(None, gt=0, le=1e12)
    risk_per_trade_pct: float | None = Field(None, gt=0, le=100)
    max_daily_loss_pct: float | None = Field(None, gt=0, le=100)
    max_positions: int | None = Field(None, ge=0, le=1000)
    min_risk_reward: float | None = Field(None, gt=0, le=1000)
    daily_pnl: float = Field(0.0, ge=-1e12, le=1e12)
    trades_today: int = Field(0, ge=0, le=10_000)
    open_positions: int = Field(0, ge=0, le=1000)



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
