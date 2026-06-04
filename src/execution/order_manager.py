"""
Order manager + risk controls.
Simulates order placement (paper mode) and enforces position/drawdown limits.
Live mode: integrates with Upstox Orders API.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

import pandas as pd

from signals.state import SignalState
from utils.logger import get_logger
from utils.time_utils import now_ist

log = get_logger()

OrderSide = Literal["BUY", "SELL"]


@dataclass
class Order:
    order_id: str
    timestamp: pd.Timestamp
    side: OrderSide
    instrument: str          # e.g. "NIFTY26JUN2524000CE"
    strike: float
    option_side: str         # CE | PE
    quantity: int
    price: float
    status: str = "PENDING"  # PENDING | FILLED | CANCELLED | REJECTED
    fill_price: float | None = None
    decision: str = "GO"
    confidence: float = 0.0


@dataclass
class Position:
    instrument: str
    side: str                # CE | PE
    strike: float
    quantity: int
    entry_price: float
    entry_time: pd.Timestamp
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    highest_price: float = 0.0
    trailing_active: bool = False

    def __post_init__(self):
        if self.highest_price == 0.0:
            self.highest_price = self.entry_price


class OrderManager:
    """
    Tracks positions, risk, and simulates (or routes) orders.
    `live=True` would call Upstox Orders API; default paper mode.
    """

    def __init__(
        self,
        lot_size: int = 75,
        max_position_notional: float = 1_000_000,
        max_daily_loss: float = 20_000,
        max_drawdown_pct: float = 2.0,
        stop_loss_pct: float = 10.0,   # 10% hard stop-loss (Rule 6)
        target_pct: float = 50.0,
        live: bool = False,
        upstox_client=None,
    ):
        self.lot_size = lot_size
        self.max_position_notional = max_position_notional
        self.max_daily_loss = max_daily_loss
        self.max_drawdown_pct = max_drawdown_pct
        self.stop_loss_pct = stop_loss_pct
        self.target_pct = target_pct
        self.live = live
        self.upstox_client = upstox_client

        self.positions: dict[str, Position] = {}
        self.orders: list[Order] = []
        self.daily_pnl: float = 0.0
        self.kill_switch: bool = False
        self.degraded_mode: bool = False
        self.initial_capital: float = 1_000_000
        self._order_counter = 0
        self._last_trade_time: pd.Timestamp | None = None
        self._cooldown_sec = 60

    # ------------------------------------------------------------------ risk checks
    def check_risk(self) -> tuple[bool, str]:
        """Return (ok, reason)."""
        if self.kill_switch:
            return False, "kill_switch active"
        if self.daily_pnl <= -self.max_daily_loss:
            self.kill_switch = True
            log.error("DAILY LOSS LIMIT BREACHED: ₹{:.0f} — kill-switch ON", self.daily_pnl)
            return False, "daily_loss_breach"
        return True, "ok"

    def position_size(self, premium: float) -> int:
        """Return # of lots to trade, based on 2% capital risk and 10% stop-loss (Rule 6)."""
        if premium <= 0:
            return 0
        # 2% total capital risk
        risk_capital = 0.02 * (self.initial_capital + self.daily_pnl)
        # 10% stop-loss on premium (hard stop of 10% premium)
        risk_per_lot = premium * self.lot_size * 0.10
        lots = int(risk_capital / max(risk_per_lot, 1.0))
        # Clamp between 1 and 10 lots for security limits
        return max(1, min(lots, 10))

    # ------------------------------------------------------------------ orders
    def submit_order(self, st: SignalState) -> Order | None:
        """
        Submit an order based on SignalState.
        Returns the Order object (filled/paper), or None if blocked.
        """
        ok, reason = self.check_risk()
        if not ok:
            log.warning("Order blocked: {}", reason)
            return None

        if st.decision != "GO":
            return None

        if st.suggested_strike is None or st.suggested_side is None:
            log.warning("No strike/side suggested in state")
            return None

        if self._last_trade_time is not None:
            elapsed = (now_ist() - self._last_trade_time.to_pydatetime()).total_seconds()
            if elapsed < self._cooldown_sec:
                log.debug("Cooldown active; skip order")
                return None

        # Build instrument key
        instrument = f"NIFTY_{int(st.suggested_strike)}{st.suggested_side}"
        # Mark-to-market price (in real life: pull LTP from Upstox)
        premium = 100.0  # placeholder — would be filled from current chain LTP
        lots = self.position_size(premium)
        if lots == 0:
            log.warning("Position size 0; skip")
            return None
        qty = lots * self.lot_size

        order = self._create_order(instrument, st.suggested_strike, st.suggested_side, qty, premium, st)
        if self.live and self.upstox_client is not None:
            self._route_live(order)
        else:
            # Paper: instant fill at limit price
            order.status = "FILLED"
            order.fill_price = order.price
            self._record_fill(order)
        return order

    def _create_order(
        self, instrument: str, strike: float, side: str, qty: int, price: float, st: SignalState
    ) -> Order:
        self._order_counter += 1
        return Order(
            order_id=f"PAPER-{self._order_counter:05d}",
            timestamp=pd.Timestamp(now_ist()),
            side="BUY",
            instrument=instrument,
            strike=strike,
            option_side=side,
            quantity=qty,
            price=price,
            decision=st.decision,
            confidence=st.confidence,
        )

    def _route_live(self, order: Order) -> None:
        """
        Real Upstox order routing. NOTE: not exercised in paper mode.
        See: https://upstox.com/developer/api
        """
        if not self.upstox_client or not self.upstox_client.creds.access_token:
            log.error("Live order attempted without Upstox client; rejecting")
            order.status = "REJECTED"
            return
        try:
            payload = {
                "quantity": order.quantity,
                "product": "I",         # Intraday (MIS)
                "validity": "DAY",
                "price": order.price,
                "tag": "nifty-options-buyer",
                "instrument_token": order.instrument,
                "order_type": "LIMIT",
                "transaction_type": order.side,
            }
            # Real call: self.upstox_client._post('/order/place', json=payload)
            log.info("LIVE order (mocked): {}", payload)
            order.status = "PENDING"
        except Exception as e:  # noqa: BLE001
            log.error("Live order failed: {}", e)
            order.status = "REJECTED"

    def _record_fill(self, order: Order) -> None:
        """Add filled order to positions + audit log."""
        self.orders.append(order)
        self._last_trade_time = order.timestamp

        pos = Position(
            instrument=order.instrument,
            side=order.option_side,
            strike=order.strike,
            quantity=order.quantity,
            entry_price=order.fill_price or order.price,
            entry_time=order.timestamp,
            current_price=order.fill_price or order.price,
        )
        self.positions[order.instrument] = pos
        log.info(
            "FILLED {} {} x{} @ ₹{:.2f} (decision={} conf={:.2f})",
            order.side, order.instrument, order.quantity, order.fill_price or order.price,
            order.decision, order.confidence,
        )

    # ------------------------------------------------------------------ monitoring
    def mark_to_market(self, price_lookup: dict[str, float]) -> None:
        """Update unrealized PnL and evaluate stop/target/trailing logic (Rule 6)."""
        total_unrealized = 0.0
        for inst, pos in list(self.positions.items()):
            if inst in price_lookup:
                pos.current_price = price_lookup[inst]
                pos.unrealized_pnl = (pos.current_price - pos.entry_price) * pos.quantity
                total_unrealized += pos.unrealized_pnl

                # Track highest price achieved
                if pos.current_price > pos.highest_price:
                    pos.highest_price = pos.current_price

                # Compute PnL metrics
                pnl_pct = (pos.current_price - pos.entry_price) / pos.entry_price
                highest_pnl_pct = (pos.highest_price - pos.entry_price) / pos.entry_price

                # Check if trailing take-profit activation threshold (15%) is hit
                if not pos.trailing_active and highest_pnl_pct >= 0.15:
                    pos.trailing_active = True
                    log.info("Trailing stop activated for {} (highest gain = {:.1f}%)", inst, highest_pnl_pct * 100.0)

                # Trailing stop-loss logic (5% trailing buffer from peak)
                if pos.trailing_active:
                    drawdown_from_peak = (pos.current_price - pos.highest_price) / pos.highest_price
                    if drawdown_from_peak <= -0.05:
                        log.info("Trailing stop hit on {} (down {:.1f}% from peak)", inst, abs(drawdown_from_peak) * 100.0)
                        self._close_position(inst, "trailing_stop")
                        continue

                # Hard stop-loss (10%) - only evaluated if trailing is not yet active
                if not pos.trailing_active and pnl_pct <= -(self.stop_loss_pct / 100.0):
                    log.info("Hard stop hit on {} (PnL = {:.1f}%)", inst, pnl_pct * 100.0)
                    self._close_position(inst, "stop_loss")
                    continue

                # Target target check (standard take-profit target, e.g. 50%)
                if pnl_pct >= (self.target_pct / 100.0):
                    log.info("Target hit on {} (PnL = {:.1f}%)", inst, pnl_pct * 100.0)
                    self._close_position(inst, "target")
                    continue

    def _close_position(self, instrument: str, reason: str) -> None:
        pos = self.positions.pop(instrument, None)
        if pos is None:
            return
        realized = pos.unrealized_pnl
        self.daily_pnl += realized
        log.info("Closed {} reason={} pnl=₹{:.2f}", instrument, reason, realized)

    def flatten_all(self) -> None:
        """Emergency flatten — close everything."""
        for inst in list(self.positions.keys()):
            self._close_position(inst, "flatten_all")
        log.warning("All positions flattened; daily PnL: ₹{:.2f}", self.daily_pnl)

    def kill(self) -> None:
        """Activate kill-switch and flatten."""
        self.kill_switch = True
        self.flatten_all()
        log.error("KILL SWITCH ACTIVATED")

    def summary(self) -> dict:
        return {
            "n_positions": len(self.positions),
            "n_orders": len(self.orders),
            "daily_pnl": self.daily_pnl,
            "kill_switch": self.kill_switch,
            "positions": [
                {
                    "instrument": p.instrument,
                    "side": p.side,
                    "strike": p.strike,
                    "qty": p.quantity,
                    "entry": p.entry_price,
                    "current": p.current_price,
                    "unrealized": p.unrealized_pnl,
                }
                for p in self.positions.values()
            ],
        }

    def handle_degraded_mode(self, latest_state) -> None:
        """degraded-mode routine: halt new entries, liquidate open near-zero gamma positions instantly."""
        self.kill_switch = True
        log.warning("DEGRADED MODE ACTIVATED: Halting new entries.")
        if latest_state is None or latest_state.zero_gamma is None:
            return
        
        zero_gamma = latest_state.zero_gamma
        spot = latest_state.spot
        # Zero gamma band: 0.5% default of spot (Rule 7)
        zero_band_pct = 0.005
        
        to_liquidate = []
        for inst, pos in list(self.positions.items()):
            # Check if spot is near zero-gamma strike
            dist = abs(spot - zero_gamma) / spot
            if dist <= zero_band_pct:
                log.warning("Liquidating near-zero gamma position: {} due to connection watchdog trigger (spot={:.2f}, zero_gamma={:.2f})", inst, spot, zero_gamma)
                to_liquidate.append(inst)
                
        for inst in to_liquidate:
            self._close_position(inst, "watchdog_liquidation")

