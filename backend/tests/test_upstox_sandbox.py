"""Sandbox-first mode (UPSTOX_SANDBOX, default true) — reported in health."""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.data.upstox import UpstoxProvider


@pytest.fixture
def restore_sandbox():
    s = get_settings()
    prev = s.upstox_sandbox
    yield
    s.upstox_sandbox = prev


def test_sandbox_default_true():
    assert get_settings().upstox_sandbox is True


async def test_health_reports_sandbox_mode(restore_sandbox):
    get_settings().upstox_sandbox = True
    h = await UpstoxProvider().health()
    assert h["mode"] == "sandbox"
    assert h["order_endpoints"] == "none (paper trading only)"


async def test_health_reports_live_mode_when_disabled(restore_sandbox):
    get_settings().upstox_sandbox = False
    h = await UpstoxProvider().health()
    assert h["mode"] == "live"


def test_sandbox_flag_reaches_provider(restore_sandbox):
    get_settings().upstox_sandbox = False
    assert UpstoxProvider().sandbox is False
    get_settings().upstox_sandbox = True
    assert UpstoxProvider().sandbox is True