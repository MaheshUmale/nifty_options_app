"""
Upstox streaming utilities.

SDK websocket integration was removed.
This module provides polling-based REST streaming as a replacement.
"""
from __future__ import annotations

from queue import Queue
import threading
import os

from utils.logger import get_logger
from data.upstox_client import make_client_from_env, resolve_option_instrument_master
import time

log = get_logger()


class UpstoxStreamer:
    """
    Polling-based replacement for the previous SDK websocket client.

    Keeps the same public surface:
      - connect()
      - subscribe(instrument_keys, mode=...)
      - disconnect()

    Internally it runs a background thread that periodically fetches LTP
    (and optionally option chain via UpstoxLiveSource logic).
    """

    def __init__(self, access_token: str):
        self.access_token = access_token
        self._thread = None
        self._stop = threading.Event()
        self.queue = Queue()
        self.instrument_keys: list[str] = []
        self.mode = "full"

        # Reuse existing REST-capable implementation
        self._live_source = None

    def connect(self):
        """Start background polling."""
        self._stop.clear()
        if self._live_source is None:
            # UpstoxLiveSource already starts a polling loop and pushes DataFrames to its queue.
            # We create it lazily once connect() is called.
            self._live_source = UpstoxLiveSource(poll_interval_sec=5.0)
        # Mirror selected instrument keys + keep previous default behavior.
        if self.instrument_keys:
            # UpstoxLiveSource currently uses a single instrument_key; set it to first key for now.
            self._live_source.instrument_key = self.instrument_keys[0]
        self._live_source.start()

    def subscribe(self, instrument_keys: list[str], mode: str = "full"):
        """Register instruments to poll."""
        self.instrument_keys = list(instrument_keys or [])
        self.mode = mode
        log.info("Subscribed to {} instruments in {} mode (polling)", len(self.instrument_keys), mode)

    def disconnect(self):
        """Stop background polling."""
        self._stop.set()
        if self._live_source is not None:
            self._live_source.stop()

class MockWebSocket:
    """Synthetic WebSocket for testing."""

    def __init__(self, rate_hz: float = 1.0):
        self.interval = 1.0 / rate_hz
        self.queue = Queue()
        self.is_running = False

    def start(self, n_minutes: int = 375):
        self.is_running = True
        self._thread = threading.Thread(target=self._run, args=(n_minutes,), daemon=True)
        self._thread.start()

    def _run(self, n_minutes: int):
        from data.mock_data import build_intraday_dataset
        import time
        ds = build_intraday_dataset(n_minutes=n_minutes)
        chains = [g for _, g in ds.groupby("timestamp")]

        for chain in chains:
            if not self.is_running:
                break
            self.queue.put(chain)
            time.sleep(self.interval)

    def stop(self):
        self.is_running = False


class UpstoxLiveSource:
    """
    Live data source using Upstox REST endpoints (polling).
    """
    def __init__(self, poll_interval_sec: float = 5.0):
        self.poll_interval = poll_interval_sec
        self.queue = Queue()
        self.client = make_client_from_env()
        # Load instrument keys from environmentking fallback to a single default.
        self.instrument_keys: list[str] = self._load_instrument_keys()

        try:
            token = (
                getattr(self.client, "creds", None)
                and getattr(self.client.creds, "access_token", None)
            )
            token_preview = (token[:6] + "..." + token[-4:]) if token else None
        except Exception:
            token_preview = None

        log.info(
            "UpstoxLiveSource init instrument_keys={} token_preview={}",
            self.instrument_keys,
            token_preview,
        )
        self._stop = threading.Event()
        self._thread = None

    def _load_instrument_keys(self) -> list[str]:
        """Parse ``UPSTOX_SPOT_INSTRUMENT_KEY`` env var with a sensible fallback.

        The original implementation returned an empty list when the variable
        was missing, which caused the streaming loop to skip polling entirely.
        For development and quick‑start scenarios we provide a default Spot
        instrument key that matches the one used in the example ``WS_INSTRUMENTS``
        configuration (the Nifty 50 index).  This ensures the dashboard can
        display live data out‑of‑the‑box while still honouring any explicit user
        configuration.

        The variable may contain a single key or a comma‑separated list of keys.
        Empty strings are ignored and whitespace around each key is stripped.
        If the variable is not set or yields no keys, a default list containing
        ``"NSE_INDEX|Nifty 50"`` is returned.
        """
        raw = os.getenv("UPSTOX_SPOT_INSTRUMENT_KEY", "")
        keys = [k.strip() for k in raw.split(",") if k.strip()]
        if not keys:
            # Fallback to a commonly used index key – this mirrors the default
            # used elsewhere in the project (see WS_INSTRUMENTS).
            log.info("UPSTOX_SPOT_INSTRUMENT_KEY not set; falling back to default spot key")
            keys = ["NSE_INDEX|Nifty 50"]
        return keys

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        log.info("UpstoxLiveSource (V3) started (polling every {}s)", self.poll_interval)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _poll_loop(self):
        """Continuously poll market data and push transformed DataFrames to the queue.

        The method fetches LTP for all configured instrument keys. For backward
        compatibility, the first key is used as the underlying instrument when
        fetching the option chain and building the DataFrame.
        """
        while not self._stop.is_set():
            # If no instrument keys are configured, skip polling and warn the user.
            if not self.instrument_keys:
                log.warning("No instrument keys configured for UpstoxLiveSource; skipping poll cycle.")
                time.sleep(self.poll_interval)
                continue
            try:
                # Request LTP for all configured instrument keys.
                resp = self.client.get_market_quote_ltp(self.instrument_keys)
                
                if not isinstance(resp, dict):
                    log.error("Unexpected response type from get_market_quote_ltp: {}", type(resp))
                    time.sleep(self.poll_interval)
                    continue

                status = resp.get("status")
                data = resp.get("data", {})

                if status != "success":
                    log.error("Upstox API error (LTP): status={} body={}", status, resp.get("errors") or resp)
                    time.sleep(self.poll_interval)
                    continue

                if not data:
                    log.warning("Upstox API returned success but empty data for keys: {}", self.instrument_keys)
                    time.sleep(self.poll_interval)
                    continue

                # Determine spot price using the first instrument key.
                spot: float | None = None
                first_key = self.instrument_keys[0]
                if first_key in data:
                    spot = data[first_key].get("last_price")

                if first_key:
                    # Dynamically find the nearest (current) expiry date
                    contracts_resp = self.client.get_option_contracts(first_key)
                    current_expiry = None
                    if contracts_resp.get("status") == "success" and contracts_resp.get("data"):
                        expiries = sorted(list(set(item["expiry_date"] for item in contracts_resp["data"])))
                        if expiries:
                            current_expiry = expiries[0]
                            log.debug("Current Expiry Detected: {}", current_expiry)

                    if not current_expiry:
                        # Fallback to manual calculation if API fails
                        from datetime import datetime, timedelta
                        today = datetime.now()
                        days_ahead = 3 - today.weekday()
                        if days_ahead < 0:
                            days_ahead += 7
                        current_expiry = (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
                        log.warning("Option contracts API failed or returned no expiries; using fallback expiry: {}", current_expiry)

                    chain_resp = self.client.get_option_chain(first_key, current_expiry)
                    if chain_resp.get("status") == "success":
                        underlying_name = (
                            first_key.split("|", 1)[1]
                            if "|" in first_key
                            else first_key
                        )
                        df = self._transform_chain(
                            chain_resp["data"],
                            spot=spot,
                            expiry_date=current_expiry,
                            underlying_name=underlying_name,
                        )
                        self.queue.put(df)
                    else:
                        log.error("Live Option Chain failed: {}", chain_resp.get("errors"))
                else:
                    log.error("Live Spot Quote (V3) failed: {}", resp.get("errors"))
            except Exception as e:
                traceback = getattr(e, "__traceback__", None)
                if traceback:
                    import traceback as tb
                    tb_str = "".join(tb.format_tb(traceback))
                    log.error("Exception in UpstoxLiveSource (V3): {} Traceback: {}", e, tb_str)
                log.error("Error in UpstoxLiveSource (V3): {}", e)
            time.sleep(self.poll_interval)

    def _transform_chain(self, data, spot: float, expiry_date: str, underlying_name: str):
        import pandas as pd

        rows = []
        ts = pd.Timestamp.now(tz="Asia/Kolkata")

        for item in data:
            strike = item.get("strike_price")

            ce = item.get("call_options", {}).get("market_data", {})
            pe = item.get("put_options", {}).get("market_data", {})

            # Resolve Upstox identifiers (token/key + tradingsymbol) per strike+CE/PE
            ce_rec = None
            pe_rec = None
            try:
                if strike is not None:
                    ce_rec = resolve_option_instrument_master(
                        underlying=underlying_name,
                        expiry=expiry_date,
                        strike=float(strike),
                        option_type="CE",
                    )
                    pe_rec = resolve_option_instrument_master(
                        underlying=underlying_name,
                        expiry=expiry_date,
                        strike=float(strike),
                        option_type="PE",
                    )
            except Exception:
                # Keep resilient: if lookup fails, still return market data columns.
                ce_rec = None
                pe_rec = None

            rows.append({
                "timestamp": ts,
                "spot": spot,
                "expiry": expiry_date,
                "strike": strike,

                # CE identifiers + market data
                "tradingsymbol_ce": (ce_rec or {}).get("tradingsymbol"),
                "instrument_key_ce": (ce_rec or {}).get("instrument_key"),
                "instrument_token_ce": (ce_rec or {}).get("instrument_token"),
                "ce_ltp": ce.get("ltp", 0),
                "ce_volume": ce.get("volume", 0),
                "ce_oi": ce.get("oi", 0),

                # PE identifiers + market data
                "tradingsymbol_pe": (pe_rec or {}).get("tradingsymbol"),
                "instrument_key_pe": (pe_rec or {}).get("instrument_key"),
                "instrument_token_pe": (pe_rec or {}).get("instrument_token"),
                "pe_ltp": pe.get("ltp", 0),
                "pe_volume": pe.get("volume", 0),
                "pe_oi": pe.get("oi", 0),

                # NOTE: IV/Greeks still placeholders until feature pipeline is upgraded
                "ce_iv": 0.15,
                "ce_delta": 0.5,
                "ce_gamma": 0.001,
                "ce_theta": -1,
                "ce_vega": 0.1,
                "pe_iv": 0.15,
                "pe_delta": -0.5,
                "pe_gamma": 0.001,
                "pe_theta": -1,
                "pe_vega": 0.1,
            })

        return pd.DataFrame(rows)
