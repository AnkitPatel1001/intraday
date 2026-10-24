"""Market data endpoints."""

from __future__ import annotations

import datetime

from fastapi import APIRouter, HTTPException, Query

from app.core.calendar import market_status_now, NSE_HOLIDAYS, SESSION_BARS
from app.core.config import get_settings
from app.core.primitives import DataFreshness
from app.core.symbols import validate_symbol, NIFTY50, SECTOR_MAP
from app.core.timezone import now_ist, to_ist
from app.data.factory import get_provider, staleness

router = APIRouter()


@router.get("/status")
async def market_status():
    return market_status_now()


@router.get("/holidays")
async def holidays(year: int | None = None):
    year = year or now_ist().year
    out = {d: name for d, name in NSE_HOLIDAYS.items() if d.startswith(str(year))}
    return {"year": year, "holidays": out, "count": len(out)}


@router.get("/indices")
async def indices():
    """Demo index overview. Synthetic data unless live provider configured."""
    provider = get_provider()
    out = []
    for idx in ("NIFTY50", "BANKNIFTY", "FINNIFTY", "NIFTYMIDCAP"):
        try:
            q = await provider.get_quote(idx)
            out.append({
                "symbol": idx,
                "last_price": q.last_price,
                "freshness": q.freshness.value,
                "source": q.source,
                "label": q.freshness.value,
            })
        except Exception:
            out.append({"symbol": idx, "error": "no data"})
    return {"indices": out, "as_of": now_ist().isoformat()}


@router.get("/sectors")
async def sectors():
    """Sector performance from demo universe."""
    provider = get_provider()
    sectors: dict[str, list[dict]] = {}
    for sym, sector in SECTOR_MAP.items():
        try:
            q = await provider.get_quote(sym)
            sectors.setdefault(sector, []).append({
                "symbol": sym, "price": q.last_price,
                "freshness": q.freshness.value,
            })
        except Exception:
            pass
    out = []
    for sector, stocks in sectors.items():
        avg = sum(s["price"] for s in stocks) / len(stocks) if stocks else 0
        out.append({"sector": sector, "avg_price": round(avg, 2), "count": len(stocks)})
    return {"sectors": out}


@router.get("/bars/{symbol}")
async def get_bars(
    symbol: str,
    interval: str = Query("5m", pattern="^(1m|5m|15m|1d)$"),
    days: int = Query(30, ge=1, le=365),
):
    try:
        sym = validate_symbol(symbol)
    except ValueError as e:
        raise HTTPException(400, str(e))
    provider = get_provider()
    end = now_ist().date()
    start = end - datetime.timedelta(days=days)
    try:
        series = await provider.get_bars(sym, interval, start, end)
    except Exception as e:
        raise HTTPException(502, "data provider error")
    return {
        "symbol": sym,
        "interval": interval,
        "exchange": series.exchange,
        "freshness": series.freshness.value,
        "source": series.source,
        "as_of": series.as_of.isoformat(),
        "staleness": staleness(series),
        "candles": [
            {
                "ts": c.ts.isoformat(),
                "open": c.open, "high": c.high,
                "low": c.low, "close": c.close, "volume": c.volume,
            }
            for c in series.candles
        ],
        "count": len(series.candles),
    }


@router.get("/quote/{symbol}")
async def get_quote(symbol: str):
    try:
        sym = validate_symbol(symbol)
    except ValueError as e:
        raise HTTPException(400, str(e))
    provider = get_provider()
    try:
        q = await provider.get_quote(sym)
    except Exception as e:
        raise HTTPException(502, "quote provider error")
    return {
        "symbol": q.symbol, "exchange": q.exchange,
        "last_price": q.last_price, "volume": q.volume,
        "ts": q.ts.isoformat(),
        "freshness": q.freshness.value, "source": q.source,
        "label": q.freshness.value,
    }


@router.get("/universe")
async def universe():
    from app.core.symbols import DEMO_UNIVERSE
    return {
        "symbols": DEMO_UNIVERSE,
        "count": len(DEMO_UNIVERSE),
        "note": "Demo universe. Not a full NSE listing. Use a data provider for complete coverage.",
    }


@router.get("/circuit-bands")
async def circuit_bands(symbol: str = Query("NIFTY50")):
    """Index circuit-breaker reference bands (SEBI ±10/15/20% from previous close).

    Reference only — computes levels and where price sits; does not model
    exchange halts or trigger intraday band logic.
    """
    try:
        sym = validate_symbol(symbol)
    except ValueError as e:
        raise HTTPException(400, str(e))

    provider = get_provider()
    end = now_ist().date()
    start = end - datetime.timedelta(days=30)
    try:
        series = await provider.get_bars(sym, "1d", start, end)
        quote = await provider.get_quote(sym)
    except Exception:
        raise HTTPException(502, "data provider error")

    closes = [c.close for c in series.candles]
    if not closes:
        raise HTTPException(400, f"no daily data for {sym}")
    prev_close = closes[-2] if len(closes) >= 2 else closes[-1]
    last = quote.last_price
    change_pct = (last - prev_close) / prev_close * 100 if prev_close else 0.0

    bands = []
    for pct in (10, 15, 20):
        bands.append({
            "pct": pct,
            "upper": round(prev_close * (1 + pct / 100), 2),
            "lower": round(prev_close * (1 - pct / 100), 2),
        })

    abs_change = abs(change_pct)
    current_band = next(
        (b["pct"] for b in reversed(bands) if abs_change >= b["pct"]), None
    )

    return {
        "symbol": sym,
        "prev_close": prev_close,
        "last": last,
        "change_pct": round(change_pct, 2),
        "bands": bands,
        "current_band": current_band,
        "status": f"band_{current_band}" if current_band else "normal",
        "freshness": series.freshness.value,
        "source": series.source,
        "as_of": series.as_of.isoformat(),
        "note": (
            "Reference levels only: ±10/15/20% from previous close as used for "
            "index circuit breakers. Not an exchange halt simulation."
        ),
    }
