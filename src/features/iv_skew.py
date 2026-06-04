"""
Implied Volatility Skew & Theta Acceleration.
Tracks IV trend (expanding vs crushing), skew, and theta second-derivative.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class IVSkewResult:
    iv_call_atm: float
    iv_put_atm: float
    iv_skew: float           # call_iv - put_iv  (negative for typical equity)
    iv_total: float          # average
    iv_trend_pct: float      # % change over window
    trend: str               # "expanding" | "crushing" | "flat"


def compute_iv_skew(chain: pd.DataFrame, spot: float) -> IVSkewResult:
    """
    Compute ATM IV skew from a single chain snapshot.
    `chain` must have columns: strike, ce_iv, pe_iv.
    """
    if chain.empty:
        return IVSkewResult(0, 0, 0, 0, 0, "flat")
    idx = _nearest_strike(chain, spot)
    row = chain.loc[idx]
    iv_c = float(row["ce_iv"])
    iv_p = float(row["pe_iv"])
    return IVSkewResult(
        iv_call_atm=iv_c,
        iv_put_atm=iv_p,
        iv_skew=iv_c - iv_p,
        iv_total=(iv_c + iv_p) / 2,
        iv_trend_pct=0.0,    # trend requires time series
        trend="flat",
    )


def compute_iv_skew_series(
    chains: list[pd.DataFrame], spot_series: list[float]
) -> pd.DataFrame:
    """Track IV skew over time + classify expansion/crush."""
    rows = []
    for ch, spot in zip(chains, spot_series):
        if ch.empty:
            continue
        r = compute_iv_skew(ch, spot)
        rows.append(
            {
                "timestamp": ch["timestamp"].iloc[0],
                "spot": spot,
                "iv_call_atm": r.iv_call_atm,
                "iv_put_atm": r.iv_put_atm,
                "iv_skew": r.iv_skew,
                "iv_total": r.iv_total,
            }
        )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)

    # % change over rolling window (default 15 min)
    df["iv_total_pct_change"] = df["iv_total"].pct_change(periods=15) * 100
    df["iv_skew_change"] = df["iv_skew"].diff()
    df["trend"] = df["iv_total_pct_change"].apply(_classify_trend)
    return df


def _classify_trend(pct: float | None) -> str:
    if pd.isna(pct):
        return "flat"
    if pct > 5.0:
        return "expanding"
    if pct < -5.0:
        return "crushing"
    return "flat"


def _nearest_strike(chain: pd.DataFrame, spot: float) -> int:
    """Return index of strike nearest to spot."""
    diffs = (chain["strike"] - spot).abs()
    return int(diffs.idxmin())


# -------------------------------------------------------------------------- #
# Theta acceleration: second derivative of option price over time
# -------------------------------------------------------------------------- #

def compute_theta_acceleration(
    option_premiums: pd.Series, timestamps: pd.Series, window: int = 10
) -> pd.Series:
    """
    Approximate d^2(price)/dt^2 (per minute) via second-order finite differences.
    Negative values = accelerating time decay (bad for long premium).
    """
    if len(option_premiums) < 3:
        return pd.Series(dtype=float)
    dt_min = timestamps.diff().dt.total_seconds() / 60.0
    first = option_premiums.diff() / dt_min
    accel = first.diff() / dt_min
    return accel.rolling(window, min_periods=2).mean()
