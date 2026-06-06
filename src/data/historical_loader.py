"""
SQLite historical data loader for backtesting.
Supports the schema from DATA_COLLECTION_TEST_CLIENT.py.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

class SQLiteHistoricalLoader:
    """
    Loads historical option chain data from a relational SQLite database.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)

    def load_intraday_data(
        self,
        target_date: str,
        expiry_date: str | None = None
    ) -> tuple[pd.DataFrame, list[pd.DataFrame]]:
        """
        Loads all snapshots for a specific date (and optionally a specific expiry).

        Args:
            target_date: Date string in 'D-Mon-YYYY' format (as stored by collector).
            expiry_date: Optional expiry date string in 'D-Mon-YYYY' format.

        Returns:
            tuple: (spot_df, list_of_chain_dfs)
        """
        logger.info(f"Loading historical data from {self.db_path} for {target_date}")

        conn = sqlite3.connect(self.db_path)

        query = "SELECT * FROM option_data WHERE historical_date = ?"
        params = [target_date]

        if expiry_date:
            query += " AND expiry_date = ?"
            params.append(expiry_date)

        df = pd.read_sql_query(query, conn, params=params)
        conn.close()

        if df.empty:
            logger.warning(f"No data found for {target_date} in {self.db_path}")
            return pd.DataFrame(), []

        # Map SQLite columns to expected engine columns
        # ce_lastPrice -> ce_ltp, ce_openInterest -> ce_oi, etc.
        rename_map = {
            "ce_lastPrice": "ce_ltp",
            "ce_openInterest": "ce_oi",
            "ce_totalTradedVolume": "ce_volume",
            "pe_lastPrice": "pe_ltp",
            "pe_openInterest": "pe_oi",
            "pe_totalTradedVolume": "pe_volume",
            "underlying_price": "spot",
            "timestamp": "ts_raw"
        }
        df = df.rename(columns=rename_map)

        # Convert timestamp (seconds since epoch) to datetime
        df["timestamp"] = pd.to_datetime(df["ts_raw"], unit='s', utc=True).dt.tz_convert("Asia/Kolkata")

        # Group by timestamp to create snapshots
        snapshots = []
        timestamps = sorted(df["timestamp"].unique())

        spot_records = []

        for ts in timestamps:
            chain_snap = df[df["timestamp"] == ts].copy()
            # Add spot_volume if missing (it usually is in this schema)
            chain_snap["spot_volume"] = 0

            spot_val = chain_snap["spot"].iloc[0]
            spot_records.append({"timestamp": ts, "spot": spot_val, "spot_volume": 0})

            snapshots.append(chain_snap)

        spot_df = pd.DataFrame(spot_records)

        logger.info(f"Successfully loaded {len(snapshots)} snapshots for {target_date}")
        return spot_df, snapshots
