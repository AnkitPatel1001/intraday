"""Security tests: auth enforcement, rate limiting, headers, CORS parsing, 500 handler."""

import json
import urllib.error

import pytest
from httpx import AsyncClient, ASGITransport

from app.core.config import get_settings, _parse_origins
from app.core.ratelimit import limiter
from app.main import app

transport = ASGITransport(app=app)


class TestAuthEnforcement:
    async def test_401_without_token(self):
        s = get_settings()
        s.auth_enabled = True
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                r = await c.get("/api/v1/paper/portfolio")
                assert r.status_code == 401
                assert r.headers.get("WWW-Authenticate") == "Bearer"
                assert "session" in r.json()["detail"]
        finally:
            s.auth_enabled = False

    async def test_public_surface_exempt(self):
        s = get_settings()
        s.auth_enabled = True
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                assert (await c.get("/api/v1/market/status")).status_code == 200
                assert (await c.get("/api/v1/market/universe")).status_code == 200
                assert (await c.get("/api/v1/scanner/presets")).status_code == 200
                assert (await c.get("/health")).status_code == 200
        finally:
            s.auth_enabled = False

    async def test_session_flow_header_and_bearer(self):
        s = get_settings()
        s.auth_enabled = True
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                r = await c.post("/api/v1/auth/session")
                assert r.status_code == 200
                token = r.json()["token"]
                assert r.json()["expires_in"] > 0

                r2 = await c.get("/api/v1/paper/portfolio",
                                 headers={"X-Session-Token": token})
                assert r2.status_code == 200

                r3 = await c.get("/api/v1/paper/portfolio",
                                 headers={"Authorization": f"Bearer {token}"})
                assert r3.status_code == 200

                bad = await c.get("/api/v1/paper/portfolio",
                                  headers={"X-Session-Token": "not-a-token"})
                assert bad.status_code == 401

                out = await c.request("DELETE", "/api/v1/auth/session",
                                      headers={"X-Session-Token": token})
                assert out.status_code == 200
                after = await c.get("/api/v1/paper/portfolio",
                                    headers={"X-Session-Token": token})
                assert after.status_code == 401
        finally:
            s.auth_enabled = False

    async def test_portfolio_isolation_per_session(self):
        s = get_settings()
        s.auth_enabled = True
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                tok_a = (await c.post("/api/v1/auth/session")).json()["token"]
                tok_b = (await c.post("/api/v1/auth/session")).json()["token"]
                h_a = {"X-Session-Token": tok_a}
                h_b = {"X-Session-Token": tok_b}

                order = await c.post(
                    "/api/v1/paper/order",
                    json={"symbol": "RELIANCE", "side": "buy", "qty": 1},
                    headers=h_a,
                )
                assert order.status_code == 200

                pa = (await c.get("/api/v1/paper/portfolio", headers=h_a)).json()
                pb = (await c.get("/api/v1/paper/portfolio", headers=h_b)).json()
                assert len(pa["positions"]) == 1
                assert pb["positions"] == []
                assert pb["cash"] == pa["cash"] or pb["cash"] > 0
                assert len(pa["positions"]) != len(pb["positions"])
        finally:
            s.auth_enabled = False


class TestRateLimit:
    async def test_429_after_burst(self):
        s = get_settings()
        s.rate_limit_per_minute = 2
        limiter.reset()
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                assert (await c.get("/api/v1/paper/portfolio")).status_code == 200
                assert (await c.get("/api/v1/paper/portfolio")).status_code == 200
                r = await c.get("/api/v1/paper/portfolio")
                assert r.status_code == 429
                assert "Retry-After" in r.headers
                assert r.json()["detail"] == "rate limit exceeded"
        finally:
            s.rate_limit_per_minute = 0
            limiter.reset()

    async def test_market_read_bucket_5x(self):
        s = get_settings()
        s.rate_limit_per_minute = 1
        limiter.reset()
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                codes = [(await c.get("/api/v1/market/status")).status_code
                         for _ in range(6)]
                assert codes[:5] == [200] * 5
                assert codes[5] == 429
        finally:
            s.rate_limit_per_minute = 0
            limiter.reset()

    async def test_health_exemp(self):
        s = get_settings()
        s.rate_limit_per_minute = 1
        limiter.reset()
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                for _ in range(5):
                    assert (await c.get("/health")).status_code == 200
        finally:
            s.rate_limit_per_minute = 0
            limiter.reset()


class TestSecurityHeaders:
    async def test_api_headers(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/market/status")
            assert r.headers["X-Content-Type-Options"] == "nosniff"
            assert r.headers["X-Frame-Options"] == "DENY"
            assert r.headers["Referrer-Policy"] == "no-referrer"
            assert r.headers["Content-Security-Policy"] == "default-src 'none'"

    async def test_non_api_no_csp(self):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/health")
            assert r.headers["X-Content-Type-Options"] == "nosniff"
            assert "Content-Security-Policy" not in r.headers


class TestCORSConfig:
    def test_json_list(self):
        assert _parse_origins('["http://a", "http://b"]', ["x"]) == [
            "http://a", "http://b"
        ]

    def test_garbage_falls_back(self):
        assert _parse_origins("not json", ["http://default"]) == ["http://default"]
        assert _parse_origins('{"a":1}', ["http://default"]) == ["http://default"]
        assert _parse_origins("[1, 2]", ["http://default"]) == ["http://default"]
        assert _parse_origins("[]", ["http://default"]) == ["http://default"]

    async def test_cors_headers_present(self):
        async with AsyncClient(transport=transport, base_url="http://test",
                               headers={"Origin": "http://localhost:3000"}) as c:
            r = await c.get("/health")
        assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


class TestUnhandled500:
    async def test_500_is_json_without_traceback(self):
        @app.get("/api/v1/__boom")
        async def boom():
            raise RuntimeError("secret boom marker")

        try:
            t = ASGITransport(app=app, raise_app_exceptions=False)
            async with AsyncClient(transport=t, base_url="http://test") as c:
                r = await c.get("/api/v1/__boom")
                assert r.status_code == 500
                body = r.json()
                assert body["detail"] == "internal server error"
                assert "secret boom marker" not in r.text
                assert "Traceback" not in r.text
        finally:
            app.router.routes[:] = [
                rt for rt in app.router.routes
                if getattr(rt, "path", None) != "/api/v1/__boom"
            ]
