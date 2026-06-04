# Signal Logic — Master Execution Matrix

This document describes the **composite signal pipeline** that maps multi-feature
state into a discrete `GO` / `NO-GO` / `HOLD` decision.

## Inputs (Computed Per Tick)

| Feature | Definition | Range / Regime |
|---------|------------|----------------|
| `PCR` | `Σ put_vol / Σ call_vol` | < 0.7 bull · 0.7–1.1 neutral · 1.1–1.4 bear · > 1.4 extreme |
| `PCR_slope` | `dPCR / dt` over 5 min | % per min |
| `IV_skew` | `CE_IV_ATM − PE_IV_ATM` | typically negative |
| `IV_pct_change` | 15-min rolling pct change of `IV_total` | ± 5% thresholds |
| `IV_trend` | bucketed: `expanding` / `crushing` / `flat` | from `IV_pct_change` |
| `Net_GEX` | `Σ(gamma × OI × spot² × 0.01 × lot)` | sign: + long-γ, − short-γ |
| `Call_wall`, `Put_wall` | strikes with largest CE/PE gamma | support/resistance |
| `Zero_gamma` | strike where cumulative GEX crosses 0 | regime boundary |
| `Max_pain` | strike minimizing total intrinsic value at expiry | magnet |
| `VWAP_call_gap` | `(NTM_call_VWAP − spot_VWAP) / spot_VWAP` | positive = premium leading |
| `Strangle_flag` | symmetric high OI on adjacent CE+PE strikes | bool |

## Sub-Signals (4 Independent Checks)

### 1. Vol-OI Nexus — *the bull-trap detector*

```python
if PCR > 1.1 and IV_trend == "crushing" and call_vwap > spot_vwap:
    return "NO_TRADE"     # IV-crush bull trap
elif 0.7 ≤ PCR ≤ 1.1 and IV_trend == "expanding" and VWAP_call_gap > 0:
    return "BUY_CALLS"    # genuine momentum breakout
elif PCR > 1.1 and IV_trend == "expanding" and put_vwap > call_vwap:
    return "BUY_CALLS"    # contrarian oversold reversal
return "HOLD"
```

**Why it works**: High PCR (>1.1) often means put-heavy sentiment. If IV is
*crushing* simultaneously, the puts were written into a vol spike that's now
fading — buying calls on a "put wall bounce" then bleeds premium.

### 2. Gamma Hedging Trigger — *the dealer squeeze detector*

```python
if spot >= call_wall * 0.999 and gex_regime == "negative":
    return "BUY_CALLS"  # about to break call wall; dealers short gamma → must buy
if spot <= put_wall * 1.001 and gex_regime == "negative":
    return "BUY_PUTS"
return "HOLD"
```

**Why it works**: When dealers are *net short gamma*, a move in either
direction forces them to **buy the underlying in the direction of the move**,
amplifying it. Crossing a major OI wall under negative GEX is the textbook
explosive setup.

### 3. Premium-Spot Lead-Lag — *institutional accumulation*

```python
if spot_range_bound and VWAP_call_gap > 0 and PCR_slope > 0.01 and IV_trend in ("expanding", "flat"):
    return "BUY_CALLS"  # call premiums leading, smart money buying
if spot_range_bound and VWAP_put_gap > 0 and PCR_slope < -0.01:
    return "BUY_PUTS"
return "HOLD"
```

**Why it works**: When spot is range-bound but call premiums are *rising
above* their VWAP with PCR climbing, it means options flow is leading the
underlying. This is institutional accumulation by definition (you can't
make spot move without an OI footprint, but you *can* quietly accumulate
calls).

### 4. No-Trade Trap Signature — *the strangle-write filter*

```python
if oi_strangle_flag and abs(PCR - 1.0) < 0.05 and abs(MaxPain_shift) < 1.0:
    return "NO_TRADE"  # dealers writing strangles; theta will dominate
return "HOLD"
```

**Why it works**: Balanced high OI on both sides + flat PCR + stationary
Max Pain = **someone sold a straddle/strangle**. Time decay will collect
the premium from any small move. Buying options here is paying for
nothing.

## Momentum Index (Continuous Score in [−1, 1])

```python
momentum = w₁ · tanh(5 · PCR_slope)
         + w₂ · tanh(50 · VWAP_call_gap)
         + w₃ · tanh(sign(net_gex) · |net_gex| / 1e9 · 5)
```

Default weights from `config/settings.yaml`:
- `w_pcr_slope = 0.30`
- `w_vwap_gap = 0.40`  (heaviest — direct flow signal)
- `w_delta_flow = 0.30` (GEX-derived)

Threshold: `> 0.55` → buy bias; `< -0.55` → exit/no-trade bias.

## Master Execution Matrix

After the 4 sub-signals + momentum index are computed, the engine evaluates
**a weighted vote** against the **time-of-day multiplier**:

| PCR Regime | IV Trend | GEX Regime | Sub-signal boost | Score |
|------------|----------|------------|------------------|-------|
| Extreme bear (>1.4) | expanding | any | gamma_trigger | +3 |
| Extreme bear | flat | any | none | NO-GO |
| Bear (1.1–1.4) | expanding | any | lead-lag | +3 |
| Bear | crushing | any | none | NO-GO (bull trap) |
| Bullish (<0.7) | expanding | neg | gamma | +2 |
| Bullish | crushing | pos | none | NO-GO |
| Neutral | expanding | neg | lead-lag + momentum | +5 |
| Neutral | flat/any | pos | none | HOLD |

The decision is:

```python
required = 3 * time_block.threshold_multiplier   # 4.2 midday, 2.55 expiry afternoon
if go_score >= required and go_score > no_go_score:    return "GO"
elif no_go_score >= required and no_go_score > go:    return "NO-GO"
else:                                                  return "HOLD"
```

### Time-of-Day Multipliers

| Block | Window (IST) | Multiplier | Reason |
|-------|--------------|------------|--------|
| Morning Open | 09:15–10:15 | 1.0× | Aggressive — clear signals are real |
| Midday Lull | 11:30–13:30 | 1.4× | Stricter — chop kills |
| Afternoon Run | 14:00–15:30 | 0.85× | Expiry play — relax |
| Afternoon + Expiry (Thu) | 14:00–15:30 | 0.75× | Even more relaxed — gamma squeezes |
| Other / pre/post | — | 1.0× | Default |

## Confidence Score

`confidence = min(1.0, abs_score / 6.0)`

- `< 0.3` → weak; dashboard "HOLD" colored grey
- `0.3–0.6` → moderate; sub-signal partial match
- `> 0.6` → strong; ready to trade (subject to order manager risk)

## Suggested Strike

For `GO + CE`: returns `call_wall` (the strike with the largest positive gamma nearby)
For `GO + PE`: returns `put_wall`
For `NO-GO`: returns the wall anyway (for monitoring)

In practice, the order manager applies further filtering (max notional,
position size, cooldown) before submitting.

## Worked Example

**Setup at 11:45 IST, NIFTY spot = 24,000**

```
PCR = 1.18 (bear regime)
IV_total_pct_change_15m = -7%  → crushing
net_gex = +₹1500 Cr (positive gamma — range-bound)
spot_vwap = 23,995
NTM_call_VWAP = 24,020  → gap = +0.10%
Max_pain = 24,000  (unchanged)
oi_strangle_flag = True
```

→ Sub-signal vol_oi: `NO_TRADE` (high PCR + IV crushing = bull trap)
→ Sub-signal gamma: `HOLD` (positive GEX, not near wall)
→ Sub-signal lead-lag: `HOLD` (VWAP gap too small)
→ Sub-signal no_trade: `NO_TRADE` (strangle flag + flat PCR + static max pain)
→ Momentum index: `+0.08` (neutral)
→ Time block: midday → multiplier 1.4 → required_score = 4
→ go_score = 0, no_go_score = 2 → **NO-GO** with high confidence

**Action**: Stay out. If entered on a long, exit on next bar.

---

**Tuning**: All thresholds live in `config/settings.yaml`. After any change,
run `python -m main backtest` and compare metrics.
