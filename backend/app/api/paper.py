"""Paper trading endpoints. Simulated only â€” no real money.

Portfolios are isolated per session token (see app/api/auth.py).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.api.auth import session_of
from app.core.config import get_settings
from app.core.symbols import validate_symbol
from app.data.factory import get_provider
from app.engine.paper import PaperTradingEngine

router = APIRouter()

# Per-session paper engines (in-memory, per-server). Production would use a DB.
_engines: dict[str, PaperTradingEngine] = {}


def get_engine(token: str = "anonymous") -> PaperTradingEngine:
    key = token or "anonymous"
    engine = _engines.get(key)
    if engine is None:
        settings = get_settings()
        engine = PaperTradingEngine(starting_cash=settings.default_capital)
        _engines[key] = engine
    return engine


def drop_engine(token: str) -> None:
    _engines.pop(token, None)


class OrderRequest(BaseModel):
    symbol: str
    side: str
    qty: int
    order_type: str = "market"
    price: float | None = None
    tag: str = ""


class FlattenRequest(BaseModel):
    symbol: str


@router.get("/portfolio")
async def portfolio(request: Request):
    e = get_engine(session_of(request))
    return e.snapshot()


@router.post("/order")
async def place_order(req: OrderRequest, request: Request):
    try:
        sym = validate_symbol(req.symbol)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if req.qty <= 0:
        raise HTTPException(400, "qty must be positive")
    if req.qty > 1_000_000:
        raise HTTPException(400, "qty must be at most 1000000")
    if req.side not in ("buy", "sell"):
        raise HTTPException(400, "side must be buy or sell")
    if req.order_type not in ("market", "limit"):
        raise HTTPException(400, "order_type must be market or limit")
    if len(req.tag) > 200:
        raise HTTPException(400, "tag must be at most 200 characters")
    if req.price is not None and req.price <= 0:
        raise HTTPException(400, "price must be positive")

    if req.order_type == "limit" and req.price is None:
        raise HTTPException(400, "limit order requires price")

    # Quote is required for market orders; used for crossing checks on limits.
    current_price: float | None = None
    provider = get_provider()
    try:
        q = await provider.get_quote(sym)
        current_price = q.last_price
    except Exception:
        if req.order_type == "market":
            raise HTTPException(502, "cannot get market price for market order")

    e = get_engine(session_of(request))
    order = e.place_order(sym, req.side, req.qty, req.order_type,
                          req.price, req.tag, current_price)
    return {
        "order": {
            "id": order.id, "symbol": order.symbol, "side": order.side,
            "qty": order.qty, "status": order.status,
            "fill_price": order.fill_price, "fees": order.fees,
            "slippage": order.slippage, "tag": order.tag,
            "limit_price": order.price if order.order_type == "limit" else None,
        },
        "portfolio": e.snapshot(),
        "label": "PAPER TRADING â€” simulated, no real money",
    }


@router.post("/flatten")
async def flatten(req: FlattenRequest, request: Request):
    try:
        sym = validate_symbol(req.symbol)
    except ValueError as e:
        raise HTTPException(400, str(e))
    e = get_engine(session_of(request))
    provider = get_provider()
    try:
        q = await provider.get_quote(sym)
        price = q.last_price
    except Exception:
        raise HTTPException(502, "cannot get price for flatten")
    order = e.flatten(sym, price)
    return {
        "flattened": order is not None,
        "order_id": order.id if order else None,
        "portfolio": e.snapshot(),
    }


@router.get("/orders")
async def list_orders(request: Request):
    e = get_engine(session_of(request))
    return {
        "orders": [
            {
                "id": o.id, "symbol": o.symbol, "side": o.side,
                "qty": o.qty, "status": o.status,
                "fill_price": o.fill_price, "limit_price": o.price,
                "order_type": o.order_type,
                "created_at": o.created_at.isoformat(),
            }
            for o in e.orders[-50:]
        ],
    }


@router.get("/audit")
async def audit_log(request: Request):
    e = get_engine(session_of(request))
    return {"log": e.audit_log[-100:]}


@router.post("/reset")
async def reset(request: Request, starting_cash: float = 500000):
    if starting_cash <= 0 or starting_cash > 1e12:
        raise HTTPException(400, "starting_cash must be > 0 and <= 1e12")
    token = session_of(request)
    _engines[token] = PaperTradingEngine(starting_cash=starting_cash)
    return {"status": "reset", "portfolio": _engines[token].snapshot()}
