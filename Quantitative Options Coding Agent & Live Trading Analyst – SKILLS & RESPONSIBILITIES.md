# Quantitative Options Coding Agent & Live Trading Analyst – SKILLS & RESPONSIBILITIES

## Executive Summary
This role involves designing and implementing an **intraday index-options buying strategy** using cross-market signals.  The analyst will architect a low-latency pipeline to ingest live market and options data, compute synchronized features (PCR regimes, IV skew, dealer gamma exposure, OI concentrations, premium VWAP), and generate composite “GO/NO-GO” signals.  Strong emphasis is placed on **multi-variable correlations and lead-lag effects** rather than isolated indicators.  Deliverables include production-ready code modules, real-time monitoring dashboards, backtest results, and thorough documentation.  

## Responsibilities & Skill Mapping
- **Data Pipeline Development:** Build real-time ingestion of market quotes, trades, option chains (tick/L2 feeds, OPRA, exchanges). Ensure normalization, time synchronization, and storage (e.g. kdb+, Kafka, or Redis) for live features.
- **Feature Engineering:** Implement calculations for PCR regimes, IV skew, theta decay acceleration, net gamma exposure, OI walls, Max Pain, and premium/spot VWAP. Use efficient numerical libraries to update these per time bucket.
- **Signal Generation:** Code the composite algorithms (Momentum Index, Vol-Crush Trap detector, Gamma-Hedge triggers, No-Trade filters) using synchronized features. Tune thresholds and logic for PCR/IV regime detection.
- **Backtesting & Analysis:** Design walk-forward backtests on historical tick/option data. Quantify strategy performance (Sharpe, drawdown, hit-rate) including realistic slippage and transaction costs. Iterate on model refinements.
- **Deployment & Monitoring:** Deploy code to low-latency servers (colocated exchanges). Build dashboards/alerts (Grafana/Plotly) for key indicators (PCR, GEX, Max Pain shifts). Implement risk checks (position/duress limits) and kill-switch on strategy breaches.
- **Documentation & Code Quality:** Write clean, modular code with unit tests. Maintain version-controlled documentation on data definitions, algorithm logic, and test cases. Ensure reproducibility (Docker/Conda environments) and peer review compliance.

| **Key Task/Deliverable**            | **Required Skills**                                    |
|------------------------------------|--------------------------------------------------------|
| Real-time Data Ingestion           | Programming (C++, Rust, Python), Kafka/ZeroMQ, kdb+    |
| Feature Computation & APIs         | Python (NumPy/Pandas), Cython, Data engineering        |
| Quantitative Modeling              | Statistics, Time-series Analysis, Option Greeks (Θ, Γ) |
| Strategy Algorithms & Backtests    | Python (SciPy, statsmodels), R (optional), Backtesting frameworks (Zipline)  |
| Low-Latency Infrastructure         | C++/Java, FPGA/GPU (optional), Network protocols (FIX) |
| Monitoring & Reporting             | Web dashboards (Dash/Plotly), Alerting (Prometheus)    |

## Technical Skills & Technology Stack
- **Languages:** Python (primary for analytics), C++/Rust/Java (low-latency services), SQL (time-series DBs), Bash for scripting.  Intermediate Scala/Go (if using specific data tools).
- **Numerical Libraries:** NumPy, Pandas, SciPy, TA-Lib, cuDF (GPU), TensorFlow/PyTorch (for any ML calibration), QuantLib (option models).
- **Data Tools:** kdb+/q or TickDB for historical tick storage, Kafka/Apache Pulsar or ZeroMQ for streaming, Redis/memcached for in-memory state. Use OPRA/OPTx feeds or vendor APIs (QuantHouse, USTP) for options.
- **Analytics:** Jupyter, Matplotlib/Seaborn for plotting, Pandas/HDF5 or Parquet for time-series. SQL or Dask for batch aggregation.
- **Infrastructure:** Linux, Docker/Kubernetes for deployment, CI/CD (Jenkins/GitHub Actions) for automated testing, AWS/GCP for cloud batch jobs if needed.
- **Risk & Execution:** FIX engines (QuickFIX/J), low-latency sockets, order management systems. Quant-focused DBs (Resque, KDB) and monitoring (Grafana, InfluxDB).
- **Versioning & QA:** Git, GitLab; pytest/unittest for code; documentation tools (Sphinx, Markdown); CI pipelines.

| **Category**         | **Examples / Libraries / Tools**                  |
|----------------------|---------------------------------------------------|
| Languages            | Python 3.x, C++17, Rust, Java, SQL                |
| Data Frameworks      | Pandas, NumPy, SciPy, Dask, PyTables, HDF5, Parquet |
| Options/Finance      | QuantLib, TA-Lib, StatsModels, py_vollib           |
| Streaming / Queue    | Kafka, RabbitMQ, ZeroMQ, Nanomsg                  |
| Databases            | kdb+/q, PostgreSQL, TimescaleDB, InfluxDB         |
| Deployment           | Docker, Kubernetes, AWS (EC2/EMR), GCP            |
| Testing              | PyTest, tox, Jenkins, GitHub Actions               |
| Charting / Dashboards| Matplotlib, Plotly, Grafana/Prometheus, Kibana    |

## Quantitative Skills
- **Statistical Analysis:** Regression, cross-correlation, covariance, hypothesis testing to identify leading/lag relationships between features.
- **Time-Series Modeling:** Autoregressive models, EWMA/VWAP filters, Fourier/wavelet (for intraday seasonality), and feature smoothing.
- **Signal Processing:** Lead-lag detection via cross-correlograms and Granger causality on tick-level data.
- **Options Theory:** Derivation of option Greeks (Δ, Γ, Θ, Vega). Modeling implied volatility surfaces; familiarity with Black-Scholes and SABR fits.
- **Gamma Exposure Modeling:** Summation of gamma * open interest to estimate net dealer hedges. Detect “gamma flip” levels where net GEX changes sign.
- **Optimization & ML (if needed):** Parameter calibration (e.g. PCR threshold), possibly reinforcement learning for execution; risk model (VaR, CVaR).
- **Microstructure Knowledge:** Tick-level flow, order book dynamics, slippage estimation, and effects of trade size on VWAP.

## Data Sources & Formats
- **Market Data:** Live tick (trades/quotes) and L2 orderbook feeds (e.g. Cboe, CME MDP). Historical tick data (Nanex, Exegy, or Tick Data, Inc.).
- **Options Data:** Streaming OPRA quotes (bid/ask, volume, open interest) for all strikes/expirations of the target index (e.g. SPX). Historical options chains with daily OI snapshots.
- **Data Vendors:** Bloomberg Terminal (B-PIPE), Refinitiv, or specialized vendors like QuantHouse for low-latency feeds. 
- **Formats:** Binary time-series (kdb+/q tables), Parquet/CSV for batch archives. OPRA messages or FIX data for live ticks.
- **Reference Data:** Corporate actions, holiday calendars, etc. Ensure sync clocks (NTP) for timestamp alignment.

## Feature Engineering (Expanded Parameter Matrix)
Develop code to compute the following per time interval (e.g. 1min or tick-aligned buckets), always synchronizing all inputs:

- **Put/Call Ratio (PCR):**  
  - *Formula:* $$PCR = \frac{\sum \text{PutVolume}}{\sum \text{CallVolume}}$$ (option volume or OI, choose consistent definition).  
  - *Regimes:* Define baseline ~0.7 (neutral).  
    - PCR < 0.7 = *Bullish regime*.  
    - PCR 0.7–0.8 = *Neutral regime*.  
    - PCR > 1.1 = *Bearish regime*.  
  - *Trend:* Compute slope `PCR_slope = d(PCR)/dt` over short windows.

- **Implied Volatility (IV) Skew:**  
  - *Compute:* Fit an IV surface or directly calculate difference between call and put IVs across strikes:  
    ``` 
    iv_skew = (IV_call_ATM - IV_put_ATM) 
    ```  
  - Or use slope of IV vs. strike. Detect expansion vs. contraction: ΔIV_skew/dt.
  - *Sample pseudocode:* `iv_skew = iv_surface[strike_call_ATM] - iv_surface[strike_put_ATM]`.

- **Theta Acceleration:**  
  - *Idea:* Compute time-decay rate change of near-ATM options.  
  - *Compute:* Estimate Θ (change of price per day), then track `d^2Θ/dt^2` over short intervals. 
  - *Logic:* Rapidly increasing negative theta indicates accelerating time-decay (bad for longs), e.g., ```theta_accel = (Theta_new - Theta_old) / Δt```.

- **Gamma Exposure (GEX):**  
  - *Aggregate:* For each strike: `gamma_OI = option_gamma(strike) * OI(strike)`. Sum over calls/puts (use spot-price scaling if needed).  
  - *Net GEX:* `net_gamma = Σ (Γ_call*OI_call) - Σ (Γ_put*OI_put)`.  
  - *Interpretation:* Positive net GEX (dealers long Γ) implies market makers *sell into rallies* (dampening moves); negative net GEX implies *buy on rallies* (amplifying moves).  
  - *Thresholds:* Identify “zero-Gamma flip zones” where net_gamma ≈ 0.

- **OI Walls & Smart Money Positions:**  
  - *Total OI Walls:* Identify large cumulative open interest at key strikes (calls vs puts).  
  - *Intraday OI Change:* Track ∆OI per strike since open. Rapid additions on CE/PE indicate institutional straddle/strangle (premium selling) or unwinds (covering).  
  - *Smart Straddle/Strangle:* Compute net changes: e.g.,  
    ``` 
    smart_flow = sum(ΔOI_call over N strikes) + sum(ΔOI_put over same strikes) 
    ```  
    Large simultaneous OI increases on adjacent CE and PE = dealer writing.

- **Max Pain & Shifts:**  
  - *Definition:* Strike minimizing combined payoff to option buyers.  
  - *Compute:* For each strike K, calculate payoff sum if underlying closes at K:  
    ```
    P&L(K) = Σ[max(0, S-K)*OI_call(K)] + Σ[max(0, K-S)*OI_put(K)]
    ```
    then `MaxPain = argmin_K P&L(K)`.  
  - *Track:* Monitor shifts in MaxPain level intraday. Stationary MaxPain suggests balanced positioning; moving MaxPain indicates directional bias from dealers.

- **Premium VWAP vs Spot VWAP:**  
  - *Premium VWAP:* Compute VWAP of NTM (near-the-money) option premiums:  
    ```
    VWAP_premium = Σ(price_option * volume_option) / Σ(volume_option)
    ```  
  - *Spot VWAP:* Standard VWAP of underlying (see Figure below).  
  - *Comparison:* When premium-VWAP diverges from spot-VWAP (normalized), it signals relative flow into option premiums vs. spot. A rising premium-VWAP ahead of spot may indicate accumulation of calls.

**Figure:** Example intraday price bars (black) with Volume-Weighted Average Price (VWAP, blue) overlay.  VWAP forms a volume-weighted “center-of-gravity” for price.  In practice, we compute premium-VWAP for ATM/Near-ATM options and compare it to spot-VWAP to identify when options are relatively expensive or cheap.

**Figure:** Implied Volatility Skew example – call IV (cyan), put IV (purple), and smoothed combined skew (orange) across strikes.  This “smile” illustrates higher OTM volatility.  In models, we track steepening vs. flattening of this skew curve.

## Composite Signal Algorithms
Design algorithms that combine the above features. Example pseudocode logic:

- **Vol-Crush Bull-Trap Detector:**  
  When bullish PCR (1.1–1.4) coincides with *narrowing* IV skew (call and put IV converging) and accelerating negative theta, signal a likely *volatility crush*.  
  ```python
  if PCR > 1.1 and PCR < 1.4 and (iv_skew_trend < -skew_threshold) and (theta_accel < -theta_threshold):
      signal = "No-Go (Vol Crush Trap)"
  ```  
  This avoids buying into a false breakout when bullish sentiment is overheated but implied volatility is collapsing.

- **Momentum Breakout Signal:**  
  Look for PCR in neutral/bullish band (e.g. 0.7–1.1), coupled with expanding IV (skew widening), surging call OI, and premium-VWAP rising above spot-VWAP. This composite suggests genuine institutional buying and fast move:  
  ```python
  if (PCR > 0.8 and PCR < 1.1) and (iv_trend > iv_threshold) and (ΔOI_calls > oi_threshold) and (VWAP_premium > VWAP_spot):
      signal = "GO (Buy Options)"
  ```  

- **Gamma Hedging Trigger:**  
  When spot price approaches a “zero-Gamma flip” zone under heavy OI walls, anticipate market maker hedging to move price. For example:  
  ```python
  if (abs(price - zero_gamma_level) < price_threshold) and (total_OI_at_strike > oi_wall_threshold):
      signal = "GO (Expect Explosive Move)"
  ```  
  Dealers short gamma will create momentum once the underlying drifts beyond their neutral zone.

- **Institutional Accumulation/Distribution:**  
  Identify divergence between spot and option flows: e.g., if price is range-bound but NTM call premium VWAP breaks out above its VWAP and PCR is climbing while ATM call OI falls (short covering), signal a hidden accumulation.  

- **No-Trade / Trap Signature:**  
  Flat PCR (~neutral), stationary MaxPain, and large simultaneous OI addition on adjacent CE and PE (dealer strangle writing) imply premiums are being sold into. Formalize as:  
  ```python
  if (abs(dPCR) < eps) and (dMaxPain == 0) and (OI_calls_at_K + OI_puts_at_K > wall_threshold for adjacent strikes):
      signal = "No-Go (Premium Drain)"
  ```  

### Mathematical Logic Summary
- **PCR Regime Index:**  
  $$ \text{PCR} = \frac{\sum_i V_{\text{put},i}}{\sum_i V_{\text{call},i}}. $$  
  Classify into regimes (e.g., PCR < 0.7 bullish, >1.1 bearish).
- **IV Skew Slope:**  
  $$ \text{IV\_skew} = IV_{\text{call}}(\text{ATM}) - IV_{\text{put}}(\text{ATM}), $$  
  track derivative $d(\text{IV\_skew})/dt$ for crush vs. expansion.
- **Theta Acceleration:**  
  $$ \Theta = -\frac{\partial V_{\text{opt}}}{\partial t}, \quad \text{ThetaAccel} = \frac{d(-\Theta)}{dt}. $$  
- **Gamma Exposure (GEX):**  
  $$ \Gamma_{\text{exp}}(K) \approx \Gamma(K)\times OI(K)\times \text{multiplier}. $$  
  Net across strikes indicates overall dealer hedge bias.
- **Max Pain:**  
  $$ \text{MaxPain} = \arg\min_K \Bigl[\sum_{\text{calls}}(S-K)_+ \cdot OI_{\text{call}} + \sum_{\text{puts}}(K-S)_+ \cdot OI_{\text{put}}\Bigr]. $$  
- **VWAP:**  
  $$ \text{VWAP} = \frac{\sum (P_i\times Q_i)}{\sum Q_i}, $$  
  applied separately to underlying and to option premium flows.

```python
# Pseudocode Example
for each time_bucket:
    PCR = sum(PutVolume) / sum(CallVolume)
    iv_skew = IV_call_ATM - IV_put_ATM
    theta_accel = computeThetaAcceleration(near_ATM_options)
    net_gamma = sum(option_gamma*OI)  # positive=dealers long gamma
    VWAP_premium = computeVWAP(option_premiums)
    VWAP_spot = computeVWAP(underlying_price)
    # Composite signals
    if PCR > 1.1 and iv_skew < skew_collapse_th and theta_accel < theta_th:
        action = "No-Trade (Vol-Crush Trap)"
    elif (PCR > 0.8 and PCR < 1.1) and (iv_skew > iv_expand_th) and (VWAP_premium > VWAP_spot):
        action = "Buy Signal (Momentum Breakout)"
    elif nearZeroGammaFlip(price, net_gamma) and strong_OI_wall:
        action = "Buy Signal (Gamma Hedge Trigger)"
    elif (abs(delta_PCR) < small) and (MaxPain unchanged) and (OI_strangle > threshold):
        action = "No-Trade (Premium Drain)"
    else:
        action = "Hold/Neutral"
```

## Testing & Backtesting
- **Datasets:** Use multi-year historical data (e.g. SPX index and SPX options from 2016–2025). Include tick-level prices, time-stamped options trades, and end-of-day/real-time OI. If possible, include 0DTE data.
- **Backtest Metrics:** Evaluate returns, Sharpe ratio, win-rate, maximum drawdown. Stress-test under volatile vs calm regimes. Use walk-forward cross-validation to simulate deployment.  
- **Costs & Slippage:** Model realistic slippage (e.g. 1–2 ticks per leg) and commission (e.g. \$1–\$2 per contract). Incorporate bid-ask spreads into P&L.  
- **Benchmarking:** Compare to naive strategies (e.g. always buy ATM calls at open). Ensure our “edge” (excess return) is statistically significant.  
- **Regression & Robustness:** Test sensitivity of signal thresholds. Ensure small parameter shifts don’t grossly flip results. Maintain unit and integration tests (pytest) for code correctness.

| **Deliverable**                  | **Test/Metric**                   | **Acceptance Criteria**                   |
|----------------------------------|-----------------------------------|-------------------------------------------|
| Feature Computation Module       | Unit tests (PCR, IV, GEX outputs) | Correct values vs. known examples; ≤1ms per tick update |
| Composite Signal Module          | Functional tests                  | Signals fire under defined conditions; review by quant |
| Backtest Report                  | Sharpe ratio, P&L curves          | Sharpe > target (e.g. 1.5) after costs; drawdown < threshold |
| Real-time Pipeline Deployment    | Latency benchmark, throughput     | End-to-end latency < specified (e.g. 10ms); 24/7 stable execution |
| Dashboards & Alerts              | Data freshness, accuracy          | Indicators update within 1s; alerts on model failure |
| Documentation (SKILLS.md, code docs) | Peer review quality check        | Complete descriptions of algorithms; reproducible examples |

## Deployment & Runbook
- **Real-Time Pipeline (Mermaid):** Design a multistage streaming pipeline. Market data feeds are ingested via a low-latency gateway, normalized, and passed to the feature computation engine. The engine updates indicators in real time, publishing signals to the execution module. The order router applies risk checks before sending orders to exchanges. A parallel dashboard process visualizes key metrics and triggers alerts.  

```mermaid
graph LR
    subgraph RealTimePipeline
        MD[Market Data (Tick/L2 Feeds)] --> Ingest[Data Ingestion & Sync]
        Ingest --> Feats[Feature Computation (PCR, IV, GEX, VWAP, etc.)]
        Feats --> SigEngine[Composite Signal Engine]
        SigEngine --> Risk[Risk & Pre-Trade Checks]
        Risk --> Exec[Order Execution System]
        Exec --> Exchange[Exchange / Broker]
        Feats --> Dashboard[Monitoring Dashboard & Alerts]
        SigEngine --> Dashboard
    end
    subgraph BatchComponents
        HistoricalDB[(Historical Tick/Option DB)] --> Feats
        Feats --> Backtester[Backtesting Suite]
    end
```

- **Latency Budgets:** Keep pipeline latency < 5–10ms for entire ingest-to-signal path. Co-locate servers near exchange gateways. Use multithreading and lock-free queues.
- **Risk Controls:** Hard stop-loss and maximum position limits. For example, if realized loss > 1% portfolio or single-day drawdown > 0.5%, auto-disable signals. Kill-switch procedures for systemic failures (e.g. network loss).
- **Monitoring:** Continuously track data feeds health, model outputs, and P&L. Generate alerts on anomalies (e.g. feature NaN, backtest drift). Use Grafana/Prometheus or equivalent.
- **Model Refresh:** Update models and parameters (PCR baseline, thresholds) at regular intervals (weekly or monthly) based on new data. Recalibrate IV surface fittings daily (intraday if computationally feasible).

## Time-of-Day Structural Filters

| **Time Block**       | **PCR Change**                                           | **Max Pain Shift**                                    | **OI Change**                                       |
|----------------------|----------------------------------------------------------|-------------------------------------------------------|-----------------------------------------------------|
| **Morning Open**     | Large swings are *meaningful*. Early PCR rise may indicate strong buy interest (overnight news). PCR opening spike likely drives initial trend. | Shifts often reflect overnight rebalancing. A move toward open-market MaxPain may set bias. | Rapid OI changes (especially call buying) suggest immediate institutional positioning. |
| **Mid-day Dull Phase** | Small PCR drift often means noise; sustained trends rare. Sudden PCR changes mid-day can signal stealth accumulation/distribution. | MaxPain is relatively static mid-day; shifts here are unusual and noteworthy for rumor-driven moves. | Gradual OI build-up (e.g. building straddles) may indicate dealer position building for later. |
| **Afternoon Expiry/Liquidation** | PCR surges >1.1 late in day often signal expiration hedging or panic buying. A rising PCR but stagnating price suggests short-covering. | MaxPain shifts can be *strategic*. A moving MaxPain toward spot indicates market-maker pinning effects before close. | Big OI additions (especially in last hour) may indicate block trades or gamma scrambles. Heavy expiring OI signals aggressive dealer hedging (possible squeezes). |

*Table:* Interpretation of PCR trends, Max Pain shifts, and OI changes across intraday segments.

## Assumptions & Constraints
- **Markets/Assets:** Focus on a major index (e.g. SPX) or its ETF (e.g. SPY). Data from Cboe/CME for SPX options and corresponding futures/spot.  
- **Capital:** Strategy sized for institutional scale (e.g. $20M–$100M notional). Position limits set accordingly.  
- **Latency:** Target sub-10ms round-trip from tick arrival to order entry; assume colocated hardware or premium cloud networking.  
- **Data Vendors:** Use OPRA-level data (e.g. directly from exchanges or via a low-latency vendor like OCC or QuantHouse). License end-of-day OI from OCC or FRAC.  
- **Execution Environment:** Linux servers with high-performance NICs; assume 24/5 market hours (US markets).  
- **Risk Limits:** E.g., max 50% of capital in any single direction, stop-trades if intraday loss >2%.  
- **Regulations:** Comply with relevant exchange rules (e.g. minimum tick sizes), no-usury of insider information.

## Deliverables & Acceptance Criteria
- **Code Repositories:** Well-structured Git repos for data ingestion, feature engines, signal logic, and execution. All code must compile/build without errors. 
- **Configuration:** Deployment scripts (Dockerfiles, Kubernetes manifests) for production rollout.  
- **Tests:** Unit tests covering edge cases for feature calculations; integration tests for pipeline end-to-end (with synthetic feeds).  
- **Backtest Results:** Detailed report with P&L charts, risk metrics, strategy description. Tables comparing test vs baseline.  
- **Dashboards:** Interactive visualizations (e.g. Real-time PCR, GEX, MaxPain levels) and example screenshots.  
- **Documentation:** This SKILLS.md plus detailed README/Confluence for setup. Include API docs (Docstrings/Sphinx) and data dictionary.  

Success is measured by: all tests passing, documentation completeness, and a convincing backtested edge (performance metrics meeting targets) approved by stakeholders. 

## Documentation & Standards
- Follow **Markdown** for text; **PEP8** for Python code. Comment complex logic extensively.  
- Use **version control** (git) with code reviews. Write **unit tests** for all formulas and functions.  
- Provide **notebooks** or scripts to reproduce key analyses (data sync, signal thresholds).  
- Maintain **change logs** for models and parameter updates.  
- Ensure **reproducibility**: share seed values, data snapshots, and environment specs. Use continuous integration to enforce quality.

