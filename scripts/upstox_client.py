
access_token = 'eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI3NkFGMzUiLCJqdGkiOiI2YTIyNWE0OTUyY2JhMjdlNTNiNWNhZDYiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6ZmFsc2UsImlhdCI6MTc4MDYzNjIzMywiaXNzIjoidWRhcGktZ2F0ZXdheS1zZXJ2aWNlIiwiZXhwIjoxNzgwNjk2ODAwfQ.Ta_pBqybIL6RB0SrU_GPJPCwkJwTN3d7KbLBniTVems'

 
import requests

url = 'https://api.upstox.com/v3/historical-candle/intraday/NSE_EQ%7CINE848E01016/minutes/3'
headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'Authorization': f'Bearer {access_token}'
}

response = requests.get(url, headers=headers)

# Check the response status
if response.status_code == 200:
    # Do something with the response data (e.g., print it)
    print(response.json())
else:
    # Print an error message if the request was not successful
    print(f"Error: {response.status_code} - {response.text}")


import requests
#      https://api.upstox.com/v3/market-quote/ltp?instrument_key=NSE_EQ%7CINE848E01016
url = 'https://api.upstox.com/v3/market-quote/ltp?instrument_key=NSE_EQ%7CINE848E01016'
headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'Authorization': f'Bearer {access_token}'
}

response = requests.get(url, headers=headers)

print(response.text)


import requests

url = 'https://api.upstox.com/v2/option/chain'
params = {
    'instrument_key': 'NSE_INDEX|Nifty 50',
    'expiry_date': '2024-03-28'
}
headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'Authorization': f'Bearer {access_token}'
}

response = requests.get(url, params=params, headers=headers)

print(response.json())
