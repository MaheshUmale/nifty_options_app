"""
Volume-Weighted Average Price (VWAP) for spot and option premium.
Used for the Lead-Lag signal (call premium VWAP vs spot VWAP).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def vwap(df: pd.DataFrame, price_col: str, volume_col: str) -> pd.Series:
    """Cumulative VWAP from price*volume / volume."""
    pv = df[price_col] * df[volume_col]
    cum_pv = pv.cumsum()
    cum_v = df[volume_col].cumsum().replace(0, np.nan)
    return (cum_pv / cum_v).ffill()


def rolling_vwap(df: pd.DataFrame, price_col: str, volume_col: str, window: int = 5) -> pd.Series:
    """Rolling N-bar VWAP."""
    pv = df[price_col] * df[volume_col]
    return pv.rolling(window, min_periods=1).sum() / df[volume_col].rolling(window, min_periods=1).sum()


@dataclass
class VWAPDivergenceResult:
    spot_vwap: float
    call_vwap: float      # NTM call premium VWAP
    put_vwap: float       # NTM put premium VWAP
    call_spot_gap: float  # (call_vwap - spot_vwap) / spot_vwap
    put_spot_gap: float
    spot_range_bound: bool  # recent spot range < threshold


def compute_premium_vwaps(
    spot_df: pd.DataFrame, chain_df: pd.DataFrame, window_min: int = 5
) -> VWAPDivergenceResult:
    """
    Compare NTM option premium VWAP vs spot VWAP.
    `spot_df` needs: timestamp, spot, volume.
    `chain_df` needs: strike, ce_ltp, pe_ltp, ce_volume, pe_volume, timestamp.
    """
    if spot_df.empty or chain_df.empty:
        return VWAPDivergenceResult(0, 0, 0, 0, 0, False)

    spot_window = spot_df.tail(window_min)
    s_vwap = float((spot_window["spot"] * spot_window["volume"]).sum()
                   / max(spot_window["volume"].sum(), 1))

    # NTM: strikes within 2% of spot
    spot_now = float(spot_df["spot"].iloc[-1])
    ntm_mask = (chain_df["strike"] >= spot_now * 0.98) & (chain_df["strike"] <= spot_now * 1.02)
    ntm = chain_df[ntm_mask]
    if ntm.empty:
        ntm = chain_df
    c_vwap = float((ntm["ce_ltp"] * ntm["ce_volume"]).sum() / max(ntm["ce_volume"].sum(), 1))
    p_vwap = float((ntm["pe_ltp"] * ntm["pe_volume"]).sum() / max(ntm["pe_volume"].sum(), 1))

    # Range bound: std/mean of recent spot < 0.2%
    rng_pct = float(spot_window["spot"].std() / max(spot_window["spot"].mean(), 1))
    range_bound = rng_pct < 0.002

    return VWAPDivergenceResult(
        spot_vwap=s_vwap,
        call_vwap=c_vwap,
        put_vwap=p_vwap,
        call_spot_gap=(c_vwap - s_vwap) / max(s_vwap, 1),
        put_spot_gap=(p_vwap - s_vwap) / max(s_vwap, 1),
        spot_range_bound=range_bound,
    )


def compute_vwap_series(spot_df: pd.DataFrame, window_min: int = 5) -> pd.DataFrame:
    """Time series of rolling spot VWAP for charting."""
    if spot_df.empty:
        return pd.DataFrame()
    df = spot_df.copy().sort_values("timestamp").reset_index(drop=True)
    df["vwap_5m"] = rolling_vwap(df, "spot", "volume", window=window_min)
    df["vwap_cum"] = vwap(df, "spot", "volume")
    return df
