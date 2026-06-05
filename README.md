# NIFTY Options Buyer

> **Institutional-grade intraday NIFTY options buying system** built from the
> research spec in `SKILLS.md`. Combines PCR, IV skew, GEX, OI walls, and VWAP
> divergence into a composite **GO / NO-GO** decision engine with live
> dashboard, backtester, and order routing.

![status](https://img.shields.io/badge/status-MVP-blue) ![python](https://img.shields.io/badge/python-3.11%2B-blue) ![license](https://img.shields.io/badge/license-MIT-green)

---

## ✨ Features

- **Live data**: Upstox V2 REST + V3 WebSocket (OAuth2, Protobuf) with auto-reconnect
- **Mock mode**: deterministic synthetic NIFTY option-chain generator for dev & backtest
- **5 feature modules**: PCR, IV Skew/Trend/Theta, GEX (+Walls +Zero-Gamma), OI Walls/Max Pain, VWAP
- **Composite signal engine** with 4 sub-signals + Master Execution Matrix decision logic
- **Backtester** with support for synthetic and real polled market data (from DuckDB)
- **Order manager** with risk controls (max notional, daily-loss kill-switch, time stops)
- **Dash dashboard** with live PCR/GEX/IV/VWAP charts and decision cards
- **Data Persistence**: Automatic storage of live option chain snapshots in **DuckDB** for future analysis
- **23 unit tests** covering features, signals, and backtester

## 🏗️ Architecture

```
nifty_options_app/
├── config/
│   ├── settings.yaml        # thresholds, weights, time blocks
│   └── .env.example
├── src/
│   ├── main.py              # CLI entry (dashboard, backtest, smoke)
│   ├── config.py            # config loader (yaml + env)
│   ├── data/
│   │   ├── upstox_client.py # OAuth2 + REST (option chain, PCR, OI, max-pain)
   │   ├── streaming.py     # Polling-based REST streaming (replaces WebSocket)
   │   ├── store.py         # DuckDB persistent storage layer
│   │   └── mock_data.py     # Synthetic NIFTY option-chain generator
│   ├── features/
│   │   ├── pcr.py           # Put/Call Ratio (volume & OI) + regime classification
│   │   ├── iv_skew.py       # IV skew, IV trend (expanding/crushing), theta accel
│   │   ├── gex.py           # Net Gamma Exposure, call/put walls, zero-gamma
│   │   ├── oi_walls.py      # OI wall detection, Max Pain, strangle flag
│   │   ├── vwap.py          # VWAP (spot & NTM call/put), divergence detection
│   │   └── time_filters.py  # Time-of-day adaptive thresholds
│   ├── signals/
│   │   ├── state.py         # SignalState dataclass
│   │   ├── composite.py     # 4 sub-signals + Master Execution Matrix
│   │   └── orchestrator.py  # Threaded data → engine → output glue
│   ├── execution/
│   │   └── order_manager.py # Position tracking + risk + paper/live order routing
│   ├── backtest/
│   │   └── engine.py        # Intraday replay + slippage + metrics
│   ├── dashboard/
│   │   └── app.py           # Dash app with live charts
│   └── utils/
│       ├── logger.py
│       └── time_utils.py
├── tests/
│   ├── test_features.py     # 15 unit tests
│   └── test_signals.py      # 8 unit tests
└── docs/
    ├── ARCHITECTURE.md
    ├── SIGNALS.md
    └── DEPLOYMENT.md
```

## 🚀 Quickstart

### 1. Install
```bash
cd nifty_options_app
pip install -r requirements.txt
cp .env.example .env       # fill in Upstox keys if you have them
```

### 2. Smoke test (no API keys needed)
```bash
python -m main smoke
```
Sample output:
```
[1/4] Generating 30 minutes of synthetic intraday data…
[2/4] Running composite signal engine on first snapshot…
      Spot: ₹24,000.00
      PCR: 1.12 (bearish)
      IV ATM: 0.150
      Net GEX: ₹1982.23 Cr (positive)
      Call wall: 24000, Put wall: 24000
      Max pain: 24000.0
      Momentum index: +0.300
      Sub-signals: vol_oi=HOLD gamma=HOLD leadlag=HOLD notrade=HOLD
      DECISION: HOLD (conf 0.30)
[3/4] Running mini-backtest over 30 minutes…
      Trades: 3, PnL: ₹6,091, Win rate: 66.7%
SMOKE TEST COMPLETE ✓
```

### 3. Backtest (Synthetic or Real)

**On synthetic data:**
```bash
python -m main backtest --minutes 375 --seed 7
```

**On real data stored in DuckDB:**
```bash
python -m main backtest --source db
```
Runs an intraday backtest using real snapshots captured during live mode.
```
============================================================
BACKTEST RESULTS
============================================================
              n_trades: 24
             total_pnl: 215514.75
          win_rate_pct: 41.67
               avg_pnl: 8979.78
      avg_hold_minutes: 6.2
                sharpe: 15.58
          max_drawdown: -8661.5
============================================================
```

### 4. Run the live dashboard
```bash
python -m main dashboard --port 8050
```
Opens a Dash UI at <http://127.0.0.1:8050> showing live PCR, GEX, IV, VWAP, decision cards.

## 📊 The Composite Signal Pipeline

Every minute (or tick) the engine computes:

| Feature | Source | Range |
|---------|--------|-------|
| **PCR** (volume) | `Σ put_vol / Σ call_vol` | 0 – ∞ (regime: <0.7 bull, >1.1 bear) |
| **PCR Slope** | `dPCR/dt` over 5 min | % per min |
| **IV Skew** | `CE_IV_ATM - PE_IV_ATM` | negative for equity |
| **IV Trend** | `pct_change` over 15 min | "expanding" / "crushing" / "flat" |
| **Net GEX** | `Σ(gamma × OI × spot² × 0.01 × lot)` | ₹ |
| **Call/Put Wall** | strike with max gamma on each side | strike |
| **Zero-Gamma** | strike where cumulative GEX crosses 0 | strike |
| **Max Pain** | strike minimizing total intrinsic value | strike |
| **VWAP gap** | `NTM_call_VWAP - spot_VWAP` | ratio |
| **Strangle flag** | symmetric high OI on both sides | bool |

→ These feed the **4 sub-signals** (Vol-OI Nexus, Gamma Hedge, Lead-Lag, No-Trade Trap)
→ Which feed the **Momentum Index** (`w₁·PCR_slope + w₂·VWAP_gap + w₃·delta_flow`)
→ Which the **Master Execution Matrix** evaluates against time-of-day thresholds
→ Producing a final **GO / NO-GO / HOLD** decision with `confidence` and `suggested_strike`.

## 🧪 Testing
```bash
python -m pytest tests/ -v
```
23 tests cover feature math, signal engine, and order manager.

## 🔌 Going Live (Upstox)

1. Get API keys at <https://upstox.com/developer/api>
2. Set in `.env`:
   ```
   UPSTOX_API_KEY=...
   UPSTOX_API_SECRET=...
   UPSTOX_REDIRECT_URI=http://localhost:5000/callback
   ```
3. Run the OAuth flow:
   ```python
   from data.upstox_client import UpstoxClient, UpstoxCreds
   c = UpstoxClient(UpstoxCreds(KEY, SECRET, REDIRECT))
   print(c.build_login_url())   # open in browser, copy `code` from redirect
   c.exchange_code_for_token(code)
   # save access_token into .env
   ```
4. Set `APP_MODE=live` in `.env`
5. `python -m main dashboard`

The `OrderManager` is paper-trading by default. Flip `live=True` to route to Upstox Orders API
(extend `_route_live()` in `execution/order_manager.py`).

## 📐 Signal Logic — see [docs/SIGNALS.md](docs/SIGNALS.md)
The Master Execution Matrix and all sub-signal rules are documented there,
with thresholds and worked examples.

## 🏛️ Architecture — see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
Data flow, threading model, latency budget, and the data → signal → execution pipeline.

## 🚢 Deployment — see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
Docker, cloud options, monitoring stack, kill-switch procedures.

## ⚠️ Disclaimer

This is a research/educational implementation. **No warranty of profitability.**
Indian F&O trading carries substantial risk; test in paper mode extensively.
The synthetic data generator is for unit-testing only — its PnL numbers are not predictive.

## 📚 References

- SKILLS.md (the brief) — institutional quant trading skills matrix
- Upstox API V2 docs — <https://upstox.com/developer/api>
- NSE F&O — <https://www.nseindia.com/products-services/equity-derivatives>
- SpotGamma (GEX methodology)
- Black-Scholes (Greeks)
