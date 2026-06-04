"""
OI Walls, Max Pain, and institutional positioning.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class OIWallResult:
    call_wall_strike: float | None
    put_wall_strike: float | None
    top_call_strikes: list[tuple[float, int]]     # (strike, oi)
    top_put_strikes: list[tuple[float, int]]
    strangle_flag: bool                           # True if symmetric OI buildup
    adjacent_oi_total: int


def detect_oi_walls(
    chain: pd.DataFrame, top_pct: float = 5.0
) -> OIWallResult:
    """
    Find strikes with the largest OI on each side.
    `top_pct` of strikes by OI = walls.
    """
    if chain.empty:
        return OIWallResult(None, None, [], [], False, 0)

    n = max(1, int(len(chain) * top_pct / 100.0))
    top_calls = chain.nlargest(n, "ce_oi")[["strike", "ce_oi"]]
    top_puts = chain.nlargest(n, "pe_oi")[["strike", "pe_oi"]]

    call_wall = float(top_calls.iloc[0]["strike"]) if not top_calls.empty else None
    put_wall = float(top_puts.iloc[0]["strike"]) if not top_puts.empty else None

    # Strangle flag: high OI on BOTH sides at adjacent strikes
    strangle = False
    adjacent_total = 0
    if not top_calls.empty and not top_puts.empty:
        call_strikes = set(top_calls["strike"].astype(int).tolist())
        put_strikes = set(top_puts["strike"].astype(int).tolist())
        overlap = call_strikes & put_strikes
        if len(overlap) >= max(1, n // 2):
            strangle = True
            adjacent_total = int(
                chain[chain["strike"].isin(overlap)]["ce_oi"].sum()
                + chain[chain["strike"].isin(overlap)]["pe_oi"].sum()
            )

    return OIWallResult(
        call_wall_strike=call_wall,
        put_wall_strike=put_wall,
        top_call_strikes=list(zip(top_calls["strike"], top_calls["ce_oi"])),
        top_put_strikes=list(zip(top_puts["strike"], top_puts["pe_oi"])),
        strangle_flag=strangle,
        adjacent_oi_total=adjacent_total,
    )


# -------------------------------------------------------------------------- #
# Max Pain
# -------------------------------------------------------------------------- #

def compute_max_pain(chain: pd.DataFrame) -> dict:
    """
    Max pain = strike that minimizes the combined intrinsic value
    of all outstanding options at expiration.
    """
    if chain.empty or "strike" not in chain.columns:
        return {"max_pain": None, "pain_by_strike": pd.DataFrame()}

    strikes = chain["strike"].values
    ce_oi = chain["ce_oi"].fillna(0).values
    pe_oi = chain["pe_oi"].fillna(0).values

    pain = []
    for K in strikes:
        call_payoff = np.maximum(0, strikes - K) * ce_oi
        put_payoff = np.maximum(0, K - strikes) * pe_oi
        pain.append((K, (call_payoff + put_payoff).sum()))

    pain_df = pd.DataFrame(pain, columns=["strike", "pain"])
    mp_strike = float(pain_df.loc[pain_df["pain"].idxmin(), "strike"])
    return {"max_pain": mp_strike, "pain_by_strike": pain_df}


def compute_max_pain_series(chains: list[pd.DataFrame]) -> pd.DataFrame:
    rows = []
    prev = None
    for ch in chains:
        if ch.empty:
            continue
        r = compute_max_pain(ch)
        mp = r["max_pain"]
        shift = (mp - prev) if prev is not None and mp is not None else 0.0
        rows.append(
            {
                "timestamp": ch["timestamp"].iloc[0],
                "max_pain": mp,
                "max_pain_shift": shift,
            }
        )
        prev = mp
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)


# -------------------------------------------------------------------------- #
# OI delta (intraday change)
# -------------------------------------------------------------------------- #

def compute_oi_change(
    chain_now: pd.DataFrame, chain_prev: pd.DataFrame
) -> pd.DataFrame:
    """Compute per-strike OI delta = current - previous."""
    if chain_now.empty or chain_prev.empty:
        return pd.DataFrame(columns=["strike", "ce_oi_change", "pe_oi_change", "ce_oi_pct", "pe_oi_pct"])

    merged = chain_now[["strike", "ce_oi", "pe_oi"]].merge(
        chain_prev[["strike", "ce_oi", "pe_oi"]],
        on="strike",
        suffixes=("_now", "_prev"),
        how="outer",
    ).fillna(0)
    merged["ce_oi_change"] = merged["ce_oi_now"] - merged["ce_oi_prev"]
    merged["pe_oi_change"] = merged["pe_oi_now"] - merged["pe_oi_prev"]
    merged["ce_oi_pct"] = np.where(
        merged["ce_oi_prev"] > 0,
        100.0 * merged["ce_oi_change"] / merged["ce_oi_prev"],
        0.0,
    )
    merged["pe_oi_pct"] = np.where(
        merged["pe_oi_prev"] > 0,
        100.0 * merged["pe_oi_change"] / merged["pe_oi_prev"],
        0.0,
    )
    return merged[["strike", "ce_oi_change", "pe_oi_change", "ce_oi_pct", "pe_oi_pct"]]
