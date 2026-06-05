"""
Upstox REST client (NO official SDK).

Provides:
- OAuth2 code->token exchange (direct HTTP)
- Market quote LTP (direct REST HTTP)
- Options chain (direct REST HTTP)

Also keeps instrument master download + resolve helper intact.
"""
from __future__ import annotations

import gzip
import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from qrcode import make
import requests
from dotenv import load_dotenv, set_key

# Updated import to reflect correct package path after fixing sys.path handling.
from utils.logger import get_logger
from config import HARDCODED_UPSTOX_ACCESS_TOKEN, get_upstox_access_token

log = get_logger()


@dataclass
class UpstoxCreds:
    api_key: str | None = None
    api_secret: str | None = None
    redirect_uri: str | None = None
    access_token: str | None = None


class UpstoxClient:
    """REST client for Upstox V3 API using direct HTTP requests."""

    BASE_URL = "https://api.upstox.com"
    LOGIN_URL = "https://api.upstox.com/v2/login/authorization/dialog"

    TOKEN_URL = "https://api.upstox.com/v2/login/token"

    def __init__(self, access_token: str | None = None, *, creds: UpstoxCreds | None = None):
        self.creds = creds or UpstoxCreds()
        # Prefer the explicitly passed token, then the OS env token via helper.
        self.creds.access_token = access_token or get_upstox_access_token() or self.creds.access_token
    def _auth_headers(self) -> dict[str, str]:
        token = self.creds.access_token
        print(f"Using access token: {token}" if token else "No access token available.")
        if not token:
            raise RuntimeError("Missing UPSTOX_ACCESS_TOKEN")
        return {
            'Content-Type': 'application/json',
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }

    def build_login_url(self) -> str:
        """OAuth2 authorization URL (browser redirect)."""
        if not self.creds.api_key or not self.creds.redirect_uri:
            raise RuntimeError("Missing UPSTOX_API_KEY or UPSTOX_REDIRECT_URI")
        params = {
            "client_id": self.creds.api_key,
            "redirect_uri": self.creds.redirect_uri,
            "response_type": "code",
        }
        return f"{self.LOGIN_URL}?{urllib.parse.urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> bool:
        """Exchanges auth code for access token and saves to .env (UPSTOX_ACCESS_TOKEN)."""
        if not self.creds.api_key or not self.creds.api_secret or not self.creds.redirect_uri:
            raise RuntimeError("Missing UPSTOX_API_KEY / UPSTOX_API_SECRET / UPSTOX_REDIRECT_URI")

        payload = {
            "code": code,
            "client_id": self.creds.api_key,
            # Fixed typo: use the proper attribute for client secret
            "client_secret": self.creds.api_secret,
            "redirect_uri": self.creds.redirect_uri,
            "grant_type": "authorization_code",
        }

        # The Upstox token endpoint expects URL‑encoded form data (application/x-www-form-urlencoded).
        # Use ``data=payload`` which makes ``requests`` encode the dict accordingly.
        headers = {"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}

        log.debug(
            "Attempting token exchange via POST (form): url=%s payload=%s headers=%s",
            self.TOKEN_URL,
            payload,
            headers,
        )
        resp = requests.post(self.TOKEN_URL, data=payload, headers=headers, timeout=30)
        # Fallback to GET if POST does not succeed (unlikely for OAuth token endpoint).
        if resp.status_code != 200:
            log.warning(
                "POST token exchange failed (status=%s). Retrying with GET. URL=%s payload=%s headers=%s",
                resp.status_code,
                self.TOKEN_URL,
                payload,
                headers,
            )
            resp = requests.get(self.TOKEN_URL, params=payload, headers=headers, timeout=30)
        if resp.status_code != 200:
            log.error("Upstox token exchange failed: status={} body={}", resp.status_code, resp.text)
            return False

        body = resp.json()
        token = body.get("access_token")
        if not token:
            log.error("Upstox token exchange succeeded but access_token missing: {}", body)
            return False

        self.creds.access_token = token

        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
        if os.path.exists(env_path):
            set_key(env_path, "UPSTOX_ACCESS_TOKEN", token)

        log.info("Access token updated successfully.")
        return True

    def get_market_quote_ltp(self, instrument_keys: list[str]) -> dict[str, Any]:
        """
        Fetch LTP for one or more instruments using Upstox REST market quote endpoint.

        Based on Upstox docs/curl examples:
        - GET /v3/market-quote/ltp?instrument_key=<comma-separated instrument_keys>
        """
        if not instrument_keys:
            return {"status": "error", "errors": ["instrument_keys empty"]}

        url = f"{self.BASE_URL}/v3/market-quote/ltp"
        headers = self._auth_headers()

        # list[str] => instrument_keys_csv  should be comma-separated for the API request
        #  but no leading or trailing commas and no comma if only one entry exist
        
        
        
        instrument_key_csv = ",".join(instrument_keys)

        # params = {"instrument_key": instrument_key_csv}
                
        # 2. Pass it inside the params dictionary
        payload = {"instrument_key": instrument_key_csv}
        
        #print all parameter and request url
        print(f"------------------------- URL:{url}###")
        print(f"====================== payload :{payload}")


        token_preview = (
            self.creds.access_token[:6] + "..." + self.creds.access_token[-4:]
            if self.creds.access_token
            else None
        )
        # Force error-level logs to ensure they show up even when INFO is filtered.
        # log.error(
        #     "UPSTOX LTP CALL: url={} params={} token_preview={} instrument_key_csv={}",
        #     url,
        #     payload,
        #     token_preview,
        #     instrument_key_csv,
        # )
        print("Sending LTP request...f")
    
        # FORM the ENCODED URL correctly with parameters for GET request
        # encoded_params = urllib.parse.urlencode(params)
        # Ensure the URL is properly formed with query parameters
        full_url = f"{url}"#?{encoded_params}"
        print(f"Full URL with encoded parameters: {full_url}")
        #make request to the full URL with headers and timeout
        access_token = self.creds.access_token
        access_token = 'eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI3NkFGMzUiLCJqdGkiOiI2YTIyNWE0OTUyY2JhMjdlNTNiNWNhZDYiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6ZmFsc2UsImlhdCI6MTc4MDYzNjIzMywiaXNzIjoidWRhcGktZ2F0ZXdheS1zZXJ2aWNlIiwiZXhwIjoxNzgwNjk2ODAwfQ.Ta_pBqybIL6RB0SrU_GPJPCwkJwTN3d7KbLBniTVems'
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {access_token}'
        }
        parameters = {
            "instrument_key": instrument_key_csv
        }
        resp = requests.get(full_url, headers=headers, params=parameters, timeout=30)


        print(f"Raw response: status={resp.status_code} body={resp.text[:200]}...")
        print(f"Full response body: {resp.text}")
        print(f"Response status code: {resp.status_code}")
        print(resp.text)
        return_code = resp.status_code
        if return_code != 200:
            log.error("Market quote LTP request failed: status={} body={}", resp.status_code, resp.text)
            return {"status": "error", "errors": [resp.text]}
        
        
        return resp.json()
    

    def get_option_chain(self, instrument_key: str, expiry_date: str) -> dict[str, Any]:
        """Fetch option chain for a given underlying *instrument_key* and *expiry_date*.

        The Upstox V2 endpoint expects URL‑encoded query parameters:
        ``GET /v2/option/chain?instrument_key=<encoded>&expiry_date=YYYY-MM-DD``.
        This method now builds the request correctly, handling URL‑encoding and
        authentication headers.
        """
        # Build request URL and parameters.
        url = f"{self.BASE_URL}/v2/option/chain"
        # ``instrument_key`` may contain characters such as ``|`` that need
        # encoding; ``requests`` will handle this when passed via ``params``.
        params = {
            "instrument_key": instrument_key,
            "expiry_date": expiry_date,
        }
        your_access_token =  HARDCODED_UPSTOX_ACCESS_TOKEN
        myheaders = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {your_access_token}'
        }

        print(f"------------------------- URL:{url}###")
        print(f"====================== payload :{params}")
        resp = requests.get(url, headers= myheaders, params=params, timeout=30)

        print(f"Option chain response: status={resp.status_code} body={resp.text[:200]}...")
        print(f"Full option chain response body: {resp.text}")
        print("-------------------------->>")
        print(resp)
        if resp.status_code != 200:
            log.error(
                "Option chain request failed: status={} body={}",
                resp.status_code,
                resp.text,
            )
            return {"status": "error", "errors": [resp.text]}


        print(f"Option chain response: status={resp.status_code} body={resp.text[:200]}...")
        # Return parsed JSON response.
        return resp.json()

    def get_option_contracts(self, instrument_key: str) -> dict[str, Any]:
        """Fetch all active option contracts (expiries) for a given underlying."""
        url = f"{self.BASE_URL}/v2/option/contract"
        params = {"instrument_key": instrument_key}
        headers = self._auth_headers()

        resp = requests.get(url, headers=headers, params=params, timeout=30)
        if resp.status_code != 200:
            log.error("Failed to fetch option contracts: status={} body={}", resp.status_code, resp.text)
            return {"status": "error", "errors": [resp.text]}
        return resp.json()


# -----------------------------
# Instruments master (token lookup)
# -----------------------------

_INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
_INSTRUMENTS_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "upstox"
_INSTRUMENTS_CACHE_GZ = _INSTRUMENTS_CACHE_DIR / "NSE.json.gz"
_INSTRUMENTS_CACHE_JSON = _INSTRUMENTS_CACHE_DIR / "NSE.json"

_INSTRUMENTS_MASTER_CACHE: dict[str, Any] | None = None
_INSTRUMENTS_LOOKUP: dict[tuple[str, str, float, str], dict[str, Any]] | None = None


def _download_instruments_master_if_needed(ttl_sec: int = 24 * 3600) -> None:
    """
    Downloads and caches the Upstox NSE instruments master (gzip JSON).
    Re-downloads only when the cached gz file is stale or missing.
    """
    _INSTRUMENTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _is_stale(p: Path) -> bool:
        if not p.exists():
            return True
        age = time.time() - p.stat().st_mtime
        return age > ttl_sec

    if not _is_stale(_INSTRUMENTS_CACHE_GZ):
        return

    log.info("Downloading Upstox instruments master to cache: {}", _INSTRUMENTS_CACHE_GZ)
    with urllib.request.urlopen(_INSTRUMENTS_URL, timeout=60) as resp:
        data = resp.read()
    _INSTRUMENTS_CACHE_GZ.write_bytes(data)

    log.info("Decompressing instruments master cache: {}", _INSTRUMENTS_CACHE_JSON)
    with gzip.open(_INSTRUMENTS_CACHE_GZ, "rb") as gz_f:
        raw = gz_f.read()
    _INSTRUMENTS_CACHE_JSON.write_bytes(raw)


def _ensure_instruments_lookup() -> None:
    """
    Loads instruments master and builds a lookup:
      (underlying, expiry, strike, option_type) -> record
    """
    global _INSTRUMENTS_MASTER_CACHE, _INSTRUMENTS_LOOKUP
    if _INSTRUMENTS_LOOKUP is not None and _INSTRUMENTS_MASTER_CACHE is not None:
        return

    _download_instruments_master_if_needed()

    if not _INSTRUMENTS_CACHE_JSON.exists():
        raise FileNotFoundError(f"Missing instruments cache JSON: {_INSTRUMENTS_CACHE_JSON}")

    log.info("Loading Upstox instruments master from cache: {}", _INSTRUMENTS_CACHE_JSON)
    raw = _INSTRUMENTS_CACHE_JSON.read_bytes()
    master_list = json.loads(raw.decode("utf-8"))

    lookup: dict[tuple[str, str, float, str], dict[str, Any]] = {}

    for rec in master_list:
        name = rec.get("name") or rec.get("underlying") or rec.get("underlying_name")
        expiry = rec.get("expiry")
        strike = rec.get("strike")
        option_type = rec.get("option_type") or rec.get("optionType") or rec.get("instrument_type")

        if name is None or expiry is None or strike is None or option_type is None:
            continue

        opt = str(option_type).upper()
        if opt not in ("CE", "PE"):
            if "CALL" in opt or opt == "C":
                opt = "CE"
            elif "PUT" in opt or opt == "P":
                opt = "PE"
            else:
                continue

        try:
            strike_f = float(strike)
        except (TypeError, ValueError):
            continue

        key = (str(name), str(expiry), strike_f, opt)
        if key not in lookup or (rec.get("tradingsymbol") and not lookup[key].get("tradingsymbol")):
            lookup[key] = rec

    _INSTRUMENTS_MASTER_CACHE = cast(dict[str, Any], master_list)
    _INSTRUMENTS_LOOKUP = lookup
    log.info("Instruments lookup ready. keys={}", len(lookup))


def resolve_option_instrument_master(
    *,
    underlying: str,
    expiry: str,
    strike: float,
    option_type: str,
) -> dict[str, Any] | None:
    """
    Resolves Upstox instrument identifiers for options.

    Returns a record (dict) with (best-effort) keys like:
      - instrument_key
      - instrument_token (if present)
      - tradingsymbol
    """
    _ensure_instruments_lookup()
    assert _INSTRUMENTS_LOOKUP is not None

    opt = str(option_type).upper()
    if opt not in ("CE", "PE"):
        raise ValueError(f"option_type must be CE or PE, got: {option_type}")

    key = (str(underlying), str(expiry), float(strike), opt)
    rec = _INSTRUMENTS_LOOKUP.get(key)

    if rec:
        return cast(dict[str, Any], rec)

    expiry_norm = str(expiry).replace("/", "-")
    if expiry_norm != str(expiry):
        key2 = (str(underlying), expiry_norm, float(strike), opt)
        rec = _INSTRUMENTS_LOOKUP.get(key2)
        if rec:
            return cast(dict[str, Any], rec)

    return None


def make_client_from_env() -> UpstoxClient:
    """
    Factory to create client using env/.env variables.

    IMPORTANT: Prefer runtime OS env `UPSTOX_ACCESS_TOKEN` over any token loaded from .env
    (prevents using stale tokens).
    """
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")

    # Load non‑token env variables from .env, but avoid loading a stale token.
    # We load the .env file without overriding existing OS env vars. This keeps
    # API key/secret/redirect values available while ensuring the access token
    # is taken only from the current process environment (i.e., a freshly set
    # UPSTOX_ACCESS_TOKEN). Stale values in .env will therefore be ignored.
    load_dotenv(env_path, override=False)

    # Token from the OS environment – this is the only source we trust for the
    # live access token.
    token_from_os = os.getenv("UPSTOX_ACCESS_TOKEN")
    access_token = token_from_os.strip() if token_from_os else None

    api_key = os.getenv("UPSTOX_API_KEY")
    api_secret = os.getenv("UPSTOX_API_SECRET")
    redirect_uri = os.getenv("UPSTOX_REDIRECT_URI")

    if access_token:
        tok_len = len(access_token)
        preview = f"{access_token[:6]}...{access_token[-4:]}"
        log.info(
            "Upstox access token loaded from OS env: present=true len={} preview={}",
            tok_len,
            preview,
        )
    else:
        log.error("Upstox access token missing in OS environment (UPSTOX_ACCESS_TOKEN).")

    creds = UpstoxCreds(
        api_key=api_key,
        api_secret=api_secret,
        redirect_uri=redirect_uri,
        access_token=access_token,
    )
    return UpstoxClient(access_token, creds=creds)
