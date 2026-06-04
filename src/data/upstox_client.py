"""
Upstox V3 REST API Client using official SDK.
Handles OAuth2, market quotes, and option chain retrieval.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import upstox_client
from upstox_client.rest import ApiException
from upstox_client.api import LoginApi, MarketQuoteV3Api, OptionsApi
from upstox_client.api_client import ApiClient
from upstox_client.configuration import Configuration

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
    """REST client for Upstox V3 API using official SDK."""

    def __init__(self, creds: UpstoxCreds):
        self.creds = creds
        self.config = Configuration()
        self.update_config()

    def update_config(self):
        if self.creds.access_token:
            self.config.access_token = self.creds.access_token
        self.api_client = ApiClient(self.config)

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
        api_instance = LoginApi(self.api_client)
        try:
            api_response = api_instance.token(
                api_version="2.0",
                code=code,
                client_id=self.creds.api_key,
                client_secret=self.creds.api_secret,
                redirect_uri=self.creds.redirect_uri,
                grant_type="authorization_code"
            )
            token = api_response.access_token
            if token:
                self.creds.access_token = token
                self.update_config()
                env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
                if os.path.exists(env_path):
                    set_key(env_path, "UPSTOX_ACCESS_TOKEN", token)
                log.info("Access token updated successfully.")
                return True
        except ApiException as e:
            log.error(f"Exception when calling LoginApi->token: {e}")
        return False

    def get_market_quote_ltp(self, instrument_keys: list[str]) -> dict[str, Any]:
        """GET /market-quote/ltp (V3)"""
        api_instance = MarketQuoteV3Api(self.api_client)
        try:
            api_response = api_instance.get_ltp(
                instrument_key=",".join(instrument_keys),
                api_version="3.0"
            )
            return api_response.to_dict()
        except ApiException as e:
            log.error(f"Exception when calling MarketQuoteV3Api->get_ltp: {e}")
            return {"status": "error", "errors": [str(e)]}

    def get_option_chain(self, instrument_key: str, expiry_date: str) -> dict[str, Any]:
        """GET /option/chain using OptionsApi"""
        api_instance = OptionsApi(self.api_client)
        try:
            api_response = api_instance.get_option_chain(
                instrument_key=instrument_key,
                expiry_date=expiry_date,
                api_version="2.0"
            )
            return api_response.to_dict()
        except ApiException as e:
            log.error(f"Exception when calling OptionsApi->get_option_chain: {e}")
            return {"status": "error", "errors": [str(e)]}

def make_client_from_env() -> UpstoxClient:
    """Factory to create client using .env variables."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
    load_dotenv(env_path)
    creds = UpstoxCreds(
        api_key=os.getenv("UPSTOX_API_KEY", ""),
        api_secret=os.getenv("UPSTOX_API_SECRET", ""),
        redirect_uri=os.getenv("UPSTOX_REDIRECT_URI", "http://localhost:5000/callback"),
        access_token=os.getenv("UPSTOX_ACCESS_TOKEN"),
    )
    return UpstoxClient(creds)
