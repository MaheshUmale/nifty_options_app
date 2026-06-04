#!/usr/bin/env python3
"""
Test script to verify Upstox API authentication using the provided access token.
"""
import sys
import os
root_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, root_dir)
sys.path.insert(0, os.path.join(root_dir, "src"))

from data.upstox_client import make_client_from_env
from utils.logger import get_logger

log = get_logger()

def test_upstox_auth():
    """Test Upstox authentication and basic API calls."""
    print("Testing Upstox API authentication...")

    # Create client from .env file
    client = make_client_from_env()

    # Check if we have an access token
    if not client.creds.access_token:
        print("ERROR: No access token found in .env file")
        print("Please ensure UPSTOX_ACCESS_TOKEN is set in .env")
        return False

    print(f"Access token found: {client.creds.access_token[:30]}...")

    # Test token validity by making a simple API call
    try:
        # Get market quote for NIFTY index
        instrument_key = "NSE_INDEX|Nifty 50"
        print(f"Fetching market quote for {instrument_key}...")

        quote_data = client.get_market_quote([instrument_key])

        if quote_data.get("status") == "success":
            data = quote_data["data"]
            if instrument_key in data:
                quote = data[instrument_key]
                last_price = quote.get("last_price", "N/A")
                print(f"Success! NIFTY 50 last price: {last_price}")
                return True
            else:
                print(f"ERROR: No data for instrument {instrument_key}")
                print(f"Response: {quote_data}")
                return False
        else:
            print(f"ERROR: API request failed")
            print(f"Response: {quote_data}")
            return False

    except Exception as e:
        print(f"ERROR: Exception during API call: {e}")
        return False

if __name__ == "__main__":
    success = test_upstox_auth()
    sys.exit(0 if success else 1)