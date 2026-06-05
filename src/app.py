"""
FastAPI application core.
Manages WebSocket connections, broadcasting, and local cache.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger

from database import DuckDBManager
from ingestion import UpstoxWSSource
from config import get_settings
from signals.orchestrator import SignalOrchestrator
from execution.order_manager import OrderManager
from data.streaming import UpstoxLiveSource, MockWebSocket
from signals.state import SignalState

import pandas as pd
import queue
from data.upstox_client import UpstoxClient

# Global State
latest_market_cache: dict[str, Any] = {}
virtual_chain_cache: dict[str, dict] = {} # instrument_key -> tick_data
option_key_to_strike_info: dict[str, dict] = {} # instrument_key -> {strike, side, greeks...}
connected_scalpers: set[WebSocket] = set()
db_manager = DuckDBManager()
ws_source: UpstoxWSSource | None = None
orchestrator: SignalOrchestrator | None = None
order_manager: OrderManager | None = None

class WSQueueSource:
    """Mock-like source for SignalOrchestrator that we manually feed with ticks."""
    def __init__(self):
        self.queue = queue.Queue() # Thread-safe Queue
    def start(self): pass
    def stop(self): pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    """
    global ws_source, orchestrator, order_manager

    settings = get_settings()
    mode = settings.get("app", {}).get("mode", "mock")

    # 1. Initialize Order Manager
    order_manager = OrderManager(
        lot_size=settings["risk"]["lot_size"],
        max_position_notional=settings["risk"]["max_position_notional"],
        max_daily_loss=settings["risk"]["max_daily_loss"],
        live=(mode == "live")
    )

    # 2. Initialize Signal Orchestrator with an event-driven source
    ws_queue_source = WSQueueSource()
    loop = asyncio.get_running_loop()

    def _on_signal_wrapper(st):
        asyncio.run_coroutine_threadsafe(handle_new_signal(st), loop)

    orchestrator = SignalOrchestrator(
        data_source=ws_queue_source,
        on_signal=_on_signal_wrapper,
        order_manager=order_manager
    )
    orchestrator.start()

    # 3. Start DuckDB flusher
    await db_manager.start_flusher(interval=2.0)

    # 4. Initialize Upstox WebSocket Source
    import os
    env_keys = os.getenv("UPSTOX_SPOT_INSTRUMENT_KEY", "")
    if env_keys:
        instrument_keys = [k.strip() for k in env_keys.split(",") if k.strip()]
    else:
        instrument_keys = settings.get("data", {}).get("ws_instruments", ["NSE_INDEX|Nifty 50"])

    if mode == "live":
        # Fetch initial option chain to get all keys and static Greeks
        try:
            client = UpstoxClient()
            # Assuming first key is Nifty 50 spot
            contracts_resp = client.get_option_contracts(instrument_keys[0])
            if contracts_resp.get("status") == "success" and contracts_resp.get("data"):
                expiries = sorted(list(set(item.get("expiry") for item in contracts_resp["data"] if item.get("expiry"))))
                if expiries:
                    current_expiry = expiries[0]
                    chain_resp = client.get_option_chain(instrument_keys[0], current_expiry)
                    if chain_resp.get("status") == "success":
                        # Populate option key lookup
                        for item in chain_resp["data"]:
                            strike = item["strike_price"]
                            for side, opt_data in [("CE", item["call_options"]), ("PE", item["put_options"])]:
                                key = opt_data["instrument_key"]
                                option_key_to_strike_info[key] = {
                                    "strike": strike,
                                    "side": side,
                                    "greeks": opt_data.get("option_greeks", {}),
                                    "expiry": current_expiry
                                }
                                instrument_keys.append(key)
                        logger.info(f"Subscribing to {len(instrument_keys)} instruments (Spot + Chain)")
        except Exception as e:
            logger.error(f"Failed to fetch initial option chain for WS subscription: {e}")

    ws_source = UpstoxWSSource(
        instrument_keys=list(set(instrument_keys)),
        on_tick=handle_new_tick,
        loop=loop
    )

    # Start ingestion in the background
    asyncio.create_task(ws_source.start())

    # 5. Background task to feed the Orchestrator periodically from accumulated ticks
    asyncio.create_task(signal_feed_loop(ws_queue_source))

    # 6. Start Mark-to-Market (MTM) loop for risk management
    asyncio.create_task(mtm_loop())

    # 7. Toggle mock generator based on APP_MODE
    if mode == "mock":
        logger.info("Starting mock tick generator (APP_MODE=mock)")
        asyncio.create_task(mock_tick_generator())
    else:
        logger.info(f"Live mode active (APP_MODE={mode}). Running event-driven signals.")

    logger.success("FastAPI Backend and Ingestion Layer Started.")

    yield

    # Shutdown logic
    if ws_source:
        await ws_source.stop()
    if orchestrator:
        orchestrator.stop()
    await db_manager.stop_flusher()
    logger.info("FastAPI Backend Shutdown.")

# Initialize FastAPI with lifespan
app = FastAPI(title="NIFTY Zero-Lag Scalper", lifespan=lifespan)

# Mount templates
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

async def handle_new_tick(tick: dict[str, Any]):
    """
    Callback for processing new market ticks.
    """
    # 1. Update Cache
    instrument = tick.get("instrument_key")
    latest_market_cache[instrument] = tick
    virtual_chain_cache[instrument] = tick

    # 1.1 Update Greeks if present in tick
    if "greeks" in tick and instrument in option_key_to_strike_info:
        option_key_to_strike_info[instrument]["greeks"] = tick["greeks"]

    # 2. Buffer for DuckDB
    db_tick = tick.copy()
    db_tick["timestamp"] = datetime.now()
    await db_manager.append_tick(db_tick)

    # 3. Broadcast to UI
    payload = {
        "type": "tick",
        "data": tick
    }
    await broadcast_payload(payload)

async def signal_feed_loop(source: WSQueueSource):
    """
    Normalizer / Cache Layer:
    Accumulates high-frequency ticks into 1-second buckets and
    pushes a consolidated 'Chain DataFrame' to the Signal Engine.
    """
    while True:
        await asyncio.sleep(1.0)

        if not virtual_chain_cache:
            continue

        try:
            spot_key = "NSE_INDEX|Nifty 50"
            spot_tick = virtual_chain_cache.get(spot_key) or virtual_chain_cache.get(spot_key.replace("|", ":"))

            if not spot_tick:
                continue

            spot_price = spot_tick["ltp"]

            strikes = {}
            for key, info in option_key_to_strike_info.items():
                tick = virtual_chain_cache.get(key)
                if not tick: continue

                strike = info["strike"]
                if strike not in strikes:
                    strikes[strike] = {
                        "strike": strike,
                        "expiry": info["expiry"],
                        "spot": spot_price
                    }

                prefix = info["side"].lower()
                strikes[strike][f"{prefix}_ltp"] = tick["ltp"]
                strikes[strike][f"{prefix}_volume"] = tick.get("volume", 0)
                strikes[strike][f"{prefix}_oi"] = tick.get("oi", 0)

                # Add Greeks for Feature Engine
                greeks = info["greeks"]
                for g_key, g_val in greeks.items():
                    strikes[strike][f"{prefix}_{g_key}"] = g_val

            df = pd.DataFrame(list(strikes.values()))
            if df.empty: continue

            df["timestamp"] = pd.Timestamp.now(tz="Asia/Kolkata")

            # Push to Signal Engine (Orchestrator)
            source.queue.put(df)

        except Exception as e:
            logger.error(f"Error in signal_feed_loop (Normalizer): {e}")

async def mtm_loop():
    """
    Risk Governance Layer:
    Periodically updates unrealized PnL and enforces stop-loss/target exit rules.
    """
    while True:
        await asyncio.sleep(5.0) # 5s MTM cycle
        if order_manager and order_manager.positions:
            # Create a simple price lookup from cache for tradingsymbols
            # Note: order_manager uses tradingsymbol/instrument name
            price_lookup = {k: v["ltp"] for k, v in latest_market_cache.items()}

            # We also need to map tradingsymbols back to LTP if they differ from instrument_key
            # For simplicity, we use the instrument_key if that's what's in the cache
            order_manager.mark_to_market(price_lookup)

async def handle_new_signal(st: SignalState):
    """
    Callback for new signals from Orchestrator.
    """
    # 1. Broadast to UI
    payload = {
        "type": "signal",
        "data": st.to_dict()
    }

    # Add position info
    if order_manager:
        payload["positions"] = order_manager.summary()

    await broadcast_payload(payload)

async def broadcast_payload(payload: dict[str, Any]):
    """Broadcasts a payload to all connected browser WebSockets."""
    if connected_scalpers:
        message = json.dumps(payload, default=str)
        await asyncio.gather(
            *[client.send_text(message) for client in connected_scalpers],
            return_exceptions=True
        )

async def mock_tick_generator():
    """Generates mock ticks for demonstration when live data is unavailable."""
    import random
    price = 24000.0
    while True:
        await asyncio.sleep(1)
        price += random.uniform(-5, 5)
        tick = {
            "instrument_key": "NSE_INDEX|Nifty 50",
            "ltp": round(price, 2),
            "volume": random.randint(1000, 5000),
            "oi": random.randint(100000, 500000)
        }
        await broadcast_payload({
            "type": "tick",
            "data": tick
        })

@app.get("/")
async def get_index(request: Request):
    """Serves the main dashboard page."""
    return templates.TemplateResponse(request=request, name="index.html")

@app.websocket("/ws/ticks")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for browser clients."""
    await websocket.accept()
    connected_scalpers.add(websocket)
    logger.info(f"New browser connection. Total: {len(connected_scalpers)}")

    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_scalpers.remove(websocket)
        logger.info(f"Browser disconnected. Total: {len(connected_scalpers)}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if websocket in connected_scalpers:
            connected_scalpers.remove(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
