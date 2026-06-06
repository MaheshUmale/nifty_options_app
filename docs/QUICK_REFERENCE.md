# Quick Reference

## Commands

| Action | Command |
|--------|---------|
| **Smoke Test** | `python3 src/main.py smoke` |
| **Run Dashboard** | `python3 src/main.py dashboard --port 8000` |
| **Run Backtest** | `python3 src/main.py backtest --minutes 375` |
| **Collect History** | `python3 scripts/collect_data.py --days 5` |
| **Backtest SQLite** | `python3 src/main.py backtest --source sqlite --start-date 4-Jun-2026` |
| **Unit Tests** | `PYTHONPATH=src python3 -m pytest tests/ -v` |

## Configuration (.env)

| Key | Description |
|-----|-------------|
| `APP_MODE` | `live`, `mock`, `replay`, or `backtest` |
| `UPSTOX_ACCESS_TOKEN` | Your OAuth2 access token |
| `UPSTOX_SPOT_INSTRUMENT_KEY` | e.g. `NSE_INDEX\|Nifty 50` |

## WebSocket API

- **Endpoint**: `/ws/ticks`
- **Payload (Tick)**:
  ```json
  {
    "type": "tick",
    "data": {
      "instrument_key": "NSE_INDEX|Nifty 50",
      "ltp": 24000.50,
      "volume": 1234,
      "oi": 5678,
      "greeks": { "delta": 0.5, "gamma": 0.001 }
    }
  }
  ```
- **Payload (Signal)**:
  ```json
  {
    "type": "signal",
    "data": {
      "decision": "GO",
      "pcr": 1.12,
      "net_gex": 140000000,
      "sub_vol_oi": "BUY",
      "confidence": 0.85
    },
    "positions": { "n_positions": 1, "daily_pnl": 500 }
  }
  ```

## Configuration (settings.yaml)

```yaml
app:
  mode: replay
replay:
  db_path: data/nifty_historical.db
  start_date: "5-Jan-2026"
```

## Key Files

- `src/app.py`: Main FastAPI app & WebSocket logic.
- `src/ingestion.py`: Upstox V3 WebSocket source.
- `src/database.py`: DuckDB storage & async flusher.
- `src/templates/index.html`: Dashboard frontend.
- `src/signals/orchestrator.py`: Multi-factor signal engine.
- `src/execution/order_manager.py`: Risk controls & execution.
