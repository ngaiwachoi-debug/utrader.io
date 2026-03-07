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

# Lua: GET current, if < time_us then SET with EX, else INCR and EXPIRE
_NONCE_SCRIPT = """
local k = KEYS[1]
local t = tonumber(ARGV[1])
local v = tonumber(redis.call('GET', k) or 0)
if v < t then
    redis.call('SET', k, ARGV[1], 'EX', ARGV[2])
    return ARGV[1]
end
local n = redis.call('INCR', k)
redis.call('EXPIRE', k, ARGV[2])
return n
"""

_sync_redis: Any = None


def _nonce_key(api_key: str) -> str:
    return NONCE_KEY_PREFIX + hashlib.sha256(api_key.encode()).hexdigest()[:16]


def nonce_key(api_key: str) -> str:
    """Public function to get nonce key for an API key."""
    return _nonce_key(api_key)


def get_sync_redis():
    """Lazy-create sync Redis from NONCE_REDIS_URL or REDIS_URL. Returns None if unset or Redis unavailable."""
    global _sync_redis
    if _sync_redis is not None:
        return _sync_redis
    url = (os.getenv("NONCE_REDIS_URL") or os.getenv("REDIS_URL") or "").strip()
    if ".upstash.io" in url and url.startswith("redis://"):
        url = url.replace("redis://", "rediss://", 1)
    if not url:
        return None
    try:
        import redis
        _sync_redis = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=5)
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
    now_us = int(time.time() * 1000000)
    r = redis_sync if redis_sync is not None else get_sync_redis()
    if r is None:
        return str(now_us)
    try:
        key = _nonce_key(api_key)
        nonce = r.eval(_NONCE_SCRIPT, 1, key, now_us, NONCE_KEY_TTL_SEC)
        if isinstance(nonce, bytes):
            return nonce.decode('utf-8')
        elif isinstance(nonce, float):
            return str(int(nonce))
        return str(nonce)
    except Exception:
        return str(now_us)


async def get_next_nonce(redis_async, api_key: str) -> str:
    """
    Return next nonce for this API key (async). Use from bot_engine when redis_async is the ARQ/worker Redis.
    """
    now_us = int(time.time() * 1000000)
    if redis_async is None:
        return str(now_us)
    try:
        key = _nonce_key(api_key)
        nonce = await redis_async.eval(_NONCE_SCRIPT, 1, key, now_us, NONCE_KEY_TTL_SEC)
        if isinstance(nonce, bytes):
            return nonce.decode('utf-8')
        elif isinstance(nonce, float):
            return str(int(nonce))
        return str(nonce)
    except Exception:
        return str(now_us)
