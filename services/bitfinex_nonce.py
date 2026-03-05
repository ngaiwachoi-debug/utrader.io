"""
Central nonce per Bitfinex API key (Redis) to avoid 10114 "nonce: small" when
both the worker and main.py (dashboard/API) use the same key.
"""
import hashlib
import os
import time
from typing import Any, Optional

NONCE_KEY_PREFIX = "bitfinex_nonce:"
NONCE_KEY_TTL_SEC = 86400  # 1 day

# Lua: INCR key, expire, max(incr_val, time_us), SET key to that max, return nonce string
_NONCE_SCRIPT = """
local k = KEYS[1]
local t = tonumber(ARGV[1])
local v = redis.call('INCR', k)
redis.call('EXPIRE', k, ARGV[2])
local n = math.max(v, t)
redis.call('SET', k, n)
return tostring(n)
"""

_sync_redis: Any = None


def _nonce_key(api_key: str) -> str:
    return NONCE_KEY_PREFIX + hashlib.sha256(api_key.encode()).hexdigest()[:16]


def get_sync_redis():
    """Lazy-create sync Redis from REDIS_URL. Returns None if REDIS_URL unset or Redis unavailable."""
    global _sync_redis
    if _sync_redis is not None:
        return _sync_redis
    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        import redis
        _sync_redis = redis.Redis.from_url(url, decode_responses=True)
        _sync_redis.ping()
        return _sync_redis
    except Exception:
        _sync_redis = None
        return None


def get_next_nonce_sync(api_key: str, redis_sync=None):
    """
    Return next nonce for this API key (sync). Uses Redis if available so worker and API share one sequence.
    redis_sync: optional sync Redis client; if None, uses lazy-created client from REDIS_URL.
    """
    r = redis_sync if redis_sync is not None else get_sync_redis()
    if r is None:
        return str(int(time.time() * 1000000))
    try:
        key = _nonce_key(api_key)
        now_us = int(time.time() * 1000000)
        nonce = r.eval(_NONCE_SCRIPT, 1, key, now_us, NONCE_KEY_TTL_SEC)
        return str(nonce) if nonce is not None else str(now_us)
    except Exception:
        return str(int(time.time() * 1000000))


async def get_next_nonce(redis_async, api_key: str) -> str:
    """
    Return next nonce for this API key (async). Use from bot_engine when redis_async is the ARQ/worker Redis.
    """
    if redis_async is None:
        return str(int(time.time() * 1000000))
    try:
        key = _nonce_key(api_key)
        now_us = int(time.time() * 1000000)
        nonce = await redis_async.eval(_NONCE_SCRIPT, 1, key, now_us, NONCE_KEY_TTL_SEC)
        return str(nonce) if nonce is not None else str(now_us)
    except Exception:
        return str(int(time.time() * 1000000))
