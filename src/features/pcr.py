"""
Put/Call Ratio (PCR) computation and regime classification.
PCR = Σ PutVolume / Σ CallVolume (volume-based; OI-based also supported).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

PCRMode = Literal["volume", "oi"]


@dataclass
class PCRResult:
    pcr: float
    put_total: float
    call_total: float
    regime: str            # "bullish" | "neutral" | "bearish" | "extreme_bearish"
    slope: float | None    # PCR/min over recent window (None if not enough data)
    change_from_open: float | None


def compute_pcr(
    chain: pd.DataFrame, mode: PCRMode = "volume"
) -> PCRResult:
    """
    Compute PCR from a single option-chain snapshot.

    `chain` columns expected: ce_volume/ce_oi, pe_volume/pe_oi.
    """
    if mode == "volume":
        put_total = float(chain["pe_volume"].sum())
        call_total = float(chain["ce_volume"].sum())
    elif mode == "oi":
        put_total = float(chain["pe_oi"].sum())
        call_total = float(chain["ce_oi"].sum())
    else:
        raise ValueError(f"Unknown PCR mode: {mode}")

    pcr = put_total / call_total if call_total > 0 else 0.0
    return PCRResult(
        pcr=pcr,
        put_total=put_total,
        call_total=call_total,
        regime=_classify_regime(pcr),
        slope=None,
        change_from_open=None,
    )


def compute_pcr_series(
    chains: list[pd.DataFrame], mode: PCRMode = "volume"
) -> pd.DataFrame:
    """Compute PCR for a sequence of chain snapshots → time series."""
    rows = []
    for ch in chains:
        if ch.empty:
            continue
        r = compute_pcr(ch, mode)
        ts = ch["timestamp"].iloc[0] if "timestamp" in ch.columns else None
        rows.append(
            {
                "timestamp": ts,
                "pcr": r.pcr,
                "put_total": r.put_total,
                "call_total": r.call_total,
                "regime": r.regime,
            }
        )
    if not rows:
        return pd.DataFrame(columns=["timestamp", "pcr", "put_total", "call_total", "regime"])
    df = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
    # Derived: slope (per minute) + change from open
    if len(df) > 1:
        dt = df["timestamp"].diff().dt.total_seconds() / 60.0
        df["pcr_slope"] = df["pcr"].diff() / dt
        df["pcr_open"] = df["pcr"].iloc[0]
        df["pcr_change_from_open"] = df["pcr"] - df["pcr_open"]
    return df


def _classify_regime(pcr: float) -> str:
    if pcr < 0.7:
        return "bullish"
    if pcr < 1.1:
        return "neutral"
    if pcr < 1.4:
        return "bearish"
    return "extreme_bearish"


def merge_pcr_with_spot(pcr_df: pd.DataFrame, spot_df: pd.DataFrame) -> pd.DataFrame:
    """Left-join PCR series with spot price for visualization."""
    if pcr_df.empty or spot_df.empty:
        return pd.DataFrame()
    return pd.merge_asof(
        pcr_df.sort_values("timestamp"),
        spot_df[["timestamp", "spot"]].sort_values("timestamp"),
        on="timestamp",
        direction="nearest",
        tolerance=pd.Timedelta("2min"),
    )
