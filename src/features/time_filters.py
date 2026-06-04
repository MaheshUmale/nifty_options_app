"""
Time-of-day segmentation & adaptive thresholds.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from utils.time_utils import get_time_block


@dataclass
class TimeContext:
    block: str
    threshold_multiplier: float
    is_expiry: bool
    minutes_to_close: float
    is_market_hours: bool

    def adjust_threshold(self, base: float) -> float:
        return base * self.threshold_multiplier


def get_time_context(ts: datetime | None = None, expiry_day: bool = False) -> TimeContext:
    from utils.time_utils import is_expiry_day, is_market_hours, now_ist

    ts = ts or now_ist()
    block = get_time_block(ts)
    is_exp = expiry_day or is_expiry_day(ts)
    market_open = is_market_hours(ts)

    # Multipliers (from SKILLS.md and config)
    multipliers = {
        "pre_market": 1.0,
        "morning_open": 1.0,
        "midday_lull": 1.4,    # need stronger signal
        "afternoon_run": 0.85,  # relax for expiry plays
        "post_market": 1.0,
        "between": 1.2,
    }
    if is_exp and block == "afternoon_run":
        multipliers["afternoon_run"] = 0.75  # even more relaxed on expiry day

    from datetime import datetime as dt, time as t
    if market_open:
        # minutes to 15:30 close
        close_today = ts.replace(hour=15, minute=30, second=0, microsecond=0)
        minutes_to_close = max((close_today - ts).total_seconds() / 60.0, 0.0)
    else:
        minutes_to_close = 0.0

    return TimeContext(
        block=block,
        threshold_multiplier=multipliers.get(block, 1.0),
        is_expiry=is_exp,
        minutes_to_close=minutes_to_close,
        is_market_hours=market_open,
    )
