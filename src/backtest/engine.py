"""
Intraday backtester.
Replays chain snapshots, runs the composite engine, simulates trades with
slippage + commission, computes performance metrics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from signals.composite import CompositeEngine
from signals.state import SignalState
from utils.logger import get_logger

log = get_logger()


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp | None
    side: str             # "CE" or "PE"
    strike: float
    entry_premium: float
    exit_premium: float | None
    quantity: int
    pnl: float
    exit_reason: str
    decision: str
    confidence: float


@dataclass
class BacktestResult:
    trades: list[Trade] = field(default_factory=list)
    pnl_series: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    total_pnl: float = 0.0
    win_rate: float = 0.0
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    n_trades: int = 0
    avg_pnl: float = 0.0
    avg_hold_minutes: float = 0.0
    equity_curve: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))


class Backtester:
    """
    Run the composite engine on a sequence of option chains and simulate trades.

    Strategy (default):
      - On GO with confidence > min_conf, buy ATM NTM call (or put)
      - Exit on: target %, stop %, time stop, or NO-GO
      - No overnight, no pyramiding
    """

    def __init__(
        self,
        engine: CompositeEngine | None = None,
        capital: float = 1_000_000.0,
        lot_size: int = 75,
        slippage_ticks: float = 1.0,
        commission_per_contract: float = 20.0,
        tick_size: float = 0.05,
        target_pct: float = 50.0,
        stop_loss_pct: float = 25.0,
        max_hold_minutes: int = 60,
        min_confidence: float = 0.55,
        cooldown_minutes: int = 5,
    ):
        self.engine = engine or CompositeEngine()
        self.capital = capital
        self.lot_size = lot_size
        self.slippage_ticks = slippage_ticks
        self.commission = commission_per_contract
        self.tick_size = tick_size
        self.target_pct = target_pct
        self.stop_loss_pct = stop_loss_pct
        self.max_hold_minutes = max_hold_minutes
        self.min_confidence = min_confidence
        self.cooldown_minutes = cooldown_minutes
        self.cfg = {
            "risk": {
                "lot_size": lot_size,
                "max_position_notional": capital,
                "max_daily_loss": capital * 0.02,
            }
        }

    def run(
        self,
        spot_df: pd.DataFrame,
        chains: list[pd.DataFrame],
    ) -> BacktestResult:
        assert len(spot_df) == len(chains), "spot_df and chains must align per timestamp"

        result = BacktestResult()
        equity = []
        current_trade: Trade | None = None
        last_trade_time: pd.Timestamp | None = None

        for i, (spot_row, chain) in enumerate(zip(spot_df.itertuples(index=False), chains)):
            ts = pd.Timestamp(getattr(spot_row, "timestamp"))
            spot = float(getattr(spot_row, "spot"))

            st: SignalState = self.engine.on_tick(
                chain=chain, spot=spot, timestamp=ts, cfg=self.cfg
            )

            # ---- Manage open position ----
            if current_trade is not None:
                held = (ts - current_trade.entry_time).total_seconds() / 60.0
                current_premium = self._get_premium(chain, current_trade.strike, current_trade.side)
                pnl_pct = 100.0 * (current_premium - current_trade.entry_premium) / current_trade.entry_premium

                exit_reason = None
                if pnl_pct >= self.target_pct:
                    exit_reason = "target"
                elif pnl_pct <= -self.stop_loss_pct:
                    exit_reason = "stop_loss"
                elif held >= self.max_hold_minutes:
                    exit_reason = "time_stop"
                elif st.decision == "NO-GO" and st.confidence > 0.6:
                    exit_reason = "no_go_exit"

                if exit_reason is not None and current_premium is not None:
                    current_trade.exit_time = ts
                    current_trade.exit_premium = current_premium
                    current_trade.pnl = self._calc_pnl(current_trade)
                    current_trade.exit_reason = exit_reason
                    result.trades.append(current_trade)
                    equity.append(
                        {
                            "timestamp": ts,
                            "pnl": current_trade.pnl,
                            "cumulative_pnl": sum(t.pnl for t in result.trades),
                        }
                    )
                    current_trade = None
                    last_trade_time = ts

            # ---- Look for new entry ----
            if current_trade is None and st.decision == "GO" and st.confidence >= self.min_confidence:
                if last_trade_time is not None and (ts - last_trade_time).total_seconds() / 60.0 < self.cooldown_minutes:
                    pass  # still in cooldown
                else:
                    strike = st.suggested_strike or self._pick_atm_strike(chain, spot)
                    side = st.suggested_side
                    premium = self._get_premium(chain, strike, side)
                    if premium is not None and premium > 0:
                        qty = self.lot_size  # 1 lot
                        # Slippage: buy at ask + slippage, sell at bid - slippage
                        current_trade = Trade(
                            entry_time=ts,
                            exit_time=None,
                            side=side,
                            strike=strike,
                            entry_premium=premium + self.slippage_ticks * self.tick_size,
                            exit_premium=None,
                            quantity=qty,
                            pnl=0.0,
                            exit_reason="",
                            decision=st.decision,
                            confidence=st.confidence,
                        )

        # ---- Close any open position at end of backtest ----
        if current_trade is not None and chains:
            last_chain = chains[-1]
            current_trade.exit_time = spot_df["timestamp"].iloc[-1]
            current_trade.exit_premium = self._get_premium(last_chain, current_trade.strike, current_trade.side)
            current_trade.pnl = self._calc_pnl(current_trade)
            current_trade.exit_reason = "eod_close"
            result.trades.append(current_trade)

        # ---- Compute metrics ----
        result.n_trades = len(result.trades)
        if result.n_trades > 0:
            result.total_pnl = sum(t.pnl for t in result.trades)
            wins = [t for t in result.trades if t.pnl > 0]
            result.win_rate = 100.0 * len(wins) / result.n_trades
            result.avg_pnl = result.total_pnl / result.n_trades
            holds = [
                (t.exit_time - t.entry_time).total_seconds() / 60.0
                for t in result.trades if t.exit_time is not None
            ]
            result.avg_hold_minutes = float(np.mean(holds)) if holds else 0.0

            if equity:
                result.equity_curve = pd.Series(
                    [e["cumulative_pnl"] for e in equity], index=pd.to_datetime([e["timestamp"] for e in equity])
                )
                result.pnl_series = result.equity_curve.diff().fillna(0)
                # Sharpe (annualized assuming 252 trading days)
                if result.pnl_series.std() > 0:
                    result.sharpe = (result.pnl_series.mean() / result.pnl_series.std()) * np.sqrt(252 * 6.25)
                # Max drawdown
                running_max = result.equity_curve.cummax()
                drawdowns = result.equity_curve - running_max
                result.max_drawdown = float(drawdowns.min())

        log.info(
            "Backtest done. trades={} pnl=₹{:,.0f} win_rate={:.1f}% sharpe={:.2f} maxDD=₹{:,.0f}",
            result.n_trades, result.total_pnl, result.win_rate, result.sharpe, result.max_drawdown,
        )
        return result

    # ------------------------------------------------------------------ helpers
    def _pick_atm_strike(self, chain: pd.DataFrame, spot: float) -> float:
        if chain.empty:
            return 0.0
        diffs = (chain["strike"] - spot).abs()
        return float(chain.loc[diffs.idxmin(), "strike"])

    def _get_premium(self, chain: pd.DataFrame, strike: float, side: str) -> float | None:
        if chain.empty:
            return None
        row = chain[chain["strike"] == strike]
        if row.empty:
            # nearest available
            diffs = (chain["strike"] - strike).abs()
            row = chain.loc[[diffs.idxmin()]]
        if side == "CE":
            return float(row["ce_ltp"].iloc[0])
        return float(row["pe_ltp"].iloc[0])

    def _calc_pnl(self, t: Trade) -> float:
        if t.exit_premium is None:
            return 0.0
        gross = (t.exit_premium - t.entry_premium) * t.quantity
        # Round-trip commission
        commission = 2 * self.commission * (t.quantity // self.lot_size)
        return gross - commission


def summarize(result: BacktestResult) -> dict[str, Any]:
    return {
        "n_trades": result.n_trades,
        "total_pnl": round(result.total_pnl, 2),
        "win_rate_pct": round(result.win_rate, 2),
        "avg_pnl": round(result.avg_pnl, 2),
        "avg_hold_minutes": round(result.avg_hold_minutes, 1),
        "sharpe": round(result.sharpe, 2),
        "max_drawdown": round(result.max_drawdown, 2),
    }
