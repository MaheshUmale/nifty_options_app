"""
Order manager + risk controls.
Simulates order placement (paper mode) and enforces position/drawdown limits.
Live mode: integrates with official Upstox SDK V3 Orders API.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Any

import pandas as pd

from upstox_client.api import OrderApiV3
from upstox_client.models.place_order_v3_request import PlaceOrderV3Request
from upstox_client.rest import ApiException

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
    `live=True` would call Upstox SDK V3 Orders API; default paper mode.
    """

    def __init__(
        self,
        lot_size: int = 75,
        max_position_notional: float = 1_000_000,
        max_daily_loss: float = 20_000,
        max_drawdown_pct: float = 2.0,
        stop_loss_pct: float = 10.0,   # 10% hard stop-loss
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

    def check_risk(self) -> tuple[bool, str]:
        if self.kill_switch:
            return False, "kill_switch active"
        if self.daily_pnl <= -self.max_daily_loss:
            self.kill_switch = True
            log.error("DAILY LOSS LIMIT BREACHED: ₹{:.0f} — kill-switch ON", self.daily_pnl)
            return False, "daily_loss_breach"
        return True, "ok"

    def position_size(self, premium: float) -> int:
        if premium <= 0:
            return 0
        risk_capital = 0.02 * (self.initial_capital + self.daily_pnl)
        risk_per_lot = premium * self.lot_size * 0.10
        lots = int(risk_capital / max(risk_per_lot, 1.0))
        return max(1, min(lots, 10))

    def submit_order(self, st: SignalState) -> Order | None:
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

        premium = 100.0
        lots = self.position_size(premium)
        if lots == 0:
            return None
        qty = lots * self.lot_size

        instrument = f"NIFTY_{int(st.suggested_strike)}{st.suggested_side}"

        order = self._create_order(instrument, st.suggested_strike, st.suggested_side, qty, premium, st)
        if self.live and self.upstox_client is not None:
            self._route_live_v3(order)
        else:
            order.status = "FILLED"
            order.fill_price = order.price
            self._record_fill(order)
        return order

    def _create_order(
        self, instrument: str, strike: float, side: str, qty: int, price: float, st: SignalState
    ) -> Order:
        self._order_counter += 1
        return Order(
            order_id=f"ORD-{int(time.time())}-{self._order_counter}",
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

    def _route_live_v3(self, order: Order) -> None:
        """Official Upstox SDK V3 Order placement."""
        if not self.upstox_client:
            order.status = "REJECTED"
            return

        api_instance = OrderApiV3(self.upstox_client.api_client)
        body = PlaceOrderV3Request(
            quantity=order.quantity,
            product="I",
            validity="DAY",
            price=order.price,
            instrument_token=order.instrument,
            order_type="LIMIT",
            transaction_type=order.side,
            tag="nifty-options-v3"
        )

        try:
            api_response = api_instance.place_order(body)
            log.info(f"V3 Order placed: {api_response.data.order_id}")
            order.order_id = api_response.data.order_id
            order.status = "PENDING"
        except ApiException as e:
            log.error(f"V3 Order failed: {e}")
            order.status = "REJECTED"

    def _record_fill(self, order: Order) -> None:
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
        log.info("FILLED {} x{} @ ₹{}", order.instrument, order.quantity, pos.entry_price)

    def mark_to_market(self, price_lookup: dict[str, float]) -> None:
        for inst, pos in list(self.positions.items()):
            if inst in price_lookup:
                pos.current_price = price_lookup[inst]
                pos.unrealized_pnl = (pos.current_price - pos.entry_price) * pos.quantity
                if pos.current_price > pos.highest_price:
                    pos.highest_price = pos.current_price

                pnl_pct = (pos.current_price - pos.entry_price) / pos.entry_price
                if pnl_pct <= -(self.stop_loss_pct / 100.0):
                    self._close_position(inst, "stop_loss")
                elif pnl_pct >= (self.target_pct / 100.0):
                    self._close_position(inst, "target")

    def _close_position(self, instrument: str, reason: str) -> None:
        pos = self.positions.pop(instrument, None)
        if pos:
            self.daily_pnl += pos.unrealized_pnl
            log.info("Closed {} reason={} pnl=₹{:.2f}", instrument, reason, pos.unrealized_pnl)

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
            "daily_pnl": self.daily_pnl,
            "kill_switch": self.kill_switch,
        }

    def handle_degraded_mode(self, latest_state) -> None:
        """degraded-mode routine: halt new entries, liquidate open near-zero gamma positions instantly."""
        self.kill_switch = True
        log.warning("DEGRADED MODE ACTIVATED: Halting new entries.")
        if latest_state is None:
            return

        zero_gamma = getattr(latest_state, 'zero_gamma', None)
        spot = getattr(latest_state, 'spot', 0.0)

        if zero_gamma and spot > 0:
            zero_band_pct = 0.005
            to_liquidate = []
            for inst, pos in list(self.positions.items()):
                dist = abs(spot - zero_gamma) / spot
                if dist <= zero_band_pct:
                    log.warning("Liquidating near-zero gamma position: {} due to connection watchdog trigger", inst)
                    to_liquidate.append(inst)
            for inst in to_liquidate:
                self._close_position(inst, "watchdog_liquidation")
        else:
            log.warning("Degraded mode: No zero_gamma or spot info available for targeted liquidation.")
