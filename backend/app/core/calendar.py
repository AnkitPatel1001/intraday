"""NSE trading calendar: sessions, holidays, half-days (Muhurat).

Session: 09:15â€“15:30 IST regular. Pre-open 09:00â€“09:15 (not candle data).
No US-style early closes; Muhurat trading is a special Diwali evening session.
"""

from __future__ import annotations

import datetime

from app.core.timezone import IST

# NSE trading session boundaries (IST wall-clock)
PRE_OPEN = datetime.time(9, 0)
OPEN = datetime.time(9, 15)
CLOSE = datetime.time(15, 30)

# 5-minute bar grid: 09:15 to 15:30 = 75 bars (09:15-09:20 is bar 0)
BAR_MIN = 5
SESSION_BARS = 75  # (15:30 - 09:15) / 5 = 75
OPEN_MIN = 9 * 60 + 15   # 555
CLOSE_MIN = 15 * 60 + 30  # 930

# NSE trading holidays 2025-2027 (trading day holidays, no session at all).
# Source: NSE annual holiday list. Extend as new lists publish.
NSE_HOLIDAYS: dict[str, str] = {
    # 2025
    "2025-02-26": "Maha Shivaratri",
    "2025-03-14": "Holi",
    "2025-03-31": "Id-ul-Fitr",
    "2025-04-10": "Shri Mahavir Jayanti",
    "2025-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
    "2025-04-18": "Good Friday",
    "2025-05-01": "Maharashtra Day",
    "2025-06-06": "Bakri Id",
    "2025-08-15": "Independence Day",
    "2025-08-27": "Ganesh Chaturthi",
    "2025-10-02": "Mahatma Gandhi Jayanti",
    "2025-10-21": "Diwali Balipratipada (Laxmi Pujan)",
    "2025-10-22": "Diwali-Balipratipada",
    "2025-11-05": "Prakash Gurpurb Sri Guru Nanak Dev",
    "2025-12-25": "Christmas Day",
    # 2026
    "2026-01-01": "New Year",
    "2026-01-14": "Lohri / Makar Sankranti",
    "2026-01-26": "Republic Day",
    "2026-03-03": "Holi",
    "2026-03-20": "Id-ul-Fitr",
    "2026-04-03": "Shri Mahavir Jayanti",
    "2026-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
    "2026-04-03": "Good Friday",
    "2026-05-01": "Maharashtra Day",
    "2026-05-27": "Bakri Id",
    "2026-08-15": "Independence Day (Saturday)",
    "2026-08-25": "Ganesh Chaturthi",
    "2026-10-02": "Mahatma Gandhi Jayanti",
    "2026-10-20": "Diwali Balipratipada",
    "2026-11-10": "Prakash Gurpurb Sri Guru Nanak Dev",
    "2026-12-25": "Christmas Day",
    # 2027
    "2027-01-01": "New Year",
    "2027-01-13": "Lohri / Makar Sankranti",
    "2027-01-26": "Republic Day",
    "2027-03-01": "Holi",
    "2027-04-02": "Good Friday",
    "2027-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
    "2027-05-01": "Maharashtra Day",
    "2027-05-18": "Bakri Id",
    "2027-08-15": "Independence Day (Sunday)",
    "2027-09-13": "Ganesh Chaturthi",
    "2027-10-02": "Mahatma Gandhi Jayanti",
    "2027-11-01": "Diwali Balipratipada",
    "2027-11-29": "Prakash Gurpurb Sri Guru Nanak Dev",
    "2027-12-25": "Christmas Day (Saturday)",
}

# Muhurat trading (Diwali special session) â€” data exists but is a special session.
NSE_MUHURAT: dict[str, str] = {
    "2025-10-21": "Muhurat Trading",
    "2026-10-20": "Muhurat Trading",
    "2027-11-01": "Muhurat Trading",
}


def is_trading_day(d: datetime.date) -> bool:
    if d.weekday() >= 5:
        return False
    return d.isoformat() not in NSE_HOLIDAYS


def is_muhurat(d: datetime.date) -> bool:
    return d.isoformat() in NSE_MUHURAT


def session_status(d: datetime.date, t: datetime.time) -> str:
    """Return 'closed', 'pre_open', 'open', or 'post_close'."""
    if not is_trading_day(d):
        return "closed"
    if t < PRE_OPEN:
        return "closed"
    if t < OPEN:
        return "pre_open"
    if t < CLOSE:
        return "open"
    return "post_close"


def bar_slot(t: datetime.time) -> int | None:
    """IST time -> 5-minute bar slot 0..74, or None outside the session."""
    mins = t.hour * 60 + t.minute
    if mins < OPEN_MIN or mins >= CLOSE_MIN:
        return None
    return (mins - OPEN_MIN) // BAR_MIN


def slot_time(slot: int) -> datetime.time:
    """Bar slot 0..74 -> IST time of bar open."""
    mins = OPEN_MIN + slot * BAR_MIN
    return datetime.time(mins // 60, mins % 60)


def slot_close_time(slot: int) -> datetime.time:
    """Bar slot 0..74 -> IST time of bar close."""
    mins = OPEN_MIN + (slot + 1) * BAR_MIN
    return datetime.time(mins // 60, mins % 60)


def next_trading_day(d: datetime.date) -> datetime.date:
    d += datetime.timedelta(days=1)
    while not is_trading_day(d):
        d += datetime.timedelta(days=1)
    return d


def prev_trading_day(d: datetime.date) -> datetime.date:
    d -= datetime.timedelta(days=1)
    while not is_trading_day(d):
        d -= datetime.timedelta(days=1)
    return d


def trading_days_between(start: datetime.date, end: datetime.date) -> list[datetime.date]:
    days = []
    d = start
    while d <= end:
        if is_trading_day(d):
            days.append(d)
        d += datetime.timedelta(days=1)
    return days


def market_status_now() -> dict:
    from app.core.timezone import now_ist
    now = now_ist()
    d = now.date()
    t = now.time()
    status = session_status(d, t)
    return {
        "status": status,
        "date": d.isoformat(),
        "time": now.strftime("%H:%M:%S"),
        "timezone": "Asia/Kolkata",
        "session_open": OPEN.strftime("%H:%M"),
        "session_close": CLOSE.strftime("%H:%M"),
        "is_trading_day": is_trading_day(d),
        "holiday": NSE_HOLIDAYS.get(d.isoformat()),
        "muhurat": is_muhurat(d),
    }
