"""
Signal state container.
Holds the latest computed features for downstream signal & execution modules.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd


@dataclass
class SignalState:
    """Snapshot of all features + decision at a single point in time."""

    timestamp: pd.Timestamp

    # --- market ---
    spot: float = 0.0
    spot_volume: float = 0.0
    volume_percent: float = 1.0

    # --- features ---
    pcr: float = 0.0
    pcr_slope: float = 0.0
    pcr_change_from_open: float = 0.0
    pcr_regime: str = "neutral"

    iv_call_atm: float = 0.0
    iv_put_atm: float = 0.0
    iv_skew: float = 0.0
    iv_total: float = 0.0
    iv_trend: str = "flat"
    iv_pct_change: float = 0.0

    net_gex: float = 0.0
    call_gex: float = 0.0
    put_gex: float = 0.0
    call_wall: float | None = None
    put_wall: float | None = None
    zero_gamma: float | None = None
    gex_regime: str = "neutral"

    max_pain: float | None = None
    max_pain_shift: float = 0.0

    spot_vwap: float = 0.0
    call_vwap: float = 0.0
    put_vwap: float = 0.0
    vwap_call_gap: float = 0.0
    vwap_put_gap: float = 0.0
    spot_range_bound: bool = False

    oi_strangle_flag: bool = False
    adjacent_oi_total: int = 0

    # --- sub-signals ---
    momentum_index: float = 0.0
    sub_vol_oi: str = "HOLD"           # Vol-OI Nexus
    sub_gamma: str = "HOLD"            # Gamma Hedging
    sub_leadlag: str = "HOLD"          # Premium-Spot Lead-Lag
    sub_no_trade: str = "HOLD"         # Trap signature

    # --- decision ---
    decision: str = "HOLD"             # GO | NO-GO | HOLD
    decision_reasons: list[str] = field(default_factory=list)
    confidence: float = 0.0            # 0..1
    suggested_strike: float | None = None
    suggested_side: str = "CE"          # CE | PE

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Convert Timestamp to string for JSON
        if isinstance(d.get("timestamp"), pd.Timestamp):
            d["timestamp"] = d["timestamp"].isoformat()
        return d


def empty_state() -> SignalState:
    return SignalState(timestamp=pd.Timestamp.now(tz="Asia/Kolkata"))
