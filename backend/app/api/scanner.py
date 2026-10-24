"""Scanner endpoints."""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Body, HTTPException, Query

from app.core.config import get_settings
from app.core.symbols import validate_symbol, DEMO_UNIVERSE
from app.core.timezone import now_ist
from app.data.factory import get_provider
from app.engine.scanner import ScanFilters, scan_symbol

router = APIRouter()


@router.post("/scan")
async def run_scan(
    symbols: list[str] | None = Body(default=None, embed=True),
    min_price: float = Query(10.0, ge=0),
    min_volume: int = Query(10000, ge=0),
    interval: str = Query("5m", pattern="^(1m|5m|15m|1d)$"),
    days: int = Query(30, ge=5, le=365),
):
    """Scan symbols for technical setups. Returns matches with explanations."""
    if symbols is not None and len(symbols) > 100:
        raise HTTPException(422, "scan accepts at most 100 symbols per request")
    syms = symbols or DEMO_UNIVERSE[:20]
    provider = get_provider()
    filters = ScanFilters(min_price=min_price, min_volume=min_volume)
    end = now_ist().date()
    start = end - datetime.timedelta(days=days)

    results = []
    errors = []
    for sym_str in syms:
        try:
            sym = validate_symbol(sym_str)
        except ValueError as e:
            errors.append({"symbol": sym_str, "error": str(e)})
            continue
        try:
            series = await provider.get_bars(sym, interval, start, end)
            r = scan_symbol(series, filters)
            if r:
                results.append({
                    "symbol": r.symbol, "price": r.price,
                    "setups": r.setups, "indicators": r.indicators,
                    "reason": r.reason,
                    "freshness": r.freshness, "source": r.source,
                    "warnings": r.warnings,
                })
        except Exception as e:
            errors.append({"symbol": sym, "error": str(e)})

    return {
        "scanned": len(syms),
        "matched": len(results),
        "errors": errors,
        "results": results,
        "as_of": now_ist().isoformat(),
        "note": "A scan is a list of charts matching a rule, not a list of stocks to buy.",
    }


@router.get("/presets")
async def presets():
    return {
        "presets": [
            {"name": "ORB", "description": "Opening-range breakout", "interval": "5m"},
            {"name": "RSI Oversold", "description": "RSI(14) < 30", "interval": "1d"},
            {"name": "MA Cross", "description": "EMA9/EMA21 crossover", "interval": "5m"},
            {"name": "Volume Spike", "description": "> 2x average volume", "interval": "5m"},
            {"name": "Breakout 20d", "description": "New 20-bar high", "interval": "1d"},
        ],
    }
