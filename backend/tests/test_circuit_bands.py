"""Circuit-bands reference endpoint."""

from httpx import AsyncClient, ASGITransport

from app.main import app

transport = ASGITransport(app=app)


class TestCircuitBands:
    async def test_shape(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/market/circuit-bands?symbol=NIFTY50")
            assert r.status_code == 200
            data = r.json()
            for key in ("symbol", "prev_close", "last", "change_pct", "bands",
                        "current_band", "status", "note"):
                assert key in data
            assert data["symbol"] == "NIFTY50"
            assert data["prev_close"] > 0
            assert data["last"] > 0
            assert len(data["bands"]) == 3
            pcts = [b["pct"] for b in data["bands"]]
            assert pcts == [10, 15, 20]
            for b in data["bands"]:
                assert b["upper"] > b["lower"]
                expect_up = data["prev_close"] * (1 + b["pct"] / 100)
                expect_dn = data["prev_close"] * (1 - b["pct"] / 100)
                assert abs(b["upper"] - expect_up) < 1.0
                assert abs(b["lower"] - expect_dn) < 1.0
            assert data["status"] in ("normal", "band_10", "band_15", "band_20")
            assert "reference" in data["note"].lower() or "Reference" in data["note"]

    async def test_invalid_symbol_400(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/market/circuit-bands?symbol=NOT%20A%20SYMBOL!")
            assert r.status_code == 400

    async def test_freshness_reported(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/market/circuit-bands?symbol=RELIANCE")
            assert r.status_code == 200
            data = r.json()
            assert "freshness" in data
            assert "source" in data
            assert "as_of" in data
