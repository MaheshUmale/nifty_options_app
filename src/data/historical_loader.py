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

    def list_available_dates(self) -> list[str]:
        """Returns a list of all historical_date strings in the database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT historical_date, timestamp FROM option_data ORDER BY timestamp ASC")
        # Get unique dates preserving temporal order
        seen = set()
        dates = []
        for row in cursor.fetchall():
            d = row[0]
            if d not in seen:
                seen.add(d)
                dates.append(d)
        conn.close()
        return dates

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
            "ce_impliedVolatility": "ce_iv",
            "ce_delta": "ce_delta",
            "ce_gamma": "ce_gamma",
            "ce_theta": "ce_theta",
            "ce_vega": "ce_vega",
            "pe_lastPrice": "pe_ltp",
            "pe_openInterest": "pe_oi",
            "pe_totalTradedVolume": "pe_volume",
            "pe_impliedVolatility": "pe_iv",
            "pe_delta": "pe_delta",
            "pe_gamma": "pe_gamma",
            "pe_theta": "pe_theta",
            "pe_vega": "pe_vega",
            "underlying_price": "spot",
            "timestamp": "ts_raw"
        }
        df = df.rename(columns=rename_map)

        # Convert timestamp to datetime.
        # The data uses format YYYYMMDD_HHMMSS (e.g., 20260101_091524)
        df["timestamp"] = pd.to_datetime(df["ts_raw"], format="%Y%m%d_%H%M%S", errors='coerce')
        if df["timestamp"].dt.tz is None:
            df["timestamp"] = df["timestamp"].dt.tz_localize("Asia/Kolkata")

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
