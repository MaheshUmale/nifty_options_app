"""
Time utilities for the NIFTY options system.
All timestamps are IST-aware.
"""
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pandas as pd

IST = ZoneInfo("Asia/Kolkata")
UTC = ZoneInfo("UTC")

# NSE F&O trading hours
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)


def now_ist() -> datetime:
    return datetime.now(IST)


def to_ist(ts: datetime | pd.Timestamp) -> pd.Timestamp:
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            return pd.Timestamp(ts).tz_localize(IST)
        return pd.Timestamp(ts).tz_convert(IST)
    return ts.tz_convert(IST) if ts.tzinfo is not None else ts.tz_localize(IST)


def is_market_hours(ts: datetime | None = None) -> bool:
    ts = ts or now_ist()
    if isinstance(ts, pd.Timestamp):
        ts = ts.to_pydatetime()
    t = ts.time()
    return MARKET_OPEN <= t <= MARKET_CLOSE


def get_time_block(ts: datetime | None = None) -> str:
    """
    Classify current time into:
      - "pre_market"   (before 09:15)
      - "morning_open" (09:15–10:15)
      - "midday_lull"  (11:30–13:30)
      - "afternoon_run"(14:00–15:30)
      - "between"      (10:15–11:30, 13:30–14:00)
      - "post_market"  (after 15:30)
    """
    ts = ts or now_ist()
    if isinstance(ts, pd.Timestamp):
        ts = ts.to_pydatetime()
    t = ts.time()
    if t < MARKET_OPEN:
        return "pre_market"
    if time(9, 15) <= t < time(10, 15):
        return "morning_open"
    if time(11, 30) <= t < time(13, 30):
        return "midday_lull"
    if time(14, 0) <= t <= MARKET_CLOSE:
        return "afternoon_run"
    if t > MARKET_CLOSE:
        return "post_market"
    return "between"


def is_expiry_day(ts: datetime | None = None) -> bool:
    """NIFTY weekly expiry = Thursday."""
    ts = ts or now_ist()
    return ts.weekday() == 3  # Mon=0, Thu=3


def next_expiry(ts: datetime | None = None) -> datetime:
    """Return next Thursday (or today if Thursday before close)."""
    ts = ts or now_ist()
    days_ahead = (3 - ts.weekday()) % 7
    if days_ahead == 0 and ts.time() >= MARKET_CLOSE:
        days_ahead = 7
    from datetime import timedelta
    return (ts + timedelta(days=days_ahead)).replace(hour=15, minute=30, second=0, microsecond=0)
