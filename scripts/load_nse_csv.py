"""
Example script: load NSE historical option chain CSVs into the data pipeline.
Usage:
  python scripts/load_nse_csv.py path/to/nse_chain_2026_06_04.csv
Expected CSV columns (NSE format):
  strike, expiry, ce_oi, pe_oi, ce_volume, pe_volume, ce_ltp, pe_ltp,
  ce_iv, pe_iv, ce_delta, ce_gamma, ce_theta, ce_vega,
  pe_delta, pe_gamma, pe_theta, pe_vega, timestamp
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from backtest.engine import Backtester, summarize
from signals.composite import CompositeEngine


def load_nse_csv(path: Path) -> tuple[pd.DataFrame, list[pd.DataFrame]]:
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df["timestamp"] = df["timestamp"].dt.tz_localize("Asia/Kolkata", ambiguous="NaT", nonexistent="shift_forward")
    spot_df = df.groupby("timestamp").agg({"spot": "first", "spot_volume": "first"}).reset_index()
    chains = [g.reset_index(drop=True) for _, g in df.groupby("timestamp")]
    return spot_df, chains


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path, help="Path to NSE option chain CSV")
    parser.add_argument("--capital", type=float, default=1_000_000)
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"CSV not found: {args.csv}")
        return 1

    print(f"Loading {args.csv}…")
    spot_df, chains = load_nse_csv(args.csv)
    print(f"  {len(chains)} snapshots, {len(spot_df)} spot points")

    print("Running backtest…")
    engine = CompositeEngine()
    bt = Backtester(engine=engine, capital=args.capital)
    result = bt.run(spot_df, chains)
    summary = summarize(result)
    for k, v in summary.items():
        print(f"  {k:>20}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
