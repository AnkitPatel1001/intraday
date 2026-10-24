"""Paper trading engine. Simulated fills, slippage, fees. No real money."""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field
from typing import Optional

from app.core.timezone import IST
from app.engine.planner import estimate_costs


@dataclass
class Order:
    id: str
    symbol: str
    side: str          # 'buy' or 'sell'
    order_type: str    # 'market' or 'limit'
    qty: int
    price: Optional[float]
    status: str = "pending"  # pending, working, filled, cancelled, rejected
    fill_price: Optional[float] = None
    fill_time: Optional[datetime.datetime] = None
    slippage: float = 0.0
    fees: float = 0.0
    tag: str = ""       # e.g. 'entry', 'stop', 'target'
    created_at: datetime.datetime = field(default_factory=lambda: datetime.datetime.now(IST))


@dataclass
class Position:
    symbol: str
    side: str
    qty: int
    avg_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    opened_at: Optional[datetime.datetime] = None
    stop: Optional[float] = None
    target: Optional[float] = None


@dataclass
class Portfolio:
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    closed_positions: list[Position] = field(default_factory=list)
    total_fees: float = 0.0
    realized_pnl: float = 0.0
    trades: int = 0


class PaperTradingEngine:
    """Simulated order execution. Paper only — no broker connectivity."""

    def __init__(self, starting_cash: float = 500000):
        self.portfolio = Portfolio(cash=starting_cash)
        self.orders: list[Order] = []
        self.audit_log: list[dict] = []

    def _log(self, action: str, **kwargs) -> None:
        self.audit_log.append({
            "ts": datetime.datetime.now(IST).isoformat(),
            "action": action,
            **kwargs,
        })

    def place_order(
        self, symbol: str, side: str, qty: int,
        order_type: str = "market", price: Optional[float] = None,
        tag: str = "", current_price: Optional[float] = None,
    ) -> Order:
        if qty <= 0:
            raise ValueError("qty must be positive")
        if side not in ("buy", "sell"):
            raise ValueError("side must be buy or sell")
        if order_type not in ("market", "limit"):
            raise ValueError(f"unsupported order_type: {order_type}")

        # Opportunistically match any resting (working) orders first
        if current_price is not None:
            self._match_working(symbol, current_price)

        order = Order(
            id=str(uuid.uuid4())[:12],
            symbol=symbol, side=side, order_type=order_type,
            qty=qty, price=price, tag=tag,
        )

        if order_type == "limit":
            if price is None:
                order.status = "rejected"
                self._log("order_rejected", order_id=order.id, symbol=symbol,
                          reason="limit order requires price")
                self.orders.append(order)
                return order
            crosses = (
                current_price is not None
                and ((side == "buy" and current_price <= price)
                     or (side == "sell" and current_price >= price))
            )
            if not crosses:
                # No market price yet, or market has not reached the limit:
                # rest the order. It can fill on later quotes (see _match_working).
                order.status = "working"
                self._log("order_working", order_id=order.id, symbol=symbol,
                          side=side, qty=qty, limit=price)
                self.orders.append(order)
                return order
            fill_price = price
            slippage = 0.0
        else:  # market
            if current_price is None:
                order.status = "rejected"
                self._log("order_rejected", order_id=order.id, symbol=symbol,
                          reason="no market price available")
                self.orders.append(order)
                return order
            slip = current_price * 0.0005  # 5 bps slippage
            fill_price = current_price + slip if side == "buy" else current_price - slip
            slippage = slip

        self._execute(order, fill_price, slippage)
        return order

    def _execute(self, order: Order, fill_price: float, slippage: float) -> None:
        costs = estimate_costs(fill_price, order.qty, order.side)
        order.fill_price = round(fill_price, 2)
        order.slippage = round(slippage, 2)
        order.fees = costs["total_est"]
        order.fill_time = datetime.datetime.now(IST)
        order.status = "filled"

        self._apply_fill(order)  # may flip to 'rejected' (insufficient cash/position)
        if order not in self.orders:
            self.orders.append(order)
        if order.status == "filled":
            self._log("order_filled", order_id=order.id, symbol=order.symbol,
                      side=order.side, qty=order.qty, price=order.fill_price,
                      fees=order.fees)

    def _match_working(self, symbol: str, current_price: float) -> None:
        """Fill resting limit orders of `symbol` when the market reaches them."""
        for o in self.orders:
            if o.status != "working" or o.symbol != symbol or o.price is None:
                continue
            reaches = (
                (o.side == "buy" and current_price <= o.price)
                or (o.side == "sell" and current_price >= o.price)
            )
            if reaches:
                self._execute(o, o.price, 0.0)

    def _apply_fill(self, order: Order) -> None:
        pf = self.portfolio
        sym = order.symbol
        pos = pf.positions.get(sym)

        if order.side == "buy":
            cost = order.fill_price * order.qty + order.fees
            if cost > pf.cash:
                order.status = "rejected"
                self._log("insufficient_cash", order_id=order.id, needed=cost, available=pf.cash)
                return
            pf.cash -= cost
            pf.total_fees += order.fees
            if pos is None:
                pf.positions[sym] = Position(
                    symbol=sym, side="long", qty=order.qty,
                    avg_price=order.fill_price, opened_at=order.fill_time,
                )
            else:
                total_qty = pos.qty + order.qty
                pos.avg_price = (pos.avg_price * pos.qty + order.fill_price * order.qty) / total_qty
                pos.qty = total_qty
            pf.trades += 1
        else:
            if pos is None or pos.qty < order.qty:
                order.status = "rejected"
                self._log("insufficient_position", order_id=order.id, symbol=sym)
                return
            proceeds = order.fill_price * order.qty - order.fees
            pnl = (order.fill_price - pos.avg_price) * order.qty - order.fees
            pf.cash += proceeds
            pf.total_fees += order.fees
            pf.realized_pnl += pnl
            pos.realized_pnl += pnl
            pos.qty -= order.qty
            if pos.qty == 0:
                pf.closed_positions.append(pos)
                del pf.positions[sym]

    def flatten(self, symbol: str, current_price: float) -> Optional[Order]:
        pos = self.portfolio.positions.get(symbol)
        if not pos:
            return None
        side = "sell" if pos.side == "long" else "buy"
        return self.place_order(symbol, side, pos.qty, "market",
                                current_price=current_price, tag="flatten")

    def update_unrealized(self, symbol: str, current_price: float) -> None:
        pos = self.portfolio.positions.get(symbol)
        if pos:
            pos.unrealized_pnl = (current_price - pos.avg_price) * pos.qty

    def snapshot(self) -> dict:
        pf = self.portfolio
        positions = [
            {
                "symbol": p.symbol, "side": p.side, "qty": p.qty,
                "avg_price": p.avg_price, "unrealized_pnl": round(p.unrealized_pnl, 2),
                "stop": p.stop, "target": p.target,
            }
            for p in pf.positions.values()
        ]
        return {
            "cash": round(pf.cash, 2),
            "positions": positions,
            "realized_pnl": round(pf.realized_pnl, 2),
            "total_fees": round(pf.total_fees, 2),
            "trades": pf.trades,
            "closed_count": len(pf.closed_positions),
            "label": "PAPER TRADING — simulated, no real money",
        }
