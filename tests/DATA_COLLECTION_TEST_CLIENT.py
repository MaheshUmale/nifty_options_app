import sqlite3
import requests
import datetime
import time
import os

# --- CONFIGURATION ---
SYMBOL = "NIFTY"
START_DATE = datetime.date(2026, 1, 1)
END_DATE = datetime.date(2026, 6, 4)
DB_NAME = "nifty_option_chain.db"

LOG_404 = "404_errors.txt"
LOG_OTHER = "other_errors.txt"

NSE_HOLIDAYS_2026 = {
    datetime.date(2026, 1, 26), datetime.date(2026, 3, 6), datetime.date(2026, 3, 19),
    datetime.date(2026, 4, 2), datetime.date(2026, 4, 14), datetime.date(2026, 5, 1),
    datetime.date(2026, 5, 21),
}

EXPIRY_STRINGS = [
    "Jan 06, 2026", "Jan 13, 2026", "Jan 20, 2026", "Jan 27, 2026",
    "Feb 03, 2026", "Feb 10, 2026", "Feb 17, 2026", "Feb 24, 2026",
    "Mar 03, 2026", "Mar 10, 2026", "Mar 17, 2026", "Mar 24, 2026", "Mar 31, 2026",
    "Apr 07, 2026", "Apr 14, 2026", "Apr 21, 2026", "Apr 28, 2026",
    "May 05, 2026", "May 12, 2026", "May 19, 2026", "May 26, 2026",
    "Jun 02, 2026", "Jun 09, 2026", "Jun 16, 2026", "Jun 23, 2026", "Jun 30, 2026"
]
EXPIRIES = sorted([datetime.datetime.strptime(d, "%b %d, %Y").date() for d in EXPIRY_STRINGS])

# --- DATABASE SETUP ---
def setup_database():
    # Delete old DB if it exists to start completely fresh
    if os.path.exists(DB_NAME):
        os.remove(DB_NAME)
        print(f"Deleted existing database '{DB_NAME}' for a clean start.")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Pragma optimization settings (must run before table creation for auto_vacuum)
    cursor.execute("PRAGMA auto_vacuum = FULL;")
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA synchronous = NORMAL;")
    
    # Structured relational schema
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
    """Finds the next upcoming expiry date. 
       If the target expiry lands on an NSE Holiday or a weekend, 
       it automatically shifts backward to the previous valid trading day.
    """
    for expiry in EXPIRIES:
        if expiry >= hist_date:
            # Check if this target expiry hits an NSE Holiday or Weekend
            adjusted_expiry = expiry
            while adjusted_expiry in NSE_HOLIDAYS_2026 or adjusted_expiry.weekday() in [5, 6]:
                # Shift backward 1 day iteratively until a valid trading day is found
                adjusted_expiry -= datetime.timedelta(days=1)
                
            # If the historic date has already passed the adjusted expiry day, 
            # we must jump to the next calendar week's expiry block.
            if hist_date <= adjusted_expiry:
                return adjusted_expiry
    return None

def format_api_date(dt):
    return f"{dt.day}-{dt.strftime('%b-%Y')}"

def log_error(file_path, hist_date_str, expiry_date_str):
    with open(file_path, "a") as f:
        f.write(f"{hist_date_str},{expiry_date_str}\n")

# --- CORE API & FAST PARSER ---
def fetch_option_chain(symbol, expiry_date_str, hist_date_str):
    url = "https://justticks.in/api/option-chain-hist-click"
    params = {
        "symbol": symbol, "expiryDate": expiry_date_str, "historicalDate": hist_date_str,
        "x": 20, "useFirstTimestamp": "false", "excludeGreeks": "false", "isLive": "FALSE"
    }
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        if response.status_code == 200: return response.json()
        elif response.status_code == 404:
            log_error(LOG_404, hist_date_str, expiry_date_str)
            return None
        else:
            log_error(LOG_OTHER, hist_date_str, expiry_date_str)
            return None
    except Exception:
        log_error(LOG_OTHER, hist_date_str, expiry_date_str)
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
    ] # Excluded underlyingValue as it is tracked globally per timestamp via data['u']
    
    ce_data = data.get("ce", {})
    pe_data = data.get("pe", {})
    
    records = []
    
    for t_idx, timestamp in enumerate(timestamps):
        underlying = underlying_prices[t_idx] if t_idx < len(underlying_prices) else None
        
        for s_idx, strike in enumerate(strikes):
            row_data = [hist_date_str, expiry_date_str, timestamp, underlying, strike]
            
            # Extract CE metrics safely
            for field in fields_to_extract:
                try:
                    val = ce_data[field][s_idx][t_idx]
                    row_data.append(float(val) if val is not None else None)
                except (KeyError, IndexError):
                    row_data.append(None)
                    
            # Extract PE metrics safely
            for field in fields_to_extract:
                try:
                    val = pe_data[field][s_idx][t_idx]
                    row_data.append(float(val) if val is not None else None)
                except (KeyError, IndexError):
                    row_data.append(None)
            
            records.append(tuple(row_data))

    if records:
        # Construct dynamic placeholders matching row column count
        placeholders = ",".join(["?"] * len(records[0]))
        cursor.executemany(f'''
            INSERT OR REPLACE INTO option_data VALUES ({placeholders})
        ''', records)
        conn.commit()
        print(f"  [Success] Inserted {len(records)} flattened rows.")

# --- JOB EXECUTORS ---
def run_initial_collection(conn):
    print("\n=== STARTING INITIAL DATA COLLECTION ===")
    current_date = START_DATE
    delta = datetime.timedelta(days=1)
    
    while current_date <= END_DATE:
        if current_date.weekday() in [5, 6] or current_date in NSE_HOLIDAYS_2026:
            current_date += delta
            continue
            
        expiry_date = get_expiry_for_date(current_date)
        if not expiry_date:
            current_date += delta
            continue
            
        hist_date_str = format_api_date(current_date)
        expiry_date_str = format_api_date(expiry_date)
        
        print(f"Processing: {hist_date_str} (Expiry: {expiry_date_str})")
        json_data = fetch_option_chain(SYMBOL, expiry_date_str, hist_date_str)
        if json_data:
            parse_and_store(conn, json_data, hist_date_str, expiry_date_str)
            
        time.sleep(1.2)
        current_date += delta

def run_fallback_processor(conn, log_file_path):
    if not os.path.exists(log_file_path) or os.path.getsize(log_file_path) == 0:
        return

    print(f"\n=== RUNNING FALLBACK RECOVERY FOR: {log_file_path} ===")
    with open(log_file_path, "r") as f:
        lines = list(set(f.readlines()))

    unresolved_entries = []
    for line in lines:
        if not line.strip(): continue
        hist_date_str, expiry_date_str = line.strip().split(',')
        
        print(f"Retrying Fallback: {hist_date_str} | Expiry: {expiry_date_str}...")
        json_data = fetch_option_chain(SYMBOL, expiry_date_str, hist_date_str)
        
        if json_data:
            parse_and_store(conn, json_data, hist_date_str, expiry_date_str)
        else:
            unresolved_entries.append(line)
        time.sleep(2.0)

    with open(log_file_path, "w") as f:
        f.writelines(unresolved_entries)

# --- MAIN ENGINE ---
if __name__ == "__main__":
    db_connection = setup_database()
    
    # 1. Primary Scrape Loop
    run_initial_collection(db_connection)
    
    # 2. Process Failures
    run_fallback_processor(db_connection, LOG_OTHER)
    run_fallback_processor(db_connection, LOG_404)
    
    # 3. Final Compact Clean Up
    print("\nOptimizing storage space via Final Vacuum...")
    cursor = db_connection.cursor()
    cursor.execute("VACUUM;")
    db_connection.commit()
    
    db_connection.close()
    print("Database finalized and compacted successfully.")