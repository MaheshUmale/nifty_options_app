"""
Upstox MarketDataStreamerV3 WebSocket ingestion layer.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable

import upstox_client
from upstox_client.feeder import MarketDataStreamerV3
from loguru import logger

from config import get_upstox_access_token

class UpstoxWSSource:
    """
    WebSocket client for Upstox V3 Market Data Streaming.

    Connects to the Upstox API V3 and streams market data for a specified
    list of instruments. Decodes binary Protobuf messages and invokes
    a callback for each received tick.
    """

    def __init__(
        self,
        instrument_keys: list[str],
        on_tick: Callable[[dict[str, Any]], Any],
        access_token: str | None = None,
        loop: asyncio.AbstractEventLoop | None = None
    ):
        self.instrument_keys = instrument_keys
        self.on_tick = on_tick
        self.access_token = access_token or get_upstox_access_token()
        self.streamer = None
        self.loop = loop or asyncio.get_event_loop()
        self._stop_event = asyncio.Event()

    async def start(self):
        """
        Starts the Upstox WebSocket stream.

        Initializes the ApiClient, configures the MarketDataStreamerV3,
        and establishes the connection.
        """
        if not self.access_token:
            logger.error("No Upstox access token provided for WebSocket.")
            return

        # Initialize the streamer
        configuration = upstox_client.Configuration()
        configuration.access_token = self.access_token
        api_client = upstox_client.ApiClient(configuration)

        self.streamer = MarketDataStreamerV3(
            api_client=api_client,
            instrumentKeys=self.instrument_keys,
            mode="full"
        )

        # Set callbacks
        self.streamer.on_open = self._on_open
        self.streamer.on_message = self._on_message
        self.streamer.on_error = self._on_error
        self.streamer.on_close = self._on_close

        logger.info(f"Connecting to Upstox WebSocket for {len(self.instrument_keys)} instruments...")

        try:
            self.streamer.connect()
            logger.success("Upstox WebSocket connection initiated.")
        except Exception as e:
            logger.exception(f"Failed to connect Upstox WebSocket: {e}")

    def _on_open(self):
        logger.info("Upstox WebSocket connection opened.")

    def _on_message(self, message):
        """
        Internal callback for incoming WebSocket messages.

        Processes binary Protobuf or JSON data from the Upstox SDK's background
        thread, normalizes the data into a common tick format, and schedules
        the `on_tick` callback to be executed in the main event loop.

        Args:
            message (dict | bytes): The raw message received from the stream.
        """
        try:
            ticks = []
            if isinstance(message, dict) and "data" in message:
                for key, data in message["data"].items():
                    # Handle both "NSE_INDEX|Nifty 50" and "NSE_INDEX:Nifty 50" formats
                    normalized_key = key.replace(":", "|")
                    tick = {
                        "timestamp": self.loop.time(),
                        "instrument_key": normalized_key,
                        "ltp": data.get("last_price") or data.get("ltp"),
                        "volume": data.get("volume") or data.get("v"),
                        "oi": data.get("oi"),
                    }
                    # Include any extra fields like Greeks if present in 'full' mode
                    if "option_greeks" in data:
                        tick["greeks"] = data["option_greeks"]
                    elif "og" in data: # Some V3 versions use short keys
                        tick["greeks"] = data["og"]

                    ticks.append(tick)

            for tick in ticks:
                if asyncio.iscoroutinefunction(self.on_tick):
                    # Safely schedule the coroutine in the main event loop
                    asyncio.run_coroutine_threadsafe(self.on_tick(tick), self.loop)
                else:
                    # If it's a regular function, it's safer to run it in the loop as well
                    # or just call it if it's thread-safe. For our app, it updates a cache.
                    self.loop.call_soon_threadsafe(self.on_tick, tick)

        except Exception as e:
            logger.error(f"Error processing WebSocket message: {e}")

    def _on_error(self, error):
        logger.error(f"Upstox WebSocket error: {error}")

    def _on_close(self, status_code, message):
        logger.warning(f"Upstox WebSocket closed: {status_code} - {message}")

    async def stop(self):
        """
        Stops the Upstox WebSocket stream.

        Disconnects the streamer and cleans up resources.
        """
        if self.streamer:
            self.streamer.disconnect()
            logger.info("Upstox WebSocket disconnected.")
