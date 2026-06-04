# CLOUDE.md - Institutional-Grade Intraday NIFTY Options Trading System

This document serves as the absolute master engineering specification and quantitative architecture blueprint for the Intraday NIFTY Options Trading System. It defines the system state data structures, real-time mathematical pipelines, and strict execution risk containers required to build and deploy a production-ready system utilizing the Upstox Developer API (v2/v3).

---

## 1. Architectural Topology & Low-Latency Pipeline

The system is designed to treat volatility trends, order flow microstructure, dealer positioning, and options-to-spot premium dynamics as a synchronized, single vector space. It processes data across three decoupled layers to protect the system from latency loops or race conditions during rapid market spikes.

### 1.1 Ingestion & Protocol Layer
* **Protocol Ingestion:** Live feeds are ingested over the Upstox Market Data Feed API v3 via persistent WebSockets using binary Google Protocol Buffers (`MarketDataFeed.proto`). 
* **Symbol Lookup & Instrument Token Engine:** The system maintains an in-memory bidirectional hash map to continuously link standard exchange symbol strings (e.g., `NIFTY26JUN2622500CE`) to the unique, platform-specific `instrument_key` tokens required by Upstox (e.g., `NSE_FO|54321`).
* **Intraday Boundary Datetime Handler:** To process historical data gaps or check option chain expiration arrays safely during ingestion without hitting array boundary exceptions, the following precise list comprehension logic must be strictly implemented:
  ```python
  valid = [datetime.strptime(e, "%d-%b-%Y") for e in expiries["expiresDts"] if datetime.strptime(e, "%d-%b-%Y") >= t_date]
  
  
  
  
  PCR Regime,IV Drift Trend,Net GEX Zone,Microstructure Volume Behavior,Concurrent Flow Requirement,Definitve Algorithmic Action
Call-Heavy(PCR<0.7),Crushing(Sloping Down),Positive GEX(Net_GEX>0),Call Open Interest Unwinding;Volume < 1× Proxy,CE Premium Fading;PE Premium Flat,NO-GO(Volatility Trap / Premium Drain)
Call-Heavy(PCR<0.7),Expanding(Sloping Up),Negative GEX(Net_GEX<0),Call Open Interest Spiking;Volume > 3× Proxy,PriceCE​>VWAPCE​∧ PricePE​<VWAPPE​,GO (Aggressive Long Call Entry)(Gamma Squeeze Breakout)
Neutral Range(0.8≤PCR≤1.1),Expanding(Sloping Up),Zero Gamma Zone(Net_GEX≈0),Call Open Interest Dropping;Volume > 2× Proxy,PriceCE​>VWAPCE​∧ PricePE​<VWAPPE​,GO (Long Call Entry)(Short-Covering Accumulation)
Put-Heavy(1.1≤PCR≤1.4),Expanding(Sloping Up),Negative GEX(Net_GEX<0),Put Open Interest Building;Volume > 2× Proxy,PricePE​>VWAPPE​∧ PriceCE​<VWAPCE​,GO (Long Put Entry)(Bearish Momentum Breakdown)
Put-Heavy(1.1≤PCR≤1.4),Crushing(Sloping Down),Positive GEX(Net_GEX>0),Put Open Interest Unwinding;Volume Under 1× Proxy,PE Premium Fading;CE Premium Flat,NO-GO(Bull-Trap Counter Reversal)
Extreme Puts(PCR>1.4),Flat / Neutral,Positive GEX(High Pin Zone),Symmetrical Open Interest LoadAcross Adjacent Strikes,High Multi-Strike Premium Bleed;Zero Divergence Gaps,NO-TRADE TRAP(Institutional Strangle Writing)




***

### 2. `INSTRUCTIONS.md` (Operational Execution Guide)

```markdown
# INSTRUCTIONS.md - System Deployment & Runtime Operational Runbook

Follow this step-by-step runtime manual to configure, validate, and execute the automated options trading engine generated using the system architecture definitions in `CLOUDE.md`.

---

## 1. System Environment Setup

The code requires a low-latency environment running Python 3.10 or higher.

### 1.1 System Packages Installation
Install the necessary numerical, mathematical, and protocol-buffer network libraries:
```bash
pip install numpy pandas websockets protobuf requests python-dotenv redis


***

### 3. `PROMPT.txt` (AI Coding Agent Orchestrator System Prompt)

```text
System Prompt for AI Coding Agent: Complete Implementation of Institutional Options Buying Framework

You are acting as an Expert Quantitative Developer, Low-Latency Options Infrastructure Engineer, and Institutional Algorithmic Execution Specialist. Your singular mandate is to generate the complete, production-grade, and ready-to-run Python source code files for the Intraday NIFTY Options Trading System based strictly on the mathematical definitions, architectural layers, and safety boundaries defined in CLOUDE.md.

### Core Architecture Implementation Protocols:
1. All modules must utilize strict static typing parameters via Python's typing library. Stale code blocks, stubbed comments, or partial placeholders are completely banned; write every single line of logic out in full.
2. Encapsulate data processing routines across separate object definitions: IngestionEngine, FeatureComputationEngine, CompositeSignalEngine, and OrderRiskManager.
3. Incorporate the exact logic requested for the historical datetime boundary exception handler during option chain parsing:
   valid = [datetime.strptime(e, "%d-%b-%Y") for e in expiries["expiresDts"] if datetime.strptime(e, "%d-%b-%Y") >= t_date]
4. Enforce the Multi-Variable Concurrent Pressure Check stringently within the signal verification process. Long call entries must be blocked unless Call Option buying pressure exists alongside Put Option selling pressure concurrently (Price_CE > VWAP_CE and Price_PE < VWAP_PE).
5. Implement the multi-variable volume proxy tracking heuristic. Calculate volumePercent via volume / ta.sma(volume, 20) to plot reference indicators representing 2x, 3x, and 4x standard volume surges to identify wick modifications and institutional participant interest.
6. Embed risk governance structures into the active transaction loop: calculate dynamic lot parameters based on 2% capital risk targets, implement a 10% hard stop-loss, and code a 15% activation threshold with a 5% trailing take-profit trailing buffer.
7. Build standalone network watchdogs to evaluate incoming connection intervals. If quote stream latency prints data delivery gaps exceeding 5 consecutive seconds, trigger the degraded-mode routine to halt new entries and cancel or liquidate open near-zero gamma positions instantly.
8. Set up high-resolution microsecond log tracking format strings ('%Y-%m-%d %H:%M:%S.%f') across every component trace.

Generate the code files directly, ensuring total end-to-end operational compilation ready for testing and live production deployment based on the instructions inside INSTRUCTIONS.md.

