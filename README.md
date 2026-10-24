# Indian Stock Market Intelligence Platform

AI-powered research, scanning, trade planning, paper trading, and backtesting for NSE equities (BSE via Yahoo `.BO` symbols).

**Paper trading by default. Not financial advice. No live order execution.**

Adapted from [day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill) (MIT, Jake Schincariol) for Indian market microstructure. See `THIRD_PARTY_NOTICES.md`.

## Quick Start

```bash
# 1. Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 2. Frontend (new terminal)
cd frontend
npm install
npm run dev

# 3. Open http://localhost:3000
```

Or with Docker:

```bash
docker compose up --build
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000/docs
```

## Architecture

```
backend/
  app/core/       IST timezone, NSE calendar, symbol validation, config
  app/data/       Provider interface, synthetic (demo), Yahoo adapter
  app/engine/     Indicators, scanner, planner, risk, paper, backtest, time machine
  app/api/        FastAPI routes
  tests/          275 tests (all offline, synthetic data)
frontend/
  src/app/        Next.js App Router pages
  src/components/ Chart, sidebar, badges
  src/lib/        API client, types, INR formatting
skills/           Adapted Claude skills (Indian market)
```

## Features

| Module | Description |
|--------|-------------|
| **Dashboard** | Market status, NSE indices, sector overview, freshness labels |
| **Scanner** | ORB, RSI, MA cross, volume spike, breakout — with explanations |
| **Time Machine** | Monte Carlo replay (10,000 sims + historical rule replay) — adapted from day-trader-skill |
| **Trade Planner** | Entry/stop/target, R:R, Indian costs (STT, brokerage, GST, stamp duty) |
| **Risk Engine** | PASS/BLOCK vs limits: daily loss, position count, R:R, entry window |
| **Paper Trading** | Simulated fills, slippage, fees, portfolio, audit log |
| **Backtesting** | ORB strategy, no look-ahead, realistic costs, equity curve |
| **Analytics** | Win rate, profit factor, P&L, CSV export |

## Indian Market Specifics

- **Session**: 09:15–15:30 IST (75 five-minute bars)
- **Timezone**: Asia/Kolkata (UTC+05:30, no DST)
- **Calendar**: NSE holidays 2025–2027, Muhurat trading
- **Symbols**: NSE format, Yahoo `.NS` mapping
- **Costs**: STT, exchange charges, GST, SEBI fees, stamp duty
- **Circuit breakers**: Reference bands from previous close (`GET /api/v1/market/circuit-bands`)

## Data Providers

| Provider | Mode | Freshness |
|----------|------|-----------|
| `demo` | Synthetic, deterministic | `synthetic` |
| `yahoo` | Free, unofficial, can lag | `delayed` |

Set `DATA_PROVIDER=demo` in `.env` for demo mode (default). No credentials required.

## API

Interactive docs at `http://localhost:8000/docs` (disabled when `APP_ENV=production`). Key endpoints:

```
POST /api/v1/auth/session        # -> {token}; send X-Session-Token or Authorization: Bearer
GET  /api/v1/market/status
GET  /api/v1/market/circuit-bands?symbol=NIFTY50
GET  /api/v1/market/bars/{symbol}?interval=5m&days=30
POST /api/v1/scanner/scan
POST /api/v1/trades/plan
POST /api/v1/trades/timemachine
POST /api/v1/trades/costs
POST /api/v1/risk/check
POST /api/v1/paper/order
GET  /api/v1/paper/portfolio
POST /api/v1/backtest/run
GET  /api/v1/analytics/performance
```

All `/api/v1/*` routes except `auth`, `market`, and `scanner/presets` require a
session token (401 without one when `AUTH_ENABLED=true`). Each token gets its
own isolated paper-trading portfolio.

## Tests

```bash
cd backend
python -m pytest tests/ -v
# 275 passed

cd ../frontend
npm test
# 37 passed (vitest)
```

All tests run offline on synthetic data. No network calls. CI enforces a
backend coverage gate of 85% (current: 91% lines).

## Security

- Session auth: opaque expiring tokens (`POST /api/v1/auth/session`); per-token
  portfolio isolation; disabled in tests only
- Sliding-window rate limiting with `429` + `Retry-After` (market reads get 5x bucket)
- Security headers: `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`,
  `Content-Security-Policy: default-src 'none'` on API responses
- Unhandled errors return JSON `500` without stack traces (details to logs)
- Secrets in environment variables only (`.env.example` has placeholders)
- No API keys exposed to frontend
- Paper trading only — no live broker connectivity
- Bounded inputs (qty, capital, replays, scan size, order types, prices)

## Regulatory Notes

- SEBI requirements for investment advice vary by product classification
- Exchange data licensing applies to live feeds
- Broker API terms of service apply for any future live integration
- This tool provides research and education, not personalized investment advice

## License

MIT. Portions adapted from day-trader-skill (MIT, Jake Schincariol). See `LICENSE` and `THIRD_PARTY_NOTICES.md`.
