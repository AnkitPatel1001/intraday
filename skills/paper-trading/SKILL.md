---
name: paper-trading
description: >-
  Simulated order execution for NSE stocks. Market/limit orders, realistic
  fills with slippage, Indian transaction fees, virtual portfolio with cash
  and positions, trade journal and audit log. No real money. Default mode
  for the entire platform. Use when executing a risk-approved trade plan
  in simulation.
argument-hint: "[symbol, side, quantity]"
---

# paper-trading

Simulated order execution. Paper only. No real money.

## Order Types

| Type | Fill Logic |
|------|------------|
| Market | Current price ± slippage (5 bps) |
| Limit | Fill if price crosses limit |
| SL | Stop-loss trigger |
| SL-M | Stop-loss market |

## Fee Model

Same Indian cost model as trade planner: brokerage, STT, exchange charges,
GST, SEBI fees, stamp duty, slippage.

## Portfolio

- Cash balance (starts at configured capital)
- Open positions with avg price, unrealized P&L
- Closed positions with realized P&L
- Total fees paid
- Trade count
- Full audit log of every action

## Rules

- Paper trading is the ONLY execution mode by default.
- Every response includes "PAPER TRADING — simulated" label.
- Insufficient cash → reject order.
- Insufficient position (sell) → reject order.
- Whole shares only.
- All actions logged to audit trail.

## Failure Conditions

- qty ≤ 0 → reject.
- Invalid side → reject.
- No price available → reject (cannot fill blindly).
