"""
Signal orchestrator.
Glue layer that connects: data source → feature engine → signal engine → order manager.
Runs as a background thread in the dashboard, or as a standalone CLI in backtest/live.
"""
from __future__ import annotations

import threading
import time
from queue import Empty, Queue
from typing import Callable

import pandas as pd

from signals.composite import CompositeEngine
from signals.state import SignalState
from utils.logger import get_logger
from utils.time_utils import now_ist

log = get_logger()


class SignalOrchestrator:
    """
    Pulls ticks from a data source queue, runs the composite engine,
    and forwards SignalState to listeners (dashboard, order manager).
    """

    def __init__(
        self,
        data_source,                  # object with .queue (Queue) and .start() / .stop()
        engine: CompositeEngine | None = None,
        on_signal: Callable[[SignalState], None] | None = None,
        poll_interval_sec: float = 1.0,
        order_manager = None,
    ):
        self.data_source = data_source
        self.engine = engine or CompositeEngine()
        self.on_signal = on_signal
        self.poll_interval = poll_interval_sec
        self.order_manager = order_manager
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.latest: SignalState | None = None
        self.history: list[SignalState] = []
        self._spot_price: float = 0.0
        self.last_tick_time = time.time()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.data_source.start()
        self.last_tick_time = time.time()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        log.info("SignalOrchestrator started")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self.data_source:
            try:
                self.data_source.stop()
            except Exception:
                pass
        log.info("SignalOrchestrator stopped")

    def _run(self) -> None:
        while not self._stop.is_set():
            # Connection Watchdog Check
            if self.order_manager and self.order_manager.live:
                gap = time.time() - self.last_tick_time
                if gap > 5.0 and not self.order_manager.degraded_mode:
                    log.error("CONNECTION WATCHDOG ALERT: Data delivery gap exceeded 5s (elapsed: {:.1f}s)!", gap)
                    self.order_manager.degraded_mode = True
                    self.order_manager.handle_degraded_mode(self.latest)

            try:
                chain = self.data_source.queue.get(timeout=self.poll_interval)
            except Empty:
                continue
            
            self.last_tick_time = time.time()
            if self.order_manager and getattr(self.order_manager, "degraded_mode", False):
                log.info("Data delivery resumed. Turning off degraded mode.")
                self.order_manager.degraded_mode = False

            try:
                if chain is None or (isinstance(chain, pd.DataFrame) and chain.empty):
                    continue

                spot = 0.0
                if "underlying_spot" in chain.columns and len(chain) > 0:
                    val = chain["underlying_spot"].iloc[0]
                    if val is not None:
                        spot = float(val)

                # If underlying_spot is missing or 0, fallback to spot column
                if spot == 0 and "spot" in chain.columns and len(chain) > 0:
                    val = chain["spot"].iloc[0]
                    if val is not None:
                        spot = float(val)

                if spot == 0:
                    log.warning("No spot price found in chain snapshot; skipping tick.")
                    continue
                st = self.engine.on_tick(chain=chain, spot=spot)
                self.latest = st
                self.history.append(st)
                # Keep only last N states
                if len(self.history) > 2000:
                    self.history = self.history[-2000:]
                if self.on_signal:
                    try:
                        self.on_signal(st)
                    except Exception as e:
                        log.error("on_signal handler error: {}", e)
            except Exception as e:
                log.exception("Error in signal loop: {}", e)
            time.sleep(self.poll_interval)

    # Convenience for backtests
    def run_once(self, chain: pd.DataFrame, spot: float) -> SignalState:
        st = self.engine.on_tick(chain=chain, spot=spot)
        self.latest = st
        return st
