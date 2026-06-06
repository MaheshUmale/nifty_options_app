# Deployment

## Environment Setup

1. **Python Version**: Ensure you are using Python 3.11 or 3.12.
2. **Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Environment Variables**: Create a `.env` file from `.env.example`.
   ```env
   UPSTOX_API_KEY=your_key
   UPSTOX_API_SECRET=your_secret
   UPSTOX_ACCESS_TOKEN=your_token
   APP_MODE=live
   ```

## Production Deployment (Linux/Server)

### 1. Process Management (Systemd)

Create `/etc/systemd/system/scalper.service`:

```ini
[Unit]
Description=NIFTY Zero-Lag Scalper
After=network.target

[Service]
User=your-user
WorkingDirectory=/path/to/nifty_options_app
EnvironmentFile=/path/to/nifty_options_app/.env
ExecStart=/usr/bin/python3 src/main.py dashboard --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

### 2. Reverse Proxy (Nginx)

```nginx
server {
    listen 80;
    server_name scalper.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

## Docker Deployment

Build the image:
```bash
docker build -t nifty-scalper .
```

Run the container:
```bash
docker run -p 8000:8000 --env-file .env nifty-scalper
```

## Monitoring

- **Logs**: Check `logs/` directory or `journalctl -u scalper`.
- **Database**: Use DuckDB CLI or DBeaver to inspect `data/market_data_v3.duckdb`.
- **Health Check**: `GET /` should return the dashboard.
