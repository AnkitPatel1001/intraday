"""Tests for NSE trading calendar."""

import datetime
import pytest
from app.core.calendar import (
    OPEN_MIN, CLOSE_MIN, SESSION_BARS, BAR_MIN,
    is_trading_day, bar_slot, slot_time, slot_close_time,
    session_status, next_trading_day, prev_trading_day,
    trading_days_between, is_muhurat, market_status_now,
    NSE_HOLIDAYS, OPEN, CLOSE,
)


class TestSessionConstants:
    def test_session_bars(self):
        assert SESSION_BARS == 75
        assert OPEN_MIN == 555  # 9:15
        assert CLOSE_MIN == 930  # 15:30
        assert BAR_MIN == 5
        assert (CLOSE_MIN - OPEN_MIN) // BAR_MIN == SESSION_BARS


class TestTradingDay:
    def test_weekday_is_trading(self):
        assert is_trading_day(datetime.date(2026, 10, 23))  # Friday

    def test_saturday_not(self):
        assert not is_trading_day(datetime.date(2026, 10, 24))

    def test_sunday_not(self):
        assert not is_trading_day(datetime.date(2026, 10, 25))

    def test_republic_day_holiday(self):
        assert not is_trading_day(datetime.date(2026, 1, 26))

    def test_christmas_holiday(self):
        assert not is_trading_day(datetime.date(2026, 12, 25))

    def test_holi_2026(self):
        assert not is_trading_day(datetime.date(2026, 3, 3))

    def test_holiday_table_has_entries(self):
        assert len(NSE_HOLIDAYS) > 20


class TestBarSlots:
    def test_first_bar(self):
        assert bar_slot(datetime.time(9, 15)) == 0

    def test_second_bar(self):
        assert bar_slot(datetime.time(9, 20)) == 1

    def test_last_bar(self):
        assert bar_slot(datetime.time(15, 25)) == 74

    def test_close_time_is_none(self):
        assert bar_slot(datetime.time(15, 30)) is None

    def test_before_open_is_none(self):
        assert bar_slot(datetime.time(9, 10)) is None

    def test_slot_time_roundtrip(self):
        for s in (0, 1, 37, 74):
            t = slot_time(s)
            assert bar_slot(t) == s

    def test_slot_close_time(self):
        assert slot_close_time(0) == datetime.time(9, 20)
        assert slot_close_time(74) == datetime.time(15, 30)


class TestSessionStatus:
    def test_before_open(self):
        d = datetime.date(2026, 10, 23)
        assert session_status(d, datetime.time(8, 0)) == "closed"

    def test_pre_open(self):
        d = datetime.date(2026, 10, 23)
        assert session_status(d, datetime.time(9, 0)) == "pre_open"

    def test_open(self):
        d = datetime.date(2026, 10, 23)
        assert session_status(d, datetime.time(10, 0)) == "open"

    def test_after_close(self):
        d = datetime.date(2026, 10, 23)
        assert session_status(d, datetime.time(16, 0)) == "post_close"

    def test_weekend_closed(self):
        d = datetime.date(2026, 10, 24)
        assert session_status(d, datetime.time(10, 0)) == "closed"


class TestNavigation:
    def test_next_trading_day(self):
        # Friday -> Monday
        fri = datetime.date(2026, 10, 23)
        assert next_trading_day(fri) == datetime.date(2026, 10, 26)

    def test_prev_trading_day(self):
        mon = datetime.date(2026, 10, 26)
        assert prev_trading_day(mon) == datetime.date(2026, 10, 23)

    def test_trading_days_between(self):
        # Mon 19 Oct - Fri 23 Oct 2026. 20 Oct is Diwali holiday.
        days = trading_days_between(datetime.date(2026, 10, 19), datetime.date(2026, 10, 23))
        assert len(days) == 4  # Mon, Wed, Thu, Fri (Tue 20 Oct = Diwali)

    def test_muhurat(self):
        assert is_muhurat(datetime.date(2026, 10, 20))


class TestMarketStatus:
    def test_returns_dict(self):
        s = market_status_now()
        assert "status" in s
        assert s["timezone"] == "Asia/Kolkata"
        assert s["session_open"] == "09:15"
        assert s["session_close"] == "15:30"
