"""Hardening-phase integration tests (TDD).

Each test pins an end-to-end contract discovered while validating the
post-remediation system. All run offline on synthetic data.
"""

import asyncio
import datetime

import pytest
from httpx import AsyncClient, ASGITransport

from app.core.config import get_settings
from app.core.ratelimit import limiter
from app.main import app

transport = ASGITransport(app=app)


def _auth_headers(token: str) -> dict:
    return {"X-Session-Token": token}


class TestAuthAwareFullJourney:
    """Session -> scan -> plan -> risk -> paper -> analytics -> export -> logout."""

    async def test_journey_with_auth_enabled(self):
        s = get_settings()
        s.auth_enabled = True
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                # 1. anonymous blocked
                assert (await c.get("/api/v1/paper/portfolio")).status_code == 401

                # 2. mint session
                tok = (await c.post("/api/v1/auth/session")).json()["token"]
                h = _auth_headers(tok)

                # 3. scan requires auth (only presets + market + auth are public)
                r = await c.post("/api/v1/scanner/scan",
                                 json={"symbols": ["RELIANCE"]}, headers=h)
                assert r.status_code == 200

                # 4. plan (auth)
                r = await c.post("/api/v1/trades/plan",
                                 json={"symbol": "RELIANCE"}, headers=h)
                assert r.status_code == 200
                plan = r.json()["plan"]
                assert plan["stop"] < plan["entry"] < plan["target"]

                # 5. risk check (auth)
                r = await c.post("/api/v1/risk/check", headers=h, json={
                    "symbol": "RELIANCE", "side": "buy",
                    "entry": plan["entry"], "stop": plan["stop"],
                    "target": plan["target"], "shares": 1,
                    "capital": 500000, "risk_per_trade_pct": 1,
                })
                assert r.status_code == 200

                # 6. paper order + portfolio (auth)
                r = await c.post("/api/v1/paper/order",
                                 json={"symbol": "RELIANCE", "side": "buy", "qty": 1},
                                 headers=h)
                assert r.status_code == 200
                pf = (await c.get("/api/v1/paper/portfolio", headers=h)).json()
                assert pf["label"].startswith("PAPER TRADING")

                # 7. analytics (auth)
                r = await c.get("/api/v1/analytics/performance", headers=h)
                assert r.status_code == 200
                perf = r.json()
                assert "win_rate_pct" in perf

                # 8. export (auth)
                r = await c.get("/api/v1/analytics/export", headers=h)
                assert r.status_code == 200
                assert r.headers["content-type"].startswith("text/csv")
                assert r.text.splitlines()[0] == (
                    "order_id,symbol,side,order_type,qty,fill_price,slippage,"
                    "fees,status,tag"
                )

                # 9. logout invalidates token + drops portfolio
                out = await c.request("DELETE", "/api/v1/auth/session", headers=h)
                assert out.status_code == 200
                assert (await c.get("/api/v1/paper/portfolio",
                                    headers=h)).status_code == 401

                # 10. fresh session starts flat again
                tok2 = (await c.post("/api/v1/auth/session")).json()["token"]
                pf2 = (await c.get("/api/v1/paper/portfolio",
                                   headers=_auth_headers(tok2))).json()
                assert pf2["positions"] == []
        finally:
            s.auth_enabled = False


class TestTimeMachineContracts:
    async def test_same_seed_reproducible(self):
        payload = {"symbol": "RELIANCE", "date": "2026-10-23",
                   "entry": 2500, "stop": 2450, "target": 2600,
                   "replays": 200, "seed": 42}
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r1 = (await c.post("/api/v1/trades/timemachine", json=payload)).json()
            r2 = (await c.post("/api/v1/trades/timemachine", json=payload)).json()
        assert r1["mc"] == r2["mc"]
        assert r1["verdict"] == r2["verdict"]

    async def test_weekend_date_400(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/trades/timemachine", json={
                "symbol": "RELIANCE", "date": "2026-10-24",  # Saturday
                "entry": 2500, "stop": 2450, "target": 2600, "replays": 10,
            })
            assert r.status_code == 400

    async def test_pros_sum_to_one(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/trades/timemachine", json={
                "symbol": "RELIANCE", "date": "2026-10-23",
                "entry": 2500, "stop": 2450, "target": 2600,
                "replays": 500, "seed": 7,
            })
        mc = r.json()["mc"]
        total = mc["p_target"] + mc["p_stop"] + mc["p_neither"]
        assert abs(total - 1.0) < 0.02


class TestPaperLifecycle:
    async def test_buy_sell_cash_consistency(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            start = 500000.0
            await c.post(f"/api/v1/paper/reset?starting_cash={start}")
            buy = await c.post("/api/v1/paper/order", json={
                "symbol": "RELIANCE", "side": "buy", "qty": 10,
            })
            assert buy.status_code == 200
            b = buy.json()["order"]
            assert b["status"] == "filled"

            sell = await c.post("/api/v1/paper/order", json={
                "symbol": "RELIANCE", "side": "sell", "qty": 10,
            })
            assert sell.status_code == 200
            s_ord = sell.json()["order"]
            assert s_ord["status"] == "filled"

            pf = (await c.get("/api/v1/paper/portfolio")).json()
            expected = start - b["fill_price"] * 10 - b["fees"] \
                + s_ord["fill_price"] * 10 - s_ord["fees"]
            assert abs(pf["cash"] - round(expected, 2)) < 0.02
            assert pf["positions"] == []
            assert pf["closed_count"] == 1

            perf = (await c.get("/api/v1/analytics/performance")).json()
            assert perf["closed_count"] == 1

    async def test_trade_count_counts_both_fills(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            await c.post("/api/v1/paper/reset")
            await c.post("/api/v1/paper/order",
                         json={"symbol": "RELIANCE", "side": "buy", "qty": 1})
            await c.post("/api/v1/paper/order",
                         json={"symbol": "RELIANCE", "side": "sell", "qty": 1})
            perf = (await c.get("/api/v1/analytics/performance")).json()
            assert perf["trade_count"] == 2

    async def test_working_limit_order_persists_across_reads(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            await c.post("/api/v1/paper/reset")
            r = await c.post("/api/v1/paper/order", json={
                "symbol": "RELIANCE", "side": "buy", "qty": 1,
                "order_type": "limit", "price": 50.0,  # far below any market
            })
            assert r.json()["order"]["status"] == "working"
            pf1 = (await c.get("/api/v1/paper/portfolio")).json()
            pf2 = (await c.get("/api/v1/paper/portfolio")).json()
            assert pf1["positions"] == pf2["positions"] == []
            orders = (await c.get("/api/v1/paper/orders")).json()["orders"]
            assert any(o["status"] == "working" for o in orders)

    async def test_flatten_roundtrip(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            await c.post("/api/v1/paper/reset")
            await c.post("/api/v1/paper/order",
                         json={"symbol": "TCS", "side": "buy", "qty": 2})
            r = await c.post("/api/v1/paper/flatten", json={"symbol": "TCS"})
            assert r.status_code == 200
            assert r.json()["flattened"] is True
            pf = (await c.get("/api/v1/paper/portfolio")).json()
            assert pf["positions"] == []


class TestCrossModuleConsistency:
    async def test_circuit_bands_match_daily_bars(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            bands = (await c.get(
                "/api/v1/market/circuit-bands?symbol=RELIANCE")).json()
            bars = (await c.get(
                "/api/v1/market/bars/RELIANCE?interval=1d&days=30")).json()
        closes = [b["close"] for b in bars["candles"]]
        assert len(closes) >= 2
        assert bands["prev_close"] == pytest.approx(closes[-2], abs=0.01)

    async def test_plan_costs_internally_consistent(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            plan = (await c.post("/api/v1/trades/plan", json={
                "symbol": "RELIANCE",
            })).json()["plan"]
        costs = plan["costs"]
        parts = (costs["brokerage"] + costs["stt"] + costs["exchange_charges"]
                 + costs["sebi_fees"] + costs["stamp_duty"] + costs["gst"]
                 + costs["slippage_est"])
        assert costs["total_est"] == pytest.approx(parts, abs=0.5)
        assert plan["risk_reward"] == pytest.approx(2.0, abs=0.01)

    async def test_backtest_contract_shape(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/backtest/run", json={
                "symbol": "RELIANCE", "days": 60,
            })
        assert r.status_code == 200
        data = r.json()
        for key in ("assumptions", "warnings", "total_return_pct",
                    "max_drawdown_pct", "sharpe", "win_rate_pct",
                    "profit_factor", "trade_count", "bars"):
            assert key in data
        assert any("No look-ahead" in a for a in data["assumptions"])


class TestConcurrentSessions:
    async def test_parallel_sessions_stay_isolated(self):
        s = get_settings()
        s.auth_enabled = True
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                toks = [(await c.post("/api/v1/auth/session")).json()["token"]
                        for _ in range(3)]
                syms = ["RELIANCE", "TCS", "INFY"]

                async def buy(tok, sym):
                    return await c.post(
                        "/api/v1/paper/order",
                        json={"symbol": sym, "side": "buy", "qty": 1},
                        headers=_auth_headers(tok),
                    )

                results = await asyncio.gather(
                    *(buy(t, s) for t, s in zip(toks, syms))
                )
                assert all(r.status_code == 200 for r in results)
                for tok, sym in zip(toks, syms):
                    pf = (await c.get("/api/v1/paper/portfolio",
                                      headers=_auth_headers(tok))).json()
                    assert [p["symbol"] for p in pf["positions"]] == [sym]
        finally:
            s.auth_enabled = False
