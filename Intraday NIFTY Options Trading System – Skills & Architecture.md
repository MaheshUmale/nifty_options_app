# Intraday NIFTY Options Trading System – Skills & Architecture

**Executive Summary:** This document outlines the required **technical, quantitative, and trading skills** to design, build, and operate an institutional-grade intraday NIFTY options buying strategy. It details data sources (Upstox APIs, NSE feeds, alternatives), end-to-end system components, and composite signal logic linking volatility (IV), gamma exposure, sentiment (PCR, volume), and order-flow data. Key outputs include code libraries and roles (Coder, Quant Analyst, Execution Trader) skill matrices, an execution trigger table, pseudocode for composite indicators, data schemas, and monitoring/retraining processes. All instructions prioritize synchronized multi-variable signals (PCR, IV skew, GEX, OI, VWAP) across day phases. (Citations refer to Upstox API docs for data fields.)

## Data Sources & Integration  

- **Upstox Developer API (Open, Free):** Primary real-time and historical data source. Key endpoints:  
  - *Option Chain API:* Returns each strike’s last price (LTP), volume, OI, bid/ask, and Greeks (IV, Theta, Gamma, Delta) for calls and puts. This enables calculation of IV skew (CE vs. PE IV), GEX (gamma×OI), and time decay.  
  - *PCR API:* Intraday bucketed Put/Call Ratio and spot price per time interval. Supports sentiment regime detection.  
  - *Get OI / Change in OI:* Total call/put open interest by strike and net change over intervals. Used to identify OI “walls” and flow (institutional straddle/strangle writing).  
  - *Max Pain API:* Intraday max pain level (strike) time-series, to detect shifts in institutionally weighted strike.  
  - *Market Quotes & Websocket:* Live spot prices and option ticks. Upstox Websocket streams LTP, volume, OI updates (for VWAP calc), subject to rate limits (50 req/s on standard APIs).  

- **NSE Official Data:** For fallback and historical: contract-wise daily CSVs and option chain archives (via [NSE website](https://www.nseindia.com) or third-party downloads). E.g., NSE’s “Historical Contract-wise Price Volume” can supply end-of-day OI and premiums by strike. Use NSE  files (e.g., BhavCopy, derivatives reports) as cold storage or to validate Upstox data.

- **Alternate Data Sources:** In absence of Upstox/Plus data: Yahoo/Google for NIFTY spot (for gap fills), MCX for currency data if needed, Quandl/AlphaVantage (limited India coverage). Paid vendors (Bloomberg, Refinitiv, TickData) exist but assume free streams. **Integration Notes:** Upstox uses OAuth2 (login flow, token refresh) and imposes rate limits (50 req/s for market data). Design the data collector to respect limits (e.g. cached calls, incremental fetch) and use Upstox’s websocket for real-time ticks. Store API keys securely and handle token refresh.  

- **Data Schema & Storage:**  
  - *Raw Feeds:* Tick-level trade/quote feeds for NIFTY futures and select near-the-money options; daily option chain snapshots (strike, bid/ask, last, vol, OI, Greeks).  
  - *Sampling Rates:*  Tick-level or 1-sec for spot, 1–5-sec for options; if limited, use 1-min bars with volume to compute VWAP. Bucket intraday into 5–15 min slices for features like PCR, Max Pain (e.g., Upstox bucket_interval).  
  - *Storage:* Hot (in-memory or fast DB) for same-day features/signals; Cold (data lake/SQL warehouse) for historical backtesting. Use timestamps with IST zone. Latency: aim sub-second market price latency; signal generation within ~1–3 sec after data tick (no strict SLA given, but target near real-time).  

- **API Data Mapping:**  

  | Feature / Dataset                   | Upstox Endpoint                    | Alt. Source              | Description                                     |
  |-------------------------------------|------------------------------------|--------------------------|-------------------------------------------------|
  | **NIFTY Spot Price**                | Websocket (NSE_INDEX\|Nifty 50)    | NSE quoted price feed    | Live index price (VWAP, breakout levels)        |
  | **Option Chain (CE/PE)**            | `/option/chain`       | NSE FO chain CSV         | Per-strike LTP, bid/ask, vol, OI, Greeks (IV, θ, γ, Δ) |
  | **Put/Call Ratio (PCR)**            | `/market/pcr`       | Compute from OI or StocksRin | Intraday PCR by volume (puts/ce OI) and trend       |
  | **Total OI (by strike)**            | `/market/oi`        | NSE chain archives       | Call and put open interest per strike |
  | **OI Change (ΔOI)**                | `/market/change-oi` | Derived from OI dumps    | Net OI build/unwind over interval by strike |
  | **Max Pain Strike (intraday)**      | `/market/max-pain`  | Manual calc (OI)         | Strike minimizing combined loss; time-series by bucket |
  | **Premium VWAP (NTM options)**      | Compute from option trade ticks    | Simulated if needed      | Volume-weighted avg of call premium (and put) vs. spot |
  | **Spot VWAP**                       | Compute from NIFTY ticks/bars      |                         | Volume-weighted NIFTY price                      |

## Master Composite Execution Matrix  

The following table cross-references **PCR regimes** (put-call sentiment) with IV trend, gamma (GEX) zone, and OI dynamics, to flag *“GO”* (favorable) versus *“NO-GO”* (trap) conditions for options buying:

| PCR Regime (Bullish Indicator) | IV Trend           | GEX Zone (Delta Hedge)    | OI/Flow Behavior         | Trading Signal      |
|-------------------------------|--------------------|---------------------------|--------------------------|---------------------|
| **PCR < 0.7** (Call-heavy)    | IV **Crushing**    | GEX strongly **>0** (high call gamma) | Call OI flat/down, puts unwinding | **NO-GO** (likely exhausted rally/bear reversal) |
|                               | IV **Expanding**   | GEX >0                     | Calls building OI       | **GO** (Bull momentum breakout) |
| **PCR 0.7–0.9** (Call-bias)   | IV rising          | GEX mildly >0              | Moderate call OI build   | **Possible GO** if supported by breakouts |
|                               | IV flat/falling    | GEX ↓ toward 0            | Stagnant OI (calls not adding) | **Caution** (watch for trap) |
| **PCR ~1.0** (Neutral)        | IV neutral or mixed| GEX ≈ 0                    | Balanced OI flows        | **Neutral** (signal depends on other cues) |
| **PCR 1.1–1.4** (Put-bias)    | IV **Expanding**   | GEX <0 (high put gamma)    | Put OI building, calls unwinding | **GO** (potential reversal upward) |
|                               | IV **Crushing**    | GEX <0                     | Puts unwinding (OI ↓)    | **NO-GO** (vol-crush bull trap) |
| **PCR > 1.4** (Extreme puts)  | IV flat/declining  | GEX ~0                     | Massive OI at adjacent CE/PE strikes (new strangle writing) | **NO-GO** (wicked range-bound trap) |
|                               | IV **volatile**    | GEX shifting ± (fractal)   | Erratic OI swings       | **Danger/Skip** (confusing signals) |

*Legend:* Bullish PCR (>1) suggests put-heavy (often contrarian to rally); low PCR (<1) means call-heavy. “IV Crushing” means implied vol is falling (often bearish after a spike); “GEX >0” implies market makers need to buy underlying on upswing (calls dominate), “GEX <0” means selling pressure on down moves (puts dominate). The **Action** column flags composite scenarios. For example, a **high PCR with collapsing IV** (PCR 1.1–1.4 plus IV crush) is a classic “bull trap” – avoid long calls. Conversely, a high PCR with rising IV and heavy put OI (implied sell-off priced) can signal an undervalued breakout move *up*, triggering a GO. These regimes integrate multiple signals rather than any single metric.

## Signal Formulas & Pseudocode  

Sample composite-signal logic (illustrative, weights to be optimized):

- **Momentum Score (example):**  
  ```
  PCR_slope  = (PCR_now - PCR_prev) / Δt
  VWAP_diff  = (Call_VWAP_NTM - Spot_VWAP)  # positive if call premiums above spot
  GEX_change = Current_GEX - Previous_GEX
  Momentum_Score = w1 * PCR_slope + w2 * VWAP_diff + w3 * GEX_change
  ```
  If `Momentum_Score` exceeds a threshold **AND** spot price breaks a key resistance level, signal **GO**.  
- **Vol-Crush Trap Detector:**  
  ```
  if PCR_now in [1.1,1.4] AND (IV_call/IV_put skew narrowing rapidly) AND (ΔOI_put < 0): 
      signal = NO_GO  # likely bull trap
  ```
- **Gamma Hedge Clue:**  
  ```
  HedgeWall = strike level of peak net call gamma (from cumulative gamma OI)
  if Spot_price crosses above HedgeWall AND GEX >0:
      anticipate rapid upswing (market maker buying) -> GO
  ```
- **VWAP Divergence Edge:**  
  ```
  if (Spot_VWAP nearly flat) AND (NTM_Call_Premium_VWAP rising) AND (PCR rising):
      # Institutional accumulation (short-covering)
      signal = GO
  ```
- **No-Trade Signature:** (time decay draining)  
  ```
  if abs(PCR_now - 1.0) < ε AND maxPain stable AND Adjacent_OI_added(CE,PE):
      signal = NO_GO  # straddle writing, avoid buying premiums
  ```

These formulas combine PCR trends, premium flow, and delta/gamma cues. The actual implementation would standardize and weight components (e.g. z-scores of PCR momentum, skew diff, gamma flux) into a **Composite Momentum Index** and apply tunable thresholds.

## Role-Specific Skills and Responsibilities

### Coder / Engineer Skills
- **Programming & Stack:** Proficient in Python (pandas, NumPy, PyTorch/TensorFlow for ML, backtesting libs), and optionally Node.js/Java for API integration. Knowledge of *dtypes* for financial time-series, multi-threading/async (for websockets).  
- **Libraries & Tools:** Data collection (requests/urllib for REST, `upstox-python-sdk` or REST SDK), Websocket clients, SQL (PostgreSQL, TimescaleDB) or NoSQL for tick storage, Kafka/Redis for stream processing. Docker/containers for deployment.  
- **API Integration:** Implement OAuth2 flow with Upstox, handle token refresh. Design robust REST client obeying rate limits and parallel streaming if needed.  
- **Feature Engineering:** Code calculation of features: PCR time series, IV skew per strike, gamma exposure (sum(Γ*OI)), OI wall detection. Automate intraday VWAP computation from trade ticks.  
- **Backtesting Engine:** Use or build a framework to replay historical ticks/bars and test signals. Handle transaction costs/slippage modeling (e.g. realized vs VWAP). Generate performance analytics (Sharpe, drawdown).  
- **Deployment & Reliability:** CI/CD pipelines for automated testing/deployment. Containerize services (data collector, signal engine, execution engine). Implement logging/metrics (CPU, latency, error rates) and alerts (e.g. API failures, data gaps). Ensure security of API keys and follow OWASP best-practices.  
- **Performance & Latency:** Profile critical paths (market data ingestion → signal calc → order send). Aim minimal processing latency (prefetch or async calls). Use in-memory databases or vectorized ops for speed. Adhere to microsecond-level delays where possible for high-frequency edge.  

### Quantitative Analyst Skills
- **Options Modeling:** Deep knowledge of option Greeks, implied volatility dynamics, and decay. Ability to derive gamma exposure (GEX) and interpret gamma/delta hedging impacts. Familiar with concepts like “hedge wall” and “volatility trigger” from market-maker theory.  
- **Feature Design:** Engineer cross-market signals (e.g. combine IV term structure, skew, PCR, and order-flow). Define regimes (PCR, IV bands) and statistical edge tests. Create labeled datasets (e.g. breakout vs trap) for model training.  
- **Statistical Analysis:** Perform correlation and lead-lag analysis between spot, PCR, premiums, GEX, and price moves. Use time-series techniques (Granger causality, cross-correlation). Validate signal significance (t-tests, p-values) and avoid lookahead bias.  
- **Risk Metrics & Backtest Design:** Calculate key metrics (profit factor, max drawdown, Value-at-Risk). Stress-test strategy across volatility regimes. Ensure proper train/test split (walk-forward). Consider transaction cost impact and realistic execution latencies.  
- **Explainability:** Document the “why” behind signals. Use SHAP or sensitivity analysis on composite indicator to interpret feature importance. Provide transparency for traders/regulators.  
- **Iterative Research:** Tune parameters using cross-validation over multiple expiries. Propose adaptive triggers for time-of-day blocks and adjust for scheduled events (macro news, RBI, etc.).  

### Execution Trader Skills
- **Order Types & Execution:** Master order types (market, limit, stop, VWAP/TWAP, iceberg if supported). For index options, leverage strategies (legging into straddles if needed). Use VWAP algorithms to minimize market impact.  
- **Broker API (Upstox):** Experience with placing and managing orders via Upstox API (v2 orders endpoints). Handle delivery vs MIS segments. Understand Upstox-specific parameters (order variety, GTT orders, AMO).  
- **Slippage & Impact:** Model expected slippage for small vs large orders. Simulate execution on real tick data. Use limit orders near VWAP or laddered orders to reduce cost.  
- **Risk Controls:** Pre-set intraday risk limits (max position size, daily P&L stop-loss). Implement kill-switch on errant signals or if system lags. Monitor real-time P&L and Greeks exposures.  
- **Monitoring & Fail-safes:** Build real-time dashboards of key metrics (PCR, IV, GEX, P&L). Use automated alerts (Slack/email) for anomalies (e.g. API disconnect, out-of-range prices). Plan fallback if primary broker/API fails (e.g. pause trading, alternate broker if available).  
- **Regulatory Compliance:** Adhere to exchange rules (price bands, circuit limits). Respect margin requirements and ensure adequate capital.  

### Feedback & Learning Loop
- **Performance Monitoring:** Continuously log trades and key signals. Post-mortem analysis on each trade (outcome vs predicted). Update performance trackers (win-rate per regime, Sharpe ratios).  
- **Model Drift Detection:** Monitor if historical correlations change (e.g. PCR no longer leads price). Use statistical divergence tests to flag model degradation.  
- **Retraining & Updates:** On a scheduled cadence (e.g. weekly/monthly), refresh statistical thresholds or retrain any ML models on latest data. Incorporate new features (time-of-day effects, implied skew shifts).  
- **Automated Alerts:** Set rules to alert when composite signal deviates (e.g. false-breakout frequency spikes). Ensure email/SMS or dashboard alerts to analysts.  
- **Documentation & Versioning:** Maintain version control for code, parameter configurations, and result logs. Record assumptions (e.g. market conditions, instrument specs).  

## Feature List

- **PCR (Put/Call Ratio):** Total and trend, via Upstox PCR API; segment into regimes (<0.7, 0.7–0.9, 1.0, 1.1–1.4, >1.4).  
- **IV Skew:** Difference between near-ATM Call IV and Put IV from Option Chain. Track steepness of skew (bearish tilt if low-strike IV ≫ high-strike).  
- **IV Trend (Expanding vs Crushing):** Time-series of ATM IV or VIX. Identify rapid drops (IV crush) or spikes.  
- **Theta Decay (Acceleration):** Change rate of option Theta (use Theta from Option Chain); accelerating negative Theta signals heavy time decay draining premiums.  
- **GEX (Net Gamma Exposure):** Σ(Call_gamma × Call_OI) – Σ(Put_gamma × Put_OI) from Option Chain. Also compute “zero-gamma” levels (spot where GEX flips sign).  
- **Delta-Hedge Triggers:** Implied thresholds where market makers will delta-hedge en masse (proxied by high local gamma zones). Derived from GEX gradient.  
- **PCR Change & Swing:** Intraday PCR change from open, and momentum of PCR (slope).  
- **Volume-to-OI Ratio:** % of OI that traded per bucket (vol/(OI_prev)). High turnover on NTM strikes indicates active unwinds/builds.  
- **OI Walls & Shifts:** Identify strikes with heavy OI (supplies a “wall” resistance/support), and detect if net OI is building or unwinding (Upstox OI/Change APIs). Track large adjacent straddle/strangle OI moves as institutional positioning shifts.  
- **Premium VWAP vs Spot VWAP:** Intraday VWAP of option premium flow (calls) vs underlying VWAP. Divergence can signal hidden buying/selling pressure (monitor via tick-level trade data).  
- **Max Pain Level:** Current max pain strike and its drift. Rising max-pain indicates puts dominating; falling indicates calls.  
- **Time-of-Day Effects:** Categorical feature (morning/midday/afternoon). Use as filter – e.g. only take breakout signals in final hour.  

## System Architecture (Mermaid Diagram)  

```mermaid
flowchart TD
    A[Data Ingestion] --> B[Feature Computation]
    B --> C[Signal Generation]
    C --> D[Execution Engine]
    D --> E[Broker API (Upstox)]
    D --> F[Execution & Risk Monitor]
    F --> G[Trade/Performance Log]
    G --> H[Analyst Review / Retraining]
    H --> C
```

*Fig: System architecture. Data is ingested (Upstox API/websocket, NSE archives) → features (PCR, IV, GEX, VWAP) are computed → composite signals generated → orders executed via broker API → monitoring/logging → feedback to analysts for retraining.* 

## Time-of-Day Flow (Mermaid Diagram)  

```mermaid
flowchart LR
    Open[Market Open (9:15)] --> Early[First Hour Trading]
    Early --> Midday[Midday Lull (11:30–13:00)]
    Midday --> Late[Afternoon Expiry Run (14:00–15:30)]
    Late --> Close[Market Close (15:30)]
```

*Fig: Intraday structural phases. Morning open often sees volatility spikes, midday is relatively quiet, and the final hour (especially expiry day) has high gamma squeeze risk. Feature interpretations (PCR swings, OI shifts, etc.) are weighted differently in each phase.*  

## Tables & Appendices

### Feature-to-Endpoint Mapping

| Feature                    | Data Endpoint / Source                         | Remark                                      |
|----------------------------|------------------------------------------------|---------------------------------------------|
| PCR, PCR Trend            | Upstox PCR API                  | Intraday PCR and bucketed time series       |
| Option Chain (LTP/OI/IV)   | Upstox Option Chain API         | Contains IV, Theta, Gamma, OI for each strike |
| Total OI & OI Walls       | Upstox Get OI API               | Strikewise call/put OI snapshot             |
| OI Changes (ΔOI)         | Upstox Change in OI API         | Strikewise net build/unwind per interval    |
| Max Pain                  | Upstox Max Pain API             | Intraday max pain level (with time buckets) |
| Spot Price                | Upstox Quote/Websocket (Nifty50)               | Live NIFTY index price (ticks)              |
| NTM Premium VWAP         | Calculate from Option Chain trades             | Needs tick or candle data (Upstox WS)       |
| Historical Data (backtest) | NSE historical CSVs or Upstox Historical API    | Past Option data for backtest               |

### Role Responsibilities Matrix

| Task / Responsibility                 | Coder/Engineer        | Quant Analyst        | Execution Trader     |
|---------------------------------------|----------------------|----------------------|----------------------|
| **Data Ingestion & Storage**          | Build ETL pipelines; manage DB schema; ensure latency targets. | Define required datasets; validate data integrity. | Provide market data requirements (ticks, OI). |
| **API Integration**                   | Implement Upstox OAuth, REST/Websocket clients; handle rate limits. | Specify endpoint usage; verify data fields (e.g. IV, Theta). | Confirm order/market data connectivity. |
| **Feature Engineering**               | Code calculations (PCR slope, IV skew, GEX) into pipeline. | Design composite features (PCR regimes, skew metrics, VWAP diff). | Feed real-time indicators to decision engine. |
| **Quant Modeling & Backtesting**      | Set up backtest framework; code signal generation logic. | Statistical modeling; parameter tuning; risk metrics. | Review simulated trade results; suggest cost assumptions. |
| **Order Execution Logic**             | Code execution rules into automated engine; integrate broker API. | Provide signal thresholds and context (e.g. volatility filter). | Implement order strategies (market/limit/VWAP); manage slippage. |
| **Risk Management**                   | Enforce system limits (max orders, throttle). | Compute risk metrics (VaR, expected loss). | Monitor exposure; cut positions on stops; ensure compliance. |
| **Monitoring & Logging**              | Develop dashboards/logging (error, latency). | Monitor performance metrics (sharpe, hit rate). | Track trade P&L vs expectations; annotate market events. |
| **CI/CD & Testing**                  | Unit tests for data and trading functions; CI pipeline. | Validate model via cross-validation; perform scenario tests. | Test order flow in paper-trading; compliance testing. |
| **Security & Compliance**             | Secure API keys; encrypt data at rest/transit. | Ensure models comply with risk policies. | Adhere to broker/exchange regulations (circuit, margins). |

*Table: Responsibilities for Engineering vs Analyst vs Trader roles. Coding tasks include API integration (Upstox OAuth, websockets), data engineering, backtesting, and CI/CD. Analyst tasks focus on feature design, statistical validation, and model risk. Trader tasks focus on execution tactics, risk limits, and real-time monitoring.*  

### Composite Execution Matrix (PCR vs. IV/GEX/OI)

| PCR Regime   | IV Trend    | GEX Zone   | OI Behavior          | Action    |
|--------------|-------------|------------|----------------------|-----------|
| <0.7 (call-heavy) | Falling | High (+)  | Calls unwinding      | **NO-GO**  |
| <0.7, IV ↑    | Rising    | High (+)  | Calls piling in      | **GO**    |
| 0.7–0.9        | Rising    | Slight (+)| Moderate call build  | **Possible GO** |
| 0.7–0.9, IV ↓ | Falling   | ↓ → 0     | Stagnant OI          | **CAUTION** |
| ~1.0 (neutral) | Neutral  | ≈ 0       | Balanced flows       | **Neutral** |
| 1.1–1.4 (put-heavy) | Rising    | High (–) | Put OI building      | **GO**    |
| 1.1–1.4, IV ↓ | Falling   | High (–) | Puts unwinding       | **NO-GO**  |
| >1.4 (extreme put)  | Flat    | ~0        | Straddle writing      | **NO-GO**  |

*Table: Composite signal matrix (condensed). “GO” indicates favorable entry conditions for buying calls; “NO-GO” flags likely traps or time-decay regimes to avoid. This combines PCR levels with volatility and OI cues for actionable guidance.*

## Visual Aids (Example Charts)  

 *Figure: **Implied Volatility Skew** – example chart of NIFTY call vs. put IV across strikes (ATM center). Equity option IV is typically lowest at ATM and rises for deep OTM puts (left side), yielding a downward-sloping skew.*  

*Note: Additional charts (e.g. GEX vs. spot price timeline, premium VWAP vs. spot VWAP) should be generated from actual market data. The diagrams above should be rendered as inline assets in the final document (e.g. PNG/SVG) for PDF export.*  

---

**Sources:** Upstox API documentation and market definitions were used to confirm available data fields. These guided the data integration and feature mapping. (Additional modeling concepts drawn from industry literature, e.g. GEX dynamics.) The SKILLS.md is intended as a comprehensive blueprint for engineers and traders to collaboratively implement, deploy, and iterate the described NIFTY options trading system.