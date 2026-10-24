"""FastAPI application for Indian Stock Market Intelligence Platform."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, market, scanner, trades, backtest, paper, risk, analytics
from app.core.config import get_settings
from app.core.ratelimit import limiter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Paths exempt from session auth (public read surface)
_AUTH_EXEMPT_PREFIXES = ("/api/v1/auth/", "/api/v1/market/")
_AUTH_EXEMPT_EXACT = ("/api/v1/scanner/presets",)

# Paths exempt from rate limiting entirely
_RATE_EXEMPT_EXACT = ("/health", "/docs", "/redoc", "/openapi.json")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info(
        "Starting Market Intel API (env=%s, provider=%s, auth=%s, rate_limit=%d/min)",
        settings.app_env, settings.data_provider, settings.auth_enabled,
        settings.rate_limit_per_minute,
    )
    if settings.app_debug:
        logger.warning("APP_DEBUG=true — never run with debug enabled in production")
    yield
    logger.info("Shutting down")


def create_app() -> FastAPI:
    settings = get_settings()
    docs_on = not settings.is_production
    app = FastAPI(
        title="Indian Stock Market Intelligence Platform",
        description=(
            "Research, scanning, trade planning, paper trading, and backtesting "
            "for NSE equities. Paper trading by default. Not financial advice."
        ),
        version="1.1.0",
        lifespan=lifespan,
        docs_url="/docs" if docs_on else None,
        redoc_url="/redoc" if docs_on else None,
        openapi_url="/openapi.json" if docs_on else None,
    )

    # --- Security middleware: rate limit -> auth -> headers ---
    @app.middleware("http")
    async def security_middleware(request, call_next):
        settings = get_settings()
        path = request.url.path

        # 1. Rate limiting (market reads get a 5x bucket)
        if settings.rate_limit_per_minute > 0 and path not in _RATE_EXEMPT_EXACT:
            is_read = path.startswith("/api/v1/market/")
            limit = settings.rate_limit_per_minute * (5 if is_read else 1)
            key = f"{request.client.host if request.client else 'unknown'}|{'read' if is_read else 'write'}"
            allowed, retry_after = limiter.check(key, limit)
            if not allowed:
                return JSONResponse(
                    {"detail": "rate limit exceeded", "retry_after": retry_after},
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )

        # 2. Session auth for all API routes except public surface
        if (
            settings.auth_enabled
            and path.startswith("/api/v1/")
            and path not in _AUTH_EXEMPT_EXACT
            and not path.startswith(_AUTH_EXEMPT_PREFIXES)
        ):
            from app.api.auth import extract_token, validate_session

            token = extract_token(request)
            if not validate_session(token):
                return JSONResponse(
                    {
                        "detail": (
                            "unauthorized: missing or invalid session token "
                            "(POST /api/v1/auth/session)"
                        )
                    },
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
            request.state.session = token
        else:
            request.state.session = "anonymous"

        response = await call_next(request)

        # 3. Security headers
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if path.startswith("/api/"):
            response.headers.setdefault("Content-Security-Policy", "default-src 'none'")
        if request.url.scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

    # --- Unhandled exception handler: structured 500, traceback to logs only ---
    @app.exception_handler(Exception)
    async def unhandled_exception(request, exc):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            {"detail": "internal server error"}, status_code=500
        )

    # CORS registered last => outermost, so 401/429 bodies still get CORS headers
    allow_credentials = "*" not in settings.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins or ["http://localhost:3000"],
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(market.router, prefix="/api/v1/market", tags=["market"])
    app.include_router(scanner.router, prefix="/api/v1/scanner", tags=["scanner"])
    app.include_router(trades.router, prefix="/api/v1/trades", tags=["trades"])
    app.include_router(backtest.router, prefix="/api/v1/backtest", tags=["backtest"])
    app.include_router(paper.router, prefix="/api/v1/paper", tags=["paper"])
    app.include_router(risk.router, prefix="/api/v1/risk", tags=["risk"])
    app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["analytics"])

    @app.get("/health")
    async def health():
        return {"status": "ok", "provider": settings.data_provider, "paper": True}

    return app


app = create_app()
