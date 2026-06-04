"""
Gamma Exposure (GEX).
Net dealer gamma in INR terms: Σ(gamma * OI * spot^2 * lot_size)
  - call_gamma * call_OI contributes positively (dealers long calls → long gamma)
  - put_gamma * put_OI contributes negatively  (dealers long puts → short gamma)
  - We invert the sign convention: GEX > 0 means market makers are NET LONG gamma
    (sell into rallies, dampen moves). GEX < 0 = short gamma (amplify moves).

This is the SpotGamma convention.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# Default contract multiplier (NIFTY lot size)
DEFAULT_LOT_SIZE = 75


@dataclass
class GEXResult:
    net_gex: float                 # signed
    call_gex: float
    put_gex: float
    zero_gamma_strike: float | None  # strike where cumulative gex crosses 0
    call_wall_strike: float | None
    put_wall_strike: float | None
    regime: str                    # "positive" | "negative" | "neutral"


def compute_gex(
    chain: pd.DataFrame,
    spot: float,
    lot_size: int = DEFAULT_LOT_SIZE,
) -> GEXResult:
    if chain.empty:
        return GEXResult(0, 0, 0, None, None, None, "neutral")

    # GEX per strike (in INR)
    chain = chain.copy()
    chain["ce_gex_strike"] = chain["ce_gamma"] * chain["ce_oi"] * (spot**2) * 0.01 * lot_size
    chain["pe_gex_strike"] = -chain["pe_gamma"] * chain["pe_oi"] * (spot**2) * 0.01 * lot_size
    # Note: put gamma itself is positive, but dealers who are SHORT puts are SHORT gamma
    # → we negate. (If customer is long put, dealer is short put = short gamma → negative)

    call_gex = float(chain["ce_gex_strike"].sum())
    put_gex = float(chain["pe_gex_strike"].sum())
    net_gex = call_gex + put_gex

    # Walls = strikes with largest |GEX| on each side
    call_wall = chain.loc[chain["ce_gex_strike"].idxmax(), "strike"] if call_gex != 0 else None
    put_wall = chain.loc[chain["pe_gex_strike"].idxmin(), "strike"] if put_gex != 0 else None

    # Zero-gamma strike: cumulative GEX from low to high, find sign change
    sorted_chain = chain.sort_values("strike")
    cum_gex = sorted_chain["ce_gex_strike"].fillna(0) + sorted_chain["pe_gex_strike"].fillna(0)
    cum_cum = cum_gex.cumsum()
    sign_change = cum_cum.diff().fillna(0).abs() > 0
    zero_strike = None
    if sign_change.any():
        idx = sign_change.idxmax()
        zero_strike = float(sorted_chain.loc[idx, "strike"])

    if net_gex > 0:
        regime = "positive"
    elif net_gex < 0:
        regime = "negative"
    else:
        regime = "neutral"

    return GEXResult(
        net_gex=net_gex,
        call_gex=call_gex,
        put_gex=put_gex,
        zero_gamma_strike=zero_strike,
        call_wall_strike=call_wall,
        put_wall_strike=put_wall,
        regime=regime,
    )


def compute_gex_series(
    chains: list[pd.DataFrame], spots: list[float], lot_size: int = DEFAULT_LOT_SIZE
) -> pd.DataFrame:
    """GEX over time — for plotting & flip detection."""
    rows = []
    for ch, s in zip(chains, spots):
        if ch.empty:
            continue
        r = compute_gex(ch, s, lot_size=lot_size)
        rows.append(
            {
                "timestamp": ch["timestamp"].iloc[0],
                "spot": s,
                "net_gex": r.net_gex,
                "call_gex": r.call_gex,
                "put_gex": r.put_gex,
                "call_wall": r.call_wall_strike,
                "put_wall": r.put_wall_strike,
                "zero_gamma": r.zero_gamma_strike,
                "regime": r.regime,
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)


def gex_per_strike(chain: pd.DataFrame, spot: float, lot_size: int = DEFAULT_LOT_SIZE) -> pd.DataFrame:
    """Per-strike GEX for bar/heatmap charts."""
    if chain.empty:
        return pd.DataFrame()
    chain = chain.copy()
    chain["call_gex"] = chain["ce_gamma"] * chain["ce_oi"] * (spot**2) * 0.01 * lot_size
    chain["put_gex"] = -chain["pe_gamma"] * chain["pe_oi"] * (spot**2) * 0.01 * lot_size
    chain["net_gex"] = chain["call_gex"] + chain["put_gex"]
    return chain[["strike", "call_gex", "put_gex", "net_gex"]]
