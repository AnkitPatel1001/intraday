---
name: nse-scanner
description: >-
  Scan NSE stocks for technical setups: opening-range breakouts, RSI extremes,
  moving-average crosses, volume spikes, breakouts. Returns matches with
  explanations of why each stock matched. Handles missing/stale data safely.
  Use when screening for trade candidates or running technical scans.
argument-hint: "[optional: symbols list or 'universe']"
---

# nse-scanner

Screen NSE stocks for technical setups. Every match includes an explanation.

## Setups Detected

| Setup | Condition |
|-------|-----------|
| ORB | Price closes above opening-range high (5-min) |
| RSI Oversold | RSI(14) < 30 |
| RSI Overbought | RSI(14) > 70 |
| MA Cross | EMA9 crosses EMA21 |
| Volume Spike | Volume > 2x 20-bar average |
| Breakout | Price > 20-bar high |

## Workflow

1. Fetch bars via market data provider (label freshness).
2. Compute indicators in Python (not LLM arithmetic).
3. Apply filters: min price, min volume.
4. For each match, generate explanation string.
5. Sort by liquidity (price × volume).
6. Return with data freshness labels.

## Rules

- A scan is a list of charts matching a rule, not a list of stocks to buy.
- Every match includes a human-readable reason.
- Missing/stale data: skip symbol, report in errors list.
- All arithmetic in tested Python functions, never LLM-generated.
- Freshness labels: synthetic/delayed/live on every result.

## Failure Conditions

- No data for symbol → add to errors, continue.
- All symbols filtered → return empty with explanation.
- Provider rate-limited → report, do not retry blindly.
