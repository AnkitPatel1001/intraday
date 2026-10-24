# Remediation Report — Indian Stock Market Intelligence Platform

**Date:** 2026-10-24
**Scope:** Full remediation of all 34 findings from `AUDIT_REPORT.md` (3 Critical, 5 High,
10 Medium, 12 Low, 4 Info), plus README requirement gaps (REQ-01, REQ-02).
**Post-fix verification:** backend **275/275 tests, 91% line coverage** (was 203/85%),
frontend **tsc clean, 37/37 vitest tests, `next build` clean** (incl. `output: "standalone"`),
`npm audit` **0 critical / 0 high / 3 moderate** (was 1 critical + 1 high + 3 moderate),
live smoke against restarted server (auth on, rate limit on).

---

## 1. Finding-by-finding status

### Critical

| ID | Status | Fix |
|---|---|---|
| SEC-01 No authentication | **FIXED** | Session auth middleware in `app/main.py`: all `/api/v1/*` routes require token except `auth/*`, `market/*`, `scanner/presets`. Token via `X-Session-Token` or `Authorization: Bearer`; sessions issued by `POST /api/v1/auth/session` (`app/api/auth.py`), expiring (`SESSION_TIMEOUT_HOURS`), `AUTH_ENABLED` default **true**. Live smoke: no token → **401** (+`WWW-Authenticate`), session → **200**, bad token → **401**, logout → 401. Tests: `tests/test_security.py`. |
| SEC-02 Shared portfolio | **FIXED** | Per-token engines: `_engines: dict[str, PaperTradingEngine]` keyed by session token (`app/api/paper.py`, `get_engine(token)`/`drop_engine`); logout drops engine. Live smoke: token A buys → A has 1 position, B has 0. Tests: `test_portfolio_isolation_per_session`. |
| SEC-03 Event-loop DoS (56 s freeze) | **FIXED** | Monte Carlo runs via `asyncio.to_thread` behind `asyncio.Semaphore(2)` (`app/api/trades.py`); backtest also offloaded to thread. Regression evidence: **health probes 11–16 ms while `replays:1000000` computed for 55.8 s** (was: 30 s+ timeouts); TM returns 200. `replays` bounded `le=1_000_000` (422 above). |

### High

| ID | Status | Fix |
|---|---|---|
| SEC-04 Rate limit never enforced | **FIXED** | Sliding-window limiter (`app/core/ratelimit.py`) enforced in middleware: 429 + `Retry-After`, market reads get 5× bucket, health/docs exempt. Live: 61st request → **429**. Tests: 3 (burst, 5× bucket, exempt). README claim now true. |
| SEC-05 Scanner unbounded fan-out | **FIXED** | `POST /scanner/scan` rejects >100 symbols with **422**. Test: 101 → 422, 100 → 200. |
| SEC-06 Limit orders fill at any price | **FIXED** | Engine rewrite (`app/engine/paper.py`): limit orders **rest** (`working`) until market crosses the limit; fills happen only on crossing, at limit price, slippage 0; resting orders re-matched on subsequent quotes; only `market`/`limit` order types allowed. API returns `fill_price: null` + `status: working`. 8 engine tests + 5 API tests. R6 now PASS. |
| SEC-07 Negative capital accepted | **FIXED** | Pydantic bounds: plan/backtest `capital`/`risk_pct`/`target_r` (`gt=0`, ranges) → **422**; `reset?starting_cash<=0` → **400**; `/size`, `/costs` `gt=0` → 422. Tests: `tests/test_validation.py`. |
| DEP-01 Next.js critical advisories | **FIXED** | Upgraded `next` 14 → **16.4.3**, `react`/`react-dom` → **19.3.1**. `npm audit`: 0 critical, **0 high**, 3 moderate (tailwind 3 chain, see §3). |
| DEP-02 PostCSS high advisories | **FIXED** | Resolved via next 16.4.3 dependency tree — `npm audit` reports 0 high. |

### Medium

| ID | Status | Fix |
|---|---|---|
| SEC-08 Unhandled 500 on overflow | **FIXED** | Bounds reject `1e308`-class inputs (422) + global exception handler returns JSON `{"detail":"internal server error"}` with traceback only to logs. Test: `test_500_is_json_without_traceback`. Provider exception text no longer reflected in 502 messages. |
| SEC-09 No payload size limits | **FIXED** | Field bounds everywhere: `tag` ≤200 chars → 400, `qty` ≤1e6 → 400, all money fields `le=1e9/1e12`, scan list ≤100, replays ≤1e6. (Raw body-size cap at server level still uvicorn default — residual note §3.) |
| SEC-10 Security headers absent | **FIXED** | `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` on all responses; `Content-Security-Policy: default-src 'none'` on `/api/*`; HSTS on https. Tests: 2. |
| SEC-11 Fragile CORS parsing | **FIXED** | `_parse_origins` uses `json.loads` with fallback to safe default (`app/core/config.py`); `allow_credentials` disabled when origins contain `*`. CORS added last (outermost) so 401/429 carry CORS headers. Tests: parsing cases + allowed-origin header. |
| SEC-12 Open docs unauthenticated | **FIXED** | `/docs`, `/redoc`, `/openapi.json` disabled when `APP_ENV=production` (checked at app creation). Live: 200 in development (expected). |
| SEC-13 Dangerous defaults | **FIXED** | `APP_DEBUG` default **false**; `APP_SECRET_KEY` defaults to random `secrets.token_hex(32)` per process. Lifespan warns if debug on. |
| SEC-14 Market order client-price fallback | **FIXED** | Market orders require a live quote: quote failure → **502** (API), engine rejects market order without price (`rejected`). Limit orders accepted without quote (rest `working`). Tests: 3. |
| SEC-15 Zero frontend tests / no security tests | **FIXED** | 37 vitest tests (3 files: formatting, API client incl. 401→re-session retry, FreshnessBadge) + `npm test` script + CI job. Backend security regression suite added (`test_security.py`, `test_orders.py`, `test_validation.py`). |
| REQ-01 Circuit breakers unimplemented | **FIXED** | `GET /api/v1/market/circuit-bands?symbol=` returns prev close, ±10/15/20% bands, current band/status, freshness/source, reference-only note. Tests: 3. README updated to point at endpoint. |
| TST-01 Yahoo provider untested (26%) | **FIXED** | Contract tests with mocked HTTP (`tests/test_yahoo_contract.py`, 17 tests): 404→DataError, 429→RateLimitError, 5xx→fallback→DataError, 403, URLError, malformed/empty/null-row/invalid-OHLC parse paths, URL construction. yahoo.py coverage **26% → 83%**. |

### Low

| ID | Status | Fix |
|---|---|---|
| SEC-16 200-with-error responses | **FIXED** | `/costs`, `/size` bounded → 422 on invalid; `position_size` error → **400** (no more `{"error":...}` in a 200). |
| SEC-17 CSV export unauthenticated | **FIXED** | Analytics routes fall under auth middleware → 401 without token (CSV formula-injection already blocked by symbol regex — unchanged). |
| SEC-18 No `.gitignore` | **FIXED** | Root `.gitignore`: Python/Node artifacts, `.env` (with `!.env.example`), db files, editors. |
| SEC-19 Containers run as root | **FIXED** | Backend Dockerfile: `python:3.13-slim`, creates + runs as non-root `appuser`; frontend runner `USER node` + `output: "standalone"` now actually produced (verified `.next/standalone/server.js` exists after build). |
| SEC-20 TM date fallback | **FALSE POSITIVE** | Correction: synthetic provider genuinely **generates** data for arbitrary requested dates (the `1900-01-01` probe returned real synthetic bars, not stale sessions); in-range missing dates already raise `TimeMachineError` → **400** (`entry_day` check in `app/engine/timemachine.py`, pinned by tests). No code change required. |
| QA-01 24 dead functions | **CORRECTED + PARTIAL** | Original claim was wrong: audit's verification used `-SimpleMatch`, breaking the `\b` regex and false-flagging test-covered functions. True dead set = **9**, all removed: `ist_date_str`, `ist_from_utc_naive`, `utc_from_ist_naive`, `now_utc`, `session_times`, `trading_day_reason`, `is_demo` (config rewritten), `LimitsUpdate`, `validate_series`. The other 15 (`clock12/24/to_utc/bar_slot/.../get_batch_quotes`/BSE helpers/`update_unrealized`) are test-covered or provider-interface methods — **kept deliberately**. |
| QA-02 No Python lockfile; dev deps mixed | **PARTIAL** | Dead DB deps removed from `requirements.txt`; dev/prod still single file; no lockfile generated (would need `pip freeze` approval — see §3). |
| QA-03 BSE helpers dead vs README claim | **FIXED (docs)** | README banner now: "NSE equities (BSE via Yahoo `.BO` symbols)" — accurate: API surface is NSE; `.BO` passthrough exists in yahoo adapter. BSE helpers retained (unit-tested, harmless). |
| QA-04 Compose hardcoded dev + no healthcheck | **FIXED** | `docker-compose.yml`: obsolete `version:` removed, `APP_ENV`/`APP_DEBUG`/auth/limit parameterized with defaults, frontend `depends_on: condition: service_healthy` (backend image ships HEALTHCHECK), no DATABASE_URL. |
| QA-05 Phantom `.env.example` knobs | **FIXED** | Removed `DATA_FALLBACK_PROVIDER`, `KITE_*`, `DHAN_*`, `FYERS_*`, `TELEGRAM_*`, `SMTP_*`, `DATABASE_*`; added `AUTH_ENABLED`, `SESSION_TIMEOUT_HOURS`, real rate-limit knob; `APP_DEBUG=false` documented. |
| QA-06 Dead DB stack | **FIXED** | `app/db/` package deleted, `sqlalchemy`/`aiosqlite` dropped from requirements, compose/env DB entries gone. |
| QA-07 CI weak + version drift | **FIXED** | CI: Python **3.13**, Node **24**, coverage gate `--cov-fail-under=85`, `npm test`, **`npm audit --audit-level=high` gate**, tsc + build. (Execution requires the git init performed with this remediation.) |
| REQ-02 README stale | **FIXED** | Test counts (275 backend / 37 frontend), rate-limit claim now true + described, circuit-bands endpoint documented, auth section + token endpoint in API list, coverage gate noted, Next.js wording updated. |

### Info

| ID | Status | Fix |
|---|---|---|
| TST-02 Missing unit tests for fixed findings | **FIXED** | 72 new tests across `test_security.py`, `test_orders.py`, `test_validation.py`, `test_circuit_bands.py`, `test_yahoo_contract.py` — covering 429s, headers, CORS parsing, 500 handler, limit crossing, bounds, scan cap, circuit bands, yahoo contract. Residual: no explicit "disallowed Origin gets no ACAO" test; no concurrent reset/order race test. |
| PERF-01 `localhost`→2 s IPv6 fallback | **UNCHANGED (environment)** | Root cause is client-side IPv6/IPv4 resolution, not app code; documented in audit. Callers should use `127.0.0.1`. |
| ENV-01 0.0.0.0 bind without auth | **MITIGATED** | Auth now on by default → network exposure requires token; rate limit adds ceiling. Bind address remains configurable via `BACKEND_HOST`. |
| TOOL-01 Lint/SAST tools blocked | **PARTially improved** | Still blocked: pylint (astroid py3.13 crash), pip-audit/bandit/ruff not installed (installation requires approval). Compensating controls added: CI coverage gate + npm audit gate + 275-test suite. |

---

## 2. Acceptance evidence (post-fix, live server)

| Check | Result |
|---|---|
| `GET /api/v1/paper/portfolio` no token | **401** + `WWW-Authenticate: Bearer` |
| `POST /api/v1/auth/session` → token → portfolio | **200** |
| Invalid token | **401** |
| Isolation: A order → A/B portfolios | A: 1 position, B: 0 |
| Rate-limit burst (61 requests) | 61st → **429** + `Retry-After` |
| `costs entry=0` with token | **422** |
| Security headers on `/api/*` | nosniff / DENY / no-referrer / `default-src 'none'` present |
| `GET /circuit-bands?symbol=NIFTY50` | 200, prev close, 3 bands, status |
| Public surface (`market/*`, `scanner/presets`, `/health`) | 200 without token |
| TM `replays=1e6` (Friday date) | **200 in 55.8 s**; concurrent health probes **11–16 ms** throughout |
| Backend suite | **275 passed**, 91% line coverage |
| Frontend | tsc 0 errors, **37/37** tests, build clean (standalone emitted) |
| `npm audit` | 0 critical, 0 high, **3 moderate** (tailwind 3 chain) |

---

## 3. Residual risks / not done (explicit)

1. **3 moderate npm advisories** (tailwindcss@3/postcss-selector-parser chain): fix requires Tailwind **v4 major migration** — not attempted, breaking.
2. **Python CVE scan still blocked** (pip-audit/safety not installed — needs approval to install).
3. **Pylint unusable** on Python 3.13 (upstream astroid crash).
4. **No Python lockfile**; prod/dev requirements not split (single `requirements.txt`).
5. **Raw HTTP body-size cap** not set at uvicorn level (field-level bounds prevent persistence/abuse of large values; 5 MB body is read then rejected).
6. **No browser-level E2E** (Playwright not installed); no explicit CORS-rejection test; no concurrent reset/order race test.
7. **Yahoo live-network integration** untested (needs network authorization); mocked contract tests only.
8. **Docker compose build** not executed this session (would pull base images).
9. **Live multi-user load testing** not performed.

**Post-remediation release posture:** acceptable for networked demo/self-hosted use —
auth + isolation + rate limit + bounded compute in place. Prior "DO NOT RELEASE"
verdict for networked use is lifted subject to the residual items above.
