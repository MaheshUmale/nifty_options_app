

In institutional options trading, Unwinding is just one quadrant of market movement. To have a complete system, your agent must track all four core data cycles: Buildup (Long/Short) and Covering (Long/Short).
When option sellers (the big institutions) act, their trades create four distinct combinations of Price Movement and Change in Open Interest (COI).
------------------------------
## The 4 Institutional Derivatives Cycles
Because you are looking at this from the Option Seller's Perspective, the definitions are flipped from standard retail textbooks:
## 1. Short Buildup (Aggressive Writing)

* What happens: Institutions are writing (selling) new contracts to create a ceiling or a floor.
* The Data: Open Interest Increases (+ COI) while Premium Price Decreases.
* Trading Context: If this happens in Calls, it is heavily Bearish (Call Writing). If this happens in Puts, it is heavily Bullish (Put Writing).

## 2. Short Covering (The Panic Rally/Drop)

* What happens: Sellers are trapped. They are forced to buy back their sold options at a loss to protect their capital, causing a massive explosive swing in the underlying index.
* The Data: Open Interest Decreases (- COI) while Premium Price Spikes Up rapidly.
* Trading Context: If Call sellers are covering, the index shoots up (Short Covering Rally). If Put sellers are covering, the index crashes.

## 3. Long Buildup (Institutional Buying)

* What happens: Large players are aggressively buying options (often done by proprietary desks for momentum breakout trading or hedging macro risk).
* The Data: Open Interest Increases (+ COI) and Premium Price Increases.
* Trading Context: High-velocity momentum setups.

## 4. Long Unwinding (Profit Booking)

* What happens: Option buyers are liquidating their positions and locking in gains, leading to a cooling-off period or a minor counter-trend retracement.
* The Data: Open Interest Decreases (- COI) and Premium Price Decreases.
* Trading Context: Signifies a trend pause or exhausting momentum.

------------------------------
## Operational Instruction Block for the Agent
To add this directly to your configuration markdown file, copy and paste this dedicated tracking module into your system prompt layout:

### 3.3 Institutional Buildup & Covering Diagnostic EngineThe agent must evaluate the relationship between Option Premium Price Action and Change in Open Interest (COI) every 5 minutes at the ATM strike to diagnose the exact market quadrant. Apply this matrix variant:
1. **CALL OPTIONS DIAGNOSTIC (CE)**
   * Premium Price UP   + COI UP   --> [LONG BUILDUP]      --> Aggressive Call buying (Intraday Bullish Momentum)
   * Premium Price DOWN + COI UP   --> [SHORT BUILDUP]     --> Aggressive Call writing (Institutional Resistance Ceiling)
   * Premium Price UP   + COI DOWN --> [SHORT COVERING]    --> Trapped Call writers panicking (Explosive Bullish Trigger)
   * Premium Price DOWN + COI DOWN --> [LONG UNWINDING]    --> Call buyers exiting (Bullish Momentum Exhaustion)
2. **PUT OPTIONS DIAGNOSTIC (PE)**
   * Premium Price UP   + COI UP   --> [LONG BUILDUP]      --> Aggressive Put buying (Intraday Bearish Momentum)
   * Premium Price DOWN + COI UP   --> [SHORT BUILDUP]     --> Aggressive Put writing (Institutional Support Floor)
   * Premium Price UP   + COI DOWN --> [SHORT COVERING]    --> Trapped Put writers panicking (Explosive Bearish Trigger)
   * Premium Price DOWN + COI DOWN --> [LONG UNWINDING]    --> Put buyers exiting (Bearish Momentum Exhaustion)
3. **High-Conviction Scalping Signals:**
   * **The Gamma Squeeze Buy:** If Spot breaks resistance AND ATM Call Option shows [SHORT COVERING], initiate immediate long momentum scalp.
   * **The Panic Breakdown Sell:** If Spot breaks support AND ATM Put Option shows [SHORT COVERING], initiate immediate short momentum scalp.

------------------------------ 