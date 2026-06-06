import yfinance as yf
import pandas as pd

# 1. Download Nifty 50 Index 1-minute data
# Yahoo ticker for Nifty Index is ^NSEI
print("Downloading Nifty Index 1m data from Yahoo...")
nifty_index = yf.download(
    tickers="^NSEI", 
    period="5d",       # Max safe history for 1m interval 
    interval="1m"
)

# Save Index to CSV
if not nifty_index.empty:
    nifty_index.to_csv("yahoo_nifty_index_1min.csv")
    print("Nifty Index saved to 'yahoo_nifty_index_1min.csv'")

# 2. Download Nifty Future 1-minute data
# Yahoo ticker for continuous Nifty Future is NIFTY=F
print("\nDownloading Nifty Future 1m data from Yahoo...")
nifty_future = yf.download(
    tickers="NIFTY=F", 
    period="5d", 
    interval="1m"
)

# Save Futures to CSV
if not nifty_future.empty:
    nifty_future.to_csv("yahoo_nifty_future_1min.csv")
    print("Nifty Future saved to 'yahoo_nifty_future_1min.csv'")
