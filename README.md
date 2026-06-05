# NIFTY Zero-Lag Scalper

> **Institutional-grade intraday NIFTY options buying system** featuring a high-frequency, event-driven architecture. Built on **FastAPI**, **Upstox API V3**, and **DuckDB**, this system provides zero-lag updates and real-time analytical storage.

![status](https://img.shields.io/badge/status-Production--Ready-success) ![python](https://img.shields.io/badge/python-3.11%2B-blue) ![license](https://img.shields.io/badge/license-MIT-green)

---

## ✨ Features

- **Event-Driven Backend**: Powered by **FastAPI** for high-performance, asynchronous processing.
- **Zero-Lag UI**: Real-time dashboard using **Vanilla JavaScript** and **TradingView Lightweight Charts** via WebSockets.
- **Upstox V3 Streaming**: Native integration with the official **MarketDataStreamerV3** for low-latency Protobuf-decoded ticks.
- **Analytical Storage**: High-throughput storage layer using **DuckDB** with asynchronous batching and flushing.
- **5 feature modules**: PCR, IV Skew/Trend/Theta, GEX (+Walls +Zero-Gamma), OI Walls/Max Pain, VWAP.
- **Composite signal engine** with 4 sub-signals + Master Execution Matrix decision logic.
- **Order manager** with risk controls (max notional, daily-loss kill-switch, time stops).
- **Comprehensive Testing**: 23 unit tests and a full end-to-end smoke test suite.

## 🏗️ Architecture

```
nifty_options_app/
├── config/
│   ├── settings.yaml        # thresholds, weights, time blocks
│   └── .env.example
├── src/
│   ├── main.py              # CLI entry (dashboard, backtest, smoke)
│   ├── app.py               # FastAPI application & WebSocket broadcast
│   ├── ingestion.py         # Upstox V3 MarketDataStreamerV3 integration
│   ├── database.py          # DuckDB async buffer & flusher
│   ├── config.py            # config loader (yaml + env)
│   ├── data/
│   │   ├── upstox_client.py # OAuth2 + REST (option chain, PCR, OI, max-pain)
│   │   ├── store.py         # Legacy DuckDB storage layer
│   │   └── mock_data.py     # Synthetic NIFTY option-chain generator
│   ├── features/            # Feature extraction modules (PCR, IV, GEX, etc.)
│   ├── signals/             # Signal processing & orchestration
│   ├── execution/           # Position tracking & order routing
│   ├── templates/
│   │   └── index.html       # Lightweight TradingView-based frontend
│   └── utils/
│       ├── logger.py
│       └── time_utils.py
├── tests/                   # Unit test suite
└── docs/                    # Documentation
```

## 🚀 Quickstart

### 1. Install
```bash
cd nifty_options_app
pip install -r requirements.txt
cp .env.example .env       # fill in Upstox keys
```

### 2. Smoke test
```bash
python3 src/main.py smoke
```

### 3. Run the live dashboard
```bash
python3 src/main.py dashboard --port 8000
```
Opens the Zero-Lag Scalper UI at <http://127.0.0.1:8000>.

## 📊 The Scalper's Architecture

The system is decoupled into five operational layers for maximum performance:
1.  **Ingestion Layer**: Asynchronous Python using Upstox `MarketDataStreamerV3`.
2.  **In-Memory Cache**: Global async dictionaries for ultra-low-latency metric access.
3.  **Analytical Database**: **DuckDB** handles sequential chunk commits every 2 seconds.
4.  **Backend API**: **FastAPI** broadcasts tick payloads via high-speed WebSockets.
5.  **Frontend Layer**: **TradingView Lightweight Charts** renders thousands of ticks per second effortlessly.

## 🧪 Testing
```bash
PYTHONPATH=src python3 -m pytest tests/ -v
```

## 🔌 AI Integration (MCP)
This project is compatible with the **Upstox MCP Server**, allowing AI agents (Claude, Cursor) to securely access market data and perform technical analysis directly within your development environment. See [docs/MCP_INVESTIGATION.md](docs/MCP_INVESTIGATION.md) for details.

## ⚠️ Disclaimer
This is a research/educational implementation. **No warranty of profitability.** Indian F&O trading carries substantial risk; test in paper mode extensively.

## 📚 References
- Upstox API V3 — <https://upstox.com/developer/api-documentation>
- TradingView Lightweight Charts — <https://www.tradingview.com/lightweight-charts/>
- Model Context Protocol — <https://modelcontextprotocol.io/>
