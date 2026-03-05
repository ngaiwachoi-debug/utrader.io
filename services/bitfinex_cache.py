"""
Cache for Bitfinex-backed API responses to stay under rate limits.
Bitfinex: 10–90 requests/min per endpoint; IP blocked 60s on ERR_RATE_LIMIT.

- Per-user, per-endpoint cache with short TTL (90s wallets, 120s lending). This is for
  rate-limit protection only; do not use for long-lived caching of real-time data.
- Call invalidate(user_id, KEY_*) after any server-side action that changes wallets or
  lending for that user so the next request gets live data.
- If Bitfinex returns rate limit, return cached data and cooldown until next allowed call.
- Response headers indicate source (live vs cache) and when cache expires.
"""
import asyncio
import time
from typing import Any, Dict, Optional, Tuple

# Bitfinex: up to ~90 req/min per endpoint; use conservative per-user limits
# Min interval between fresh calls per (user_id, endpoint). Increased for dashboard fold + repeat visits.
CACHE_TTL_WALLETS_SEC = 90   # wallets + credits: 90s
CACHE_TTL_LENDING_SEC = 120  # funding trades + tickers: 120s
RATE_LIMIT_COOLDOWN_SEC = 60  # when Bitfinex returns ERR_RATE_LIMIT, don't call again for 60s

# Cap in-memory entries so 1000+ users don't grow unbounded (evict oldest when over limit).
MAX_CACHE_ENTRIES = 5000

_cache: Dict[Tuple[int, str], Dict[str, Any]] = {}
_lock = asyncio.Lock()

# Keys
KEY_WALLETS = "wallets"
KEY_LENDING = "lending"


def _cache_key(user_id: int, endpoint: str) -> Tuple[int, str]:
    return (user_id, endpoint)


def _get_ttl(endpoint: str) -> int:
    if endpoint == KEY_WALLETS:
        return CACHE_TTL_WALLETS_SEC
    return CACHE_TTL_LENDING_SEC


async def get_cached(user_id: int, endpoint: str) -> Optional[Tuple[Any, bool]]:
    """
    Returns (cached_data, from_cache) or None if miss/expired.
    from_cache True means we're returning stored data.
    """
    async with _lock:
        key = _cache_key(user_id, endpoint)
        entry = _cache.get(key)
        if not entry:
            return None
        data = entry.get("data")
        cached_at = entry.get("cached_at", 0)
        cooldown_until = entry.get("cooldown_until", 0)
        ttl = _get_ttl(endpoint)
        now = time.monotonic()
        # If in rate-limit cooldown, return cache (or None if no data yet)
        if cooldown_until and now < cooldown_until:
            return (data, True) if data is not None else None
        # If within TTL, return cache
        if data is not None and (now - cached_at) < ttl:
            return (data, True)
        return None


async def is_in_cooldown(user_id: int, endpoint: str) -> bool:
    """True if we are in rate-limit cooldown and must not call Bitfinex."""
    async with _lock:
        key = _cache_key(user_id, endpoint)
        entry = _cache.get(key)
        if not entry:
            return False
        cooldown_until = entry.get("cooldown_until", 0)
        return bool(cooldown_until and time.monotonic() < cooldown_until)


def _evict_oldest_if_over_limit() -> None:
    """Caller must hold _lock. Evict one oldest entry (by cached_at) when over MAX_CACHE_ENTRIES."""
    if len(_cache) <= MAX_CACHE_ENTRIES:
        return
    oldest_key = min(
        _cache.keys(),
        key=lambda k: _cache[k].get("cached_at", 0),
    )
    del _cache[oldest_key]


async def set_cached(user_id: int, endpoint: str, data: Any) -> None:
    async with _lock:
        key = _cache_key(user_id, endpoint)
        _cache[key] = {
            "data": data,
            "cached_at": time.monotonic(),
            "cooldown_until": 0,
        }
        _evict_oldest_if_over_limit()


async def invalidate(user_id: int, endpoint: str) -> None:
    """Remove cached data for this user/endpoint so the next request hits Bitfinex."""
    async with _lock:
        key = _cache_key(user_id, endpoint)
        if key in _cache:
            del _cache[key]


async def set_rate_limit_cooldown(user_id: int, endpoint: str) -> None:
    """Call when Bitfinex returns ERR_RATE_LIMIT; keep existing cache and set cooldown."""
    async with _lock:
        key = _cache_key(user_id, endpoint)
        entry = _cache.get(key) or {}
        entry["cooldown_until"] = time.monotonic() + RATE_LIMIT_COOLDOWN_SEC
        if "data" not in entry:
            entry["data"] = None
        if "cached_at" not in entry:
            entry["cached_at"] = 0
        _cache[key] = entry
        _evict_oldest_if_over_limit()


async def cache_expires_at(user_id: int, endpoint: str) -> Optional[float]:
    """Unix timestamp when cache expires (for X-Cache-Expires-At header)."""
    async with _lock:
        key = _cache_key(user_id, endpoint)
        entry = _cache.get(key)
        if not entry:
            return None
        cached_at = entry.get("cached_at", 0)
        cooldown_until = entry.get("cooldown_until", 0)
        ttl = _get_ttl(endpoint)
        now = time.monotonic()
        if cooldown_until and now < cooldown_until:
            return time.time() + (cooldown_until - now)
        return time.time() + max(0, ttl - (now - cached_at))


def is_rate_limit_error(err: Optional[str]) -> bool:
    if not err:
        return False
    return "ERR_RATE_LIMIT" in err or "rate limit" in err.lower()
