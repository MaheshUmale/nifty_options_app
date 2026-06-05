"""
Dash dashboard for live signal monitoring.
Run with: `python -m dashboard.app` (after `pip install -r requirements.txt`).
"""
from __future__ import annotations

import json
import threading
import time
import traceback
from datetime import timedelta

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, dcc, html
from plotly.subplots import make_subplots

from config import get_settings
from data.streaming import MockWebSocket
from execution.order_manager import OrderManager
from signals.orchestrator import SignalOrchestrator
from signals.state import SignalState
from utils.logger import setup_logger, get_logger
from utils.time_utils import IST, now_ist

log = get_logger()


def make_layout() -> html.Div:
    return dbc.Container(
        [
            dbc.Row(
                dbc.Col(
                    html.H2("NIFTY Options Buyer — Live Signal Dashboard", className="text-center my-3"),
                    width=12,
                )
            ),
            # Top status row
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardBody(
                                    [
                                        html.H6("NIFTY Spot", className="text-muted"),
                                        html.H3(id="kpi-spot", children="—"),
                                        html.Small(id="kpi-spot-time", className="text-muted"),
                                    ]
                                )
                            ],
                            style={"border": "2px solid #007bff", "backgroundColor": "#f8f9fa"}
                        ),
                        width=3,
                    ),
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardBody(
                                    [
                                        html.H6("Decision", className="text-muted"),
                                        html.H3(id="kpi-decision-val", children="—"),
                                        html.Small(id="kpi-conf", className="text-muted"),
                                    ]
                                )
                            ],
                            style={"border": "2px solid #28a745", "backgroundColor": "#f8f9fa"}
                        ),
                        width=3,
                    ),
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardBody(
                                    [
                                        html.H6("PCR", className="text-muted"),
                                        html.H3(id="kpi-pcr", children="—"),
                                        html.Small(id="kpi-pcr-regime", className="text-muted"),
                                    ]
                                )
                            ],
                            style={"border": "2px solid #17a2b8", "backgroundColor": "#f8f9fa"}
                        ),
                        width=3,
                    ),
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardBody(
                                    [
                                        html.H6("Net GEX", className="text-muted"),
                                        html.H3(id="kpi-gex", children="—"),
                                        html.Small(id="kpi-gex-regime", className="text-muted"),
                                    ]
                                )
                            ],
                            style={"border": "2px solid #ffc107", "backgroundColor": "#f8f9fa"}
                        ),
                        width=3,
                    ),
                ],
                className="mb-3",
            ),
            # Charts row 1
            dbc.Row(
                [
                    dbc.Col(dcc.Graph(id="chart-pcr", style={"border": "1px solid #ddd"}), width=6),
                    dbc.Col(dcc.Graph(id="chart-iv", style={"border": "1px solid #ddd"}), width=6),
                ]
            ),
            # Charts row 2
            dbc.Row(
                [
                    dbc.Col(dcc.Graph(id="chart-gex", style={"border": "1px solid #ddd"}), width=6),
                    dbc.Col(dcc.Graph(id="chart-vwap", style={"border": "1px solid #ddd"}), width=6),
                ]
            ),
            # Sub-signals & reasons
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader("Sub-Signals"),
                                dbc.CardBody(id="sub-signals"),
                            ]
                        ),
                        width=6,
                    ),
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader("Execution Decision & Reasons"),
                                dbc.CardBody(id="decision-card"),
                            ]
                        ),
                        width=6,
                    ),
                ]
            ),
            # Refresh
            dcc.Interval(id="interval", interval=2000, n_intervals=0),
            # Hidden state
            dcc.Store(id="signal-store"),
        ],
        fluid=True,
    )


def build_app(orchestrator: SignalOrchestrator, order_mgr: OrderManager) -> dash.Dash:
    app = dash.Dash(
        __name__,
        external_stylesheets=[dbc.themes.FLATLY],
        title="NIFTY Options Buyer",
    )
    app.layout = make_layout()

    @app.callback(
        [
            Output("kpi-spot", "children"),
            Output("kpi-spot-time", "children"),
            Output("kpi-decision-val", "children"),
            Output("kpi-conf", "children"),
            Output("kpi-pcr", "children"),
            Output("kpi-pcr-regime", "children"),
            Output("kpi-gex", "children"),
            Output("kpi-gex-regime", "children"),
            Output("chart-pcr", "figure"),
            Output("chart-iv", "figure"),
            Output("chart-gex", "figure"),
            Output("chart-vwap", "figure"),
            Output("sub-signals", "children"),
            Output("decision-card", "children"),
        ],
        [Input("interval", "n_intervals")],
    )
    def update_dashboard(n):
        try:
            history = orchestrator.history
            if not history:
                empty = _empty_fig()
                return (
                    "—", "—", "—", "—", "—", "—", "—", "—",
                    empty, empty, empty, empty, "No data yet", "Waiting for ticks…"
                )
            latest = history[-1]

            # KPI cards
            spot_kpi = f"₹{latest.spot:,.2f}"
            spot_time = pd.Timestamp(latest.timestamp).strftime("%H:%M:%S")
            decision = latest.decision
            decision_color = {"GO": "success", "NO-GO": "danger", "HOLD": "secondary"}.get(decision, "secondary")
            conf = f"conf {latest.confidence:.2f}"
            pcr_kpi = f"{latest.pcr:.2f}"
            gex_kpi = f"₹{latest.net_gex/1e7:.2f} Cr"
            gex_regime = latest.gex_regime

            # Build figures
            df = pd.DataFrame([s.to_dict() for s in history])
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.sort_values("timestamp")

            pcr_fig = _pcr_figure(df)
            iv_fig = _iv_figure(df)
            gex_fig = _gex_figure(df)
            vwap_fig = _vwap_figure(df, latest)

            # Sub-signals
            sub_signals = dbc.ListGroup(
                [
                    dbc.ListGroupItem(
                        [
                            html.Strong("Vol-OI Nexus: "),
                            dbc.Badge(latest.sub_vol_oi, color=_signal_color(latest.sub_vol_oi)),
                        ]
                    ),
                    dbc.ListGroupItem(
                        [
                            html.Strong("Gamma Hedge: "),
                            dbc.Badge(latest.sub_gamma, color=_signal_color(latest.sub_gamma)),
                        ]
                    ),
                    dbc.ListGroupItem(
                        [
                            html.Strong("Lead-Lag: "),
                            dbc.Badge(latest.sub_leadlag, color=_signal_color(latest.sub_leadlag)),
                        ]
                    ),
                    dbc.ListGroupItem(
                        [
                            html.Strong("No-Trade Trap: "),
                            dbc.Badge(latest.sub_no_trade, color=_signal_color(latest.sub_no_trade)),
                        ]
                    ),
                    dbc.ListGroupItem(
                        [
                            html.Strong("Momentum Index: "),
                            f"{latest.momentum_index:+.3f}",
                        ]
                    ),
                ]
            )

            # Decision card
            decision_card = html.Div(
                [
                    html.H4(
                        [
                            "Decision: ",
                            dbc.Badge(latest.decision, color=decision_color, className="ms-2"),
                        ]
                    ),
                    html.P(f"Suggested: {latest.suggested_side} @ {latest.suggested_strike}", className="mb-1"),
                    html.Hr(),
                    html.Ul([html.Li(r) for r in latest.decision_reasons]),
                    html.Hr(),
                    html.H6("Positions"),
                    html.Pre(json.dumps(order_mgr.summary(), indent=2)),
                ]
            )

            return (
                spot_kpi, spot_time, decision, conf, pcr_kpi, latest.pcr_regime, gex_kpi, gex_regime,
                pcr_fig, iv_fig, gex_fig, vwap_fig, sub_signals, decision_card,
            )
        except Exception as e:
            log.exception("Dashboard update error: {}", e)
            err_msg = html.Div([
                html.P(f"Error: {str(e)}", className="text-danger"),
                html.Pre(traceback.format_exc(), style={"fontSize": "10px"})
            ])
            empty = _empty_fig()
            return (
                "ERR", "ERR", "ERR", "ERR", "ERR", "ERR", "ERR", "ERR",
                empty, empty, empty, empty, err_msg, err_msg
            )

    return app


def _signal_color(sig: str) -> str:
    return {
        "BUY_CALLS": "success",
        "BUY_PUTS": "success",
        "NO_TRADE": "warning",
        "NO-GO": "danger",
        "HOLD": "secondary",
    }.get(sig, "secondary")


def _empty_fig():
    fig = go.Figure()
    fig.update_layout(template="plotly_white", height=300, margin=dict(l=0, r=0, t=10, b=0))
    return fig


def _pcr_figure(df: pd.DataFrame) -> go.Figure:
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
    if "spot" in df.columns:
        fig.add_trace(go.Scatter(x=df["timestamp"], y=df["spot"], name="NIFTY Spot", line=dict(color="black")), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["pcr"], name="PCR", line=dict(color="blue")), row=2, col=1)
    fig.add_hline(y=0.7, line_dash="dot", line_color="green", row=2, col=1)
    fig.add_hline(y=1.1, line_dash="dot", line_color="red", row=2, col=1)
    fig.update_layout(template="plotly_white", height=350, title="Spot & PCR", margin=dict(l=0, r=0, t=30, b=0))
    return fig


def _iv_figure(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if "iv_total" in df.columns:
        fig.add_trace(go.Scatter(x=df["timestamp"], y=df["iv_total"], name="ATM IV (avg)", line=dict(color="purple")))
    if "iv_pct_change" in df.columns:
        fig.add_trace(go.Scatter(x=df["timestamp"], y=df["iv_pct_change"], name="IV % change (15m)", yaxis="y2", line=dict(color="orange", dash="dot")))
    fig.add_hline(y=5, line_dash="dot", line_color="red", annotation_text="crush")
    fig.add_hline(y=-5, line_dash="dot", line_color="red", annotation_text="crush")
    fig.update_layout(
        template="plotly_white",
        height=350,
        title="IV Skew & Trend",
        yaxis=dict(title="IV"),
        yaxis2=dict(title="% change", overlaying="y", side="right"),
        margin=dict(l=0, r=0, t=30, b=0),
    )
    return fig


def _gex_figure(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if "net_gex" in df.columns:
        fig.add_trace(go.Scatter(x=df["timestamp"], y=df["net_gex"] / 1e7, name="Net GEX (₹ Cr)", line=dict(color="teal"), fill="tozeroy"))
    if "max_pain" in df.columns and df["max_pain"].notna().any():
        fig.add_trace(go.Scatter(x=df["timestamp"], y=df["max_pain"], name="Max Pain", line=dict(color="red", dash="dash"), yaxis="y2"))
    if "spot" in df.columns:
        fig.add_trace(go.Scatter(x=df["timestamp"], y=df["spot"], name="Spot", line=dict(color="black", width=1), yaxis="y2"))
    fig.update_layout(
        template="plotly_white",
        height=350,
        title="GEX & Max Pain",
        yaxis=dict(title="GEX (₹ Cr)"),
        yaxis2=dict(title="Price", overlaying="y", side="right"),
        margin=dict(l=0, r=0, t=30, b=0),
    )
    return fig


def _vwap_figure(df: pd.DataFrame, latest: SignalState) -> go.Figure:
    fig = go.Figure()
    if "spot" in df.columns:
        fig.add_trace(go.Scatter(x=df["timestamp"], y=df["spot"], name="Spot", line=dict(color="black")))
    if "spot_vwap" in df.columns:
        fig.add_trace(go.Scatter(x=df["timestamp"], y=df["spot_vwap"], name="Spot VWAP", line=dict(color="blue", dash="dot")))
    if "call_vwap" in df.columns:
        fig.add_trace(go.Scatter(x=df["timestamp"], y=df["call_vwap"], name="Call VWAP", line=dict(color="green")))
    fig.update_layout(
        template="plotly_white",
        height=350,
        title=f"VWAP (call_spot_gap={latest.vwap_call_gap*100:.2f}%)",
        margin=dict(l=0, r=0, t=30, b=0),
    )
    return fig


def run_dashboard(host: str = "127.0.0.1", port: int = 8050, debug: bool = False) -> None:
    """Standalone run: spin up mock data, signal orchestrator, dashboard."""
    settings = get_settings()
    setup_logger(level=settings["app"]["log_level"])

    mode = settings["app"].get("mode", "mock")

    if mode == "live":
        from data.streaming import UpstoxLiveSource
        poll_sec = float(settings["data"]["refresh"].get("signal_refresh_seconds", 5))
        data_src = UpstoxLiveSource(poll_interval_sec=poll_sec)
        log.info("Using live data source (UpstoxLiveSource, polling every {}s)", poll_sec)

        # Active client and live order manager
        from data.upstox_client import make_client_from_env
        client = make_client_from_env()
        order_mgr = OrderManager(
            lot_size=settings["risk"]["lot_size"],
            max_position_notional=settings["risk"]["max_position_notional"],
            max_daily_loss=settings["risk"]["max_daily_loss"],
            live=True,
            upstox_client=client,
        )
    else:
        from data.streaming import MockWebSocket
        data_src = MockWebSocket(rate_hz=1.0)
        log.info("Using mock data source (MockWebSocket)")
        order_mgr = OrderManager(
            lot_size=settings["risk"]["lot_size"],
            max_position_notional=settings["risk"]["max_position_notional"],
            max_daily_loss=settings["risk"]["max_daily_loss"],
            live=False,
        )

    def _on_signal(st: SignalState) -> None:
        if st.decision == "GO" and st.confidence >= 0.6:
            order_mgr.submit_order(st)

    orch = SignalOrchestrator(data_source=data_src, on_signal=_on_signal, order_manager=order_mgr)
    orch.start()

    app = build_app(orch, order_mgr)
    log.info("Starting dashboard on http://{}:{}", host, port)
    # Force debug=True for debugging session as requested
    app.run(host=host, port=port, debug=True)


if __name__ == "__main__":
    run_dashboard()
