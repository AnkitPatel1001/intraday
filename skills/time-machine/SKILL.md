---
name: time-machine
description: >-
  Replay a planned NSE day trade before risking money: 10,000 Monte Carlo
  simulations of the rest of the session from the stock's own 5-minute bars,
  plus every past session where the same setup fired. Reports odds of target
  first, stop first, or neither. Honest verdict. Simulation, not prediction.
  Adapted from trader-timemachine for NSE (09:15-15:30 IST, 75 bars).
  Use after trade planning, before position sizing.
argument-hint: "[NSE symbol or path to plan]"
---

# time-machine

Replay a planned trade. 10,000 simulations + historical rule replay.
Built from the stock's own recent NSE sessions. Not a prediction.

## How It Works

1. **Pool**: Full NSE sessions (75 five-minute bars, 09:15–15:30 IST)
   before the plan's date. Each bar stored as ratios to previous close.
2. **One replay**: Start at entry price. For each remaining bar, pick
   a past bar from same time of day (±2 bars), scale to current price.
   Stop checked before target (conservative).
3. **10,000 replays**: Target first %, stop first %, neither %, green %.
   Average R, median close, 5th–95th percentile.
4. **History**: Same ORB rule re-run on every past real session.
5. **Verdict**: Compares target's share of side-hits to break-even (1/(1+R)).

## Verdict Thresholds

| Gap from break-even | Verdict |
|---------------------|---------|
| < 5 points | Close to coin flip (1R) / break-even (other R) |
| 5–15 points | Leans toward target / stop |
| ≥ 15 points | Strongly toward target / stop |

## Rules

- Same seed + same data = same numbers. Always report seed.
- Simulation ≠ prediction. Earnings/halts can exceed historical patterns.
- Never round a coin flip into an edge.
- A gap through the stop still counts as -1R here; real fill can be worse.
- Refuse with < 20 full sessions, missing entry bar, or invalid plan.
- One plan per run. Changed entry/stop/target = new run.

## Data Requirements

- 5-minute NSE bars, at least 20 full sessions before plan date.
- All 75 bars per session (half days excluded).
- Entry bar must exist in data and be complete.
