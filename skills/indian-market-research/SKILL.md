---
name: indian-market-research
description: >-
  Indian equity market research for NSE/BSE stocks. Reads company data,
  financial statements, and valuation metrics from available sources.
  Separates verified facts from model-generated interpretations. Cites
  sources and timestamps. Never fabricates news, figures, or citations.
  Use when researching an Indian company, analyzing fundamentals, or
  summarizing earnings/announcements. Not financial advice.
argument-hint: "[NSE symbol, e.g. RELIANCE]"
---

# indian-market-research

Research an NSE/BSE listed company. Read available data, present facts with
sources, separate interpretation from verified data. Never invent numbers.

## Data Sources

| Source | What | Freshness |
|--------|------|-----------|
| Yahoo Finance (.NS) | Price, volume, basic financials | Delayed, unofficial |
| NSE website | Official announcements, corporate actions | End-of-day |
| BSE website | Results, announcements | End-of-day |
| Synthetic provider | Demo mode only | Synthetic |

## Workflow

1. Validate the NSE symbol format.
2. Fetch available price data via the market data interface.
3. Present: last price, 52-week range, volume, sector.
4. Present available fundamentals with source labels.
5. Clearly separate: FACT (with source) vs INTERPRETATION (model-generated).
6. Add timestamp and freshness label to every data point.

## Rules

- Never fabricate financial figures, news, or citations.
- Every number carries a source label and freshness timestamp.
- Interpretations are labeled "INTERPRETATION — model-generated".
- Not financial advice. No guaranteed returns.
- If data is unavailable, say so plainly — do not guess.

## Failure Conditions

- Unknown symbol → reject with validation error.
- Data provider down → report stale/unavailable, do not substitute.
- Insufficient data → say "insufficient data for analysis".
