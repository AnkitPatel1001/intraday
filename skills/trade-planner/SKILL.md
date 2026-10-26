---
name: trade-planner
description: >-
  Build a complete trade plan for an NSE stock: entry, stop-loss, target,
  risk/reward, position size, Indian transaction costs (STT, brokerage, GST,
  stamp duty), invalidation conditions, and maximum holding period. Outputs
  a research plan, not a buy/sell instruction. Use after identifying a
  setup and before risk-checking or paper trading.
argument-hint: "[NSE symbol]"
---

# trade-planner

Build a full trade plan from market data. Calculate everything that can be
calculated. Label output as research, not advice.

## Plan Components

1. **Setup**: What triggered the opportunity (ORB, breakout, etc.)
2. **Entry**: Price and timing (bar number, IST time)
3. **Stop-loss**: Based on setup structure (OR midpoint, OR low, ATR)
4. **Target**: Risk-multiple (1R, 2R, 3R) or structural level
5. **Risk/Reward**: Calculated ratio
6. **Position Size**: From capital × risk% ÷ risk per share
7. **Costs**: STT, brokerage, exchange charges, GST, SEBI fees, stamp duty, slippage
8. **Invalidation**: What proves the setup wrong
9. **Max Holding**: Bars until session end

## Indian Cost Model (Intraday)

| Component | Rate |
|-----------|------|
| Brokerage | ~0.03% of turnover |
| STT | 0.025% on sell |
| Exchange charges | 0.00345% |
| GST | 18% on (brokerage + exchange + SEBI) |
| SEBI fees | 0.0001% |
| Stamp duty | 0.015% on buy |
| Slippage | ~5 bps per side (estimate) |

## Rules

- All arithmetic in tested Python functions.
- Position size: whole shares only (Indian market constraint).
- Reject if risk per share ≤ 0 or capital insufficient.
- Output labeled "RESEARCH PLAN — not a buy/sell instruction".
- Never promise guaranteed returns.

## Failure Conditions

- Insufficient bars for setup → reject with explanation.
- Stop on wrong side of entry → reject.
- Zero position size → warn, return plan with zero shares.
