import sqlite3
import requests
import time

DB_NAME = "nifty_option_chain.db"
SYMBOL = "NIFTY"

# Explicitly corrected pairings based on actual 2026 NSE Holiday shifts
FAILED_PAIRS = [
    # ("3-Mar-2026", "2-Mar-2026"),    # Holi Shift: Expiry is Mar 02
    # ("30-Mar-2026", "30-Mar-2026"),  # Mahavir Jayanti Shift: Expiry is Mar 30
    # ("10-Apr-2026", "13-Apr-2026"),  # Ambedkar Jayanti Shift: Expiry is Apr 13
    # ("27-Feb-2026", "2-Mar-2026"),
    # ("25-Feb-2026", "2-Mar-2026"),
    # ("27-Mar-2026", "30-Mar-2026"),
    # ("2-Mar-2026", "2-Mar-2026"),
    # ("26-Feb-2026", "2-Mar-2026"),
    # ("8-Apr-2026", "13-Apr-2026"),
    # ("9-Apr-2026", "13-Apr-2026"),
    # ("26-Mar-2026", "30-Mar-2026"),
    # ("13-Apr-2026", "13-Apr-2026"),
    # ("31-Mar-2026", "30-Mar-2026"),  # Holiday itself, but checking just in case
    # ("25-Mar-2026", "30-Mar-2026")

    
	("06-Feb-2026", "10-Feb-2026"),    
	("03-Mar-2026", "10-Mar-2026"),    # Holi Shift: Expiry is Mar 02
    ("30-Mar-2026", "30-Mar-2026"),  # Mahavir Jayanti Shift: Expiry is Mar 30
    ("10-Apr-2026", "13-Apr-2026"),  # Ambedkar Jayanti Shift: Expiry is Apr 13
    ("27-Feb-2026", "02-Mar-2026"),
    ("25-Feb-2026", "02-Mar-2026"),
    ("27-Mar-2026", "30-Mar-2026"),
    ("02-Mar-2026", "02-Mar-2026"),
    ("26-Feb-2026", "02-Mar-2026"),
    ("08-Apr-2026", "13-Apr-2026"),
    ("09-Apr-2026", "13-Apr-2026"),
    ("26-Mar-2026", "30-Mar-2026"),
    ("13-Apr-2026", "13-Apr-2026"),
    ("31-Mar-2026", "30-Mar-2026"),  # Holiday itself, but checking just in case
    ("25-Mar-2026", "30-Mar-2026")
	
]

def fetch_option_chain(symbol, expiry_date_str, hist_date_str):
    url = "https://justticks.in/api/option-chain-hist-click"
    params = {
        "symbol": symbol, "expiryDate": expiry_date_str, "historicalDate": hist_date_str,
        "x": 20, "useFirstTimestamp": "false", "excludeGreeks": "false", "isLive": "FALSE"
    }
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=20)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"  [Status {response.status_code}] Could not fetch {hist_date_str}")
            return None
    except Exception as e:
        print(f"  [Network Error] Failed for {hist_date_str}: {e}")
        return None

def parse_and_store(conn, data, hist_date_str, expiry_date_str):
    cursor = conn.cursor()
    timestamps = data.get("t", [])
    underlying_prices = data.get("u", [])
    strikes = data.get("strikes", [])
    
    fields_to_extract = [
        "change", "changeinOpenInterest", "delta", "gamma", "impliedVolatility",
        "lastPrice", "openInterest", "pChange", "pchangeinOpenInterest",
        "theta", "totalTradedVolume", "vega"
    ]
    
    ce_data = data.get("ce", {})
    pe_data = data.get("pe", {})
    records = []
    
    for t_idx, timestamp in enumerate(timestamps):
        underlying = underlying_prices[t_idx] if t_idx < len(underlying_prices) else None
        for s_idx, strike in enumerate(strikes):
            row_data = [hist_date_str, expiry_date_str, timestamp, underlying, strike]
            
            for field in fields_to_extract:
                try:
                    val = ce_data[field][s_idx][t_idx]
                    row_data.append(float(val) if val is not None else None)
                except (KeyError, IndexError): row_data.append(None)
                    
            for field in fields_to_extract:
                try:
                    val = pe_data[field][s_idx][t_idx]
                    row_data.append(float(val) if val is not None else None)
                except (KeyError, IndexError): row_data.append(None)
            
            records.append(tuple(row_data))

    if records:
        placeholders = ",".join(["?"] * len(records[0]))
        cursor.executemany(f"INSERT OR REPLACE INTO option_data VALUES ({placeholders})", records)
        conn.commit()
        print(f"  [Success] Patched {len(records)} rows into DB.")

def patch_missing_data():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    print("=== STARTING TARGETED DB PATCH ROUND ===")
    
    for hist_date, expiry_date in FAILED_PAIRS:
        # Check database to see if we already managed to write this historical date
        cursor.execute("SELECT COUNT(*) FROM option_data WHERE historical_date = ?", (hist_date,))
        exists = cursor.fetchone()[0]
        
        if exists > 0:
            print(f"[{hist_date}] Already exists in DB. Skipping duplicate request.")
            continue
            
        print(f"[{hist_date}] Missing. Fetching target expiry: {expiry_date}...")
        json_data = fetch_option_chain(SYMBOL, expiry_date, hist_date)
        
        if json_data:
            parse_and_store(conn, json_data, hist_date, expiry_date)
            
        time.sleep(2.0) # Rate limit protection block
        
    print("\nRunning clean optimization check...")
    cursor.execute("VACUUM;")
    conn.commit()
    conn.close()
    print("Database patched and fully compact.")

if __name__ == "__main__":
    patch_missing_data()