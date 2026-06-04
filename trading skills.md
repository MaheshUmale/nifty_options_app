# SKILLS.md

## Executive Summary  
This document outlines the technical, quantitative, and soft skill requirements for a Quantitative Options/HFT Coding Agent and Live Trading Analyst. It also translates high-level research goals (e.g. Volatility-OI Nexus, Gamma Hedging, Lead-Lag signals) into concrete data-processing and algorithmic tasks. We list each required skill with proficiency level, typical responsibilities, example tools/libraries, and measurable acceptance criteria. We specify data inputs (tick-level, market data, option chains, etc.), sampling rates, latency targets, and storage needs for each feature. We present a **Master Composite Execution Matrix** (a decision table) that cross-references PCR regimes with IV trends, Gamma Exposure zones, and open-interest behavior, indicating clear **GO/NO-GO** triggers. Pseudocode snippets demonstrate key composite signal computations (Volatility-OI Nexus, Gamma hedging clues, Premium vs Spot divergence, Time-of-Day filters, No-Trade signatures). Finally, we define a unit/integration test checklist and outline monitoring, alerting, and fail-safe procedures (circuit breakers, kill switches, degraded-mode) for live deployment. This SKILLS.md is concise, structured, and ready for a development team to implement, with references to industry standards and libraries.

## Technical Skills

- **Python (Expert)** – Develop and prototype algorithms and data pipelines.  
  **Tasks:** Ingest and process tick/quote data, implement signal computations, build backtest frameworks and monitoring scripts.  
  **Example Tools:** Pandas, NumPy, TA-Lib, Numba for JIT optimization, Matplotlib/Plotly for visualization, PyTest for testing.  
  **Acceptance Criteria:** Clean, modular code with full test coverage; meeting latency targets (e.g. end-to-end signal update within ~100ms under load); proper handling of edge cases and missing data.

- **C/C++ (Expert)** – Implement latency-critical components (data handlers, order routing).  
  **Tasks:** Build low-level data listeners (e.g. via sockets or pcap), optimized numeric kernels (e.g. option pricing, Greeks computation), ultra-low-latency order gateways.  
  **Example Tools:** GCC/Clang compilers, Boost.Asio for networking, Intel TBB/OpenMP for parallelism.  
  **Acceptance Criteria:** Achieve microsecond-level response (e.g. <5µs order generation), memory-safe code, benchmarked throughput, integration with exchange APIs, adherence to clean code standards.

- **Data Engineering & Databases (Advanced)** – Manage large historical and streaming datasets.  
  **Tasks:** Design schemas for tick data and option chains; build ETL pipelines from exchanges/venues; optimize for query performance.  
  **Example Tools:** kdb+/q for time-series (millions of ticks/sec), InfluxDB/ClickHouse for aggregated metrics, Kafka/RabbitMQ for message queues.  
  **Acceptance Criteria:** Data ingestion at production rates without loss; sub-second queries on multi-day data; data compression/archival policies; clear documentation of data schemas.

- **Real-Time Messaging & APIs (Advanced)** – Interface with market data and execution systems.  
  **Tasks:** Connect to exchange feeds (FIX, binary protocols), parse L1/L2 quotes and trades, send orders via FIX/REST/WebSocket APIs.  
  **Example Tools:** QuickFIX (C++/Python) for FIX, exchange SDKs (e.g. CME MD/AQ APIs), sockets/ZeroMQ for custom feeds.  
  **Acceptance Criteria:** Continuous data feed with <5ms end-to-end lag; automatically reconnect/handle dropouts; accurate message parsing and order acknowledgements; adhere to exchange protocols.

- **Distributed & Low-Latency Infrastructure (Intermediate)** – Ensure fast, scalable execution.  
  **Tasks:** Deploy services on dedicated Linux servers (tuned network/stack), containerize (Docker), maintain host OS (kernel tuning, NIC settings).  
  **Example Tools:** Linux (Ubuntu/CentOS), Docker/Kubernetes, Linux perf/FlameGraphs, DPDK for ultra-low-latency networking.  
  **Acceptance Criteria:** Consistent throughput with <1% CPU overhead from OS, microsecond timestamp accuracy (e.g. via PTP or GPS), auto-scaling pipelines for load.

- **Version Control & CI/CD (Intermediate)** – Manage code quality and deployment.  
  **Tasks:** Write unit/integration tests, use Git workflows, continuous integration (Jenkins/GitHub Actions), code reviews.  
  **Acceptance Criteria:** 100% of new code covered by tests; all merges pass linting and performance benchmarks; automated deployment scripts.

- **Trading & Risk Systems (Intermediate)** – Integrate with risk monitoring tools.  
  **Tasks:** Query position/risk databases, enforce risk limits, log PnL and performance.  
  **Example Tools:** Custom in-house risk API, or industry platforms (Murex/Calypso), FIX order routing flags, FINRA/T+1 reports.  
  **Acceptance Criteria:** Real-time risk checks on each trade (no breaches allowed); compliance with exchange regulatory feeds; logging for audits.

## Quantitative Skills

- **Options Pricing & Greeks (Expert)** – Model option values, sensitivities and surfaces.  
  **Tasks:** Compute Black–Scholes/Merton Greeks (Δ,Γ,Θ,ν); calibrate implied volatility (IV) surfaces (e.g. SVI/JW models); model time decay.  
  **Example Tools:** QuantLib or custom C/Python implementations; use SciPy for calibration.  
  **Acceptance Criteria:** Greeks consistent with exchange data (e.g. <1% error vs known values); IV surface smoothness (no arbitrage); correct θ acceleration curves; documented validation against benchmarks.

- **Implied Volatility and Skew Analysis (Advanced)** – Analyze IV trends and skew behavior.  
  **Tasks:** Track IV of calls vs puts across strikes (IV skew); measure IV changes over time; detect “IV crush” or expansion events.  
  **Acceptance Criteria:** Automated computation of IV skew metrics each minute; statistical validation (e.g. correlation with realized vol); timely flags when IV trend diverges from norms.

- **Gamma Exposure (GEX) & Market Maker Dynamics (Advanced)** – Compute net gamma and hedging signals.  
  **Tasks:** Aggregate per-strike gamma (Γ) weighted by open interest to get net Gamma Exposure; find “zero gamma” price levels; monitor delta-hedging triggers.  
  **Example Tools:** Python/NumPy for calculations, possibly accelerated by Numba/Cython; SpotGamma-like models for dealer vs customer flows.  
  **Acceptance Criteria:** GEX time series updating in real time (<1s lag) using live trades; correct identification of gamma flip zones; backtested ability to signal hedging events.

- **Order Flow & Open Interest Analytics (Expert)** – Analyze volume, open interest, and positioning.  
  **Tasks:** Calculate Put/Call ratios (PCR) from live volume and OI; detect OI walls (strikes with large OI); compute Max Pain levels from OI distribution; track intraday OI changes.  
  **Example Tools:** Pandas for data tables, NumPy for numeric ops.  
  **Acceptance Criteria:** Correct PCR and OI metrics each minute; table of top OI strikes; real-time “smart money straddle shifts” via cumulative OI at multiple strikes; tests confirming data aggregation logic.

- **Market Microstructure (Advanced)** – Understand tick-level behavior and time-of-day effects.  
  **Tasks:** Analyze bid/ask book, trades, and price action patterns; segment day (open/midday/close) and compare behaviors; incorporate execution microstructure into signals.  
  **Acceptance Criteria:** Verified detection of typical patterns (opening auction spikes, lunchtime lulls, end-of-day runs); empirically-backed time-of-day filters (e.g. avoid trading during midday with low volume).

- **Statistical & Machine Learning (Intermediate)** – Analyze multi-variate signals and implement algorithms.  
  **Tasks:** Correlation analysis (e.g. PCR vs IV changes), regression/pca for feature reduction, anomaly detection on feed quality. May use ML models (scikit-learn, XGBoost) for regime classification.  
  **Example Tools:** scikit-learn, PyTorch/TensorFlow for custom models.  
  **Acceptance Criteria:** Model validation metrics (accuracy/R^2) on historical signals; automated feature pipelines with unit tests; resource usage within limits.

- **Signal Development & Backtesting (Advanced)** – Build and test trading signals.  
  **Tasks:** Implement trading logic combining features (Vol-OI composite, gamma hedging clues, etc.); backtest on historical intraday data; refine signals.  
  **Example Tools:** Backtesting frameworks (e.g. Zipline, QSTrader) or custom engine; vectorized Pandas calculations.  
  **Acceptance Criteria:** Backtest results with realistic costs/slippage; Sharpe ratios and drawdowns meeting design criteria; reproducible performance in paper trading before live.

## Soft Skills

- **Decision-Making Under Pressure** – Rapid judgment on GO/NO-GO signals.  
  **Tasks:** Assess real-time signal validity, weigh risk-reward quickly, collaborate with trading desk in volatile markets.  
  **Acceptance Criteria:** Consistent justification of actions; post-mortem analysis of decisions; positive peer feedback on sound reasoning.

- **Incident Response and Risk Awareness** – React to system anomalies or market crises.  
  **Tasks:** Execute kill-switch protocols; communicate with risk managers; adapt strategies during market dislocations (circuit breaker events).  
  **Acceptance Criteria:** Adherence to fail-safe checklists; timely escalation of alerts; no major errors in simulated crash drills.

- **Communication & Collaboration** – Work with developers, traders, and compliance.  
  **Tasks:** Document algorithms and tests; present signal rationale; write clear code comments.  
  **Acceptance Criteria:** Reviewed documentation for each signal; code reviewed and approved; training materials for other analysts.

- **Adaptability & Learning** – Stay updated on market structure changes.  
  **Tasks:** Research new order types, exchange features, regulatory updates; refine models accordingly.  
  **Acceptance Criteria:** Incorporate at least one new data source or technique per quarter; continuous improvement of models.

## Feature Engineering & Signal Computation

- **PCR and Sentiment Signals:** Compute real-time *Put/Call Ratio* (e.g. volume of puts / volume of calls, or vice versa) for index options. Categorize into regimes (e.g. PCR \<0.7, 0.7–1.0, >1.0). Tasks: stream aggregated volumes from trades or quotes; update ratio each second. Feature: *PCR Trend* (derivative) and *PCR Change from Open* (difference from session start). Input: tick/trade data (calls and puts) at 1–5 second sampling. Latency: \<1s for updates. Storage: keep 1-minute PCR history; raw tick data stored (unspecified retention). Acceptance: ratio matches known values (e.g. CBOE data).

- **Implied Volatility Skew & Theta:** From live option quotes (or trades), extract at-the-money (ATM) and near-the-money (NTM) IV for calls and puts. Compute **IV Skew** = CE_IV / PE_IV or difference at given strike. Track **IV Trend**: e.g. moving averages of IV or its slope over 5–15 min. Compute *Time Decay (Theta)*: using option pricing (QuantLib/BS) to estimate acceleration of theta for NTM options. Input: continuous quote stream at 1s or tick resolution. Output: skew and theta curves per minute. Acceptance: stable IV surface with correct sign (calls typically > puts if bullish skew). 

- **Gamma Exposure (GEX):** Calculate net gamma = Σ (Γ_i * net open interest_i) across strikes and expirations. Use intraday OI estimates (adjust official OI with trade flow). Identify *Zero-Gamma level*: price where net gamma ≈0. Determine *GEX Zones*: positive (>0) or negative (<0) net gamma. Input: trade prints, intraday OI, option Greeks; sampling: update on every sizable trade or max 1s. Latency: \<100ms for gamma calc. Acceptance: GEX sign flips match major price moves in test data; zero-gamma aligns with support/resistance from backtest.

- **OI Walls & Institutional Positioning:** Detect *OI Walls* by finding strikes with unusually large open interest (e.g. top 5% of OI values). Track *Total OI* and *Intraday OI Changes* per strike. Compute *Max Pain* (price minimizing intrinsic value sum) each interval and shifts. Compute *Cumulative OI shifts* (e.g. sum of changes across straddle/strangle strikes). Input: official OI (updated EOD) plus intraday volume adjustments; sampling: OI updates as received (min once/day, intraday adjustment every 1–5min). Latency: intraday OI used within 1min of trade. Acceptance: stress-tested on sample sessions with known OI walls; max-pain computation sanity-checked.

- **Volume-Premium VWAP:** For NTM call and put series, compute *Premium Volume Weighted Average Price* (PVWAP = Σ(price * volume)/Σ(volume)) and underlying *Spot VWAP* over rolling windows (e.g. 5min). Monitor deviation: e.g. (PVWAP_call – SpotVWAP). Input: trade ticks for underlying and selected options; sampling tick-level or aggregated 1s. Acceptance: VWAPs converge to expected under neutral conditions; divergence correlates with directional moves (validated on backtest).

- **Composite Signal Computations:** Combine features as per research objectives. For example, *Volatility-OI Nexus*: when (PCR in bull regime **AND** IV Skew collapsing **AND** OI on calls spiking) ⇒ signal a “Vol-Crush Bull Trap” (NO-GO on call buys). Conversely, (PCR bull regime **AND** IV expanding **AND** increasing call OI) ⇒ “High-Velocity Breakout” (GO). *Gamma Hedging Clue*: near zero-gamma price + heavy OI wall in calls + accelerating underlying = trigger for market-maker shorting (GO to buy calls anticipating squeeze). *Lead-Lag (Premium vs Spot)*: if spot range-bound, but NTM call premium breaks above VWAP while PCR rising and ATM call OI dropping (short-covering), then this signals latent bullish accumulation (GO). Each composite requires synchronized input streams (PCR, IV, OI, spot).  

- **Time-of-Day Segmentation:** Tag data into three windows: **Morning Open** (first 60m), **Midday Dull** (lunch hours), **Afternoon Run** (last hour). Adjust filters per block: e.g. ignore small signals midday, tighten criteria at open, relax on final hour. Monitor PCR change, Max Pain shift, OI flows in context. Acceptance: backtests show significantly different performance by time block; rules flag historically correct/no-trade periods.

- **No-Trade (Trap) Signature:** Detect when *PCR is flat (near neutral)* **AND** *Max Pain stationary* **AND** *massive OI build-up on both CE and PE* (e.g. writes of short strangles/straddles). This indicates premiums draining to theta – a signal to avoid new longs. Implementation: if flat PCR (e.g. within ±5% of open) and Net OI change > X at adjacent strikes with balanced CE/PE buildup, raise NO-TRADE flag.  

*Input Data Types:* Level-1 market data (best bid/ask, last trade) for underlying index; Level-1/2 option quotes and trades; daily OI snapshots (exchange) + intraday trade flow; historical tick data for backtests. *Sampling Rates:* Underlying and option quotes at millisecond-level or 1-second bars; aggregated features (PCR, GEX) updated 1–5s. *Latency Targets:* Final composite signals computed within ~100ms of data ingestion (preferably <50ms) to allow timely execution. *Storage/Retention:* Raw tick data stored long-term (e.g. 1 year or more); aggregated features (per-minute summaries) kept for multi-year backtesting. (Where unspecified, marked as “unspecified”.)

## Master Composite Execution Matrix

| PCR Regime                  | IV Trend       | Gamma Zone       | OI Behavior                                 | Decision (GO/NO-GO)                                                 |
|-----------------------------|---------------|------------------|---------------------------------------------|--------------------------------------------------------------------|
| **Low** (PCR ≪ 0.7: *Bullish*, many calls)  | Expanding      | **Negative GEX** (gamma short)  | Rising *Call OI* (accumulation)                     | **GO**: Expect breakout (bull trend). Buy calls if premium signals confirm.  |
| **Low** (PCR ≪ 0.7)          | Crushing (fall) | **Positive GEX** (gamma long)  | Neutral OI or balanced builds                     | **NO-GO**: Bear trap likely; time decay dominates. Avoid new longs.        |
| **Neutral** (PCR ~0.7–1.0)    | Expanding      | near-zero or **Positive GEX** | Mixed/flat OI             | *Conditional*: Possibly opportunistic buys if confirmation; otherwise sideline. |
| **High** (PCR ≫1.3: *Bearish*, many puts) | Expanding      | **Negative GEX**            | Rising *Put OI* (hedging support)                 | **GO (Aggressive)**: Expect momentum breakout downward.  Short or buy puts.  |
| **High** (PCR ≫1.3)           | Crushing (fall) | **Positive GEX**           | Symmetric OI build (sell-side)                   | **NO-GO**: Volatility drain; market biased sideways. Avoid directional bets.   |

*Notes:* PCR regimes refer to put/call flow (e.g. PCR≪0.7 indicates call-heavy bullish sentiment). “Expanding IV” means rising implied volatility (momentum likely); “Crushing IV” is a rapid IV drop (trap risk). Positive GEX (net dealer gamma long) implies range-biased market; negative GEX implies trend bias. OI behavior distinguishes accumulation (e.g. build-up in calls) vs balanced writing. Triggers: **GO** when all bullish or bearish signals align (e.g. bull PCR + rising IV + heavy call OI; or bear PCR + rising IV + heavy put OI). **NO-GO** when mixed signals (e.g. bullish PCR but IV collapsing) indicate traps. The neutral regime requires further confirmation. This matrix guides automated decision logic for each minute.

## Algorithmic Pseudocode Snippets

```python
# 1) Volatility-OI Nexus (Bull Trap vs Breakout)
if PCR > 1.1 and IV_skew_decreasing and call_OI_increase > threshold:
    signal = "NO_TRADE  # High bull trap risk (IV crush impending)"
elif PCR > 1.1 and IV_expanding and call_OI_increase > threshold:
    signal = "BUY_CALLS  # Momentum breakout"
```

```python
# 2) Gamma Hedging Clue
# Identify zero-gamma price and heavy OI walls
if abs(spot_price - zero_gamma_level) < gamma_level_buffer:
    if call_OI_wall_nearby > put_OI_wall_nearby * 1.5:
        signal = "SHORT_COVER  # MMs likely to buy (positive squeeze ahead)"
    elif put_OI_wall_nearby > call_OI_wall_nearby * 1.5:
        signal = "SHORT_OPTS  # MMs likely to sell underlying (downward risk)"
```

```python
# 3) Premium vs Spot Lead-Lag (Institutional Accumulation)
if spot_range_bound and call_premium_VWAP > spot_VWAP and PCR_trend > 0.1:
    if atm_call_OI_drop_significant:
        signal = "BUY_CALLS  # Short-covering sign"
```

```python
# 4) Time-of-Day Filter
if time < 10:30:
    apply_strict_thresholds()
elif time in [11:30,13:00]:
    raise_alert_suppression  # midday lull
elif time > 15:30:
    widen_signals()  # afternoon running
```

```python
# 5) No-Trade Signature
if abs(PCR - PCR_open) < 0.05 and max_pain_shift < epsilon and \
   CE_OI_addition + PE_OI_addition > large_threshold:
    signal = "NO_TRADE  # Short straddle writing, premiums decaying"
```

### Test & Validation Checklist
- *Unit Tests for Feature Calculations:* e.g. feed synthetic option chains to verify IV skew, Gamma, Theta, and PCR calculations produce expected results.  
- *Integration Tests for Data Pipelines:* simulate streaming trade data and ensure the end-to-end flow (ingest → compute features → trigger signals) works correctly.  
- *Backtesting Tests:* apply signals on historical intraday sessions; verify results against known outcomes (e.g. bull-trap episodes should have given `NO_TRADE`).  
- *Latency and Throughput Tests:* benchmark data ingestion and signal update times under load; ensure single-update (from data to alert) completes <100ms.  
- *Edge Case Handling:* test market halts, data gaps, zero volume periods; verify safe behavior (e.g. no false signals on missing data).  
- *Performance Regression:* monitor memory/CPU use; integrate checks that new code does not degrade performance beyond X%.  
- *Deployment Dry-Run:* simulate failover and kill-switch activation to ensure automated processes intervene as designed.

## Monitoring, Alerting, and Fail-Safes

- **Automated Strategy Monitoring:** Continuously track key metrics per strategy (order rate, cancel/fill ratio, position P&L, net delta). Use a monitoring platform (e.g. Grafana or 3rd-party) to visualize these in real time. Set thresholds (e.g. abnormal order rate or slippage) to trigger immediate alerts.  
- **Circuit Breakers & Kill Switch:** Implement an emergency kill-switch that, when activated, _immediately_ disables all trading and cancels working orders. Trigger this on extreme losses, regulatory halts, or rule violations. For example, PnL drawdown > X% or catastrophic system error should invoke kill-switch.  
- **Degraded-Mode Behavior:** Define fallback procedures if market data or connectivity fails (e.g. switch to static spreads or close positions). For instance, if option feed stalls >5s, shut off new orders and clear near-zero gamma positions to minimize exposure.  
- **Alerting:** Send automated alerts (email/SMS/Slack) to analysts and risk managers on critical events: signal breaches, latencies > threshold, kill-switch events, etc. Maintain an audit log with microsecond timestamps for all signals and actions for compliance.  
- **Risk Limits Enforcement:** Monitor positions against pre-set limits (size, delta, gamma). If any limit is breached or about to, suspend trading until reviewed. This is in addition to kill-switch and serves as a pre-trade check.  
- **Audit & Compliance:** Ensure every kill-switch activation and signal is logged with context. Provide operators with dashboards summarizing system health and strategy activity (helps meet regulatory requirements).

