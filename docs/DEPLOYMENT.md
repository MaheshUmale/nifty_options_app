# Deployment Guide

## Local Development

```bash
git clone <repo>
cd nifty_options_app
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m main smoke
```

## Docker

`Dockerfile`:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1
EXPOSE 8050
CMD ["python", "-m", "main", "dashboard", "--host", "0.0.0.0", "--port", "8050"]
```

Build & run:
```bash
docker build -t nifty-options-buyer .
docker run -p 8050:8050 --env-file .env nifty-options-buyer
```

## Cloud Options

### AWS (recommended for low latency to Upstox)
- **Mumbai region (ap-south-1)** for proximity to NSE
- **EC2 c5.xlarge** or **c6i.xlarge** (4 vCPU, low-latency networking)
- **ENA enabled**, **Placement groups** for cluster placement
- **EBS gp3** for fast Parquet writes
- **CloudWatch** for log aggregation
- **SNS** for SMS kill-switch alerts

### GCP
- **Mumbai region (asia-south1)**
- **n2-standard-4** VM
- **Cloud Logging** + **Pub/Sub** for alerts

### Latency Notes
- Upstox servers are hosted in **AWS Mumbai (ap-south-1)**; co-locate there.
- Target: **< 50 ms** round-trip from WS feed to order acknowledgement.

## Monitoring Stack

| Component | Tool | Purpose |
|-----------|------|---------|
| Logs | CloudWatch / Stackdriver | Searchable historical record |
| Metrics | Prometheus + Grafana | Dashboards (latency, PnL, signal counts) |
| Alerts | Alertmanager / PagerDuty | SMS/email on kill-switch or stale data |
| Uptime | Healthchecks.io | External "I'm alive" ping |
| Audit | S3 / GCS | Immutable signal + order log |

Prometheus metrics to expose (recommended):
```
nifty_signal_decision_total{decision="GO|NO-GO|HOLD"}
nifty_signal_latency_seconds{stage="ingest|features|composite|order"}
nifty_order_pnl_total
nifty_position_count{side}
nifty_kill_switch_active
```

## Kill-Switch Procedures

The `OrderManager` has 3 trip-wires:

1. **Daily loss limit** (`risk.max_daily_loss` in `settings.yaml`)
   - Default: ₹20,000
   - On breach: `kill_switch = True`, all positions flattened
2. **Drawdown limit** (`risk.max_drawdown_pct`)
   - Default: 2% of capital
3. **Manual kill** (operator triggered)
   - Send `POST /admin/kill` to a small Flask companion (TODO)
   - Or: `pkill -SIGTERM nifty-options-buyer`; SIGTERM triggers `OrderManager.kill()` via atexit hook

### Simulated Drills
```bash
# Force trigger via CLI
python -c "from execution.order_manager import OrderManager; o = OrderManager(max_daily_loss=1); o.daily_pnl = -100; o.check_risk()"
# Should print "DAILY LOSS LIMIT BREACHED"
```

## Backtest → Paper → Live Rollout

1. **Backtest** on synthetic data (fast iteration)
2. **Backtest** on NSE historical CSVs (validate signal on real data)
3. **Paper trading** with live Upstox data (no orders) for 2 weeks
4. **Live small size** (1 lot, max 5% of capital) for 1 month
5. **Scale up** only after Sharpe > 1.0 in paper AND live

## Operational Runbook

### Pre-Market (08:30 IST)
- [ ] Run smoke test: `python -m main smoke`
- [ ] Verify Upstox token valid: `python -c "from data.upstox_client import make_client_from_env; c = make_client_from_env(); print(c.get_market_quote(['NSE_INDEX|Nifty 50']))"`
- [ ] Check disk space for Parquet logs
- [ ] Start dashboard: `python -m main dashboard`

### Market Hours (09:15–15:30 IST)
- [ ] Watch dashboard for stale-data indicator
- [ ] If `kill_switch` triggers, investigate via logs
- [ ] On `NO-GO` cluster, confirm via P&L log

### Post-Market (15:45 IST)
- [ ] System auto-flattens at 15:25 (TODO: add end-of-day flatten)
- [ ] Backup Parquet logs to S3
- [ ] Run post-mortem on any losing trades

## Disaster Recovery

| Scenario | Recovery |
|----------|----------|
| Dashboard crash | Restart (`python -m main dashboard`); signal orchestrator persists in memory only — restart loses in-progress state but not capital |
| WS disconnect | Auto-reconnect within 30s |
| REST 401 | Refresh access_token (TODO: implement refresh_token flow) |
| Order rejected | Log + alert; never retry without manual review |
| Network partition | `OrderManager` will not receive fills; `mark_to_market` will detect mismatch and pause |
| Disk full | Rotate logs (already automatic via loguru); old Parquet files compressed |

## Capacity Planning

For 1 NIFTY option chain × 21 strikes × 1-min updates:
- Storage: ~50 MB/day (Parquet compressed)
- CPU: < 5% of 1 core
- Memory: ~500 MB (state + history)
- Network: ~100 KB/min outbound (after gzip)

Can comfortably run on the smallest cloud VM (1 vCPU, 1 GB RAM) for a single
instrument. To add BANKNIFTY + FINNIFTY, scale to 2 vCPUs and 2 GB.

## Security Checklist

- [x] API keys in `.env`, never committed
- [x] `.gitignore` includes `.env`, `data/`, `logs/`
- [x] No real money mode in default config (`APP_MODE=mock`)
- [x] Live mode requires explicit `APP_MODE=live` and `live=True` in OrderManager
- [ ] Token encryption at rest (TODO: use `cryptography` Fernet)
- [ ] Audit log signing (TODO: HMAC each log line)
- [ ] 2FA on Upstox account itself
