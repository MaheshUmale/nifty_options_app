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

# Global State
latest_market_cache: dict[str, Any] = {}
connected_scalpers: set[WebSocket] = set()
db_manager = DuckDBManager()
ws_source: UpstoxWSSource | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    """
    global ws_source

    # Start DuckDB flusher
    await db_manager.start_flusher(interval=2.0)

    # Initialize Upstox WebSocket Source
    # instrument_keys = ["NSE_INDEX|Nifty 50"]
    instrument_keys = get_settings().get("data", {}).get("ws_instruments", ["NSE_INDEX|Nifty 50"])

    ws_source = UpstoxWSSource(
        instrument_keys=instrument_keys,
        on_tick=handle_new_tick,
        loop=asyncio.get_running_loop()
    )

    # Start ingestion in the background
    asyncio.create_task(ws_source.start())

    # Start mock generator for UI demonstration (optional, could be toggled)
    asyncio.create_task(mock_tick_generator())

    logger.success("FastAPI Backend and Ingestion Layer Started.")

    yield

    # Shutdown logic
    if ws_source:
        await ws_source.stop()
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

    # 2. Buffer for DuckDB
    db_tick = tick.copy()
    db_tick["timestamp"] = datetime.now()
    await db_manager.append_tick(db_tick)

    # 3. Broadcast to UI
    await broadcast_tick(tick)

async def broadcast_tick(tick: dict[str, Any]):
    """Broadcasts a tick to all connected browser WebSockets."""
    if connected_scalpers:
        message = json.dumps(tick)
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
        await broadcast_tick(tick)

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
