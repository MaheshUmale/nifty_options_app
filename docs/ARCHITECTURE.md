# Architecture

## Event-Driven Data Flow

```
┌────────────────┐      ┌────────────────┐
│  Upstox WS V3  │      │ Mock Generator │
│  (Protobuf)    │      │ (Simulation)   │
└────────┬───────┘      └────────┬───────┘
         │                       │
         ▼                       ▼
   ┌───────────────────────────────────┐
   │        Ingestion Layer            │
   │ (UpstoxWSSource / Protobuf Decode)│
   └────────────┬──────────────────────┘
                │ Async Ticks
                ▼
   ┌───────────────────────────────────┐
   │        FastAPI Application        │
   │ (Normalizer & WebSocket Broadcast) │
   └────────────┬─────────────┬────────┘
                │             │
                ▼             ▼
   ┌──────────────────┐  ┌──────────────────┐
   │ Analytical Store │  │ Signal Engine    │
   │ (DuckDB Buffer)  │  │ (Orchestrator)   │
   └──────────────────┘  └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │ Risk & Execution │
                         │ (Order Manager)  │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │ Zero-Lag UI      │
                         │ (TradingView)    │
                         └──────────────────┘
```

## Operational Layers

### 1. Ingestion Layer (`ingestion.py`)
Uses the official `MarketDataStreamerV3` via a persistent WebSocket stream. Decodes binary Protobuf ticks in microseconds.

### 2. Analytical Storage (`database.py`)
Configured with **DuckDB**. Uses an in-memory buffer array wrapped in an `asyncio.Lock`. A background flusher task wakes up every 2 seconds to bulk insert accumulated ticks.

### 3. Application & Broadcast (`app.py`)
Built on **FastAPI**. Maintains an active `latest_market_cache` for O(1) metric lookups. Broadcasts tick payloads to all active `connected_scalpers` using `asyncio.gather`.

### 4. Zero-Lag UI (`templates/index.html`)
Lightweight HTML5 + Vanilla JS. Uses **TradingView Lightweight Charts** (Canvas-based) for high-frequency rendering. Dynamic DOM manipulation for KPI updates.

## Latency Budget

| Stage | Target |
|-------|--------|
| Tick arrival → Bcast | < 2 ms |
| Bcast → UI Render | < 10 ms |
| Tick arrival → DB Buffer | < 1 ms |
| **Total Pipeline** | **< 15 ms** |

## Data Persistence
Real-time ticks are stored in `data/market_data_v3.duckdb`. Legacy snapshots from REST polling are stored in `data/market_data.duckdb`.

## Failure Modes & Fallbacks

| Failure | Detection | Response |
|---------|-----------|----------|
| **WS disconnect** | SDK Callback | Auto-reconnect (managed by SDK) |
| **Buffer Overflow** | Buffer length check | Alert + emergency flush |
| **DB Lock Contention**| Exception | Log + retry next cycle |
| **UI Lag** | Frame drop | Reduce chart update frequency |
