# Architecture

## High-Level Data Flow

```
┌────────────────┐  ┌────────────────┐
│  Upstox REST   │  │  Upstox WS V3  │
│  /option/chain │  │  (Protobuf)    │
│  /market/pcr   │  │                │
│  /market/oi    │  │                │
│  /max-pain     │  │                │
└────────┬───────┘  └────────┬───────┘
         │                   │
         ▼                   ▼
      ┌──────────────────────────┐
      │  Normalizer / Cache      │   ← 50 req/s throttle, 1–5s buckets
      │  (in-memory + Parquet)   │
      └────────────┬─────────────┘
                   │ Chain DataFrame
                   ▼
      ┌──────────────────────────┐
      │  Feature Engine          │
      │  • PCR + slope           │
      │  • IV skew + trend       │
      │  • GEX + walls + zero-γ  │
      │  • OI walls + Max Pain   │
      │  • VWAP divergence       │
      │  • Theta acceleration    │
      └────────────┬─────────────┘
                   │ Feature Vector
                   ▼
      ┌──────────────────────────┐
      │  Composite Signal Engine │
      │  • Vol-OI Nexus          │
      │  • Gamma Hedge Trigger   │
      │  • Lead-Lag (Premium)    │
      │  • No-Trade Trap         │
      │  • Momentum Index        │
      │  • Master Exec Matrix    │
      └────────────┬─────────────┘
                   │ SignalState
                   ▼
      ┌──────────────────────────┐
      │  Order Manager           │
      │  • Risk checks           │
      │  • Position sizing       │
      │  • Paper / Live routing  │
      │  • Mark-to-market        │
      └────────────┬─────────────┘
                   │
       ┌───────────┴───────────┐
       ▼                       ▼
   Upstox Orders         Dashboard
   API (live)            (Dash/Plotly)
```

## Threading Model

| Thread | Owner | Frequency | Purpose |
|--------|-------|-----------|---------|
| **WS Reader** | `UpstoxWebSocket` | per WS message | Decode Protobuf → push to `queue.Queue` |
| **Signal Loop** | `SignalOrchestrator` | 1 s | Pop queue → run engine → call listeners |
| **Dashboard Refresh** | Dash `dcc.Interval` | 2 s | Re-render charts from `orchestrator.history` |
| **MTM Loop** | `OrderManager` | 5 s | Update unrealized PnL, auto-exit on stops |

Threads are **daemon=True** so they die when the main process exits.

## Latency Budget

| Stage | Target |
|-------|--------|
| Tick arrival → queue | < 5 ms |
| Queue → engine compute | < 50 ms |
| Engine → SignalState | < 10 ms |
| SignalState → order submission | < 30 ms |
| **Total** | **< 100 ms** |

For HFT-grade latency, replace the `Queue` with a `multiprocessing.Queue` and
move the signal engine to a separate process pinned to a CPU core.

## Data Storage

| Layer | Tech | Retention | Access |
|-------|------|-----------|--------|
| Hot (live) | In-memory pandas | 1 day | O(1) feature lookups |
| Warm | Parquet (per-day files) | 30 days | Sub-second columnar scans |
| Cold | S3 / GCS (partitioned by year/month) | ∞ | Bulk backtest reads |

Storage layout:
```
data/
├── live/                   # today
│   ├── ticks_20260604.parquet
│   ├── features_20260604.parquet
│   └── signals_20260604.parquet
├── warm/                   # last 30 days
└── cold/
    └── year=2026/month=06/day=04/ticks.parquet
```

## Failure Modes & Fallbacks

| Failure | Detection | Response |
|---------|-----------|----------|
| **WS disconnect** | Heartbeat timeout (10 s) | Auto-reconnect with exponential backoff (1s → 30s) |
| **REST rate limit** (429) | HTTP status | Retry with backoff; cache to disk for replay |
| **Token expiry** | 401 from REST | Auto-refresh (TODO: implement refresh_token flow) |
| **Stale data** (no tick > 5s) | Last-tick timestamp | Degraded mode: cancel pending orders, alert |
| **Order reject** | Broker response | Log + alert; do not retry |
| **Slippage > X%** | Fill price vs limit | Alert + pause for 60s |
| **Daily loss ≥ limit** | `OrderManager.daily_pnl` | Kill-switch ON, flatten all |
| **Net delta > limit** | `mark_to_market` Greeks check | Reduce / hedge with futures |

## Test Strategy

- **Unit tests** (`tests/test_features.py`, `test_signals.py`): feature math
  and signal logic with synthetic inputs
- **Integration tests** (TODO): replay NSE historical CSVs through full pipeline
- **Property tests** (TODO): invariant checks (PCR ≥ 0, GEX sign consistency)
- **Backtester** as the "system test": full day replay with assertions on
  drawdown, order count, and final PnL reasonableness

## Configuration Hot Reload

The `Config` object is a plain dict — the signal engine reads thresholds at
each `on_tick` call. To hot-reload:
```python
from config import get_settings
get_settings()["signals"]["momentum"]["buy_threshold"] = 0.6
```
For production: watch the YAML file with `watchdog` and re-emit.

## Observability

- **Logs** (loguru): structured, rotating, 30-day retention
- **Metrics** (planned: Prometheus): latency per stage, signal counts, PnL
- **Traces** (planned: OpenTelemetry): tie a signal to its triggering ticks
- **Audit log**: every order + signal persisted with µs timestamp
