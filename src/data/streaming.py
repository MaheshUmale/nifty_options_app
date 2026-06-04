"""
Upstox V3 WebSocket (Protobuf) Integration.
Provides a client to stream real-time data.
"""
from __future__ import annotations

import asyncio
import json
import ssl
from typing import Any, Callable
from queue import Queue
import threading

import websockets
from utils.logger import get_logger

log = get_logger()

class UpstoxStreamer:
    """WebSocket client for Upstox V3 Market Data."""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.uri = "wss://api.upstox.com/v2/feed/market-data-feed"
        self.ws = None
        self.callbacks: list[Callable[[dict], None]] = []

    def add_callback(self, cb: Callable[[dict], None]):
        self.callbacks.append(cb)

    async def connect(self):
        """Connects to the WebSocket feed."""
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }
        try:
            self.ws = await websockets.connect(self.uri, extra_headers=headers)
            log.info("WebSocket connected to Upstox.")
        except Exception as e:
            log.error(f"Failed to connect to Upstox WebSocket: {e}")
            raise

    async def subscribe(self, instrument_keys: list[str], mode: str = "full"):
        """Subscribes to instruments."""
        if not self.ws:
            await self.connect()

        payload = {
            "guid": "guid123",
            "method": "sub",
            "data": {
                "mode": mode,
                "instrumentKeys": instrument_keys
            }
        }
        await self.ws.send(json.dumps(payload))
        log.info(f"Subscribed to {len(instrument_keys)} instruments in {mode} mode.")

    async def listen(self):
        """Main loop to listen for messages."""
        if not self.ws:
            await self.connect()

        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                except:
                    data = {"raw": str(message)}

                for cb in self.callbacks:
                    cb(data)
        except websockets.exceptions.ConnectionClosed:
            log.warning("WebSocket connection closed.")
        except Exception as e:
            log.error(f"Error in WebSocket listener: {e}")

class MockWebSocket:
    """Synthetic WebSocket for testing."""

    def __init__(self, rate_hz: float = 1.0):
        self.interval = 1.0 / rate_hz
        self.queue = Queue()
        self.is_running = False

    def add_callback(self, cb):
        pass # Not used in orchestrator pattern

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
    Live data source using Upstox REST API polling.
    """
    def __init__(self, poll_interval_sec: float = 5.0):
        from data.upstox_client import make_client_from_env
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
        log.info("UpstoxLiveSource started (polling every {}s)", self.poll_interval)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _poll_loop(self):
        import time
        import pandas as pd
        while not self._stop.is_set():
            try:
                quote = self.client.get_market_quote([self.instrument_key])
                if quote.get("status") == "success":
                    spot = quote["data"][self.instrument_key]["last_price"]
                    # Assume current expiry for demo
                    from datetime import datetime, timedelta
                    today = datetime.now()
                    # Next Thursday
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
                    log.error("Live Spot Quote failed: {}", quote.get("errors"))
            except Exception as e:
                log.error("Error in UpstoxLiveSource: {}", e)
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
