"""
Data storage layer using DuckDB.
Saves live market data (option chains) for future backtesting/replay.
"""
from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pandas as pd

from utils.logger import get_logger

log = get_logger()

class MarketDataStore:
    """Stores market data snapshots into a persistent DuckDB database."""

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            # Default to data/market_data.duckdb
            root = Path(__file__).resolve().parents[2]
            data_dir = root / "data"
            data_dir.mkdir(exist_ok=True)
            db_path = data_dir / "market_data.duckdb"

        self.db_path = str(db_path)
        log.info("Initializing MarketDataStore at {}", self.db_path)

        # Ensure the table exists
        self._init_db()

    def _init_db(self):
        """Creates the necessary tables if they don't exist."""
        with duckdb.connect(self.db_path) as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS option_chain_snapshots (
                    timestamp TIMESTAMPTZ,
                    underlying_symbol VARCHAR,
                    expiry DATE,
                    strike DOUBLE,
                    spot DOUBLE,
                    ce_ltp DOUBLE,
                    ce_volume BIGINT,
                    ce_oi DOUBLE,
                    pe_ltp DOUBLE,
                    pe_volume BIGINT,
                    pe_oi DOUBLE,
                    tradingsymbol_ce VARCHAR,
                    tradingsymbol_pe VARCHAR
                )
            """)

    def save_snapshot(self, df: pd.DataFrame):
        """Appends a NIFTY option chain DataFrame to the store."""
        if df.empty:
            return

        try:
            # Prepare the DataFrame for insertion (matching the schema)
            # UpstoxLiveSource._transform_chain produces a DF with these columns:
            # timestamp, spot, expiry, strike, ce_ltp, ce_volume, ce_oi, pe_ltp, pe_volume, pe_oi, etc.

            # Map columns to schema
            insert_df = df[[
                "timestamp", "spot", "expiry", "strike",
                "ce_ltp", "ce_volume", "ce_oi",
                "pe_ltp", "pe_volume", "pe_oi",
                "tradingsymbol_ce", "tradingsymbol_pe"
            ]].copy()

            # Add underlying_symbol (default to NIFTY)
            insert_df["underlying_symbol"] = "NIFTY"

            # Reorder to match schema exactly for safety (optional with DuckDB)
            # con.append works well with matching names

            with duckdb.connect(self.db_path) as con:
                con.execute("INSERT INTO option_chain_snapshots SELECT * FROM insert_df")

            log.debug("Saved {} rows to DuckDB", len(insert_df))
        except Exception as e:
            log.error("Failed to save market data to DuckDB: {}", e)

    def load_data(self, start_date: str | None = None, end_date: str | None = None) -> pd.DataFrame:
        """Loads historical data from the store."""
        query = "SELECT * FROM option_chain_snapshots"
        params = []

        conditions = []
        if start_date:
            conditions.append("timestamp >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("timestamp <= ?")
            params.append(end_date)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY timestamp ASC"

        with duckdb.connect(self.db_path) as con:
            return con.execute(query, params).df()
