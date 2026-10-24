# Comprehensive Audit Report — Indian Stock Market Intelligence Platform
**Date:** 2026-10-24
**Mode:** READ-ONLY audit. No code, tests, config, or dependency changes were made.
**Auditor role:** Senior QA / Test Automation / Software Architect / Application Security Engineer (authorized pentest, isolated local targets only).

---

## 1. Executive Summary

**Project health: FUNCTIONALLY STRONG, SECURITY-WEAK.**

- 203/203 automated tests pass (85% line / 82% branch coverage). Integration suite (19 tests) validates full workflows end-to-end at the API layer.
- TypeScript clean (`tsc` exit 0), Next build previously verified clean, all 9 frontend routes render HTTP 200.
- **3 Critical + 4 High security defects confirmed with reproducible evidence** — the dominant theme is *no authentication, no isolation between users, and unbounded synchronous compute*.
- **Core functional defect:** paper-trading limit orders fill at any price (₹1 buy, ₹999,999 sell both "fill") — undermines the product's central promise of realistic simulation.
- **1 requirement gap:** README claims "Circuit breakers: Index bands (10/15/20%) awareness" — no implementation exists anywhere.
- **Docs drift:** README claims "Rate limiting configurable" (no rate limiter exists) and "184 tests" (actual: 203).
- **Dependencies:** npm audit reports 1 critical + 1 high in production dependencies (Next.js advisories; PostCSS via Next). Python dependency scanning **BLOCKED** (pip-audit/safety not installed; installation requires approval).
- **Critical blockers:** not a git repository (no baseline commit/rollback); browser-level E2E not executed (no browser automation tool installed); Yahoo provider integration untested (requires network authorization).

**Top recommendations (order of priority):** (1) add authentication + per-session portfolio isolation, (2) move Monte Carlo to a worker/thread pool with hard time budget, (3) enforce rate limiting, (4) fix limit-order fill logic to compare against market price, (5) upgrade Next.js, (6) implement or remove the circuit-breaker requirement.

---

## 2. Project Inventory

### Technology stack
| Layer | Technology |
|---|---|
| Backend | Python 3.13.5, FastAPI 0.115.6, Uvicorn 0.34.0, Pydantic 2.10.4 |
| Frontend | Next.js 14 (App Router), React 18.3.1, TypeScript, Tailwind, lightweight-charts 4.2 |
| Data | SyntheticProvider (demo, default), YahooProvider (unofficial v8 chart API) |
| Database | **None in use** (sqlalchemy/aiosqlite pinned but never imported; `app/db/` empty) |
| Tests | pytest 8.3.4, pytest-asyncio, pytest-cov; 203 tests, all offline |
| CI | GitHub Actions (`.github/workflows/ci.yml`) — py3.12 tests + node20 tsc/build |
| Deploy | Docker (backend/frontend Dockerfiles + docker-compose), both run as root |
| Extras | 6 adapted Claude skills (`skills/`), MIT license + third-party notices |

### Architecture / modules
- `app/core/` — timezone (IST), NSE calendar (holidays 2025–27, Muhurat), symbol validation, config
- `app/data/` — provider ABC, synthetic, yahoo, factory
- `app/engine/` — indicators, scanner, planner (Indian costs), risk, paper, backtest, time machine
- `app/api/` — 7 routers, 29 routes; `app/main.py` — CORS, lifespan, /health
- `frontend/src/app/` — 9 pages (dashboard, scanner, research/[symbol], calculator, timemachine, paper, backtest, risk)
- No auth module, no session module, no database layer, no background jobs, no message queues, no scheduled tasks.

### Entry points (complete)
- 29 HTTP API routes under `/api/v1/*` + `/health` + `/docs` + `/redoc` + `/openapi.json`
- 9 frontend pages; `GET/POST` fetch wrapper `frontend/src/lib/api.ts` → `NEXT_PUBLIC_API_URL`
- External outbound: Yahoo hosts `query1/query2.finance.yahoo.com` (only when `DATA_PROVIDER=yahoo`)

### Environments
- Local dev (current): backend :8000 (`uvicorn`), frontend :3000 (`next dev`), `DATA_PROVIDER=demo`
- Docker compose (not executed this session), GitHub Actions (never run — no git repo)

---

## 3. Requirements Validation Matrix

Source: `README.md` (only requirements document present; no formal spec/user stories found).

| # | Requirement | Status | Coverage | Evidence | Gap |
|---|---|---|---|---|---|
| R1 | Dashboard: market status, indices, sectors, freshness labels | **PASS** | test_api (indices/status) | GET `/` 200; `/market/status`, `/indices` verified | — |
| R2 | Scanner: ORB, RSI, MA cross, volume spike, breakout + explanations | **PASS** | test_scanner (10) | POST `/scanner/scan` 200, results carry `reason` | Symbol list unbounded (H2) |
| R3 | Time Machine: Monte Carlo replay + historical rule replay | **PASS** | test_timemachine (28) | POST `/timemachine` 200, probs sum≈1 | DoS via replays (C3) |
| R4 | Trade planner: entry/stop/target, R:R, Indian costs (STT, GST, stamp…) | **PASS** | test_planner (10) | `/trades/plan` + `/costs` verified vs engine | Negative inputs accepted (H4, L1) |
| R5 | Risk engine: PASS/BLOCK vs daily loss, positions, R:R, entry window | **PASS** | test_risk (13), api/risk.py 100% cov | BLOCK on bad R:R + missing stop confirmed | — |
| R6 | Paper trading: simulated fills, slippage, fees, portfolio, audit log | **FAIL** | test_paper (16) | Limit buy @₹1 and sell @₹999999 both fill (H3) | Fill logic ignores market price |
| R7 | Backtesting: ORB, no look-ahead, realistic costs, equity curve | **PASS** | test coverage 90% | POST `/backtest/run` 200 + warnings + assumptions | No strategy-math cross-validation vs reference |
| R8 | Analytics: win rate, profit factor, P&L, CSV export | **PASS** | analytics.py 97% | `/analytics/performance` + `/export` 200 | Export unauthenticated (L2) |
| R9 | Session 09:15–15:30 IST, 75 bars, timezone, holidays, Muhurat | **PASS** | test_calendar (25), test_timezone (11) | `NSE_MUHURAT`, `is_muhurat` present | — |
| R10 | NSE symbol format, Yahoo `.NS` mapping | **PASS** | test_symbols (19) | Injection/traversal/homoglyph payloads all 400 | BSE code helpers dead (QA-03) |
| R11 | **Circuit breakers: index bands (10/15/20%) awareness** | **FAIL** | none | grep `circuit` in app+frontend → 0 hits | Requirement not implemented at all |
| R12 | Data providers: `demo` synthetic labeled / `yahoo` delayed | **PARTIAL** | yahoo.py **26% line cov** | demo verified; yahoo never exercised (needs network) | Integration BLOCKED (see §5) |
| R13 | Security: secrets via env only | **PASS** | grep secret-patterns → 0 hardcoded | `.env.example` placeholders only; no `.env` committed | — |
| R14 | Security: no API keys exposed to frontend | **PASS** | api.ts reads only `NEXT_PUBLIC_API_URL` | grep in frontend → no keys | — |
| R15 | Security: paper-only, no live broker connectivity | **PASS** | no broker client code exists | kite/dhan config fields unused | — |
| R16 | Security: "Rate limiting configurable" | **FAIL** | config value defined, never used | 65-request burst → 0×429 (H1) | Claim false |
| R17 | Security: "Input validation on all endpoints" | **PARTIAL** | — | bounds good on bars/plan/timemachine; `/costs`, `/size`, `starting_cash` accept negatives (L1, H4) | Gaps listed in findings |
| R18 | Tests: "184 tests, offline, no network" | **PARTIAL** | actual **203** pass offline | pytest run (§12) | README count stale |
| R19 | Docker: `docker compose up --build` works | **NOT TESTED** | — | Docker binary available; build not run this session | Needs approval/time |
| R20 | CI runs tests + typecheck + build | **NOT TESTED** | config reviewed only | No git repo → Actions never executed | BLOCKED |

**Requirement coverage: 13 PASS, 2 FAIL, 3 PARTIAL, 2 NOT TESTED.**

---

## 4. Unit Testing Report (TDD assessment)

**Execution:** `python -m pytest tests/ -q --cov=app --cov-branch` → **203 passed, 0 failed, 0 skipped, 0 xfail** (8.6 s).

| File | Tests | Asserts | Ratio |
|---|---|---|---|
| test_api.py | 24 | 53 | 2.2 |
| test_calendar.py | 25 | 33 | 1.3 |
| test_indicators.py | 19 | 34 | 1.8 |
| test_integration.py | 19 | 70 | 3.7 |
| test_paper.py | 16 | 23 | 1.4 |
| test_planner.py | 10 | 19 | 1.9 |
| test_risk.py | 13 | 17 | 1.3 |
| test_scanner.py | 10 | 13 | 1.3 |
| test_symbols.py | 19 | 27 | 1.4 |
| test_synthetic.py | 9 | 21 | 2.3 |
| test_timemachine.py | 28 | 44 | 1.6 |
| test_timezone.py | 11 | 16 | 1.5 |

**TDD quality assessment:**
- No skipped/xfail/flaky markers, no order-dependence (suite runs standalone + with coverage identically), no `assert True` placeholders, no swallowed exceptions in tests.
- Boundary tests exist and are meaningful (entry_bar 0/74, replays bounds, holiday/session edges, stop>entry rejection).
- **Tests that pass despite incorrect functionality (critical insight):**
  - Paper limit-order fills are tested *only for quantity/cash math*, never against market price → H3 slipped through green tests.
  - `starting_cash` reset accepts any float — no test asserts positivity → H4 green-but-wrong.
  - `/costs` negative inputs — untested → L1 green-but-wrong.
  - CORS/rate-limit/security headers — no tests at all → H1 green-but-claim-false.

**Missing test cases (recommendations only, not created):**
1. `reset(starting_cash<=0)` → expect 400.
2. `costs(entry<=0 or qty<=0)` → expect 400.
3. Limit order: buy limit price < market → expect not-filled (or fill at market); sell > market → same.
4. `scanner/scan` with N>max symbols → expect 422.
5. Concurrent `reset` + `order` → deterministic state (race guard).
6. Rate-limit middleware → 429 on 61st request.
7. CORS: disallowed `Origin` → no `access-control-allow-origin` (exists for evil origin today — pin it with a test).
8. Yahoo provider contract tests (mocked HTTP: 200/404/429/malformed JSON paths — yahoo.py has 80 uncovered lines).
9. Frontend: zero automated tests exist (no `test` script in package.json) — component/RTL tests recommended.

---

## 5. Integration Testing Report

**Executed (isolated, in-process ASGI — no live server side effects):** `tests/test_integration.py`, 19/19 PASS covering:
- Scan → plan → risk → paper flow (freshness on every response)
- Buy→sell round trip, P&L, audit log persistence, repeated trades
- Time Machine via API: probability normalization (sum ≈ 1), invalid-plan rejection (400)
- Backtest metrics + assumptions disclosure + small-sample warning
- Cross-module consistency: API `/size` ≡ engine `position_size`; `/costs` ≡ `estimate_costs`; risk fingerprint stable

**Integration failures found during this audit (pre-fix evidence retained):** scanner `symbols` body param returned 422 before the `Body(embed=True)` correction — caught by the integration suite (TDD worked).

**Untested integrations / blockers:**
| Integration | Status | Blocker |
|---|---|---|
| Yahoo Finance HTTP | **BLOCKED** | Real network calls to 3rd party need explicit authorization; no HTTP-mock layer installed (respx/responses not permitted to install) |
| Database (if ever used) | N/A | No DB code exists; `DATABASE_URL` is dead config |
| Zerodha/Dhan/Fyers brokers | N/A | Not implemented (by design) |
| Email/Telegram alerts | N/A | Not implemented (phantom `.env.example` entries) |
| Docker compose stack | **BLOCKED** | Build not authorized this session; would create images/volumes |
| GitHub Actions CI | **BLOCKED** | Not a git repository |
| Browser-level API-to-UI integration | **BLOCKED** | No Playwright/Cypress installed (installation = modification requiring approval) |

**Verified manually (live server, non-test-path):** all 29 routes respond; config/env loading (CORS origins, provider selection, defaults) verified by behavior.

---

## 6. End-to-End and Functional Testing Report

| Workflow | Expected | Actual | Result |
|---|---|---|---|
| Dashboard loads, shows status/indices/freshness | 200 + data | `/` 200 (9.8 KB); status/indices endpoints 200 with `synthetic` labels | **PASS** |
| Scanner page → scan → results with explanations | matches + reasons | API contract verified; UI route 200 | **PASS** (API-level) |
| Research page for valid symbol | chart + bars | `/research/RELIANCE` 200 (16 KB) | **PASS** |
| Research page malicious symbol `<script>…` | safe handling | 404 (Next router) — no reflection | **PASS** |
| Research page path traversal `../../etc/passwd` | safe handling | 200 shell page, no file served, symbol validated by API on data fetch | **PASS** |
| Time machine → plan → verdict | full chain | API chain verified in integration tests | **PASS** (API-level) |
| Paper: buy → portfolio updates → sell → analytics | state consistency | verified in integration tests; **but** limit-order pricing wrong (H3) | **FAIL** (H3) |
| Backtest → metrics → warnings | 200 + metrics + assumptions | verified | **PASS** |
| CSV export | downloadable CSV | 200 `text/csv`, formula chars blocked upstream by symbol regex | **PASS** (auth gap L2) |
| 404 page | graceful | `/nonexistent-page` → 404 | **PASS** |
| Form validation (negative qty, bad symbol) | 400s | verified (qty=-5→400, injection symbols→400) | **PASS** |
| Concurrent repeated submissions | stable state | 16 parallel resets all 200 (C2; no isolation, last-write-wins) | **FAIL** (C2) |
| Pagination/filter/sort | — | No pagination requirements exist; `/orders` returns last 50, `/audit` last 100 (bounded) | N/A (spec silent) |
| Session/auth workflows | — | **No auth exists** (C1) | NOT IMPLEMENTED |

Browser rendering, responsive layout, and cross-browser checks: **NOT TESTED** (no browser automation available).

---

## 7. Security Penetration Testing Report

### Scope & methodology
Black-box HTTP probing of local backend :8000 + frontend :3000 (isolated, authorized), plus source review of findings. Scripts: `pentest/probe1.py`, `pentest/probe2.py`; raw evidence in session logs. OWASP-aligned categories A01–A10. No destructive actions, no DoS beyond single bounded proof requests, no third-party systems.

### Confirmed vulnerabilities (reproducible evidence)

**CRITICAL**

**SEC-01 — No authentication on any endpoint** *(conf: confirmed)*
- Endpoint: all 29 routes. Evidence: `POST /api/v1/paper/reset?starting_cash=1` → `200` with zero credentials; `POST /paper/order`, `/paper/flatten` same.
- Vector (est. CVSS:3.1 `AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:H/A:H` = **9.1**; environmental caveat: current deployment is local demo).
- Impact: anonymous portfolio destruction, order injection, analytics poisoning. CWE-306.
- Repro: `curl -X POST http://localhost:8000/api/v1/paper/reset?starting_cash=1`

**SEC-02 — Global shared portfolio, no per-client isolation** *(conf: confirmed)*
- `backend/app/api/paper.py:16-24` — single `_engine` module global; 16 concurrent resets all `200`.
- All clients read/mutate one shared state; horizontal data breach between users + cross-user tampering. CWE-668. Est. vector `AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:H/A:N` = **8.2**.

**SEC-03 — Event-loop-blocking DoS: 1 request freezes server ~56 s** *(conf: confirmed)*
- `POST /api/v1/trades/timemachine` `replays:1000000` → server computes synchronously for 56.0 s (`app/api/trades.py:124` calls CPU-bound `run_time_machine` directly in async handler).
- Concurrent `GET /health`: timeout at 30 s, then 20.9 s, baseline 2.1 s → whole API unresponsive. `replays` capped at 1e6 (no time budget). CWE-400. Est. `AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` = **7.5**.

**HIGH**

**SEC-04 — Rate limit configured but never enforced** *(confirmed)*
- `config.py:69` `rate_limit_per_minute=60`; grep shows zero consumers. Burst: 65 requests/133 s → codes `{200}`, 0×429. README security claim false. CWE-770.

**SEC-05 — Scanner unbounded fan-out** *(confirmed)*
- 500-symbol body → still computing at 92 s (client timeout). No list-length cap (`app/api/scanner.py:35-53` serial provider calls). CWE-400.

**SEC-06 — Limit orders fill at any price (business-logic abuse)** *(confirmed)*
- `app/engine/paper.py:107-112`: fill base = client price; no market comparison.
- Evidence: limit buy @₹1 → `filled @1.0`; limit sell @₹999999 → `filled`, `realized_pnl: 998160.89`. Fabricated profit breaks analytics, risk reports, backtest-vs-paper comparison. CWE-682. (Also a functional defect — R6.)

**SEC-07 — Negative capital accepted** *(confirmed)*
- `reset?starting_cash=-1000` → 200 (`cash:-1000.0`); `/trades/plan` `capital:-1` → 200 full plan. No validation at API or engine boundary. CWE-20.

**MEDIUM**

**SEC-08 — Unhandled 500 on float overflow** *(confirmed)* — `/trades/plan` `{capital:1e308, risk_pct:99}` → raw `500 Internal Server Error`. CWE-754.
**SEC-09 — No payload size limits** *(confirmed)* — 5 MB `tag` accepted + persisted into orders/audit log. CWE-770.
**SEC-10 — All HTTP security headers absent** *(confirmed)* — no CSP, HSTS, X-Frame-Options, X-Content-Type-Options; `server: uvicorn` disclosed. CWE-693.
**SEC-11 — Fragile CORS parsing + credentialed wildcard grant** *(likely → confirmed by code)* — `config.py:59` string-replace parsing; `["*"]` env + `allow_credentials=True` + `allow_methods/headers:"*"` (`main.py:41-43`) = one misconfig from full CORS bypass. Current runtime behavior correct (evil origin gets no ACAO; preflight 400). CWE-942. Est. `AV:N/AC:H/PR:N/UI:R/S:U/C:L/I:H` ≈ 6.1 conditional.
**SEC-12 — OpenAPI/docs unauthenticated** *(confirmed)* — `/docs`, `/redoc`, `/openapi.json` → 200; full attack-surface enumeration. CWE-200.
**SEC-13 — Dangerous defaults** *(confirmed, latent)* — `APP_DEBUG` default `True`, `APP_SECRET_KEY` default `"change-me"` (`config.py:39-40`). Not currently wired to FastAPI debug (500 body = plain text, verified — **no traceback leak today**). CWE-1188.
**SEC-14 — Market order falls back to client price** *(confirmed by code)* — `paper.py:65-67`: quote failure → `req.price` becomes fill basis. CWE-20.
**SEC-15 — No frontend tests + zero security regression tests** *(gap)* — H1/SEC-10/SEC-11 have no automated pin; regressions would pass CI green.

**LOW**

**SEC-16 — Validation inconsistencies (200-with-error)** — `/costs` with `entry:-100,qty:-5` → 200 plausible numbers; `/size` `stop==entry` → 200 `{"error":…}`. CWE-754.
**SEC-17 — CSV export unauthenticated** — 200 CSV to anonymous caller (formula injection mitigated: symbol regex `^[A-Z][A-Z0-9&\-\.]{0,19}$` blocks `=`,`+`,`@`, leading `-` — verified `-RELIANCE` → 400). CWE-200.
**SEC-18 — No `.gitignore`** — no `.env` exists now; future secret-commit risk. CWE-538.
**SEC-19 — Containers run as root** — no `USER` in either Dockerfile. CWE-250.
**SEC-20 — Time Machine date fallback** — `date:1900-01-01` → 200, simulation silently uses last 64 sessions (disclosed in `note`, misleading if ignored).

### Suspected / conditional
- **SEC-21 (likely, unverified):** Next.js self-hosted advisories (see DEP-01) — exploitable paths (Image Optimizer `remotePatterns`, RSC deserialization, rewrite smuggling) depend on runtime config; app uses default config + `next start` only in Docker.
- **SEC-22 (potential, code review):** `BACKEND_HOST=0.0.0.0` exposes API to all interfaces without auth (amplifies SEC-01 on shared networks).

### False positives / verified-resistant
- SQL/NoSQL injection: **not applicable** (no user-driven queries; no SQL executed).
- Command injection: none (no subprocess/shell usage — grep clean).
- Path traversal: rejected upstream (`../../etc/passwd` → 400).
- XSS: React escaping holds; no `dangerouslySetInnerHTML`/`eval`/`innerHTML` in frontend; `<script>` route → 404.
- SSTI/unsafe deserialization: none (JSON + Pydantic only).
- SSRF: outbound host list hard-coded Yahoo; symbol sanitized before URL build (`urllib.parse.quote` + regex) — **likely safe, not exploited**.
- Homoglyph/null-byte/newline symbol evasion: all 400.
- Secrets in code/responses/bundles: none found (`.env` absent; OpenAPI body keyword-scan clean; `NEXT_PUBLIC_*` only carries URL/name/mode).
- Cookie/session issues: no cookies/tokens exist at all (absence = SEC-01).

### Testing limitations
- pip-audit/safety/bandit/ruff/mypy not installed → Python SAST/SCA **partially blocked** (not installable without approval).
- Pylint unusable on Python 3.13 (astroid `visit_typealias` crash) → static lint **blocked**.
- Browser automation absent → UI security testing limited to HTTP-level reflection checks.
- Yahoo/live endpoints not exercised (network authorization).
- CVSS scores are **estimates** (environmental scope = local demo); full temporal/environmental scoring not performed.

---

## 8. Code Quality and Dependency Report

### Static analysis
- **tsc --noEmit**: exit 0 (clean).
- **pylint**: BLOCKED (crashes on py3.13 — tool bug, not code). Partial run emitted no errors before crash; unreliable → not counted as pass.
- **ruff/bandit/mypy**: not installed (no-install rule respected → reported as blocker).
- **No lint config exists** in repo (no ruff/flake8/pylint config) → no enforced standards.

### Dead code (grep-verified: zero refs in app + tests) — QA-01
24 functions: `bar_slot, clock12, clock24, ist_date_str, ist_from_utc_naive, now_utc, to_utc, utc_from_ist_naive, next_trading_day, prev_trading_day, trading_days_between, session_times, slot_close_time, trading_day_reason` (core), `scan_universe, stochastic` (engine), `is_valid_bse_code, to_yahoo_bse` (BSE support unused), `get_batch_quotes` (3 implementations, 0 callers), `is_demo, is_production` (config), `update_unrealized, validate_series` (engine/data).
- Est. ~150–200 unreachable lines. Medium maintenance cost, zero runtime impact.

### Dependency risks
| ID | Severity | Package | Evidence | Notes |
|---|---|---|---|---|
| DEP-01 | **Critical** | `next` 9.3.4–16.3.0 | npm audit: GHSA-9g9p (Image Optimizer DoS), GHSA-h25m (RSC deser. DoS), GHSA-ggv3 (request smuggling via rewrites) | Prod dep; fix = next 16.4.3 (semver-major); exploitability in this app **unverified** (default config) |
| DEP-02 | **High** | `postcss` ≤8.5.22 (bundled under next) | GHSA-qx2v XSS in `</style>`, GHSA-6g55/fxqj/r28c arbitrary `.map` file read via `sourceMappingURL` | Prod; mostly build-time processing conditions |
| DEP-03 | Moderate ×3 | `postcss-selector-parser`, `tailwindcss`, `postcss-nested` | GHSA-rj75 CPU exhaustion; fixes need major upgrades | Mixed dev/prod |
| DEP-04 | **BLOCKED** | Python stack (fastapi 0.115.6, uvicorn 0.34.0, pydantic 2.10.4, httpx 0.28.1, python-multipart 0.0.20) | pip-audit/safety unavailable | Scanner limitation, assessment date 2026-10-24; **CVE status unknown** |
| DEP-05 | Low | `requirements.txt` mixes pytest\* dev deps into prod install | file content | Supply-chain surface inflation |

- npm audit date: 2026-10-24 (live registry query — counts verified: 1 critical, 1 high, 3 moderate).
- Lockfiles: `package-lock.json` present ✓; no Python lockfile (pip freeze/lock absent) → non-reproducible backend installs. **QA-02**

### Configuration weaknesses
- docker-compose hardcodes `APP_ENV=development` (SEC-13 amplifier) + obsolete `version:` key. **QA-04**
- `.env.example` advertises 6 non-existent knobs: `DATA_FALLBACK_PROVIDER`, `FYERS_*`, `KITE_ACCESS_TOKEN`, `TELEGRAM_*`, `SMTP_*` (zero code references). **QA-05**
- `DATABASE_URL`, `sqlalchemy`, `aiosqlite`, `DATABASE_ECHO` — dead (no DB layer). **QA-06**
- CI: no security scanning steps; py3.12/node20 vs local py3.13/node24 drift; never executed (no git). **QA-07**

### Error handling & logging
- `logging.basicConfig(INFO)` only; audit log exists for paper trades ✓; provider errors surfaced as `502 "data provider error: {e}"` — exception text reflected to client (minor info disclosure, folded into SEC-08 class).

---

## 9. Performance and Reliability Report

**Measured (not estimated):**

| Metric | Result |
|---|---|
| Backend `/health` via `http.client` → 127.0.0.1 | **14–40 ms** |
| Backend via urllib/PowerShell → `localhost` | ~2.05 s (constant) |
| Root cause of 2 s | **Client-side**: `localhost` resolves IPv6 `::1` first; server binds IPv4 `0.0.0.0` only → ~2 s fallback. NOT a server defect. (Evidence: `http.client`→127.0.0.1 fast; `urllib.getproxies()` = `{}`; `urllib localhost` = 2.113 s vs `127.0.0.1` = 0.039 s) |
| Frontend page TTFB | 0.04–1.38 s (first paint includes compile) |
| Time Machine 1e6 replays | **56.0 s CPU, blocks event loop** (SEC-03) |
| Scan 500 symbols | **>92 s** unbounded (SEC-05) |
| Test suite | 203 tests in 8.6 s |

**Bottlenecks:** (1) synchronous Monte Carlo in async handler; (2) serial per-symbol scan fan-out; (3) IPv4-only bind causing `localhost` latency for all local clients (informational; dual-stack bind or `127.0.0.1` in docs would remove).
**Failure handling:** provider failure → 502 with message ✓; Yahoo retry/429 backoff coded ✓ but untested (26% cov); no global exception handler (raw 500s, SEC-08).
**N+1 / DB:** no DB → not applicable.
**Unbounded retrieval:** `/market/bars` returns all candles for `days` (≤365 — bounded but ~160 KB/response measured); no pagination anywhere (bounded lists chosen instead — acceptable given spec).
**Tests not performed:** load/stress testing (outside authorization), Docker under load, memory-leak soak.

---

## 10. Master Findings Register (deduplicated, prioritized)

| ID | Sev | Title | Category | Status |
|---|---|---|---|---|
| SEC-01 | **Critical** | No authentication on any endpoint | A07 auth failure | Confirmed |
| SEC-02 | **Critical** | Global shared portfolio — no user isolation | A01 broken access | Confirmed |
| SEC-03 | **Critical** | Event-loop DoS — 1 request = 56 s freeze | A05 injection/DoS | Confirmed |
| SEC-04 | High | Rate limiter never implemented (README claim false) | A06 config | Confirmed |
| SEC-05 | High | Scanner unbounded symbol fan-out | A04 resource | Confirmed |
| SEC-06 | High | Limit orders fill at any price (R6 functional FAIL) | Business logic | Confirmed |
| SEC-07 | High | Negative capital accepted (plan + reset) | Input validation | Confirmed |
| DEP-01 | High | Next.js critical advisories (DoS/smuggling) | Supply chain | Scanner-confirmed, exploit unverified |
| DEP-02 | High | PostCSS high advisories (XSS/file read) | Supply chain | Scanner-confirmed, conditions unverified |
| SEC-08 | Medium | Unhandled 500 on float overflow | Robustness | Confirmed |
| SEC-09 | Medium | No payload size limits (5 MB accepted) | A04 resource | Confirmed |
| SEC-10 | Medium | Security headers all absent | A05 config | Confirmed |
| SEC-11 | Medium | CORS string-hack parsing + credentialed wildcard | A05 config | Code-confirmed, currently not exploitable |
| SEC-12 | Medium | /docs + openapi unauthenticated | A01 exposure | Confirmed |
| SEC-13 | Medium | APP_DEBUG=True + secret="change-me" defaults | Config | Confirmed (latent) |
| SEC-14 | Medium | Market order → client price fallback | Business logic | Code-confirmed |
| SEC-15 | Medium | Zero frontend tests; no security regression tests | Testing gap | Confirmed |
| REQ-01 | Medium | Circuit-breaker requirement (README) not implemented | Requirement | Confirmed |
| TST-01 | Medium | Yahoo provider untested (26% cov) — BLOCKED | Integration gap | Confirmed blocker |
| SEC-16 | Low | 200-with-error-body validation inconsistencies | Input validation | Confirmed |
| SEC-17 | Low | CSV export unauthenticated | Exposure | Confirmed |
| SEC-18 | Low | No `.gitignore` | Hygiene | Confirmed |
| SEC-19 | Low | Docker images run as root | Config | Confirmed |
| SEC-20 | Low | Time Machine silent date fallback | UX/data honesty | Confirmed |
| QA-01 | Low | 24 dead functions | Maintainability | Confirmed |
| QA-02 | Low | No Python lockfile; dev deps in prod requirements | Supply chain | Confirmed |
| QA-03 | Low | BSE helpers dead (BSE claimed in README banner) | Requirement | Confirmed |
| QA-04 | Low | Compose: APP_ENV=development hardcoded, obsolete `version` | Config | Confirmed |
| QA-05 | Low | .env.example: 6 phantom config knobs | Docs | Confirmed |
| QA-06 | Low | Dead DB stack (sqlalchemy/aiosqlite/DATABASE_URL) | Dead code | Confirmed |
| QA-07 | Low | CI: no security steps, version drift, never run (no git) | CI/CD | Confirmed |
| REQ-02 | Low | README stale ("184 tests"; rate-limit claim → see SEC-04) | Docs | Confirmed |
| TST-02 | Info | Missing unit tests for SEC-04/06/07/09/16 (listed §4) | Test gap | Confirmed |
| PERF-01 | Info | `localhost`→2 s IPv6 fallback (client/env, not app) | Environment | Confirmed root cause |
| ENV-01 | Info | 0.0.0.0 bind without auth on shared networks | Config | Confirmed |
| TOOL-01 | Info | Pylint/ruff/bandit/pip-audit unavailable or broken on py3.13 | Tooling | Blocker |

**Distribution: 3 Critical, 5 High, 10 Medium, 12 Low, 4 Info = 34 findings.**

---

## 11. Recommended Remediation Roadmap (recommendation-only)

### Immediate (before any deployment / multi-user use)
1. **SEC-01/SEC-02** — session-based auth + per-session paper engine (or API keys per client). Rationale: without these, all other integrity controls are moot.
   *Regression:* integration tests: unauthenticated write → 401; two sessions get independent portfolios.
2. **SEC-03** — run `run_time_machine` via `asyncio.to_thread` (or process pool) + lower `replays` cap + per-request time budget. Rationale: single-request full outage.
   *Regression:* concurrent health probe during max-replays request must stay < 1 s.
3. **SEC-06** — fill limit orders only when market crosses the limit price; never fill away from the market. Rationale: core product promise.
   *Regression:* buy-limit ₹1 with market ₹2700 → `working`, not `filled`.
4. **SEC-04** — implement rate-limit middleware consuming existing config. Rationale: README already promises it; enables DoS ceiling.
5. **DEP-01/DEP-02** — plan `next` upgrade (16.x, major) or mitigation review; re-run `npm audit`. Rationale: critical advisories on self-hosted prod path.

### Short-term
6. **SEC-07/SEC-16/SEC-09** — Pydantic bounds (`gt=0`) on capital/costs/qty/starting_cash/tag-length; global exception handler for structured 500s (SEC-08).
7. **SEC-05** — cap `symbols` list (e.g. ≤100) + concurrent fetch.
8. **SEC-10/SEC-11/SEC-12/SEC-13** — add security headers; replace string-hack CORS parsing with `json.loads` + deny `*` when credentials on; gate `/docs` behind non-prod; remove debug/secret defaults.
9. **REQ-01** — decide: implement index-band awareness or remove README claim (requirement owner decision).
10. **TST-01** — mocked-Yahoo contract tests (recommend installing `respx` with approval), covering 404/429/malformed paths.

### Longer-term
11. **QA-01/QA-06/QA-02** — remove dead code + dead DB deps; add Python lockfile; split dev/prod requirements.
12. **SEC-15/TST-02** — frontend test harness (RTL + Playwright smoke) + security regression suite.
13. **QA-07/SEC-18** — init git, add `.gitignore`, CI security steps (pip-audit, npm audit gate, bandit), align CI runtimes with local.
14. **SEC-19/QA-04** — non-root users in Dockerfiles, `APP_ENV` parameterization, compose healthchecks.
15. **SEC-14/SEC-20** — remove client-price fallback; warn loudly on out-of-range dates.

---

## 12. Test Execution Evidence

| # | Command / action | Result | When |
|---|---|---|---|
| 1 | `python -m pytest tests/ -v` (baseline) | 184 passed (prior session) | earlier |
| 2 | `python -m pytest tests/ -q --cov=app --cov-report=term` | 203 passed, 85% line cov | 2026-10-24 |
| 3 | `python -m pytest tests/ -q --cov=app --cov-branch` | 203 passed, 82% branch (73 missed branches) | 2026-10-24 |
| 4 | `npx tsc --noEmit --incremental false` | exit 0 | 2026-10-24 |
| 5 | `npm audit` / `npm audit --json` | 1 critical, 1 high, 3 moderate (live registry) | 2026-10-24 |
| 6 | `pylint app --enable=E,CRITICAL` | tool crash (astroid py3.13 bug) — BLOCKED | 2026-10-24 |
| 7 | `pentest/probe1.py` | findings C/H/M/L as §7 (pre-fix evidence) | 2026-10-24 |
| 8 | `pentest/probe2.py` | headers/rate-limit/500s/size evidence | 2026-10-24 |
| 9 | Frontend route smoke (11 URLs incl. XSS/traversal) | 9×200, XSS→404, traversal→200 shell, 404 page | 2026-10-24 |
| 10 | Latency matrix (`http.client` vs urllib vs PS) | 14–40 ms server; 2 s = client IPv6 fallback | 2026-10-24 |
| 11 | Dead-code AST scan + grep verification | 24 functions confirmed unreferenced | 2026-10-24 |
| 12 | Secrets grep (py/ts/yml/json/compose) | no hardcoded secrets; `.env` absent | 2026-10-24 |

**Tool versions:** Python 3.13.5, pytest 9.0.2, pytest-cov 7.1.0, Node v24.12.0, npm 11.6.2, Docker CLI present, Git present (repo not initialized).
**Environment assumptions:** local demo mode (`DATA_PROVIDER=demo`), no network dependencies in tests, servers on 0.0.0.0:8000/3000, Windows 11 host.
**Baseline preservation:** zero files modified during this audit; probes are read-only HTTP (only benign state changes on the *local demo* paper engine, restored to `starting_cash=500000`).

---

## 13. Final Verdict

| Question | Answer |
|---|---|
| Does the project meet supplied requirements? | **PARTIAL** — 13/20 PASS, 2 FAIL (circuit breakers unimplemented; rate-limit claim false), 3 PARTIAL, 2 NOT TESTED (Docker build, CI). |
| Do unit tests pass? | **YES — 203/203, 85% line / 82% branch.** Quality good; 9 missing test classes identified for known defects. |
| Do integration tests pass? | **YES — 19/19** at API/ASGI level. Yahoo, Docker, CI, browser integrations BLOCKED (documented). |
| Critical workflows validated? | API-level: YES. Browser-level: NO tooling (blocked). One workflow functionally broken: limit-order fills (SEC-06). |
| Significant security risks remain? | **YES — 3 Critical, 5 High.** Auth absence + shared state + event-loop DoS are release blockers for any networked/multi-user use. |
| Areas untested? | Yahoo live provider, browser UI flows, Docker stack, CI execution, Python CVE scan, load testing, SAST (tools blocked). |
| Release recommendation | **DO NOT RELEASE** for networked or multi-user use in current state. Acceptable only as single-user localhost demo (current actual deployment mode) **with** the caveat that SEC-06 corrupts paper results even locally. Security remediation per §11 items 1–5 required before any exposure beyond localhost. |

**No finding was closed, no code was changed, and no vulnerability was fixed during this audit, per instruction. Awaiting your approval to proceed to remediation.**
