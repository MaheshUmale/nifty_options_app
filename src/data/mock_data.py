"""
Synthetic NIFTY data generator for backtesting and smoke tests.
Generates realistic price paths and option chains with Greeks.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from scipy.stats import norm


def bs_greeks(
    S: float, K: float, t: float, r: float, sigma: float, is_call: bool = True
) -> dict[str, float]:
    """
    Standard Black-Scholes Greeks.
    t is time to expiry in years.
    """
    if t <= 0:
        return {
            "price": max(0, (S - K) if is_call else (K - S)),
            "delta": 1.0 if (is_call and S > K) else (-1.0 if (not is_call and S < K) else 0.0),
            "gamma": 0.0,
            "theta": 0.0,
            "vega": 0.0,
        }

    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)

    if is_call:
        price = S * norm.cdf(d1) - K * math.exp(-r * t) * norm.cdf(d2)
        delta = norm.cdf(d1)
        theta = -(S * norm.pdf(d1) * sigma) / (2 * math.sqrt(t)) - r * K * math.exp(-r * t) * norm.cdf(d2)
    else:
        price = K * math.exp(-r * t) * norm.cdf(-d2) - S * norm.cdf(-d1)
        delta = norm.cdf(d1) - 1
        theta = -(S * norm.pdf(d1) * sigma) / (2 * math.sqrt(t)) + r * K * math.exp(-r * t) * norm.cdf(-d2)

    gamma = norm.pdf(d1) / (S * sigma * math.sqrt(t))
    vega = S * norm.pdf(d1) * math.sqrt(t)

    return {
        "price": price,
        "delta": delta,
        "gamma": gamma,
        "theta": theta / 365.0,  # daily theta
        "vega": vega / 100.0,    # per 1% vol change
    }


class NiftyGenerator:
    """Simulates a NIFTY spot path using Geometric Brownian Motion."""

    def __init__(self, start_price: float = 24000.0, vol: float = 0.15, mu: float = 0.05):
        self.price = start_price
        self.vol = vol
        self.mu = mu
        self.dt = 1 / (252 * 375)  # 1 minute in trading years

    def next_price(self, seed: int | None = None) -> float:
        if seed is not None:
            np.random.seed(seed)
        epsilon = np.random.normal()
        self.price *= math.exp((self.mu - 0.5 * self.vol**2) * self.dt + self.vol * math.sqrt(self.dt) * epsilon)
        return self.price


def build_intraday_dataset(
    n_minutes: int = 375,
    seed: int = 42,
    start_price: float = 24000.0,
    interval_min: int = 1
) -> pd.DataFrame:
    """
    Builds a DataFrame containing n_minutes of data.
    Each row is a strike-timestamp combination.
    """
    np.random.seed(seed)
    gen = NiftyGenerator(start_price=start_price)

    start_ts = pd.Timestamp.now(tz="Asia/Kolkata").replace(hour=9, minute=15, second=0, microsecond=0)

    rows = []

    # Static parameters
    r = 0.07
    expiry_days = 7
    lot_size = 75

    current_spot = start_price

    for m in range(0, n_minutes, interval_min):
        ts = start_ts + timedelta(minutes=m)
        current_spot = gen.next_price()

        # Spot-level volume
        spot_vol = np.random.randint(10000, 50000)

        # Option chain: 10 strikes around ATM
        atm_strike = round(current_spot / 50) * 50
        strikes = range(atm_strike - 250, atm_strike + 300, 50)

        for k in strikes:
            t = (expiry_days - (m / 375)) / 365.0

            # CE
            ce = bs_greeks(current_spot, k, t, r, 0.15, is_call=True)
            # PE
            pe = bs_greeks(current_spot, k, t, r, 0.16, is_call=False)

            # Volumes & OI (synthetic)
            dist = abs(k - current_spot)
            ce_vol = max(10, int(2000 * math.exp(-dist / 100) + np.random.randint(0, 500)))
            pe_vol = max(10, int(2000 * math.exp(-dist / 100) + np.random.randint(0, 500)))

            ce_oi = int(100000 * math.exp(-dist / 200))
            pe_oi = int(100000 * math.exp(-dist / 200))

            rows.append({
                "timestamp": ts,
                "spot": current_spot,
                "spot_volume": spot_vol,
                "strike": k,
                "ce_ltp": ce["price"],
                "ce_iv": 0.15,
                "ce_delta": ce["delta"],
                "ce_gamma": ce["gamma"],
                "ce_theta": ce["theta"],
                "ce_vega": ce["vega"],
                "ce_volume": ce_vol,
                "ce_oi": ce_oi,
                "pe_ltp": pe["price"],
                "pe_iv": 0.16,
                "pe_delta": pe["delta"],
                "pe_gamma": pe["gamma"],
                "pe_theta": pe["theta"],
                "pe_vega": pe["vega"],
                "pe_volume": pe_vol,
                "pe_oi": pe_oi,
            })

    return pd.DataFrame(rows)
