# Indian Stock Market Intelligence Platform

AI-powered research, scanning, trade planning, paper trading, and backtesting for NSE equities (BSE via Yahoo `.BO` symbols).

**Paper trading by default. Not financial advice. No live order execution.**

Adapted from [day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill) (MIT, Jake Schincariol) for Indian market microstructure. See `THIRD_PARTY_NOTICES.md`.

## Quick Start

```bash
# 1. Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000 --no-server-header

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
| **Auto-Trade** | Time-machine-gated automatic buy/sell — paper only, see below |
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
| `upstox` | Free official API; WebSocket quotes + REST history | `live` / `delayed` / `historical` |

Set `DATA_PROVIDER=demo` in `.env` for demo mode (default). No credentials required.

### Upstox (free official data, WebSocket quotes)

**Paper only: this app places zero broker orders. The Upstox integration is
market-data read-only — no order, portfolio, or account endpoints exist in the
code (enforced by tests).** Sandbox note: Upstox's sandbox
(`https://sandbox.upstox.com`) exists only for *order* APIs (place/modify/cancel).
This app uses no order APIs at all — real or sandbox — so it cannot touch your
real account. Only read-only market-data endpoints on `api.upstox.com` are used
(prices, candles, instrument file; reading them involves no money and no
account actions). Trading happens solely in the local paper engine.

How to get a free Upstox API key:

1. **Open a free Upstox trading account** at upstox.com (₹0 account opening;
   PAN + Aadhaar + bank account required). API access is tied to an account.
2. Go to **upstox.com/developer** → *Manage API Apps* → **Create new app**
   (name + any redirect URL like `http://localhost:3000`). Free: all trading +
   market-data APIs cost ₹0.
3. Note your **API Key** and **API Secret** from the app page.
4. **Authorize once (OAuth):** open in a browser (fill `YOUR_API_KEY`):

   ```
   https://api.upstox.com/v2/login/auth/authorization?response_type=code&api_key=YOUR_API_KEY&redirect_uri=http://localhost:3000
   ```

   Log in and approve. You are redirected to your redirect URL with `?code=XXXX`.
   Exchange it within 30 seconds:

   ```bash
   curl -X POST https://api.upstox.com/v2/login/auth/token \
     -H "Content-Type: application/json" \
     -d '{"code":"XXXX","api_key":"YOUR_API_KEY","api_secret":"YOUR_SECRET","redirect_uri":"http://localhost:3000"}'
   ```

   → `access_token` (valid 1 day) + `refresh_token`.
5. **Get an Analytics Token** (recommended): long-lived, read-only, powers
   market data + WebSocket **without daily re-authorization** — generate it from
   your developer app page (see the *Analytics Token* announcement in the
   Upstox developer docs).
6. Put them in `.env`:

   ```bash
   DATA_PROVIDER=upstox
   UPSTOX_ANALYTICS_TOKEN=...   # preferred (long-lived)
   UPSTOX_ACCESS_TOKEN=...      # daily OAuth fallback
   ```

Why WebSocket: quotes stream over one `wss://api.upstox.com/v3/feed/market-data-feed`
connection (LTPC mode, protobuf frames) instead of REST polling — quote reads
never consume the 50 req/s REST quota, so no 429s. REST historical calls are
client-side throttled (`UPSTOX_REST_MAX_PER_SECOND`, default 10/s) with
`Retry-After` backoff as a second line of defense. Disable the feed with
`UPSTOX_WS_ENABLED=false` to force REST-only quotes.

Notes: first use downloads the public NSE instrument file (symbol → instrument
key) and caches it for 7 days under `backend/data/` (gitignored). Intraday
history is fetched in ≤27-day chunks (Upstox API limit). Without any token the
provider fails with a setup hint (502) — set `DATA_PROVIDER` back to `demo`.

### Sandbox mode (default: on)

`UPSTOX_SANDBOX=true` (default) — verified against Upstox on 2026-10-25:

- Sandbox host is `https://api-sandbox.upstox.com` (the older
  `sandbox.upstox.com` no longer resolves). It exposes **order APIs only**:
  market-data probes (`/v3/historical-candle`, `/v3/market-quote/ltp`) return
  `404 UDAPI100060 Resource not Found`, matching Upstox's statement that the
  sandbox "supports only the Order Placement API".
- Market data therefore stays on `api.upstox.com` — but data endpoints are
  **read-only** (quotes/candles/instrument file). Reading prices cannot place
  orders, touch funds, or view your account.
- This app contains **zero order endpoints** (source-scan enforced in
  `tests/test_upstox.py`) — stronger than sandbox: live order APIs are never
  called, sandbox or otherwise. All trading is the local paper engine.
- Provider health reports the mode: `mode: "sandbox"`,
  `order_endpoints: "none (paper trading only)"`.
- Want a sandbox token anyway (for external order testing later): Developer
  Apps page → **New Sandbox App** → **Generate** — no OAuth redirect needed,
  token valid 30 days, one sandbox app per user. Not needed by this app.

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
POST /api/v1/trades/auto         # time-machine-gated automatic buy/sell (paper)
POST /api/v1/trades/costs
POST /api/v1/risk/check
POST /api/v1/paper/order
GET  /api/v1/paper/portfolio
POST /api/v1/backtest/run
GET  /api/v1/analytics/performance
```

### Auto-Trade (`POST /api/v1/trades/auto`)

A strategy that closes the loop between Time Machine and Paper Trading:
given a symbol and side, it derives entry/stop/target from the live quote
(skill defaults: 0.5% stop distance, 2R target), risk-checks the plan
against the account's limits and current portfolio, then replays it
through the Monte Carlo + historical rule engine on the symbol's own past
sessions. **A paper order is placed automatically — in the caller's own
session portfolio — only when the risk check PASSes *and* the replay's
target-vs-stop edge is at or above `min_edge`** (default 0.05, matching the
Time Machine verdict's own "leans" threshold; 0.15 for "strongly"). Pass
`execute: false` to see the decision (and the full plan/risk/Monte Carlo
detail) without ever placing an order. Like every other execution path in
this app, it is **paper-only** — it places orders through the same
in-memory paper engine as `POST /api/v1/paper/order` and never calls a
live broker.

All `/api/v1/*` routes except `auth`, `market`, and `scanner/presets` require a
session token (401 without one when `AUTH_ENABLED=true`). Each token gets its
own isolated paper-trading portfolio.

## Tests

```bash
cd backend
python -m pytest tests/ -v
# 415 passed

cd ../frontend
npm test
# 52 passed (vitest)
```

All tests run offline on synthetic data. No network calls. CI enforces a
backend coverage gate of 85% (current: 90% lines).

## Security

- Session auth: opaque expiring tokens (`POST /api/v1/auth/session`); per-token
  portfolio isolation; disabled in tests only
- Sliding-window rate limiting with `429` + `Retry-After`, keyed per
  `host|token|bucket` (market reads get 5x bucket; one exhausted session cannot
  starve other sessions behind the same IP)
- Security headers: `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`,
  `Content-Security-Policy: default-src 'none'` on API responses; no
  `Server: uvicorn` fingerprint (launch with `--no-server-header`, as README
  quick start and Dockerfile do)
- Unhandled errors return JSON `500` without stack traces (details to logs)
- Secrets in environment variables only (`.env.example` has placeholders)
- No API keys exposed to frontend
- Paper trading only — no live broker connectivity
- Bounded inputs (qty, capital, replays, scan size, order types, prices);
  `/market/bars` capped at 10000 bars per request

## Operational Notes

- **In-memory state:** sessions and paper portfolios live in process memory.
  Server restart logs everyone out and flattens portfolios; run a single
  uvicorn worker (multi-worker would fragment state).
- **Long-only paper model:** NSE intraday short selling is not modeled; sells
  without a long position are rejected.
- **Session gate:** paper orders are accepted only while the NSE session is
  open (09:15-15:30 IST, trading days) — outside hours the API returns `400`
  unless `PAPER_ALLOW_OFF_HOURS=true` (used by tests/demos).
- **Order lifecycle:** rejected orders return HTTP `400` with a reason; working
  limit orders expire at the end of their calendar day; cancel via
  `DELETE /api/v1/paper/orders/{id}`; optional `stop`/`target` on entry orders
  auto-exit the position when the quote breaches them.
- **CSV export schema:** one row per order —
  `order_id,symbol,side,order_type,qty,fill_price,slippage,fees,status,tag`.

## Regulatory Notes

- SEBI requirements for investment advice vary by product classification
- Exchange data licensing applies to live feeds
- Broker API terms of service apply for any future live integration
- This tool provides research and education, not personalized investment advice

## License

MIT. Portions adapted from day-trader-skill (MIT, Jake Schincariol). See `LICENSE` and `THIRD_PARTY_NOTICES.md`.
