"""Indian market time utilities. IST is UTC+05:30 with no DST."""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
UTC = datetime.timezone.utc


def now_ist() -> datetime.datetime:
    return datetime.datetime.now(IST)


def to_ist(dt: datetime.datetime) -> datetime.datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(IST)


def to_utc(dt: datetime.datetime) -> datetime.datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=IST)
    return dt.astimezone(UTC)


def parse_clock(text: str, what: str = "time") -> int:
    """'09:15', '3:45 PM', '15:20', '01:00' -> minutes after midnight.
    A bare hour 1-8 without AM/PM is treated as PM (trader convention).
    An hour with a leading zero (e.g. '01:00') is treated as 24h."""
    import re
    m = re.match(r"^\s*(\d{1,2}):(\d{2})\s*(?:([AaPp])\.?\s*[Mm]\.?)?\s*$", str(text or ""))
    if not m:
        raise ValueError(f"{what} wants a time like 09:15 or 3:45 PM, not {text!r}")
    h_str = m.group(1)
    h, mi, ap = int(h_str), int(m.group(2)), (m.group(3) or "").lower()
    if mi > 59 or h > 23 or (ap and not 1 <= h <= 12):
        raise ValueError(f"{what} {text!r} is not a clock time")
    if ap == "p" and h != 12:
        h += 12
    elif ap == "a" and h == 12:
        h = 0
    elif not ap and 1 <= h <= 8 and len(h_str) == 1:
        h += 12
    return h * 60 + mi


def clock12(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def clock24(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def epoch_to_ist(ts: int | float) -> datetime.datetime:
    return (datetime.datetime(1970, 1, 1, tzinfo=UTC) + datetime.timedelta(seconds=int(ts))).astimezone(IST)

