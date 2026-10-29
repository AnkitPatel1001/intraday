"""Tests for the time-machine-gated automatic buy/sell feature.

Covers the pure decision gate (app.engine.autotrade) and the end-to-end
POST /api/v1/trades/auto flow: plan derivation, risk gating, Monte Carlo
replay, and — only on a clear decision — an actual paper order placed
through the caller's own portfolio. Paper only; no network, no live broker.
"""

from __future__ import annotations

import datetime

import pytest
from httpx import AsyncClient, ASGITransport

import app.api.trades as trades_mod
from app.core.timezone import IST
from app.engine.autotrade import decide_auto_trade, EDGE_LEAN
from app.main import app

transport = ASGITransport(app=app)

# A fixed in-window IST timestamp so risk's entry_window check never blocks
# on real wall-clock time (see test_integration.py for the same pattern).
IN_WINDOW = datetime.datetime(2026, 10, 29, 11, 0, tzinfo=IST)


class TestDecideAutoTrade:
    """Pure decision gate — no network, no wall clock."""

    def test_zero_shares_skips(self):
        d = decide_auto_trade({"p_target": 0.6, "p_stop": 0.3, "r_at_target": 2.0},
                               risk_passed=True, shares=0)
        assert d["action"] == "skip"
        assert "position size" in d["reason"]

    def test_risk_blocked_skips(self):
        d = decide_auto_trade({"p_target": 0.6, "p_stop": 0.3, "r_at_target": 2.0},
                               risk_passed=False, shares=10)
        assert d["action"] == "skip"
        assert "risk check" in d["reason"]

    def test_missing_mc_skips(self):
        d = decide_auto_trade(None, risk_passed=True, shares=10)
        assert d["action"] == "skip"
        assert d["edge"] is None

    def test_no_side_hit_skips(self):
        d = decide_auto_trade({"p_target": 0.0, "p_stop": 0.0, "r_at_target": 2.0},
                               risk_passed=True, shares=10)
        assert d["action"] == "skip"
        assert "no replay reached" in d["reason"]

    def test_strong_edge_enters(self):
        # p_target 0.8 vs p_stop 0.2 at 2R: share=0.8, even=1/3 -> edge ~0.47
        d = decide_auto_trade({"p_target": 0.8, "p_stop": 0.2, "r_at_target": 2.0},
                               risk_passed=True, shares=10, min_edge=EDGE_LEAN)
        assert d["action"] == "enter"
        assert d["edge"] > EDGE_LEAN

    def test_weak_edge_skips(self):
        # p_target 0.34 vs p_stop 0.33 at 1R: coin flip, edge near 0
        d = decide_auto_trade({"p_target": 0.34, "p_stop": 0.33, "r_at_target": 1.0},
                               risk_passed=True, shares=10, min_edge=EDGE_LEAN)
        assert d["action"] == "skip"
        assert d["edge"] is not None
        assert abs(d["edge"]) < EDGE_LEAN

    def test_edge_favoring_stop_skips_even_at_zero_threshold(self):
        d = decide_auto_trade({"p_target": 0.2, "p_stop": 0.8, "r_at_target": 2.0},
                               risk_passed=True, shares=10, min_edge=0.0)
        assert d["action"] == "skip"
        assert d["edge"] < 0


@pytest.fixture(autouse=True)
def _fixed_entry_window(monkeypatch):
    monkeypatch.setattr(trades_mod, "now_ist", lambda: IN_WINDOW)


class TestAutoTradeEndpoint:
    """POST /api/v1/trades/auto — end to end, synthetic provider."""

    async def test_bad_symbol_400(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/trades/auto", json={"symbol": "<script>"})
            assert r.status_code == 400

    async def test_dry_run_never_places_order(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            await c.post("/api/v1/paper/reset?starting_cash=500000")
            r = await c.post("/api/v1/trades/auto", json={
                "symbol": "TCS", "side": "buy", "min_edge": 0.0, "execute": False,
            })
            assert r.status_code == 200
            data = r.json()
            assert data["order"] is None
            # Preview must not mutate the caller's portfolio.
            pf = await c.get("/api/v1/paper/portfolio")
            assert pf.json()["trades"] == 0

    async def test_enter_decision_places_paper_order(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            await c.post("/api/v1/paper/reset?starting_cash=500000")
            r = await c.post("/api/v1/trades/auto", json={
                "symbol": "TCS", "side": "buy", "min_edge": 0.0,
            })
            assert r.status_code == 200
            data = r.json()
            assert data["decision"]["action"] == "enter"
            assert data["order"] is not None
            assert data["order"]["status"] == "filled"
            assert data["order"]["qty"] > 0
            assert data["order"]["stop"] == data["plan"]["stop"]
            assert data["order"]["target"] == data["plan"]["target"]
            assert "auto:timemachine" in data["order"]["tag"]

            pf = await c.get("/api/v1/paper/portfolio")
            snap = pf.json()
            assert snap["trades"] == 1
            assert any(p["symbol"] == "TCS" for p in snap["positions"])

    async def test_strict_threshold_skips_without_order(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            await c.post("/api/v1/paper/reset?starting_cash=500000")
            r = await c.post("/api/v1/trades/auto", json={
                "symbol": "TCS", "side": "buy", "min_edge": 0.9,
            })
            assert r.status_code == 200
            data = r.json()
            assert data["decision"]["action"] == "skip"
            assert data["order"] is None

    async def test_sizing_respects_position_concentration_limit(self):
        """Risk-budget sizing with a tight stop_pct must not blow past the
        risk check's own max_position_pct — else the feature would always
        self-block on its own default parameters."""
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            await c.post("/api/v1/paper/reset?starting_cash=500000")
            r = await c.post("/api/v1/trades/auto", json={
                "symbol": "RELIANCE", "side": "buy", "min_edge": 0.0,
                "stop_pct": 0.5, "risk_pct": 1.0, "capital": 500000,
                "execute": False,
            })
            assert r.status_code == 200
            data = r.json()
            checks = {c_["name"]: c_ for c_ in data["risk"]["checks"]}
            assert checks["position_size"]["passed"] is True

    async def test_explicit_qty_overrides_sizing(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            await c.post("/api/v1/paper/reset?starting_cash=500000")
            r = await c.post("/api/v1/trades/auto", json={
                "symbol": "INFY", "side": "buy", "min_edge": 0.0, "qty": 3,
            })
            assert r.status_code == 200
            data = r.json()
            assert data["plan"]["shares"] == 3
            if data["decision"]["action"] == "enter":
                assert data["order"]["qty"] == 3

    async def test_risk_payload_includes_fingerprint(self):
        """The frontend's RiskResponse type declares fingerprint non-optional —
        the /auto handler must forward it like /risk/check does."""
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/trades/auto", json={
                "symbol": "TCS", "side": "buy", "min_edge": 0.0, "execute": False,
            })
            assert r.status_code == 200
            assert r.json()["risk"]["fingerprint"]

    async def test_response_is_paper_labeled(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/trades/auto", json={
                "symbol": "WIPRO", "side": "sell", "min_edge": 0.0, "execute": False,
            })
            assert r.status_code == 200
            data = r.json()
            assert "PAPER" in data["label"]
            assert data["side"] == "sell"
            # sell: stop above entry, target below
            assert data["plan"]["stop"] > data["plan"]["entry"] > data["plan"]["target"]
