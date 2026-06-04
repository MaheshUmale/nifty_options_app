"""
Upstox V3 WebSocket (Protobuf) Integration using official SDK.
Provides a client to stream real-time data.
"""
from __future__ import annotations

import asyncio
import json
import ssl
from typing import Any, Callable
from queue import Queue
import threading

from upstox_client import MarketDataStreamerV3
from utils.logger import get_logger
from data.upstox_client import make_client_from_env

log = get_logger()

class UpstoxStreamer:
    """WebSocket client for Upstox V3 Market Data using official SDK."""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.streamer = MarketDataStreamerV3(access_token)
        self._setup_callbacks()

    def _setup_callbacks(self):
        self.streamer.on("open", self._on_open)
        self.streamer.on("message", self._on_message)
        self.streamer.on("error", self._on_error)
        self.streamer.on("close", self._on_close)

    def _on_open(self):
        log.info("Upstox V3 WebSocket connected.")

    def _on_message(self, message):
        log.debug(f"Received message: {message}")

    def _on_error(self, error):
        log.error(f"WebSocket error: {error}")

    def _on_close(self, close_status_code, close_msg):
        log.warning(f"WebSocket closed: {close_status_code} - {close_msg}")

    def connect(self):
        """Connects to the WebSocket feed."""
        self.streamer.connect()

    def subscribe(self, instrument_keys: list[str], mode: str = "full"):
        """Subscribes to instruments."""
        # mode can be 'ltp', 'full'
        self.streamer.subscribe(instrument_keys, mode)
        log.info(f"Subscribed to {len(instrument_keys)} instruments in {mode} mode.")

    def disconnect(self):
        self.streamer.disconnect()

class MockWebSocket:
    """Synthetic WebSocket for testing."""

    def __init__(self, rate_hz: float = 1.0):
        self.interval = 1.0 / rate_hz
        self.queue = Queue()
        self.is_running = False

    def start(self, n_minutes: int = 375):
        self.is_running = True
        self._thread = threading.Thread(target=self._run, args=(n_minutes,), daemon=True)
        self._thread.start()

    def _run(self, n_minutes: int):
        from data.mock_data import build_intraday_dataset
        import time
        ds = build_intraday_dataset(n_minutes=n_minutes)
        chains = [g for _, g in ds.groupby("timestamp")]

        for chain in chains:
            if not self.is_running:
                break
            self.queue.put(chain)
            time.sleep(self.interval)

    def stop(self):
        self.is_running = False

class UpstoxLiveSource:
    """
    Live data source using Upstox SDK (polling for now, extensible to WS).
    Uses V3 endpoints for market quotes.
    """
    def __init__(self, poll_interval_sec: float = 5.0):
        self.poll_interval = poll_interval_sec
        self.queue = Queue()
        self.client = make_client_from_env()
        self._stop = threading.Event()
        self._thread = None
        self.instrument_key = "NSE_INDEX|Nifty 50"

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        log.info("UpstoxLiveSource (V3) started (polling every {}s)", self.poll_interval)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _poll_loop(self):
        import time
        import pandas as pd
        while not self._stop.is_set():
            try:
                # Use V3 LTP endpoint
                resp = self.client.get_market_quote_ltp([self.instrument_key])
                if resp.get("status") == "success":
                    data = resp.get("data", {})
                    if self.instrument_key in data:
                        spot = data[self.instrument_key]["last_price"]

                        # Fetch Option Chain (Still V2 as per SDK dir, but used within V3 context)
                        from datetime import datetime, timedelta
                        today = datetime.now()
                        days_ahead = 3 - today.weekday()
                        if days_ahead < 0: days_ahead += 7
                        next_thursday = (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

                        chain_resp = self.client.get_option_chain(self.instrument_key, next_thursday)
                        if chain_resp.get("status") == "success":
                            df = self._transform_chain(chain_resp["data"], spot)
                            self.queue.put(df)
                        else:
                            log.error("Live Option Chain failed: {}", chain_resp.get("errors"))
                else:
                    log.error("Live Spot Quote (V3) failed: {}", resp.get("errors"))
            except Exception as e:
                log.error("Error in UpstoxLiveSource (V3): {}", e)
            time.sleep(self.poll_interval)

    def _transform_chain(self, data, spot):
        import pandas as pd
        rows = []
        ts = pd.Timestamp.now(tz="Asia/Kolkata")
        for item in data:
            strike = item.get("strike_price")
            ce = item.get("call_options", {}).get("market_data", {})
            pe = item.get("put_options", {}).get("market_data", {})
            rows.append({
                "timestamp": ts, "spot": spot, "strike": strike,
                "ce_ltp": ce.get("ltp", 0), "ce_volume": ce.get("volume", 0), "ce_oi": ce.get("oi", 0),
                "pe_ltp": pe.get("ltp", 0), "pe_volume": pe.get("volume", 0), "pe_oi": pe.get("oi", 0),
                "ce_iv": 0.15, "ce_delta": 0.5, "ce_gamma": 0.001, "ce_theta": -1, "ce_vega": 0.1,
                "pe_iv": 0.15, "pe_delta": -0.5, "pe_gamma": 0.001, "pe_theta": -1, "pe_vega": 0.1,
            })
        return pd.DataFrame(rows)
