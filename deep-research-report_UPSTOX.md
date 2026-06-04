# Executive Summary

Building an institutional-grade intraday NIFTY options buying system requires end-to-end integration of market data, quantitative signal generation, and execution components.  The system must treat the options ecosystem holistically – correlating implied volatility (IV) skew and trend, time decay (theta), put/call ratio (PCR), gamma exposure (GEX) and market-maker hedging, open interest (OI) walls, and premium VWAP vs. spot VWAP – rather than in isolation.  We outline the required skills for each role (Coding Agent, Live Trading Analyst, Execution Trader), map skills to concrete tasks and deliverables, and specify the technical architecture, data pipelines, and algorithms needed.  We include example pseudocode and composite signal formulas, an execution “go/no-go” matrix (PCR × IV × GEX × OI regimes), and flow diagrams.  The plan assumes Upstox’s free APIs (OAuth token, REST and WebSocket market feed) for live NIFTY data (with fallback to alternative historical sources), and NSE trading hours 9:15–15:30 IST.  All development must incorporate robust testing, monitoring, and feedback loops for continuous improvement.

## Roles & Responsibilities

### Coding Agent: Technical Implementation

- **API Integration:** Implement OAuth2 login and token refresh for Upstox (REST) and maintain a live WebSocket v3 connection.  For example, use Upstox’s OAuth 2.0 flow to obtain `access_token` and attach `Authorization: Bearer {token}` to all REST calls.  Handle two-factor methods (SMS/TOTP) if needed.  
- **WebSocket Feed (Protobuf):** Connect to Upstox Market Data Feed V3 (WSS).  Use Protobuf definitions provided by Upstox (e.g. `MarketDataFeed.proto`) to decode real-time messages.  Subscribe to `instrumentKeys` for NIFTY spot/future (`NSE_INDEX|Nifty 50` or futures) and relevant options (`NSE_FO|...`).  Use modes `ltpc` (LTP/close), `option_greeks`, or `full` as needed.  For free accounts, note the subscription limits: up to 5000 keys for LTPC and 3000 for Option Greeks.  Implement automatic reconnection and redirection handling in case Upstox reroutes the WSS endpoint.  
- **REST Data Ingestion:** Use Upstox REST endpoints to pull option chains and Greeks.  For example, call `GET /v2/option/chain?instrument_key=NSE_INDEX|Nifty 50&expiry_date=YYYY-MM-DD` to retrieve strike-wise call/put OI, IV, Greeks, bid/ask etc.  Also use `GET /market-quote/quotes` for snapshots or historical candles for backfill.  
- **Data Engineering:** Define schemas to store (or stream) fields: timestamps, LTP, bid/ask prices and sizes, volume, OI, IV, delta, gamma, theta, vega, etc.  Normalize Upstox field names (e.g. `market_data.oi`→`open_interest`, `option_greeks.iv`→`implied_vol`).  For example, Upstox JSON provides: `call_options.market_data.ltp`, `oi`, `bid_price`, and `put_options.option_greeks.iv`.  Combine this with spot data.  If high-resolution data is needed, also ingest intraday candles via Upstox (V3 intraday endpoints) or store raw ticks from WSS.  Ensure all data is timestamped in IST and aligned (e.g. round to nearest second or millisecond).  
- **Fallback Data Sources:** Upstox’s free API may not provide historical OI/IV. Plan alternatives: Download daily F&O reports from NSE’s website (which publishes contract-wise OI and volume CSVs) or use public libraries (e.g. `yfinance` or `nsepy`) to fetch historical index futures and options data.  Pre-process and reconcile formats (mapping NSE strike/expiry codes to Upstox instrument_keys).  Document assumptions for missing data (e.g. assume zero OI beyond available history).  
- **Composite Signal Algorithms:** Implement the quantitative formulas and pseudocode for the multi-variable signals.  For example:
  
  ```python
  # Example: Composite Momentum Index for NTM call premium
  PCR_series = get_put_call_ratio_series()
  IV_skew = iv_call_NTM / iv_put_NTM
  theta_accel = compute_theta_acceleration(time, theta_series)
  GEX = compute_net_gamma_exposure()
  spot = get_current_spot()
  max_gamma_strike = find_strike_with_max_gamma()
  dist_to_gamma = (spot - max_gamma_strike) / spot
  
  # Volatility-OI Nexus
  if PCR < 0.7 and IV_skew is falling:
      alert("Bull trap: high calls but collapsing IV")
  if PCR rising and OI increasing and IV expanding:
      signal_momentum_breakout = True
  
  # Market Maker Gamma Hedging
  zero_gamma_zone = identify_zero_gamma_zone(terms)  # e.g., where small delta moves cause big hedging
  if heavy_call_OI_wall and spot near zero_gamma_zone:
      anticipation = "market-makers short gamma -> hedging expected (likely explosive move)"
  
  # Price/Premium Lead-Lag
  call_VWAP = compute_VWAP(call_trade_prices, call_volumes)  # formula from Investopedia
  spot_VWAP = compute_VWAP(spot_prices, spot_volumes)
  if spot_rangebound and call_VWAP > spot_VWAP and PCR is rising and ATM_call_OI dropping:
      signal = "Call premium leading -> potential short covering breakout"
  ```
  
  Reference: PCR interpretation and thresholds, VWAP formula, Upstox data fields, and gamma hedging intuition.  
- **Example Code Snippets:** Show key patterns:
  
  ```python
  # Upstox REST: get access token and option chain
  import requests
  token = get_upstox_access_token(client_id, client_secret)  # OAuth2 flow
  headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
  resp = requests.get('https://api.upstox.com/v2/option/chain',
                      params={'instrument_key':'NSE_INDEX|Nifty 50','expiry_date':'2026-06-29'},
                      headers=headers)
  option_data = resp.json()['data']
  ```
  
  ```python
  # Websocket subscription (pseudocode)
  ws = websocket.connect('wss://api.upstox.com/mfeed/v3/')
  ws.send({'method':'sub', 'data':{'mode':'full','instrumentKeys':['NSE_FO|12345','NSE_INDEX|Nifty 50']}})
  for msg in ws:
      feed = MarketDataFeed_pb2.FeedResponse()
      feed.ParseFromString(msg)
      ltpc = feed.feeds['NSE_FO|12345'].fullFeed.marketFF.ltpc
      # process ltpc.ltp, option greeks, oi, etc.
  ```
  
- **Error Handling & Rate Limits:** Implement retry/backoff for HTTP 4XX/5XX.  Respect Upstox REST limits (50 req/sec, 2000/30min) and WS limits.  For example, batch instrument_keys in chunks (≤500 per full-quote call).  Handle token expiration by auto-refresh.  Log any decode errors on the Protobuf feed.  
- **Unit/Integration Tests & Synthetic Data:** Develop unit tests for each data parser (e.g. validate that given a sample JSON/protobuf, the code extracts correct fields).  Create synthetic tick data generators: e.g. simulate an option chain where OI moves or IV expands, to test alert triggers.  Example: write tests that check `compute_VWAP()` and `put_call_ratio()` functions return expected values on known inputs.  
- **DevOps & CI/CD:** Use version control (Git), automated testing (e.g. `pytest`), and containerization.  Continuous integration should run tests on each commit.  Deployment checklist: code linting, config for tokens (securely handled), SSL for WSS.  

### Live Trading Analyst: Quant Research & Monitoring

- **Quantitative Modeling:** Deep understanding of options Greeks, volatility surfaces, and structural flows.  Skills in statistics/Python/R for backtesting signals.  Familiarity with options theory (e.g. volatility skew, forward PDE for decay).  
- **Data Analysis:** Monitor real-time signals (PCR, IV skew, premium flows) and verify against market outcomes.  For example, track how PCR regimes (<0.7, 0.7–1.1, 1.1–1.4) have historically correlated with NIFTY moves.  Use tools (Python, Pandas) to compute moving averages/slopes of PCR and IV.  
- **Composite Signal Integration:** Implement and refine composite triggers.  For instance, code a “Momentum Index” as: 
  \[
  M = w_1 \times \frac{d(PCR)}{dt} + w_2 \times (VWAP_{call} - VWAP_{spot}) + w_3 \times \frac{d(\Delta)}{dt},
  \]
  where weights \(w_i\) are tuned.  Use pseudocode (see Coding Agent) to prototype.  Validate signals by backtesting on historical intraday data.  
- **Strategy & Risk Definition:** Define explicit GO/NO-GO rules.  E.g., flag a “no-trade” scenario when PCR≈1, Max Pain level is static, and large straddle OI builds (institution writing strangles).  Conversely, identify “gamma-hunt” buy setups: heavy call walls, spot near zero-gamma point, short gamma exposure (see Composite Matrix).  
- **Backtesting & Metrics:** Build a backtest framework to simulate trades.  Key metrics: hit-rate, average gain/loss, drawdown, Sharpe ratio, latency impact.  For example, simulate buying ATM NIFTY calls when our composite conditions are met and track P/L.  Use non-overfitting practices (e.g. walk-forward).  
- **Monitoring & Reporting:** Implement real-time dashboards.  Plot live PCR, IV, GEX, P&L.  Alert on signal events.  Continuously record system performance and P&L for calibration.  Example visual: PCR vs. time of day plot, VWAP premium vs. time chart.  Document every anomaly or false signal and iterate.  

### Execution Trader: Order Execution & Risk Controls

- **Market Microstructure:** Expertise in NSE F&O specifics: trading hours (9:15–15:30 IST), tick size (₹0.05 for index options), lot sizes, and typical intraday patterns (U-shaped volume/spread).  Understand how bid-ask spreads widen intraday (widest at open/close) and thus tailor execution.  
- **Order Types & Slicing:** Use smart order execution.  E.g., break a large call-buy order into smaller limit orders (“iceberg” algorithm) to reduce slippage.  Decide order type by liquidity: for highly liquid near-ATM calls use Aggressive limit (or IOC), for thin far-OTM use cautious.  Incorporate delta-hedge triggers: e.g., once a call position is entered, hedge by selling futures when delta exceeds threshold.  
- **Execution Algorithms:** Pseudocode example:
  ```python
  total_qty = calculate_position_size(risk_per_trade)
  slices = slice_order(total_qty, liquidity_profile)
  for qty in slices:
      submit_order('BUY', symbol, qty, price=calc_limit_price(qty))
      if trailing_stop or time_elapsed > t_max:
          break
  ```
  Use real-time premium VWAP vs. spot VWAP to gauge if buying is populating at premium or mid-market.  If premium/VWAP divergence is large, be prepared for adverse fill and widen limits.  Monitor execution slippage and adjust size thresholds (e.g. reduce slice size if fills are slow).  
- **Risk Management:** Enforce stop-loss and position limits.  If a trade goes against the signal (e.g. price moves opposite despite positive signal), cut losses quickly.  For multiple simultaneous edges, allocate capital proportionally.  During high-IV periods (which inflate premiums), reduce notional to control Vega risk.  
- **Time-of-Day Filters:** Different tactics by session.  For example:
  - **Morning (9:15–10:15):** Use first-hour momentum; be aggressive on clear signals (higher liquidity, tighter spreads).  
  - **Midday (11:30–13:30):** Markets lull; lean passive.  Only trade high-conviction signals (perhaps smaller size).  
  - **Afternoon (14:00–15:30):** Watch for expiry/position squaring.  Leverage any shift in Max Pain or large final hour flows to enter/exit.  For instance, if Max Pain shifts up and PCR rises late, consider late entry.  If near expiry and a big gamma pin is expected, be ready to sell or close out.  
- **GO/NO-GO Decision Rules:** Implement a simple decision table (illustrated below) per time block.  E.g., *“No-Trade”* if PCR ≈1 and IV flat and large adjacent CE/PE OI added simultaneously – indicates a big straddle write (time decay ramp) and premiums draining.  *“Trade”* if PCR rises from <0.7, IV expanding, and a large underlying move is initiated, signalling momentum.  These rules translate to clear intraday trading actions or flat positions.  

## Skill-to-Task Mapping

| Role                | Key Skills & Tools                                                     | Example Tasks / Deliverables                                          |
|---------------------|------------------------------------------------------------------------|-----------------------------------------------------------------------|
| **Coding Agent**    | • Languages: Python (requests, websockets), C++/Java for low-latency if needed.  Libraries: Protobuf, Pandas/Numpy, `pandas`, Async I/O.<br>• Upstox API (REST, WSS) and OAuth2, JSON/Proto parsing.<br>• Data engineering: schema design (Parquet/SQL), Docker, Git, CI/CD pipelines, unit testing (pytest).<br>• DevOps: AWS/GCP containers, monitoring (Prometheus/Grafana). | • Implement Upstox auth flow; retrieve/refresh `access_token`.\n• Write WebSocket client to decode Upstox feeds (subscribe to NIFTY spot/options) and output normalized JSON.\n• Develop data ingestion pipeline storing time-series in a database or time-series store.\n• Unit tests for data parsers, mock WSS messages (synthetic protobuf) and verify fields.\n• Integration test using a small live feed (or sandbox mode).\n• Handle reconnection, logging, rate-limit sleeps.\n• Document API field mappings (e.g. Upstox’s `oi` = open interest).  |
| **Live Trading Analyst** | • Quant skills: Option Greeks, volatility modeling, statistics (regressions, time-series analysis).<br>• Data analysis: Python, Pandas, R, Jupyter.<br>• Backtesting frameworks, historical data handling.<br>• Visualizations: Plotly/Matplotlib for intraday charts.\n• NSE F&O domain knowledge, probability and stats (for POV models).<br>• Machine learning for pattern detection (optional). | • Define PCR regimes (e.g. PCR<0.7, 0.7–1.1, 1.1–1.4) and backtest their outcomes.\n• Code composite metrics: e.g. compute **IV skew** = IV_CE_LTM / IV_PE_LTM, **theta accel** as second derivative of option price w.r.t time.\n• Implement `compute_net_gamma_exposure()` summing (gamma * OI) across strikes and expiries; detect “zero-gamma” points.\n• Run historical simulations: calculate our Momentum Index over days, measure hit-rate and drawdowns.\n• Maintain dashboards of live metrics (PCR, IV surface, OI walls).  Annotate when signals fire.  Provide feedback to coder to tweak formula weights.\n• Generate training data: label past intraday periods “good”/“bad” based on actual moves, to refine thresholds. |
| **Execution Trader** | • Trading expertise: NSE F&O rules, order book dynamics (L1/L2 order flow).<br>• Skills in algorithms: VWAP, TWAP, iceberg slicing.<br>• Risk management: portfolio Greeks, size control, hedging (delta-hedge futures).<br>• Tools: algorithmic trading platform (could be custom or broker-provided).<br>• Real-time decision making under pressure. | • Implement execution logic: decide when to submit orders (market vs limit vs IOC).  Eg: if implied volatility skew is steep and liquidity thin, use limit orders away from market.  In code: place limit order at mid or +1 tick, with time-in-force.<br>• Monitor fills: if partial fill, resend remaining or cancel after timeout.<br>• Delta-hedge: after buying calls, monitor combined delta; if delta exceeds threshold, send hedge (sell futures).<br>• Build order size calculator: e.g. if volatility regime = high, cap position at smaller size; otherwise scale up. \n• Real-time check of the **Execution Matrix**: as conditions change during the day, either escalate or abort trades. |


## Composite Execution Matrix

This table summarizes ideal *Go/No-Go* triggers combining PCR, IV trend, GEX and OI patterns.  (Cells below describe typical scenarios; actual thresholds to be calibrated.)

| **PCR Regime**         | **IV Trend**           | **Gamma Zone (GEX)**           | **OI Pattern**                                   | **Action & Sizing**                                                            | **Notes**                              |
|-----------------------|------------------------|-------------------------------|-------------------------------------------------|-------------------------------------------------------------------------------|----------------------------------------|
| **PCR < 0.7** (Strongly bullish) | **Crushing** (IV ↓)    | Long Gamma (market pins)     | Calls OI built, Puts OI low                   | **No-Go (Bull Trap)** – Stay out or small size **<br>** (“vol-crush” setup)    | High call buying but IV falling. Risk of abrupt reversal.  |
| **PCR 0.7–1.1** (Neutral)      | **Rising** (IV ↑)     | Short→Long Gamma Flip       | Balanced or increasing call+put OI            | **Go** – Larger size. Trend-confirmed breakout if IV/volume surge.             | If underlying approaches large OI wall and GEX flips, exploit gamma hedging.  |
| **PCR 1.1–1.4** (Bearish)      | **Expanding** (IV ↑)  | Possibly Short Gamma        | Puts OI built or both sides rising           | **Go (Contrarian)** – Enter cautiously on extreme bearishness + IV expansion   | High PCR indicates pessimism; IV rise suggests capitulation. Use stops. |
| **PCR 1.1–1.4** (Bearish)      | **Crushing** (IV ↓)    | Long Gamma (market calm)    | Calls OI or straddle OI building             | **No-Go (Bear Trap)** – Avoid; potential overshoot reversal.                   | Plunging IV despite bearish PCR is contrarian setup.         |
| **PCR > 1.4** (Extreme Bear)   | **Mixed/Flat**        | Short Gamma (pinned)        | Straddles huge (CE & PE OI surge)            | **No-Go (Strangle)** – Flat position. Possible systematic time decay trap.     | Signals institutional strangle writing; premiums decaying.                  |

- *Go*: Proceed with a trade; consider position size. *No-Go*: Avoid initiating new buys (or flatten existing positions).
- This matrix is a guideline. Actual triggers use continuous measurements (e.g. PCR slope, IV skew rate, distance to zero-gamma).  E.g. a high PCR in row 3 combined with a sudden spike in spot moving through a call wall can flip to *Go* (covering short puts).  The “No-Go” signature (row 5) reflects PCR≈1.0, static Max Pain, and simultaneous big OI adds on both calls and puts – a classic straddle-write trap (time decay heavy).  

## Example Algorithms & Pseudocode

1. **Composite Momentum Signal** – e.g. an index combining PCR trend, VWAP divergence, and delta-change.  
   ```python
   PCR = compute_put_call_ratio(puts_volume, calls_volume)
   PCR_slope = (PCR_current - PCR_prev) / dt
   premium_VWAP = calc_VWAP(option_prices, option_volumes)   # see VWAP formula
   spot_VWAP = calc_VWAP(spot_prices, spot_volumes)
   delta_change = current_delta - previous_delta
   
   # Custom Momentum Index
   M = w1*PCR_slope + w2*(premium_VWAP - spot_VWAP) + w3*delta_change
   if M > BUY_THRESHOLD:
       signal = "LONG"
   elif M < SELL_THRESHOLD:
       signal = "EXIT"
   ```
2. **Gamma Hedge Trigger** – anticipate market-maker hedging.  
   ```python
   # Net Gamma Exposure (approx)
   net_GEX = sum(strike.gamma * strike.oi for strike in strikes)
   zero_gamma_price = find_zero_gamma_price(strikes)  # when net_GEX ~ 0
   dist = abs(spot_price - zero_gamma_price)
   if net_GEX < 0 and dist < small_percent_of_spot:
       # market makers short gamma near flip zone -> hedging imminent
       alert("Gamma flip: expect sharp move")
   ```
3. **Order Slicing Algorithm** – microstructure-aware execution.  
   ```python
   def execute_buy(instrument, total_qty):
       # Break into N slices based on liquidity
       slices = slice_order(total_qty, max_per_order=100)
       for qty in slices:
           limit_price = get_preferred_limit(instrument)
           order_id = place_limit_order('BUY', instrument, qty, price=limit_price, time_in_force='IOC')
           time.sleep(0.2)  # pace orders to avoid bursts
           fill = check_fill(order_id)
           if fill < qty:
               remaining = qty - fill
               # try remaining with tighter or cancel
               place_limit_order('BUY', instrument, remaining, price=limit_price)
           # delta-hedge after each fill if needed
           update_delta_hedge()
   ```
4. **VWAP Calculation** (for illustration):  
   \[
   VWAP = \frac{\sum_i (P_i \times V_i)}{\sum_i V_i} \quad\text{where } P_i,V_i \text{ are price and volume ticks.}
   \]

## Data Flow & Time-of-Day Diagrams

Below are schematic diagrams of the system data flow and intraday time segmentation.  (When exporting to PDF or DOC, convert these Mermaid diagrams to images. For example, generate the diagram PNG and embed as `![Data Flow Diagram](data_flow.png)`.)  

```mermaid
flowchart LR
    subgraph Ingestion
      A[Upstox REST/API] --> B[WebSocket Feed]
      B --> C[Parser (Protobuf → JSON)]
      C --> D[Message Queue / Stream DB]
    end
    subgraph Processing
      D --> E[Normalization/Storage]
      E --> F[Signal Computation]
      F --> G[Dashboard/Alerts]
      F --> H[Order Execution Module]
      D --> I[Backtester / Historical DB]
    end
    E --> I
    G --> J[Risk Monitor]
    H --> K[Broker Order API (Upstox)]
    style Ingestion fill:#f0f8ff,stroke:#333,stroke-width:1px
    style Processing fill:#f8f0ff,stroke:#333,stroke-width:1px
```

```mermaid
flowchart TB
    start((Start of Day))
    start --> Morning["Morning Open (9:15–10:15)"]
    Morning --> |Check PCR/IV| MCond{Signal?}
    MCond -->|Yes: Strong Signal| Action1[Execute Trade Strategy]
    MCond -->|No/Weak| Passive1[Monitor Only]
    Passive1 --> Midday["Midday Lull (11:30–14:00)"]
    Action1 --> Midday
    Midday --> |Check Trend| DCond{Trend Forming?}
    DCond -->|Yes| Action2[Execute/Adjust Strategy]
    DCond -->|No| Passive2[Hold or Close Positions]
    Passive2 --> Afternoon["Afternoon Run (14:00–15:30)"]
    Action2 --> Afternoon
    Afternoon --> |Check OI/MaxPain| ACond{Expiry Moves?}
    ACond -->|Yes| FinalAction[Execute/Hedge/Close Out]
    ACond -->|No| FinalAction
    FinalAction --> end((End of Day))
```

## Implementation Roadmap

1. **Phase 1 – Data & API Setup (Weeks 1–2):** Obtain Upstox API keys. Implement login/auth module (OAuth flow). Connect to WebSocket feed and REST to confirm data access. Parse sample data (option chain, quotes) and verify fields. Establish database or message queue schema. *Milestone:* Real-time data pipeline up and running (with logging).  

2. **Phase 2 – Core Metric Computation (Weeks 2–4):** Code routines for PCR, IV skew, theta acceleration, net gamma, premium VWAP, etc. Ingest a few days of historical NIFTY options data (via Upstox or alternative) and compute these metrics offline. *Milestone:* Standalone backtest scripts producing historical signal plots (e.g. PCR time series vs. index moves).  

3. **Phase 3 – Signal Integration & Backtest (Weeks 4–6):** Combine metrics into composite signals (per pseudocode above). Implement signal engine that scans live feed and flags conditions. Backtest these signals on historical intraday data to estimate performance (P&L, hit rate, drawdown). *Milestone:* Documented performance report; adjustable parameters for signal thresholds.  

4. **Phase 4 – Execution Module (Weeks 6–8):** Build order execution logic. Simulate order placements with hypothetical fills to estimate slippage. Integrate delta-hedge routine (link option buys to underlying futures sells). *Milestone:* End-to-end simulated trading from signal to order logic, with risk checks (size limits, stops).  

5. **Phase 5 – Deployment & Monitoring (Weeks 8–10):** Containerize system, deploy to a cloud server or VPS. Set up continuous integration (GitHub Actions) and monitoring dashboards (e.g. Grafana for latency, logs). Develop alerting (email/SMS) for signals and errors. Document security (store API keys securely, refresh tokens). *Milestone:* Live paper-trading or small real-money run with logging of all metrics (latency, fill quality, P&L).  

6. **Phase 6 – Iteration & Learning (Ongoing):** Collect trading outcomes and label each trade (win/lose/cancel). Analysts refine signal models using real performance feedback. Implement drift detection on input features (if PCR/IV distributions shift, retrain thresholds). Continually incorporate new data (e.g. annual NSE contract changes) and update the system.  

Each phase should include peer reviews and regression testing. Progress along this roadmap ensures readiness for live deployment under strict risk controls.

---

**Sources:** Upstox API documentation provides the exact fields for market data and option chain (e.g. `market_data.oi`, `option_greeks.iv`).   Real-time feed limits are noted in Upstox docs.  Market-microstructure context (U-shaped intraday spreads) is from NSE research.  Put/Call Ratio interpretation is guided by Investopedia.  VWAP formula is standard, and gamma exposure impacts are described in quantitative trading literature.  NSE trading hours (9:15–15:30 IST) are from official schedule. Each of these underpins the design above. 

