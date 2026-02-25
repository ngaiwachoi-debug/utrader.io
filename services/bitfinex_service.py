"""
Bitfinex API v2 authenticated client.
Uses the EXACT same request as debug_bitfinex_connection.py (requests.post + data=json_body)
so signature and body are byte-identical. Sync call run via asyncio.to_thread.
"""
import asyncio
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional, Tuple

import requests


BASE_URL = "https://api.bitfinex.com"


def _post_sync(api_key: str, api_secret: str, endpoint: str, payload: Optional[Dict[str, Any]] = None) -> Tuple[Optional[Any], Optional[str]]:
    """
    EXACT copy of debug_bitfinex_connection.py test_endpoint() logic.
    Uses requests.post(..., data=json_body) so Bitfinex receives the same bytes we signed.
    """
    payload = payload if payload is not None else {}
    nonce = str(int(time.time() * 1000000))
    json_body = json.dumps(payload, separators=(",", ":"))
    signature_payload = f"/api/{endpoint}{nonce}{json_body}"
    signature = hmac.new(
        api_secret.encode("utf-8"),
        signature_payload.encode("utf-8"),
        hashlib.sha384,
    ).hexdigest()
    headers = {
        "bfx-nonce": nonce,
        "bfx-apikey": api_key,
        "bfx-signature": signature,
        "content-type": "application/json",
    }
    url = f"{BASE_URL}/{endpoint}"
    try:
        response = requests.post(url, headers=headers, data=json_body, timeout=30)
        raw = response.text
        if response.status_code != 200:
            return None, raw or f"HTTP {response.status_code}"
        try:
            data = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return None, raw or "Invalid JSON"
        # Bitfinex error array: [error_code, "message"] with codes 10100, 10101, etc. (1xxxx)
        # Success e.g. user info returns [user_id, email, ...] where user_id can be > 10000
        if isinstance(data, list) and len(data) >= 2 and isinstance(data[0], int) and 10000 <= data[0] <= 10199:
            return None, data[1] if isinstance(data[1], str) else str(data)
        return data, None
    except Exception as e:
        return None, str(e)


class BitfinexManager:
    """
    Bitfinex v2 auth. Delegates to _post_sync (same as debug script) run in thread.
    """

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret

    async def _post(self, endpoint: str, payload: Optional[Dict[str, Any]] = None) -> Tuple[Optional[Any], Optional[str]]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: _post_sync(self.api_key, self.api_secret, endpoint, payload or {}),
        )

    async def info_user(self) -> Tuple[Optional[Any], Optional[str]]:
        """POST v2/auth/r/info/user. Returns (data, error)."""
        return await self._post("v2/auth/r/info/user", {})

    async def permissions(self) -> Tuple[Optional[Any], Optional[str]]:
        """POST v2/auth/r/permissions. Returns (data, error)."""
        return await self._post("v2/auth/r/permissions", {})

    async def wallets(self) -> Tuple[Optional[Any], Optional[str]]:
        """POST v2/auth/r/wallets."""
        return await self._post("v2/auth/r/wallets", {})

    async def funding_offers(self) -> Tuple[Optional[Any], Optional[str]]:
        """POST v2/auth/r/funding/offers."""
        return await self._post("v2/auth/r/funding/offers", {})

    async def funding_trades_hist(self) -> Tuple[Optional[Any], Optional[str]]:
        """POST v2/auth/r/funding/trades/hist."""
        return await self._post("v2/auth/r/funding/trades/hist", {})

    async def compute_usd_balances(self) -> Dict[str, Any]:
        """Uses wallets() to compute USD balance summary."""
        wallets, err = await self.wallets()
        if err or not isinstance(wallets, list):
            return {
                "total_usd_all": 0.0,
                "usd_only": 0.0,
                "per_currency": {},
                "per_currency_usd": {},
            }
        balances: Dict[str, float] = {}
        for w in wallets:
            try:
                w_type, currency, balance = w[0], w[1], float(w[2])
            except (IndexError, TypeError, ValueError):
                continue
            if w_type != "funding":
                continue
            currency = currency.upper() if isinstance(currency, str) else str(currency)
            balances[currency] = balances.get(currency, 0.0) + balance
        usd = balances.get("USD", 0.0)
        usdt = balances.get("USDt", 0.0) + balances.get("USDT", 0.0)
        per_currency_usd: Dict[str, float] = {"USD": usd, "USDT": usdt}
        total_usd_all = usd + usdt
        return {
            "total_usd_all": total_usd_all,
            "usd_only": usd,
            "per_currency": balances,
            "per_currency_usd": per_currency_usd,
        }


def hash_bitfinex_id(master_user_id: str) -> str:
    """SHA-256 hash of Bitfinex master user ID (for trial history)."""
    return hashlib.sha256(master_user_id.encode("utf-8")).hexdigest()
