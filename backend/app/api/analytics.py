"""Performance analytics endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.auth import session_of
from app.api.paper import get_engine

router = APIRouter()

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_cell(value: object) -> str:
    """Neutralize CSV/formula injection, then quote per RFC 4180."""
    s = "" if value is None else str(value)
    if s[:1] in _FORMULA_PREFIXES:
        s = "'" + s
    if any(c in s for c in (",", '"', "\n", "\r")):
        s = '"' + s.replace('"', '""') + '"'
    return s


@router.get("/performance")
async def performance(request: Request):
    e = get_engine(session_of(request))
    snap = e.snapshot()
    pf = e.portfolio
    wins = [p for p in pf.closed_positions if p.realized_pnl > 0]
    losses = [p for p in pf.closed_positions if p.realized_pnl <= 0]
    total_closed = len(pf.closed_positions)
    win_rate = len(wins) / total_closed * 100 if total_closed else 0
    avg_win = sum(p.realized_pnl for p in wins) / len(wins) if wins else 0
    avg_loss = sum(p.realized_pnl for p in losses) / len(losses) if losses else 0
    gross_win = sum(p.realized_pnl for p in wins)
    gross_loss = abs(sum(p.realized_pnl for p in losses))
    pf_ratio = gross_win / gross_loss if gross_loss > 0 else 0

    return {
        "realized_pnl": snap["realized_pnl"],
        "total_fees": snap["total_fees"],
        "trade_count": snap["trades"],
        "closed_count": total_closed,
        "win_rate_pct": round(win_rate, 1),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(pf_ratio, 2),
        "closed_trades": [
            {
                "symbol": p.symbol, "qty": p.qty,
                "avg_price": p.avg_price,
                "pnl": round(p.realized_pnl, 2),
            }
            for p in pf.closed_positions[-50:]
        ],
        "label": "PAPER TRADING analytics — simulated results",
    }


@router.get("/export")
async def export_csv(request: Request):
    e = get_engine(session_of(request))
    # Honest per-order schema: one row per order, columns match header.
    lines = [
        "order_id,symbol,side,order_type,qty,fill_price,slippage,fees,status,tag"
    ]
    for o in e.orders:
        fill = "" if o.fill_price is None else f"{o.fill_price:.2f}"
        slip = "" if o.fill_price is None else f"{o.slippage:.2f}"
        fees = "" if o.fill_price is None else f"{o.fees:.2f}"
        row = [o.id, o.symbol, o.side, o.order_type, o.qty,
               fill, slip, fees, o.status, o.tag]
        lines.append(",".join(_csv_cell(c) for c in row))
    csv = "\n".join(lines)
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(csv, media_type="text/csv")
