import hashlib
import hmac
import json
import time
from typing import Any, Dict, Tuple, List

import aiohttp


BITFINEX_REST_URL = "https://api.bitfinex.com/v2"


def _build_auth_headers(api_key: str, api_secret: str, path: str, body: Dict[str, Any] | None) -> Dict[str, str]:
    """
    Builds Bitfinex v2 auth headers for a given path and JSON body.
    """
    nonce = str(int(time.time() * 1000000))
    payload = json.dumps(body) if body else "{}"
    signature_payload = f"/api/v2{path}{nonce}{payload}"
    signature = hmac.new(api_secret.encode(), signature_payload.encode(), hashlib.sha384).hexdigest()
    return {
        "bfx-nonce": nonce,
        "bfx-apikey": api_key,
        "bfx-signature": signature,
        "Content-Type": "application/json",
    }


async def _post(api_key: str, api_secret: str, path: str, body: Dict[str, Any] | None = None) -> Any:
    headers = _build_auth_headers(api_key, api_secret, path, body or {})
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{BITFINEX_REST_URL}{path}", headers=headers, json=body or {}) as resp:
            if resp.status != 200:
                return None
            try:
                return await resp.json()
            except Exception:
                return None


async def get_master_user_id(api_key: str, api_secret: str) -> str | None:
    """
    Calls v2/auth/r/info/user and returns the Bitfinex master user ID as a string.
    """
    data = await _post(api_key, api_secret, "/auth/r/info/user", {})
    if not data or not isinstance(data, list):
        return None

    # The exact layout can vary; we keep this defensive.
    try:
        # Typical shape: [userId, email, ...]
        master_id = str(data[0])
        return master_id
    except Exception:
        return None


def hash_bitfinex_id(master_user_id: str) -> str:
    """
    SHA-256 hash of the Bitfinex master user ID, stored in TrialHistory.
    """
    return hashlib.sha256(master_user_id.encode("utf-8")).hexdigest()


async def validate_api_permissions(api_key: str, api_secret: str) -> Tuple[bool, str | None]:
    """
    Validates that the Bitfinex API key has the required permissions:
    - Account History (Read)
    - Margin Funding (Read/Write)
    - Wallets (Read)
    - IP Access (No restrictions)

    Bitfinex exposes a permissions summary via /auth/r/info/user. We interpret it
    defensively and surface a generic error if we cannot confirm the toggles.
    """
    data = await _post(api_key, api_secret, "/auth/r/info/user", {})
    if not data or not isinstance(data, list):
        return False, "Unable to fetch Bitfinex account permissions."

    # The second or third element often contains a permissions object; we keep this loose.
    perms_blob = None
    for item in data:
        if isinstance(item, dict) and "permissions" in item:
            perms_blob = item["permissions"]
            break

    if not isinstance(perms_blob, dict):
        # Fallback: we cannot positively assert permissions – fail closed.
        return False, "Unable to verify Bitfinex API permissions. Please ensure required toggles are enabled."

    # The concrete keys may differ; we check for a few reasonable aliases.
    def _flag(path_candidates: list[str]) -> bool:
        for key in path_candidates:
            if key in perms_blob and bool(perms_blob[key]):
                return True
        return False

    has_account_history = _flag(["account/history", "history", "read_account"])
    has_margin_funding = _flag(["funding/read", "funding/write", "margin/funding"])
    has_wallets = _flag(["wallets/read", "wallets"])
    ip_unrestricted = not perms_blob.get("ip_whitelist_only", False)

    if not has_account_history:
        return False, "Bitfinex permission 'Account History (Read)' must be enabled."
    if not has_margin_funding:
        return False, "Bitfinex permission 'Margin Funding (Read/Write)' must be enabled."
    if not has_wallets:
        return False, "Bitfinex permission 'Wallets (Read)' must be enabled."
    if not ip_unrestricted:
        return False, "Bitfinex API key must not be IP-restricted."

    return True, None


async def get_wallets(api_key: str, api_secret: str) -> Any:
    """
    Returns the raw Bitfinex wallets payload for this key.
    """
    return await _post(api_key, api_secret, "/auth/r/wallets", {})


async def get_tickers(symbols: List[str]) -> Dict[str, float]:
    """
    Fetches public tickers for spot symbols like tBTCUSD and returns last prices.
    """
    if not symbols:
        return {}
    joined = ",".join(symbols)
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BITFINEX_REST_URL}/tickers?symbols={joined}") as resp:
            if resp.status != 200:
                return {}
            data = await resp.json()
            result: Dict[str, float] = {}
            for row in data:
                try:
                    symbol = row[0]
                    last_price = float(row[7])
                    result[symbol] = last_price
                except Exception:
                    continue
            return result


async def compute_usd_balances(
    api_key: str, api_secret: str
) -> Dict[str, Any]:
    """
    Computes:
    - total_usd_all: USD value of USD + USDT + selected majors
    - usd_only: USD funding wallet balance
    - per_currency and per_currency_usd for a few key assets
    """
    wallets = await get_wallets(api_key, api_secret)
    if not wallets or not isinstance(wallets, list):
        return {
            "total_usd_all": 0.0,
            "usd_only": 0.0,
            "per_currency": {},
            "per_currency_usd": {},
        }

    # Funding wallet balances by currency
    balances: Dict[str, float] = {}
    for w in wallets:
        try:
            w_type, currency, balance = w[0], w[1], float(w[2])
        except Exception:
            continue
        if w_type != "funding":
            continue
        balances[currency.upper()] = balances.get(currency.upper(), 0.0) + balance

    usd = balances.get("USD", 0.0)
    usdt = balances.get("USDt", 0.0) + balances.get("USDT", 0.0)

    # Map a few common currencies to tickers
    symbol_map = {
        "BTC": "tBTCUSD",
        "ETH": "tETHUSD",
        "XRP": "tXRPUSD",
    }
    needed_symbols = [s for cur, s in symbol_map.items() if cur in balances]
    prices = await get_tickers(needed_symbols)

    per_currency_usd: Dict[str, float] = {}
    per_currency_usd["USD"] = usd
    per_currency_usd["USDT"] = usdt  # assume 1:1

    for cur, sym in symbol_map.items():
        bal = balances.get(cur, 0.0)
        if bal and sym in prices:
            per_currency_usd[cur] = bal * prices[sym]

    total_usd_all = sum(per_currency_usd.values())

    return {
        "total_usd_all": total_usd_all,
        "usd_only": usd,
        "per_currency": balances,
        "per_currency_usd": per_currency_usd,
    }

