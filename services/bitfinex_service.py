"""
Bitfinex API v2 authenticated client.
Strict auth to avoid 10100 "Invalid or expired token":
- Nonce: micro-timestamp (no spaces in payload/signature).
- Signature: /api/{path}{nonce}{json_body} with json_body from json.dumps(..., separators=(',', ':')).
"""
import hashlib
import hmac
import json
import time
from typing import Any, Dict, List, Optional, Tuple

import aiohttp


BITFINEX_REST_URL = "https://api.bitfinex.com"


class BitfinexManager:
    """
    Handles Bitfinex v2 auth with strict signature format.
    Path for requests: "v2/auth/r/..." (no leading slash).
    Signature payload: /api/{path}{nonce}{json_body} with NO spaces in json_body.
    """

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret

    def _nonce(self) -> str:
        """Micro-timestamp for high accuracy (Bitfinex requirement)."""
        return str(int(time.time() * 1000000))

    def _json_body(self, payload: Dict[str, Any]) -> str:
        """JSON with no spaces so signature matches request body exactly."""
        return json.dumps(payload, separators=(",", ":"))

    def _build_signature(self, path: str, payload: Dict[str, Any]) -> str:
        """
        Signature payload: /api/{path}{nonce}{json_body}
        e.g. path = "v2/auth/r/info/user", body = "{}"
        """
        nonce = self._nonce()
        json_body = self._json_body(payload)
        signature_payload = f"/api/{path}{nonce}{json_body}"
        sig = hmac.new(
            self.api_secret.encode("utf-8"),
            signature_payload.encode("utf-8"),
            hashlib.sha384,
        ).hexdigest()
        return sig

    def _headers(self, path: str, payload: Dict[str, Any]) -> Dict[str, str]:
        nonce = self._nonce()
        json_body = self._json_body(payload)
        signature_payload = f"/api/{path}{nonce}{json_body}"
        bfx_signature = hmac.new(
            self.api_secret.encode("utf-8"),
            signature_payload.encode("utf-8"),
            hashlib.sha384,
        ).hexdigest()
        return {
            "bfx-nonce": nonce,
            "bfx-apikey": self.api_key,
            "bfx-signature": bfx_signature,
            "content-type": "application/json",
        }

    async def _post(self, path: str, payload: Optional[Dict[str, Any]] = None) -> Tuple[Optional[Any], Optional[str]]:
        """
        POST to Bitfinex v2 auth endpoint. path = "v2/auth/r/info/user" etc.
        Returns (response_data, error_message). error_message set on HTTP error or API error array.
        """
        payload = payload or {}
        url = f"{BITFINEX_REST_URL}/{path}"
        headers = self._headers(path, payload)
        body_str = self._json_body(payload)
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=body_str) as resp:
                raw = await resp.text()
                if resp.status != 200:
                    return None, raw or f"HTTP {resp.status}"
                try:
                    data = json.loads(raw) if raw else None
                except json.JSONDecodeError:
                    return None, raw or "Invalid JSON"
                # Bitfinex v2 often returns [error_code, "error message"]
                if isinstance(data, list) and len(data) >= 2 and isinstance(data[0], int) and data[0] >= 10000:
                    return None, data[1] if isinstance(data[1], str) else str(data)
                return data, None

    # --- Step 1: Test connection ---
    async def info_user(self) -> Tuple[Optional[Any], Optional[str]]:
        """POST /v2/auth/r/info/user. Returns (data, error)."""
        return await self._post("v2/auth/r/info/user", {})

    # --- Step 2: Permissions ---
    async def permissions(self) -> Tuple[Optional[Any], Optional[str]]:
        """POST /v2/auth/r/permissions. Returns (data, error)."""
        return await self._post("v2/auth/r/permissions", {})

    # --- Step 3: Wallets, funding offers, funding trades hist ---
    async def wallets(self) -> Tuple[Optional[Any], Optional[str]]:
        """POST /v2/auth/r/wallets."""
        return await self._post("v2/auth/r/wallets", {})

    async def funding_offers(self) -> Tuple[Optional[Any], Optional[str]]:
        """POST /v2/auth/r/funding/offers."""
        return await self._post("v2/auth/r/funding/offers", {})

    async def funding_trades_hist(self) -> Tuple[Optional[Any], Optional[str]]:
        """POST /v2/auth/r/funding/trades/hist (test read access)."""
        return await self._post("v2/auth/r/funding/trades/hist", {})

    # --- Balance summary for response ---
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
