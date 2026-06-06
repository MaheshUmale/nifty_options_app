"""
Composite Signal Engine.
Combines PCR, IV, GEX, OI, VWAP into:
  1) Momentum Index (continuous score)
  2) Sub-signals: Vol-OI Nexus, Gamma Hedging, Lead-Lag, No-Trade Trap
  3) Final GO/NO-GO via the Master Execution Matrix
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from features.gex import compute_gex
from features.iv_skew import compute_iv_skew
from features.oi_walls import (
    compute_max_pain,
    detect_oi_walls,
)
from features.pcr import compute_pcr
from features.time_filters import get_time_context
from features.vwap import compute_premium_vwaps
from signals.state import SignalState
from utils.logger import get_logger
from utils.time_utils import now_ist

log = get_logger()


@dataclass
class CompositeEngine:
    """
    Stateful engine that ingests chain + spot ticks and produces SignalState.
    Maintains a rolling history of features for slope/trend computations.
    """

    # History (capped to last N bars to bound memory)
    history_size: int = 240  # 4 hours @ 1min

    # Weights for momentum index (config-overridable)
    w_pcr_slope: float = 0.30
    w_vwap_gap: float = 0.40
    w_delta_flow: float = 0.30

    # Thresholds
    buy_threshold: float = 0.55
    sell_threshold: float = -0.55

    def __post_init__(self) -> None:
        self._spot_history: list[tuple[pd.Timestamp, float, float]] = []
        self._pcr_history: list[tuple[pd.Timestamp, float]] = []
        self._iv_history: list[tuple[pd.Timestamp, float]] = []
        self._premium_history: list[dict] = []
        self._max_pain_history: list[tuple[pd.Timestamp, float | None]] = []
        self._last_pcr_open: float | None = None

    # ------------------------------------------------------------------ tick
    def on_tick(
        self,
        chain: pd.DataFrame,
        spot: float,
        spot_volume: float = 0.0,
        timestamp: pd.Timestamp | None = None,
        prev_chain: pd.DataFrame | None = None,
        cfg: dict | None = None,
    ) -> SignalState:
        """
        Process one chain snapshot → SignalState.
        `prev_chain` (optional) is used to compute OI delta and to derive
        OI buildup flags.
        """
        if timestamp:
            ts = timestamp
        elif not chain.empty and "timestamp" in chain.columns:
            ts = chain["timestamp"].iloc[0]
        else:
            ts = pd.Timestamp.now(tz="Asia/Kolkata")
        ts = pd.Timestamp(ts)
        if ts.tzinfo is None:
            ts = ts.tz_localize("Asia/Kolkata")

        st = SignalState(timestamp=ts, spot=spot, spot_volume=spot_volume)

        if chain.empty:
            st.decision = "HOLD"
            st.decision_reasons.append("empty chain")
            return st

        # ---------- 1) PCR ----------
        try:
            pcr_res = compute_pcr(chain, mode="volume")
        except Exception as e:
            log.error(f"Error computing PCR: {e}")
            st.decision = "HOLD"
            st.decision_reasons.append(f"PCR error: {e}")
            return st
        st.pcr = pcr_res.pcr
        st.pcr_regime = pcr_res.regime

        self._pcr_history.append((ts, pcr_res.pcr))
        if len(self._pcr_history) > self.history_size:
            self._pcr_history = self._pcr_history[-self.history_size:]

        if self._last_pcr_open is None:
            self._last_pcr_open = pcr_res.pcr
        st.pcr_change_from_open = pcr_res.pcr - self._last_pcr_open

        # PCR slope over last 5 readings
        if len(self._pcr_history) >= 2:
            recent = self._pcr_history[-6:]  # 5 min window
            if len(recent) >= 2:
                t0, p0 = recent[0]
                t1, p1 = recent[-1]
                dt_min = (t1 - t0).total_seconds() / 60.0
                st.pcr_slope = (p1 - p0) / dt_min if dt_min > 0 else 0.0

        # ---------- 2) IV Skew ----------
        iv_res = compute_iv_skew(chain, spot)
        st.iv_call_atm = iv_res.iv_call_atm
        st.iv_put_atm = iv_res.iv_put_atm
        st.iv_skew = iv_res.iv_skew
        st.iv_total = iv_res.iv_total

        # Use historical chain to compute IV trend (last 15 readings)
        self._iv_history.append((ts, iv_res.iv_total))
        if len(self._iv_history) > self.history_size:
            self._iv_history = self._iv_history[-self.history_size:]

        if len(self._iv_history) >= 2:
            recent_iv = self._iv_history[-15:]
            t0, iv0 = recent_iv[0]
            t1, iv1 = recent_iv[-1]
            st.iv_pct_change = ((iv1 - iv0) / iv0) * 100.0 if iv0 > 0 else 0.0
            
            if st.iv_pct_change > 5.0:
                st.iv_trend = "expanding"
            elif st.iv_pct_change < -5.0:
                st.iv_trend = "crushing"
            else:
                st.iv_trend = "flat"
        else:
            st.iv_pct_change = 0.0
            st.iv_trend = "flat"

        # ---------- 3) GEX ----------
        lot_size = (cfg or {}).get("risk", {}).get("lot_size", 75)
        gex_res = compute_gex(chain, spot, lot_size=lot_size)
        st.net_gex = gex_res.net_gex
        st.call_gex = gex_res.call_gex
        st.put_gex = gex_res.put_gex
        st.call_wall = gex_res.call_wall_strike
        st.put_wall = gex_res.put_wall_strike
        st.zero_gamma = gex_res.zero_gamma_strike
        st.gex_regime = gex_res.regime

        # ---------- 4) Max Pain ----------
        mp = compute_max_pain(chain)
        st.max_pain = mp["max_pain"]
        self._max_pain_history.append((ts, mp["max_pain"]))
        if len(self._max_pain_history) > self.history_size:
            self._max_pain_history = self._max_pain_history[-self.history_size:]
        if len(self._max_pain_history) >= 2 and mp["max_pain"] is not None:
            prev_mp = self._max_pain_history[-2][1]
            if prev_mp is not None:
                st.max_pain_shift = mp["max_pain"] - prev_mp

        # ---------- 5) OI Walls + Strangle Flag ----------
        oi_res = detect_oi_walls(chain)
        st.oi_strangle_flag = oi_res.strangle_flag
        st.adjacent_oi_total = oi_res.adjacent_oi_total

        # ---------- 6) VWAP Divergence ----------
        # Build minimal spot history DataFrame for VWAP function
        self._spot_history.append((ts, spot, spot_volume))
        if len(self._spot_history) > self.history_size:
            self._spot_history = self._spot_history[-self.history_size:]

        # volumePercent calculation via volume / 20-period SMA volume (Rule 5)
        vols = [h[2] for h in self._spot_history[-20:]]
        if len(vols) >= 20:
            avg_vol = sum(vols) / 20.0
            st.volume_percent = spot_volume / avg_vol if avg_vol > 0 else 1.0
        else:
            st.volume_percent = 1.0

        if len(self._spot_history) >= 2:
            spot_df = pd.DataFrame(self._spot_history, columns=["timestamp", "spot", "volume"])
            vwap_res = compute_premium_vwaps(spot_df, chain, window_min=5)
            st.spot_vwap = vwap_res.spot_vwap
            st.call_vwap = vwap_res.call_vwap
            st.put_vwap = vwap_res.put_vwap
            st.vwap_call_gap = vwap_res.call_spot_gap
            st.vwap_put_gap = vwap_res.put_spot_gap
            st.spot_range_bound = vwap_res.spot_range_bound

            # Multi-Variable Concurrent Pressure Check: Roll NTM call/put average prices & volumes
            ntm_mask = (chain["strike"] >= spot * 0.98) & (chain["strike"] <= spot * 1.02)
            ntm = chain[ntm_mask]
            if ntm.empty:
                ntm = chain
            
            self._premium_history.append({
                "timestamp": ts,
                "c_price": vwap_res.call_vwap,
                "p_price": vwap_res.put_vwap,
                "c_vol": float(ntm["ce_volume"].sum() or 1),
                "p_vol": float(ntm["pe_volume"].sum() or 1),
            })
            if len(self._premium_history) > self.history_size:
                self._premium_history = self._premium_history[-self.history_size:]

            # Compute rolling option premium VWAP over time (last 5 readings)
            recent_prems = self._premium_history[-5:]
            sum_c_pv = sum(h["c_price"] * h["c_vol"] for h in recent_prems)
            sum_c_v = sum(h["c_vol"] for h in recent_prems)
            self.rolling_vwap_ce = sum_c_pv / sum_c_v if sum_c_v > 0 else vwap_res.call_vwap
            
            sum_p_pv = sum(h["p_price"] * h["p_vol"] for h in recent_prems)
            sum_p_v = sum(h["p_vol"] for h in recent_prems)
            self.rolling_vwap_pe = sum_p_pv / sum_p_v if sum_p_v > 0 else vwap_res.put_vwap

        # ---------- 7) Sub-signals ----------
        st.sub_vol_oi = self._signal_vol_oi(st)
        st.sub_gamma = self._signal_gamma_hedge(st)
        st.sub_leadlag = self._signal_lead_lag(st)
        st.sub_no_trade = self._signal_no_trade(st)

        # ---------- 8) Momentum Index ----------
        st.momentum_index = self._momentum_index(st)

        # ---------- 9) Master Execution Matrix ----------
        expiry: str | None = None
        if "expiry" in chain.columns and not chain.empty:
            expiry = chain["expiry"].iloc[0]

        decision, reasons, conf, strike, side, suggested_instrument = self._execution_matrix(
            st, cfg=cfg, expiry=expiry, chain_data=chain
        )
        st.decision = decision
        st.decision_reasons = reasons
        st.confidence = conf
        st.suggested_strike = strike
        st.suggested_side = side

        if suggested_instrument:
            st.suggested_trading_symbol = suggested_instrument.get("tradingsymbol")
            st.suggested_instrument_token = suggested_instrument.get("instrument_token")

        return st

    # ------------------------------------------------------------------ sub-signals
    def _signal_vol_oi(self, st: SignalState) -> str:
        """Volatility-OI Nexus (Bull Trap vs Breakout)."""
        if st.pcr > 1.1 and st.iv_trend == "crushing" and st.call_vwap > st.spot_vwap:
            return "NO_TRADE"  # IV-crush bull trap
        if (
            0.7 <= st.pcr <= 1.1
            and st.iv_trend == "expanding"
            and st.vwap_call_gap > 0
        ):
            return "BUY_CALLS"  # momentum breakout
        if st.pcr > 1.1 and st.iv_trend == "expanding" and st.put_vwap > st.call_vwap:
            return "BUY_CALLS"  # contrarian oversold reversal
        return "HOLD"

    def _signal_gamma_hedge(self, st: SignalState) -> str:
        """Market-maker gamma hedging trigger."""
        if st.zero_gamma is None or st.call_wall is None or st.put_wall is None:
            return "HOLD"
        if st.spot >= st.call_wall * 0.999 and st.gex_regime == "negative":
            return "BUY_CALLS"  # about to break call wall, dealers short gamma
        if st.spot <= st.put_wall * 1.001 and st.gex_regime == "negative":
            return "BUY_PUTS"
        return "HOLD"

    def _signal_lead_lag(self, st: SignalState) -> str:
        """Premium vs Spot Lead-Lag (institutional accumulation)."""
        if (
            st.spot_range_bound
            and st.vwap_call_gap > 0
            and st.pcr_slope > 0.01
            and st.iv_trend in ("expanding", "flat")
        ):
            return "BUY_CALLS"
        if (
            st.spot_range_bound
            and st.vwap_put_gap > 0
            and st.pcr_slope < -0.01
        ):
            return "BUY_PUTS"
        return "HOLD"

    def _signal_no_trade(self, st: SignalState) -> str:
        """Trap signature: strangle write, premium drain."""
        if st.oi_strangle_flag and abs(st.pcr - 1.0) < 0.05 and abs(st.max_pain_shift) < 1.0:
            return "NO_TRADE"
        return "HOLD"

    # ------------------------------------------------------------------ momentum
    def _momentum_index(self, st: SignalState) -> float:
        """Weighted composite momentum score in [-1, 1]."""
        # Normalize each component
        pcr_norm = float(np.tanh(st.pcr_slope * 5.0))    # slope amplification
        vwap_norm = float(np.tanh(st.vwap_call_gap * 50.0))
        # delta_flow: simple proxy from GEX sign (positive gex = dampener, negative = amplifier)
        gex_sign = -1.0 if st.net_gex < 0 else 1.0
        delta_norm = float(np.tanh(gex_sign * (abs(st.net_gex) / 1e9) * 5.0))

        score = (
            self.w_pcr_slope * pcr_norm
            + self.w_vwap_gap * vwap_norm
            + self.w_delta_flow * delta_norm
        )
        return float(np.clip(score, -1.0, 1.0))

    # ------------------------------------------------------------------ execution matrix
    def _execution_matrix(
        self,
        st: SignalState,
        cfg: dict | None = None,
        expiry: str | None = None,
        chain_data: pd.DataFrame | None = None,
    ) -> tuple[str, list[str], float, float | None, str, dict[str, Any] | None]:
        """
        Master Composite Execution Matrix.
        Returns: (decision, reasons, confidence, suggested_strike, suggested_side, suggested_instrument_record)
        """
        from typing import Any  # local import to keep top imports stable

        reasons: list[str] = []
        cfg = cfg or {}
        risk = cfg.get("risk", {})

        # ---------- 0) Time-of-day filter ----------
        tctx = get_time_context(st.timestamp.to_pydatetime() if hasattr(st.timestamp, "to_pydatetime") else None)
        if not tctx.is_market_hours:
            return "HOLD", [f"outside market hours ({tctx.block})"], 0.0, None, "CE", None

        # ---------- 1) No-Trade overrides everything ----------
        if st.sub_no_trade == "NO_TRADE":
            reasons.append("Trap signature: flat PCR + static Max Pain + strangle OI buildup")
            return "NO-GO", reasons, 0.9, None, "CE", None

        # ---------- 2) Matrix evaluation ----------
        go_score = 0
        no_go_score = 0
        go_reasons: list[str] = []
        no_reasons: list[str] = []

        # PCR regime contributions
        if st.pcr_regime == "extreme_bearish":
            if st.iv_trend == "expanding":
                go_score += 1
                go_reasons.append("PCR>1.4 + IV expanding = contrarian reversal")
            else:
                no_go_score += 1
                no_reasons.append("PCR>1.4 + IV flat = strangle-write trap")
        elif st.pcr_regime == "bearish":  # 1.1..1.4
            if st.iv_trend == "expanding":
                go_score += 1
                go_reasons.append("PCR 1.1-1.4 + IV expanding = contrarian buy")
            elif st.iv_trend == "crushing":
                no_go_score += 2  # bull trap
                no_reasons.append("PCR 1.1-1.4 + IV crushing = IV-crush bull trap")
        elif st.pcr_regime == "bullish":  # < 0.7
            if st.iv_trend == "crushing":
                no_go_score += 2
                no_reasons.append("PCR<0.7 + IV crushing = bear trap")
            else:
                go_score += 1
                go_reasons.append("PCR<0.7 = call-heavy regime")
        else:  # neutral
            if st.iv_trend == "expanding" and st.vwap_call_gap > 0:
                go_score += 2
                go_reasons.append("PCR neutral + IV expanding + call VWAP > spot VWAP = breakout")
            else:
                # neutral → require sub-signal boost
                pass

        # Gamma zone
        if st.gex_regime == "negative":
            go_score += 1
            go_reasons.append("Negative GEX = dealers short gamma (amplify moves)")
        elif st.gex_regime == "positive":
            # positive gamma = range-bound; only GO if OI walls align
            if st.call_wall and st.spot >= st.call_wall:
                go_score += 1
                go_reasons.append("Positive GEX + above call wall = breakout potential")

        # Sub-signals
        if st.sub_gamma == "BUY_CALLS":
            go_score += 2
            go_reasons.append("Gamma hedge trigger: call wall break imminent")
        if st.sub_gamma == "BUY_PUTS":
            go_score += 2
            go_reasons.append("Gamma hedge trigger: put wall break imminent")
        if st.sub_leadlag == "BUY_CALLS":
            go_score += 1
            go_reasons.append("Lead-lag: call premium leading spot")
        if st.sub_leadlag == "BUY_PUTS":
            go_score += 1
            go_reasons.append("Lead-lag: put premium leading spot")

        # Momentum index
        if st.momentum_index > self.buy_threshold:
            go_score += 2
            go_reasons.append(f"Momentum index {st.momentum_index:.2f} > buy threshold")
        elif st.momentum_index < self.sell_threshold:
            no_go_score += 1
            no_reasons.append(f"Momentum index {st.momentum_index:.2f} < sell threshold")

        # ---------- 3) Time-of-day adjustment ----------
        # Midday: require stronger score
        required_score = int(round(3 * tctx.threshold_multiplier))
        if tctx.is_expiry and tctx.block == "afternoon_run":
            required_score = max(2, required_score - 1)

        # ---------- 4) Decision ----------
        side = "CE"
        if "BUY_PUTS" in (st.sub_gamma, st.sub_leadlag):
            side = "PE"
        strike = self._suggest_strike(st, side)

        suggested_instrument: dict[str, Any] | None = None
        if strike is not None:
            # First, try to resolve instrument from the input chain_data mapping
            if chain_data is not None and not chain_data.empty:
                row = chain_data[chain_data["strike"] == strike]
                if not row.empty:
                    prefix = side.lower()
                    key = row[f"{prefix}_key"].iloc[0] if f"{prefix}_key" in row.columns else None
                    symbol = row[f"{prefix}_symbol"].iloc[0] if f"{prefix}_symbol" in row.columns else None
                    if key:
                        suggested_instrument = {
                            "instrument_key": key,
                            "tradingsymbol": symbol,
                            "instrument_token": key # V3 often uses key as token if not explicitly found
                        }

            # Fallback to Master Lookup if mapping failed and we have an expiry
            if suggested_instrument is None and expiry:
                try:
                    from data.upstox_client import resolve_option_instrument_master
                    # Underlying name: default to Nifty 50; can be improved later if chain carries underlying.
                    suggested_instrument = resolve_option_instrument_master(
                        underlying="Nifty 50",
                        expiry=expiry,
                        strike=float(strike),
                        option_type=side,
                    )
                except Exception:
                    suggested_instrument = None

        if go_score >= required_score and go_score > no_go_score:
            # Multi-Variable Concurrent Pressure Check (Rule 4)
            vwap_ce = getattr(self, "rolling_vwap_ce", 0.0)
            vwap_pe = getattr(self, "rolling_vwap_pe", 0.0)

            if side == "CE":
                # Calls: Price_CE > VWAP_CE and Price_PE < VWAP_PE
                pressure_ok = (st.call_vwap > vwap_ce) and (st.put_vwap < vwap_pe)
                if not pressure_ok:
                    reasons = [f"Blocked by Concurrent Pressure Check: Call price (LTP={st.call_vwap:.2f}) must exceed VWAP ({vwap_ce:.2f}) and Put price (LTP={st.put_vwap:.2f}) must be below VWAP ({vwap_pe:.2f}) concurrently."]
                    return "HOLD", reasons, 0.4, strike, side, suggested_instrument
            else:  # side == "PE"
                # Puts: Price_PE > VWAP_PE and Price_CE < VWAP_CE (symmetric logic)
                pressure_ok = (st.put_vwap > vwap_pe) and (st.call_vwap < vwap_ce)
                if not pressure_ok:
                    reasons = [f"Blocked by Concurrent Pressure Check (PE): Put price (LTP={st.put_vwap:.2f}) must exceed VWAP ({vwap_pe:.2f}) and Call price (LTP={st.call_vwap:.2f}) must be below VWAP ({vwap_ce:.2f}) concurrently."]
                    return "HOLD", reasons, 0.4, strike, side, suggested_instrument

            confidence = min(1.0, go_score / 6.0)
            return "GO", go_reasons, confidence, strike, side, suggested_instrument
        elif no_go_score >= required_score and no_go_score > go_score:
            confidence = min(1.0, no_go_score / 6.0)
            return "NO-GO", no_reasons, confidence, strike, side, suggested_instrument

        # Default: HOLD
        reasons.append(f"insufficient conviction: go={go_score} no_go={no_go_score} required={required_score}")
        return "HOLD", reasons, 0.3, strike, side, None

    def _suggest_strike(self, st: SignalState, side: str) -> float | None:
        """Pick a strike to trade. For CE: ATM or slightly OTM. For PE: same logic."""
        if not st.call_wall or not st.put_wall:
            return None
        # Choose the wall closer to spot on the relevant side
        if side == "CE":
            return float(st.call_wall)
        return float(st.put_wall)
