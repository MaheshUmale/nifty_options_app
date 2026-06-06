"""
Historical Option Chain Collector.
Optimized for NSE (India) data collection via justticks.in API.
"""
import sqlite3
import requests
import datetime
import time
import os
import argparse
from loguru import logger
from tqdm import tqdm

# --- CONFIGURATION ---
NSE_HOLIDAYS_2026 = {
    datetime.date(2026, 1, 26), datetime.date(2026, 3, 6),
    datetime.date(2026, 3, 19),
    datetime.date(2026, 4, 2), datetime.date(2026, 4, 14),
    datetime.date(2026, 5, 1),
    datetime.date(2026, 5, 21),
}

# Approximate NIFTY expiries for 2026
EXPIRY_STRINGS = [
    "Jan 06, 2026", "Jan 13, 2026", "Jan 20, 2026", "Jan 27, 2026",
    "Feb 03, 2026", "Feb 10, 2026", "Feb 17, 2026", "Feb 24, 2026",
    "Mar 03, 2026", "Mar 10, 2026", "Mar 17, 2026", "Mar 24, 2026", "Mar 31, 2026",
    "Apr 07, 2026", "Apr 14, 2026", "Apr 21, 2026", "Apr 28, 2026",
    "May 05, 2026", "May 12, 2026", "May 19, 2026", "May 26, 2026",
    "Jun 02, 2026", "Jun 09, 2026", "Jun 16, 2026", "Jun 23, 2026", "Jun 30, 2026"
]
EXPIRIES = sorted([datetime.datetime.strptime(d, "%b %d, %Y").date() for d in EXPIRY_STRINGS])

def setup_database(db_name):
    """Initializes the SQLite schema."""
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute("PRAGMA auto_vacuum = FULL;")
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA synchronous = NORMAL;")

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS option_data (
        historical_date TEXT,
        expiry_date TEXT,
        timestamp INTEGER,
        underlying_price REAL,
        strike REAL,
        ce_change REAL, ce_changeinOpenInterest REAL, ce_delta REAL, ce_gamma REAL,
        ce_impliedVolatility REAL, ce_lastPrice REAL, ce_openInterest REAL, ce_pChange REAL,
        ce_pchangeinOpenInterest REAL, ce_theta REAL, ce_totalTradedVolume REAL, ce_vega REAL,
        pe_change REAL, pe_changeinOpenInterest REAL, pe_delta REAL, pe_gamma REAL,
        pe_impliedVolatility REAL, pe_lastPrice REAL, pe_openInterest REAL, pe_pChange REAL,
        pe_pchangeinOpenInterest REAL, pe_theta REAL, pe_totalTradedVolume REAL, pe_vega REAL,
        PRIMARY KEY (historical_date, expiry_date, timestamp, strike)
    )
    ''')
    conn.commit()
    return conn

def get_expiry_for_date(hist_date):
    """Finds the next upcoming expiry date."""
    for expiry in EXPIRIES:
        if expiry >= hist_date:
            adjusted_expiry = expiry
            while adjusted_expiry in NSE_HOLIDAYS_2026 or adjusted_expiry.weekday() in [5, 6]:
                adjusted_expiry -= datetime.timedelta(days=1)
            if hist_date <= adjusted_expiry:
                return adjusted_expiry
    return None

def format_api_date(dt):
    return f"{dt.day}-{dt.strftime('%b-%Y')}"

def fetch_option_chain(symbol, expiry_date_str, hist_date_str):
    url = "https://justticks.in/api/option-chain-hist-click"
    params = {
        "symbol": symbol, "expiryDate": expiry_date_str, "historicalDate": hist_date_str,
        "x": 20, "useFirstTimestamp": "false", "excludeGreeks": "false", "isLive": "FALSE"
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        if response.status_code == 200: return response.json()
        return None
    except Exception as e:
        logger.error(f"Request failed: {e}")
        return None

def parse_and_store(conn, data, hist_date_str, expiry_date_str):
    cursor = conn.cursor()
    timestamps = data.get("t", [])
    underlying_prices = data.get("u", [])
    strikes = data.get("strikes", [])
    fields = [
        "change", "changeinOpenInterest", "delta", "gamma",
        "impliedVolatility", "lastPrice", "openInterest", "pChange",
        "pchangeinOpenInterest", "theta", "totalTradedVolume", "vega"
    ]
    ce_data = data.get("ce", {})
    pe_data = data.get("pe", {})
    records = []

    for t_idx, timestamp in enumerate(timestamps):
        underlying = underlying_prices[t_idx] if t_idx < len(underlying_prices) else None
        for s_idx, strike in enumerate(strikes):
            row = [hist_date_str, expiry_date_str, timestamp, underlying, strike]
            for field in fields:
                try:
                    val = ce_data[field][s_idx][t_idx]
                    row.append(float(val) if val is not None else None)
                except: row.append(None)
            for field in fields:
                try:
                    val = pe_data[field][s_idx][t_idx]
                    row.append(float(val) if val is not None else None)
                except: row.append(None)
            records.append(tuple(row))

    if records:
        placeholders = ",".join(["?"] * len(records[0]))
        cursor.executemany(f"INSERT OR REPLACE INTO option_data VALUES ({placeholders})", records)
        conn.commit()
    return len(records)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument("--days", type=int, default=5)
    parser.add_argument("--db", default="data/nifty_historical.db")
    args = parser.parse_args()

    os.makedirs("data", exist_ok=True)
    conn = setup_database(args.db)

    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=args.days)

    current_date = start_date
    pbar = tqdm(total=args.days)

    while current_date <= end_date:
        pbar.update(1)
        if current_date.weekday() in [5, 6] or current_date in NSE_HOLIDAYS_2026:
            current_date += datetime.timedelta(days=1)
            continue

        expiry = get_expiry_for_date(current_date)
        if not expiry:
            current_date += datetime.timedelta(days=1)
            continue

        hist_str = format_api_date(current_date)
        exp_str = format_api_date(expiry)

        logger.info(f"Fetching {hist_str}...")
        data = fetch_option_chain(args.symbol, exp_str, hist_str)
        if data:
            count = parse_and_store(conn, data, hist_str, exp_str)
            logger.success(f"Stored {count} records for {hist_str}")

        time.sleep(1.0)
        current_date += datetime.timedelta(days=1)

    conn.close()
    logger.info("Collection complete.")

if __name__ == "__main__":
    main()
