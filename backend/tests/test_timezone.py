"""Tests for timezone utilities."""

import datetime
import pytest
from app.core.timezone import (
    IST, parse_clock, clock12, clock24, to_ist, to_utc,
)


class TestParseClock:
    def test_24h(self):
        assert parse_clock("09:15") == 9 * 60 + 15
        assert parse_clock("15:20") == 15 * 60 + 20
        assert parse_clock("00:00") == 0

    def test_12h_pm(self):
        assert parse_clock("3:45 PM") == 15 * 60 + 45
        assert parse_clock("12:00 PM") == 12 * 60

    def test_12h_am(self):
        assert parse_clock("12:00 AM") == 0
        assert parse_clock("9:15 AM") == 9 * 60 + 15

    def test_bare_afternoon(self):
        # bare 1-8 defaults to PM
        assert parse_clock("3:45") == 15 * 60 + 45

    def test_invalid(self):
        with pytest.raises(ValueError):
            parse_clock("25:00")
        with pytest.raises(ValueError):
            parse_clock("abc")
        with pytest.raises(ValueError):
            parse_clock("")


class TestClockFormat:
    def test_clock12(self):
        assert clock12(555) == "9:15 AM"
        assert clock12(920) == "3:20 PM"

    def test_clock24(self):
        assert clock24(555) == "09:15"
        assert clock24(930) == "15:30"

    def test_roundtrip(self):
        for m in range(0, 1440, 5):
            assert parse_clock(clock24(m)) == m


class TestTimezone:
    def test_ist_offset(self):
        now = datetime.datetime.now(IST)
        assert now.utcoffset() == datetime.timedelta(hours=5, minutes=30)

    def test_to_ist(self):
        utc = datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)
        ist = to_ist(utc)
        assert ist.hour == 5 and ist.minute == 30

    def test_to_utc(self):
        ist = datetime.datetime(2026, 1, 1, 5, 30, tzinfo=IST)
        utc = to_utc(ist)
        assert utc.hour == 0 and utc.minute == 0
