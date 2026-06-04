"""
Unit tests for feature modules.
Run: `pytest tests/test_features.py -v`
"""
import math

import numpy as np
import pandas as pd
import pytest

from data.mock_data import NiftyGenerator, bs_greeks, build_intraday_dataset
from features.gex import compute_gex, gex_per_strike
from features.iv_skew import compute_iv_skew, _nearest_strike
from features.oi_walls import compute_max_pain, detect_oi_walls
from features.pcr import compute_pcr, compute_pcr_series
from features.vwap import rolling_vwap, vwap, compute_premium_vwaps


# ------------------------------------------------------------------ mock data
@pytest.fixture
def sample_chain():
    """Minimal chain DataFrame for testing."""
    return pd.DataFrame(
        {
            "strike": [23900, 23950, 24000, 24050, 24100],
            "ce_ltp": [120, 80, 50, 25, 10],
            "pe_ltp": [10, 25, 50, 80, 120],
            "ce_volume": [1000, 1500, 2000, 1500, 1000],
            "pe_volume": [2000, 1500, 1000, 1500, 2000],
            "ce_oi": [50000, 70000, 100000, 70000, 50000],
            "pe_oi": [50000, 70000, 100000, 70000, 50000],
            "ce_iv": [0.15, 0.14, 0.13, 0.14, 0.15],
            "pe_iv": [0.17, 0.15, 0.14, 0.15, 0.17],
            "ce_delta": [0.7, 0.6, 0.5, 0.4, 0.3],
            "ce_gamma": [0.005, 0.008, 0.01, 0.008, 0.005],
            "ce_theta": [-2.0, -2.5, -3.0, -2.5, -2.0],
            "ce_vega": [1.0, 1.5, 2.0, 1.5, 1.0],
            "pe_delta": [-0.3, -0.4, -0.5, -0.6, -0.7],
            "pe_gamma": [0.005, 0.008, 0.01, 0.008, 0.005],
            "pe_theta": [-2.0, -2.5, -3.0, -2.5, -2.0],
            "pe_vega": [1.0, 1.5, 2.0, 1.5, 1.0],
            "timestamp": pd.Timestamp("2026-06-04 09:30", tz="Asia/Kolkata"),
        }
    )


# ------------------------------------------------------------------ PCR
def test_pcr_basic(sample_chain):
    res = compute_pcr(sample_chain, mode="volume")
    expected = (2000 + 1500 + 1000 + 1500 + 2000) / (1000 + 1500 + 2000 + 1500 + 1000)
    assert math.isclose(res.pcr, expected, rel_tol=1e-6)
    assert res.regime in ("bullish", "neutral", "bearish", "extreme_bearish")


def test_pcr_oi_mode(sample_chain):
    res = compute_pcr(sample_chain, mode="oi")
    # All OI equal → PCR = 1.0
    assert math.isclose(res.pcr, 1.0, rel_tol=1e-6)
    assert res.regime == "neutral"


def test_pcr_zero_call_volume():
    chain = pd.DataFrame(
        {
            "strike": [24000],
            "ce_volume": [0],
            "pe_volume": [1000],
            "ce_oi": [0],
            "pe_oi": [1000],
        }
    )
    res = compute_pcr(chain, mode="volume")
    assert res.pcr == 0.0


# ------------------------------------------------------------------ IV skew
def test_iv_skew_nearest():
    chain = pd.DataFrame(
        {
            "strike": [23900, 23950, 24000, 24050, 24100],
            "ce_iv": [0.15, 0.14, 0.13, 0.14, 0.15],
            "pe_iv": [0.17, 0.15, 0.14, 0.15, 0.17],
        }
    )
    idx = _nearest_strike(chain, 23998)
    assert chain.loc[idx, "strike"] == 24000


def test_iv_skew_result(sample_chain):
    res = compute_iv_skew(sample_chain, 23998)
    assert res.iv_call_atm == 0.13  # ATM strike
    assert res.iv_put_atm == 0.14
    assert math.isclose(res.iv_skew, -0.01, abs_tol=1e-9)


# ------------------------------------------------------------------ GEX
def test_gex_basic(sample_chain):
    # Asymmetric chain to break the symmetry in test
    chain = sample_chain.copy()
    chain["pe_oi"] = chain["pe_oi"] * 2  # double put OI
    res = compute_gex(chain, spot=24000, lot_size=75)
    assert res.net_gex != 0  # has positions
    assert res.call_gex > 0 or res.put_gex != 0


def test_gex_zero_when_empty():
    empty = pd.DataFrame(columns=["strike", "ce_gamma", "ce_oi", "pe_gamma", "pe_oi"])
    res = compute_gex(empty, 24000, lot_size=75)
    assert res.net_gex == 0
    assert res.regime == "neutral"


def test_gex_per_strike_returns_columns(sample_chain):
    df = gex_per_strike(sample_chain, 24000, 75)
    assert "call_gex" in df.columns
    assert "put_gex" in df.columns
    assert "net_gex" in df.columns


# ------------------------------------------------------------------ OI walls
def test_max_pain_atm():
    chain = pd.DataFrame(
        {
            "strike": [23900, 24000, 24100],
            "ce_oi": [1000, 5000, 1000],   # most OI at 24000
            "pe_oi": [1000, 5000, 1000],
        }
    )
    res = compute_max_pain(chain)
    assert res["max_pain"] == 24000  # equal OI at strike → min pain at that strike


def test_detect_oi_walls(sample_chain):
    res = detect_oi_walls(sample_chain, top_pct=20.0)
    assert res.call_wall_strike is not None
    assert res.put_wall_strike is not None
    # Top OI is at 24000 for both CE and PE in sample
    assert res.call_wall_strike == 24000
    assert res.put_wall_strike == 24000


# ------------------------------------------------------------------ VWAP
def test_vwap_basic():
    df = pd.DataFrame(
        {
            "price": [100, 101, 102, 103, 104],
            "volume": [10, 20, 30, 40, 50],
        }
    )
    v = vwap(df, "price", "volume")
    # Expected: cumulative
    assert math.isclose(v.iloc[-1], (100*10 + 101*20 + 102*30 + 103*40 + 104*50) / 150)


def test_rolling_vwap():
    df = pd.DataFrame(
        {
            "price": [100, 102, 104, 106, 108],
            "volume": [10, 10, 10, 10, 10],
        }
    )
    v = rolling_vwap(df, "price", "volume", window=3)
    # Last 3-bar VWAP = (104+106+108)/3 = 106
    assert math.isclose(v.iloc[-1], 106, abs_tol=1e-6)


# ------------------------------------------------------------------ Black-Scholes
def test_bs_greeks_call_atm():
    g = bs_greeks(S=100, K=100, t=30/365, r=0.06, sigma=0.20)
    assert 0.45 < g["delta"] < 0.6   # ATM call delta ~ 0.5
    assert g["gamma"] > 0
    assert g["theta"] < 0   # negative theta for long option


def test_bs_greeks_otm_put():
    g = bs_greeks(S=100, K=120, t=30/365, r=0.06, sigma=0.20, )
    # OTM put should have small |delta|
    assert abs(g["delta"]) < 0.3


# ------------------------------------------------------------------ PCR series
def test_pcr_series():
    chains = []
    for i in range(5):
        c = pd.DataFrame(
            {
                "strike": [24000],
                "ce_volume": [1000 + i * 100],
                "pe_volume": [1500 + i * 50],
                "ce_oi": [5000],
                "pe_oi": [7000],
                "timestamp": pd.Timestamp(f"2026-06-04 09:{30 + i}", tz="Asia/Kolkata"),
            }
        )
        chains.append(c)
    df = compute_pcr_series(chains, mode="volume")
    assert len(df) == 5
    assert "pcr_slope" in df.columns
    assert "pcr_change_from_open" in df.columns
