"""
Main entry point — CLI for the NIFTY options system.
Usage:
  python -m main dashboard          # launch live dashboard (mock data)
  python -m main backtest --days 5  # run backtest on synthetic data
  python -m main smoke              # quick smoke test of all modules
  python -m main backtest --source nse --csv path/to/nse_chain.csv
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

# Reconfigure stdout to use UTF-8 on Windows to support currency symbols like ₹
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

from pathlib import Path

from config import get_settings
from utils.logger import get_logger, setup_logger
from utils.time_utils import now_ist

log = get_logger()


def cmd_dashboard(args) -> int:
    from dashboard.app import run_dashboard
    run_dashboard(host=args.host, port=args.port, debug=args.debug)
    return 0


def cmd_backtest(args) -> int:
    """Run a backtest. Default: synthetic data. Use --source db to replay from DuckDB."""
    from backtest.engine import Backtester, summarize
    from signals.composite import CompositeEngine

    if args.source == "db":
        from data.store import MarketDataStore
        store = MarketDataStore()
        log.info("Loading market data from DuckDB for backtest...")
        ds = store.load_data(start_date=args.start_date, end_date=args.end_date)
        if ds.empty:
            log.error("No data found in DuckDB for the specified range.")
            return 1
        log.info("Loaded {} rows from DuckDB", len(ds))
        # Add dummy spot_volume if missing
        if "spot_volume" not in ds.columns:
            ds["spot_volume"] = 0

        spot_df = ds.groupby("timestamp").agg({"spot": "first", "spot_volume": "first"}).reset_index()
        chains = [g.reset_index(drop=True) for _, g in ds.groupby("timestamp")]
    elif args.csv:
        # Real NSE replay (CSV must contain timestamp, strike, ce_ltp, pe_ltp, etc.)
        raise NotImplementedError("NSE CSV replay not yet implemented; please contribute.")
    else:
        # Synthetic
        from data.mock_data import build_intraday_dataset
        log.info(f"Generating {args.minutes} min of synthetic intraday data (seed={args.seed})")
        ds = build_intraday_dataset(n_minutes=args.minutes, seed=args.seed)
        # Build spot_df and chain list
        spot_df = ds.groupby("timestamp").agg({"spot": "first", "spot_volume": "first"}).reset_index()
        chains = [g.reset_index(drop=True) for _, g in ds.groupby("timestamp")]

    engine = CompositeEngine()
    bt = Backtester(engine=engine, capital=args.capital, lot_size=args.lot_size)
    result = bt.run(spot_df, chains)
    summary = summarize(result)

    print("\n" + "=" * 60)
    print("BACKTEST RESULTS")
    print("=" * 60)
    for k, v in summary.items():
        print(f"  {k:>20}: {v}")
    print("=" * 60)

    if not result.equity_curve.empty:
        out_path = Path("data") / f"backtest_equity_{now_ist():%Y%m%d_%H%M%S}.csv"
        out_path.parent.mkdir(exist_ok=True)
        result.equity_curve.to_csv(out_path)
        print(f"  Equity curve saved to {out_path}")
    return 0


def cmd_smoke(args) -> int:
    """Quick end-to-end test of feature + signal + backtest modules."""
    from backtest.engine import Backtester
    from data.mock_data import build_intraday_dataset
    from signals.composite import CompositeEngine

    print("=" * 60)
    print("NIFTY OPTIONS BUYER — SMOKE TEST")
    print("=" * 60)
    print(f"Time: {now_ist()}")

    # 1. Generate synthetic data
    print("\n[1/4] Generating 30 minutes of synthetic intraday data…")
    ds = build_intraday_dataset(n_minutes=30, seed=42)
    spot_df = ds.groupby("timestamp").agg({"spot": "first", "spot_volume": "first"}).reset_index()
    chains = [g.reset_index(drop=True) for _, g in ds.groupby("timestamp")]
    print(f"      Generated {len(chains)} snapshots with {len(ds)} total rows")

    # 2. Run signal engine
    print("\n[2/4] Running composite signal engine on first snapshot…")
    engine = CompositeEngine()
    st = engine.on_tick(chain=chains[0], spot=float(spot_df["spot"].iloc[0]))
    print(f"      Spot: ₹{st.spot:,.2f}")
    print(f"      PCR: {st.pcr:.2f} ({st.pcr_regime})")
    print(f"      IV ATM: {st.iv_total:.3f}")
    print(f"      Net GEX: ₹{st.net_gex/1e7:.2f} Cr ({st.gex_regime})")
    print(f"      Call wall: {st.call_wall}, Put wall: {st.put_wall}")
    print(f"      Max pain: {st.max_pain}")
    print(f"      Momentum index: {st.momentum_index:+.3f}")
    print(
        f"      Sub-signals: vol_oi={st.sub_vol_oi} gamma={st.sub_gamma} leadlag={st.sub_leadlag} notrade={st.sub_no_trade}"
    )
    print(f"      DECISION: {st.decision} (conf {st.confidence:.2f})")
    for r in st.decision_reasons:
        print(f"        - {r}")

    # 3. Run backtest
    print("\n[3/4] Running mini-backtest over 30 minutes…")
    bt = Backtester(engine=engine, capital=1_000_000, lot_size=75)
    result = bt.run(spot_df, chains)
    print(f"      Trades: {result.n_trades}, PnL: ₹{result.total_pnl:,.0f}, Win rate: {result.win_rate:.1f}%")

    # 4. Order manager
    print("\n[4/4] Testing order manager…")
    from execution.order_manager import OrderManager

    om = OrderManager(lot_size=75, max_position_notional=1_000_000, max_daily_loss=20_000)
    o = om.submit_order(st)
    if o:
        print(f"      Order: {o.order_id} {o.side} {o.instrument} x{o.quantity} @ ₹{o.price}")
    else:
        print("      No order (decision was not GO)")
    print(f"      Open positions: {om.summary()['n_positions']}")
    print(f"      Kill switch: {om.kill_switch}")

    print("\n" + "=" * 60)
    print("SMOKE TEST COMPLETE ✓")
    print("=" * 60)
    return 0


def cmd_upstox_smoke(args) -> int:
    """Resolve Upstox instrument identifiers for the engine's suggested strike/side."""
    from data.mock_data import build_intraday_dataset
    from data.upstox_client import resolve_option_instrument_master
    from signals.composite import CompositeEngine

    print("=" * 60)
    print("UPSTOX TOKEN RESOLUTION — SMOKE TEST")
    print("=" * 60)
    print(f"Time: {now_ist()}")

    ds = build_intraday_dataset(n_minutes=args.minutes, seed=args.seed)
    spot_df = ds.groupby("timestamp").agg({"spot": "first", "spot_volume": "first"}).reset_index()
    chains = [g.reset_index(drop=True) for _, g in ds.groupby("timestamp")]
    if not chains:
        print("No synthetic chain snapshots produced.")
        return 1

    chain0 = chains[0]
    spot0 = float(spot_df["spot"].iloc[0])

    engine = CompositeEngine()
    st = engine.on_tick(chain=chain0, spot=spot0)

    chosen_strike = st.suggested_strike
    chosen_side = st.suggested_side

    print("\n[1/2] Engine suggestion")
    print(f"  chosen strike: {chosen_strike}")
    print(f"  chosen side:   {chosen_side}")
    print(f"  decision:      {st.decision} (conf {st.confidence:.2f})")

    if chosen_strike is None or chosen_side is None:
        print("No strike/side suggested; cannot resolve token.")
        return 1

    # Synthetic chains don't carry expiry; pick next Thursday for stability.
    from datetime import datetime, timedelta

    today = datetime.now()
    days_to_thu = 3 - today.weekday()
    if days_to_thu < 0:
        days_to_thu += 7
    expiry = (today + timedelta(days=days_to_thu)).strftime("%Y-%m-%d")

    print("\n[2/2] Token resolution (Upstox instruments master lookup)")
    rec = resolve_option_instrument_master(
        underlying="Nifty 50",
        expiry=expiry,
        strike=float(chosen_strike),
        option_type=str(chosen_side),
    )

    if not rec:
        print(
            f"  No match found for underlying=Nifty 50 expiry={expiry} strike={chosen_strike} type={chosen_side}"
        )
        return 1

    tradingsymbol = rec.get("tradingsymbol")
    instrument_key = rec.get("instrument_key")
    instrument_token = rec.get("instrument_token")

    print(f"  expiry:                 {expiry}")
    print(f"  matched tradingsymbol: {tradingsymbol}")
    print(f"  resolved instrument_key: {instrument_key}")
    print(f"  resolved instrument_token: {instrument_token}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="nifty-options-buyer", description="NIFTY options buying system")
    sub = parser.add_subparsers(dest="cmd")

    # dashboard
    p_dash = sub.add_parser("dashboard", help="Run live dashboard")
    p_dash.add_argument("--host", default="127.0.0.1")
    p_dash.add_argument("--port", type=int, default=5000)
    p_dash.add_argument("--debug", action="store_true")
    p_dash.set_defaults(func=cmd_dashboard)

    # backtest
    p_bt = sub.add_parser("backtest", help="Run backtest on synthetic or historical data")
    p_bt.add_argument("--minutes", type=int, default=375, help="minutes of synthetic data (default=375=full day)")
    p_bt.add_argument("--seed", type=int, default=42)
    p_bt.add_argument("--capital", type=float, default=1_000_000)
    p_bt.add_argument("--lot-size", type=int, default=75)
    p_bt.add_argument("--source", choices=["synthetic", "nse", "db"], default="synthetic")
    p_bt.add_argument("--csv", type=str, default=None)
    p_bt.add_argument("--start-date", type=str, default=None, help="YYYY-MM-DD for DB source")
    p_bt.add_argument("--end-date", type=str, default=None, help="YYYY-MM-DD for DB source")
    p_bt.set_defaults(func=cmd_backtest)

    # smoke
    p_smoke = sub.add_parser("smoke", help="Quick smoke test of all modules")
    p_smoke.set_defaults(func=cmd_smoke)

    # upstox token resolution smoke
    p_upstox = sub.add_parser("upstox-smoke", help="Resolve Upstox instrument token for chosen strike/side")
    p_upstox.add_argument("--minutes", type=int, default=30, help="minutes of synthetic data to generate (default=30)")
    p_upstox.add_argument("--seed", type=int, default=42)
    p_upstox.add_argument("--expiry-days-ahead", type=int, default=3, help="used to pick next expiry proxy for synthetic test")
    p_upstox.set_defaults(func=lambda args: cmd_upstox_smoke(args))

    args = parser.parse_args()
    settings = get_settings()
    setup_logger(level=settings["app"]["log_level"])

    if not args.cmd:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())