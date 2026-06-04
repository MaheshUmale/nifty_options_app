# NIFTY Options Trading System - Master Engineering Specification

This document consolidates the quantitative strategy, architectural blueprints, and operational procedures for the institutional-grade intraday NIFTY options buying system.

---

## 1. Strategy & Quantitative Edge

The system treats volatility, order flow, and market-maker positioning as a synchronized ecosystem. It seeks composite signatures where multiple indicators align.

### 1.1 Volatility-OI Nexus
- **Core Principle**: Avoid "IV-Crush Traps" where PCR is high but implied volatility (IV) is collapsing.
- **Breakout Profile**: Moderate PCR (~1.0) + Rising IV + Increasing Call OI.
- **Trap Profile**: High PCR (>1.15) + Collapsing IV.

### 1.2 Market-Maker Gamma Hedging
- **Call Wall**: Strike with the largest call gamma; dealers are short calls here and must buy underlying as price breaches this level.
- **Put Wall**: Symmetric level on the downside.
- **Gamma Flip**: The "Zero-Gamma" level marking a regime change (above is dampening, below is amplifying volatility).
- **Trigger**: Price crossing an OI wall in a negative-gamma zone.

### 1.3 Lead-Lag & VWAP Divergence
- **Divergence**: Spot flat + Call-premium VWAP up + PCR↑ + Call OI↓ (short covering accumulation).
- **Concurrent Pressure**: Long call entries require `Price_CE > VWAP_CE` AND `Price_PE < VWAP_PE`.

---

## 2. Technical Architecture

The system is decoupled into three layers to ensure low latency and prevent race conditions.

### 2.1 Ingestion Layer
- **Protocols**: Upstox REST V2 and WebSocket V3 (Protobuf).
- **Symbol Engine**: Bidirectional hash map linking exchange strings (e.g., `NIFTY26JUN2524000CE`) to Upstox `instrument_key` tokens.

### 2.2 Feature & Signal Engine
- **PCR Regime**: <0.7 (Bullish), 0.7-1.1 (Neutral), >1.1 (Bearish).
- **IV Trend**: Slope of ATM IV over 15-minute windows.
- **Momentum Index**: Weighted score of `PCR_slope`, `VWAP_gap`, and `GEX_flow`.
- **Master Execution Matrix**: Final GO/NO-GO decision logic applying time-of-day filters.

### 2.3 Execution & Risk Layer
- **Risk Governance**: 2% capital risk per trade, 10% hard stop-loss, 15% take-profit threshold with 5% trailing buffer.
- **Network Watchdog**: Liquidates near-zero gamma positions if data delivery gaps exceed 5 seconds.

---

## 3. Composite Execution Matrix

| PCR Regime | IV Trend | GEX Zone | OI Pattern | Action |
|---|---|---|---|---|
| PCR < 0.7 | Crushing | Positive | Calls building | **NO-GO** (Volatility Trap) |
| PCR < 0.7 | Expanding | Negative | Calls spiking | **GO** (Gamma Squeeze) |
| 0.8 ≤ PCR ≤ 1.1 | Expanding | Zero Gamma | Call OI dropping | **GO** (Short-Covering) |
| 1.1 ≤ PCR ≤ 1.4 | Expanding | Negative | Put OI building | **GO** (Momentum Breakdown) |
| 1.1 ≤ PCR ≤ 1.4 | Crushing | Positive | Puts unwinding | **NO-GO** (Bull-Trap) |
| PCR > 1.4 | Neutral | Positive | Symmetrical Load | **NO-TRADE** (Strangle Writing) |

---

## 4. Operational Runbook

### 4.1 Deployment
1. Set up `.env` with `UPSTOX_ACCESS_TOKEN`.
2. Run `python -m main smoke` for sanity check.
3. Launch dashboard: `python -m main dashboard --port 8050`.

### 4.2 Time-of-Day Blocks
- **Opening Hour (9:15-10:15)**: High conviction required; noise from overnight hedges.
- **Midday Lull (11:30-13:30)**: Lean passive; avoid low-volume false signals.
- **Power Hour (14:30-15:30)**: Focus on Max Pain shifts and gamma pin effects.
