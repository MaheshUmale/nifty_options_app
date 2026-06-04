"""
Upstox V2 REST API Client.
Handles OAuth2, market quotes, and option chain retrieval.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests
from dotenv import load_dotenv, set_key
from utils.logger import get_logger

log = get_logger()

@dataclass
class UpstoxCreds:
    api_key: str
    api_secret: str
    redirect_uri: str
    access_token: str | None = None

class UpstoxClient:
    """REST client for Upstox V2 API."""

    BASE_URL = "https://api.upstox.com/v2"

    def __init__(self, creds: UpstoxCreds):
        self.creds = creds

    def _get_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.creds.access_token:
            headers["Authorization"] = f"Bearer {self.creds.access_token}"
        return headers

    def build_login_url(self) -> str:
        """Returns the OAuth2 login URL."""
        import urllib.parse
        params = {
            "client_id": self.creds.api_key,
            "redirect_uri": self.creds.redirect_uri,
            "response_type": "code",
        }
        return f"https://api.upstox.com/v2/login/authorization/dialog?{urllib.parse.urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> bool:
        """Exchanges auth code for access token and saves to .env."""
        url = f"{self.BASE_URL}/login/authorization/token"
        data = {
            "code": code,
            "client_id": self.creds.api_key,
            "client_secret": self.creds.api_secret,
            "redirect_uri": self.creds.redirect_uri,
            "grant_type": "authorization_code",
        }
        resp = requests.post(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
        if resp.status_code == 200:
            token = resp.json().get("access_token")
            if token:
                self.creds.access_token = token
                # Update .env file
                env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
                if os.path.exists(env_path):
                    set_key(env_path, "UPSTOX_ACCESS_TOKEN", token)
                return True
        return False

    def get_market_quote(self, instrument_keys: list[str]) -> dict[str, Any]:
        """GET /market-quote/quotes"""
        url = f"{self.BASE_URL}/market-quote/quotes"
        params = {"instrument_key": ",".join(instrument_keys)}
        resp = requests.get(url, params=params, headers=self._get_headers())
        return resp.json()

    def get_option_chain(self, instrument_key: str, expiry_date: str) -> dict[str, Any]:
        """GET /option/chain"""
        url = f"{self.BASE_URL}/option/chain"
        params = {"instrument_key": instrument_key, "expiry_date": expiry_date}
        resp = requests.get(url, params=params, headers=self._get_headers())
        return resp.json()

def make_client_from_env() -> UpstoxClient:
    """Factory to create client using .env variables."""
    # Ensure .env is loaded
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
    load_dotenv(env_path)

    creds = UpstoxCreds(
        api_key=os.getenv("UPSTOX_API_KEY", ""),
        api_secret=os.getenv("UPSTOX_API_SECRET", ""),
        redirect_uri=os.getenv("UPSTOX_REDIRECT_URI", "http://localhost:5000/callback"),
        access_token=os.getenv("UPSTOX_ACCESS_TOKEN"),
    )
    return UpstoxClient(creds)
