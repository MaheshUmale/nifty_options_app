from tvDatafeed import TvDatafeed, Interval
import pandas as pd

# Initialize TvDatafeed
tv = TvDatafeed()

# 1. Download Nifty Index 1-minute data
print("Downloading Nifty Index data...")
nifty_data = tv.get_hist(
    symbol='NIFTY', 
    exchange='NSE', 
    interval=Interval.in_1_minute, 
    n_bars=5000
)

# Save Index data to CSV
if nifty_data is not None and not nifty_data.empty:
    nifty_data.to_csv('nifty_index_1min.csv')
    print("Nifty Index data saved successfully to 'nifty_index_1min.csv'!")

# 2. Download Nifty Future 1-minute data
print("Downloading Nifty Future data...")
nifty_fut_data = tv.get_hist(
    symbol='NIFTY', 
    exchange='NSE', 
    interval=Interval.in_1_minute, 
    n_bars=5000, 
    fut_contract=1
)

# Save Futures data to CSV
if nifty_fut_data is not None and not nifty_fut_data.empty:
    nifty_fut_data.to_csv('nifty_future_1min.csv')
    print("Nifty Future data saved successfully to 'nifty_future_1min.csv'!")
