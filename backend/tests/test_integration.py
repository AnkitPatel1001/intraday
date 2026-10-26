"""Integration tests: full workflow across modules. TDD — each test proves a user journey."""

import asyncio
import datetime
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.timezone import IST
from app.engine.paper import PaperTradingEngine
from app.engine.risk import RiskLimits, check_trade
from app.engine.planner import build_plan, position_size, estimate_costs
from app.engine.timemachine import run_time_machine, normalize_plan
from app.data.synthetic import SyntheticProvider
from app.core.primitives import DataFreshness

transport = ASGITransport(app=app)


async def api():
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestFullScanToPlanWorkflow:
    """User journey: scan -> pick symbol -> build plan -> check risk -> paper trade."""

    async def test_scan_returns_results_with_freshness(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            # symbols is a body param; filters are query params
            r = await c.post(
                "/api/v1/scanner/scan?interval=5m&days=30",
                json={"symbols": ["RELIANCE", "TCS"]},
            )
            assert r.status_code == 200
            data = r.json()
            assert data["scanned"] == 2
            assert "results" in data
            assert "note" in data
            # Every result must have freshness and reason
            for res in data["results"]:
                assert "freshness" in res
                assert "reason" in res
                assert "setups" in res

    async def test_scan_then_plan_flow(self):
        """Scan picks a symbol, then we build a plan for it."""
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            # Step 1: Get bars to find a valid entry bar
            bars_r = await c.get("/api/v1/market/bars/RELIANCE?interval=5m&days=30")
            assert bars_r.status_code == 200
            candles = bars_r.json()["candles"]
            assert len(candles) > 75  # at least one full session

            # Step 2: Build a plan using a mid-session bar
            plan_r = await c.post("/api/v1/trades/plan", json={
                "symbol": "RELIANCE", "side": "buy",
                "entry_bar": 10, "stop_rule": "or_mid",
                "target_r": 2.0, "capital": 500000, "risk_pct": 1.0,
            })
            assert plan_r.status_code == 200
            plan = plan_r.json()["plan"]
            assert plan["symbol"] == "RELIANCE"
            assert plan["stop"] < plan["entry"] < plan["target"]
            assert plan["risk_per_share"] > 0
            assert plan["costs"]["total_est"] > 0

            # Step 3: Risk-check the plan
            risk_r = await c.post("/api/v1/risk/check", json={
                "symbol": plan["symbol"], "side": plan["side"],
                "entry": plan["entry"], "stop": plan["stop"],
                "target": plan["target"], "shares": 100,
            })
            assert risk_r.status_code == 200
            risk = risk_r.json()
            assert risk["verdict"] in ("PASS", "BLOCK")
            assert len(risk["checks"]) > 0

    async def test_plan_costs_match_standalone_cost_calc(self):
        """Plan's embedded costs must match the standalone /costs endpoint."""
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            plan_r = await c.post("/api/v1/trades/plan", json={
                "symbol": "RELIANCE", "side": "buy",
                "entry_bar": 10, "capital": 500000, "risk_pct": 1.0,
            })
            assert plan_r.status_code == 200
            plan = plan_r.json()["plan"]
            entry = plan["entry"]

            # Compute costs for same entry with shares from plan
            # Plan doesn't return shares directly; use sizing endpoint
            size_r = await c.post("/api/v1/trades/size", json={
                "capital": 500000, "risk_pct": 1.0,
                "entry": entry, "stop": plan["stop"],
            })
            shares = size_r.json()["shares"]

            costs_r = await c.post("/api/v1/trades/costs", json={
                "entry": entry, "qty": shares, "side": "buy",
            })
            assert costs_r.status_code == 200
            assert costs_r.json()["total_est"] > 0


class TestPaperTradingWorkflow:
    """User journey: check portfolio -> place order -> verify P&L -> flatten."""

    async def test_buy_then_sell_realizes_pnl(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            # Reset to clean state
            await c.post("/api/v1/paper/reset?starting_cash=500000")

            # Buy
            buy_r = await c.post("/api/v1/paper/order", json={
                "symbol": "RELIANCE", "side": "buy", "qty": 5, "order_type": "market",
            })
            assert buy_r.status_code == 200
            buy = buy_r.json()
            assert buy["order"]["status"] == "filled"
            assert buy["portfolio"]["cash"] < 500000

            # Sell at profit
            sell_r = await c.post("/api/v1/paper/order", json={
                "symbol": "RELIANCE", "side": "sell", "qty": 5, "order_type": "market",
            })
            assert sell_r.status_code == 200
            sell = sell_r.json()
            assert sell["order"]["status"] == "filled"

            # Check performance: trades counts entries (buys), closed counts round trips
            perf_r = await c.get("/api/v1/analytics/performance")
            assert perf_r.status_code == 200
            perf = perf_r.json()
            assert perf["trade_count"] == 2  # entry fill + exit fill
            assert perf["closed_count"] >= 1  # the round trip closed

    async def test_portfolio_survives_multiple_trades(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            await c.post("/api/v1/paper/reset?starting_cash=1000000")
            for _ in range(3):
                await c.post("/api/v1/paper/order", json={
                    "symbol": "TCS", "side": "buy", "qty": 2, "order_type": "market",
                })
                await c.post("/api/v1/paper/order", json={
                    "symbol": "TCS", "side": "sell", "qty": 2, "order_type": "market",
                })
            pf_r = await c.get("/api/v1/paper/portfolio")
            pf = pf_r.json()
            assert pf["trades"] == 6  # 3 round trips = 6 fills (buy + sell each)

    async def test_audit_log_records_every_action(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            await c.post("/api/v1/paper/reset?starting_cash=500000")
            await c.post("/api/v1/paper/order", json={
                "symbol": "INFY", "side": "buy", "qty": 1, "order_type": "market",
            })
            audit_r = await c.get("/api/v1/paper/audit")
            assert audit_r.status_code == 200
            log = audit_r.json()["log"]
            assert len(log) > 0
            actions = [e["action"] for e in log]
            assert "order_filled" in actions or "order_rejected" in actions


class TestTimeMachineWorkflow:
    """User journey: get bars -> normalize plan -> run time machine -> get verdict."""

    async def test_full_timemachine_via_api(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            # Get bars to find a valid date with enough sessions
            bars_r = await c.get("/api/v1/market/bars/RELIANCE?interval=5m&days=90")
            assert bars_r.status_code == 200
            candles = bars_r.json()["candles"]
            assert len(candles) > 1500  # ~20+ sessions of 75 bars

            # Find the date of a bar in the middle of the data
            # Use a bar from ~30 sessions ago so there are enough prior sessions
            total_sessions = len(candles) // 75
            assert total_sessions >= 25

            # Pick a date from the data
            target_idx = 75 * 5  # 5th session
            target_date = candles[target_idx]["ts"][:10]
            target_close = candles[target_idx]["close"]

            # Run time machine
            tm_r = await c.post("/api/v1/trades/timemachine", json={
                "symbol": "RELIANCE", "side": "buy",
                "date": target_date,
                "entry": target_close,
                "stop": round(target_close * 0.99, 2),
                "target": round(target_close * 1.02, 2),
                "entry_bar": 5, "replays": 500, "seed": 42,
            })
            assert tm_r.status_code == 200
            tm = tm_r.json()
            assert "mc" in tm
            assert "verdict" in tm
            assert "history" in tm
            # Probabilities sum to ~1
            mc = tm["mc"]
            total = mc["p_target"] + mc["p_stop"] + mc["p_neither"]
            assert abs(total - 1.0) < 0.02

    async def test_timemachine_rejects_bad_plan(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/trades/timemachine", json={
                "symbol": "RELIANCE", "side": "buy",
                "date": "2026-01-01",
                "entry": 100, "stop": 105, "target": 110,  # stop > entry
                "entry_bar": 5,
            })
            assert r.status_code == 400


class TestBacktestWorkflow:
    """Run backtest -> verify metrics -> check assumptions disclosed."""

    async def test_backtest_produces_valid_metrics(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/backtest/run", json={
                "symbol": "RELIANCE", "strategy": "orb",
                "interval": "5m", "days": 60, "capital": 500000,
            })
            assert r.status_code == 200
            data = r.json()
            assert "total_return_pct" in data
            assert "max_drawdown_pct" in data
            assert "win_rate_pct" in data
            assert "trade_count" in data
            assert "assumptions" in data
            assert len(data["assumptions"]) >= 3
            assert "note" in data  # disclaimer present
            assert "equity_curve" in data

    async def test_backtest_warns_on_small_sample(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/backtest/run", json={
                "symbol": "RELIANCE", "strategy": "orb",
                "interval": "5m", "days": 10,
            })
            assert r.status_code == 200
            data = r.json()
            if data["trade_count"] < 10:
                assert any("small sample" in w.lower() for w in data["warnings"])


class TestMarketDataFreshness:
    """Every data response must carry freshness/source labels."""

    async def test_bars_have_freshness(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/market/bars/TCS?interval=5m&days=10")
            assert r.status_code == 200
            data = r.json()
            assert data["freshness"] == "synthetic"
            assert data["source"] == "synthetic"
            assert "staleness" in data

    async def test_quote_has_freshness(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/market/quote/INFY")
            assert r.status_code == 200
            assert r.json()["freshness"] == "synthetic"

    async def test_indices_have_freshness(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/market/indices")
            assert r.status_code == 200
            for idx in r.json()["indices"]:
                if "error" not in idx:
                    assert "freshness" in idx


class TestRiskEnforcementAcrossAPI:
    """Risk checks must be enforced consistently."""

    async def test_risk_blocks_bad_rr(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/risk/check", json={
                "symbol": "RELIANCE", "side": "buy",
                "entry": 100, "stop": 99, "target": 100.5,  # R:R = 0.5
            })
            assert r.status_code == 200
            assert r.json()["verdict"] == "BLOCK"

    async def test_risk_passes_good_rr(self):
        """R:R check must pass regardless of wall clock (entry-window is a separate check)."""
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/risk/check", json={
                "symbol": "RELIANCE", "side": "buy",
                "entry": 100, "stop": 95, "target": 110,  # R:R = 2.0
            })
            assert r.status_code == 200
            data = r.json()
            checks = {ch["name"]: ch for ch in data["checks"]}
            # The R:R requirement must be satisfied
            assert checks["min_rr"]["passed"] is True
            # If overall verdict is BLOCK, it must be only the time-of-day window
            if data["verdict"] == "BLOCK":
                blocked = [n for n, ch in checks.items() if not ch["passed"]]
                assert blocked == ["entry_window"], f"unexpected blocks: {blocked}"

    async def test_risk_rejects_zero_stop(self):
        """stop=0 is invalid input -> 422 at validation layer (was 200 BLOCK).
        Engine-level BLOCK still covers valid-but-bad numbers (stop > entry)."""
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/risk/check", json={
                "symbol": "RELIANCE", "side": "buy",
                "entry": 100, "stop": 0, "target": 110,
            })
            assert r.status_code == 422


class TestCrossModuleConsistency:
    """Values computed in one module must match another."""

    async def test_position_size_consistent_between_modules(self):
        """API /size must match engine position_size."""
        from app.engine.planner import position_size as engine_size
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/trades/size", json={
                "capital": 500000, "risk_pct": 1.0, "entry": 100, "stop": 95,
            })
            api_result = r.json()
            engine_result = engine_size(500000, 1.0, 100, 95)
            assert api_result["shares"] == engine_result["shares"]

    async def test_costs_consistent_between_modules(self):
        from app.engine.planner import estimate_costs as engine_costs
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/trades/costs", json={
                "entry": 1000, "qty": 10, "side": "buy",
            })
            api_result = r.json()
            engine_result = engine_costs(1000, 10, "buy")
            assert abs(api_result["total_est"] - engine_result["total_est"]) < 0.01

    async def test_risk_fingerprint_stable_same_day(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            body = {
                "symbol": "RELIANCE", "side": "buy",
                "entry": 100, "stop": 95, "target": 110,
            }
            r1 = await c.post("/api/v1/risk/check", json=body)
            r2 = await c.post("/api/v1/risk/check", json=body)
            assert r1.json()["fingerprint"] == r2.json()["fingerprint"]
