"""
Analytical storage layer using DuckDB.
Handles asynchronous batching and flushing of market ticks.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
from loguru import logger

class DuckDBManager:
    """
    Manages DuckDB connections and asynchronous data flushing.

    Attributes:
        db_path (str): Path to the DuckDB file.
        buffer (list): In-memory storage for incoming ticks.
        lock (asyncio.Lock): Lock to ensure thread-safe access to the buffer during flushes.
    """

    def __init__(self, db_path: str | Path | None = None):
        """
        Initializes the DuckDBManager.

        Args:
            db_path (str | Path | None): Optional custom path for the database file.
        """
        if db_path is None:
            root = Path(__file__).resolve().parent.parent
            data_dir = root / "data"
            data_dir.mkdir(exist_ok=True)
            db_path = data_dir / "market_data_v3.duckdb"

        self.db_path = str(db_path)
        self.buffer = []
        self.lock = asyncio.Lock()
        self.flusher_task = None
        self._con = None
        self._init_db()

    def _init_db(self):
        """
        Initializes the DuckDB schema and opens a persistent connection.

        This creates the 'ticks' table if it does not exist.
        """
        logger.info(f"Initializing DuckDB at {self.db_path}")
        self._con = duckdb.connect(self.db_path)
        self._con.execute("""
            CREATE TABLE IF NOT EXISTS ticks (
                timestamp TIMESTAMPTZ,
                instrument_key VARCHAR,
                ltp DOUBLE,
                volume BIGINT,
                bid DOUBLE,
                ask DOUBLE,
                oi DOUBLE
            )
        """)
        logger.success("DuckDB schema initialized and connection opened.")

    async def start_flusher(self, interval: float = 2.0):
        """
        Starts the background flusher task.

        Args:
            interval (float): Seconds between database flushes.
        """
        if self.flusher_task is not None:
            return

        self.flusher_task = asyncio.create_task(self._flush_loop(interval))
        logger.info(f"DuckDB flusher started with interval {interval}s")

    async def stop_flusher(self):
        """
        Stops the background flusher task and closes the connection.

        Ensures any remaining data in the buffer is flushed before closing.
        """
        if self.flusher_task:
            self.flusher_task.cancel()
            try:
                await self.flusher_task
            except asyncio.CancelledError:
                pass
            await self.flush_to_db()
            self.flusher_task = None

        if self._con:
            self._con.close()
            self._con = None
            logger.info("DuckDB connection closed.")

    async def _flush_loop(self, interval: float):
        """
        Internal loop for periodic flushing.

        Args:
            interval (float): The sleep duration between flushes.
        """
        while True:
            await asyncio.sleep(interval)
            await self.flush_to_db()

    async def append_tick(self, tick: dict[str, Any]):
        """
        Appends a tick to the in-memory buffer.

        Args:
            tick (dict): The tick data to store.
        """
        async with self.lock:
            self.buffer.append(tick)

    async def flush_to_db(self):
        """
        Converts buffer to DataFrame and bulk inserts into DuckDB.

        Uses a context manager lock to safely copy the buffer before insertion.
        Empty columns are reindexed to match the database schema.
        """
        async with self.lock:
            if not self.buffer:
                return

            data_to_flush = self.buffer.copy()
            self.buffer.clear()

        try:
            df = pd.DataFrame(data_to_flush)
            schema_cols = ["timestamp", "instrument_key", "ltp", "volume", "bid", "ask", "oi"]

            # Ensure all schema columns exist in the DataFrame, filling missing with None (NULL in DuckDB)
            df = df.reindex(columns=schema_cols)

            if self._con:
                # Use the connection to insert. DuckDB handles Pandas DataFrames directly.
                self._con.execute("INSERT INTO ticks SELECT * FROM df")
                logger.debug(f"Flushed {len(data_to_flush)} ticks to DuckDB.")
            else:
                logger.error("DuckDB connection is not open.")
        except Exception as e:
            logger.error(f"Failed to flush ticks to DuckDB: {e}")
            async with self.lock:
                self.buffer = data_to_flush + self.buffer
