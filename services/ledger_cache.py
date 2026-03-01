"""
Historical ledger cache for fee-calculation resilience (e.g. API key removed at 05:00 UTC).
09:00 UTC pre-window fetch stores full Margin Funding ledger per user; 7-day TTL.
Cached data is encrypted (no plaintext ledger in Redis/DB). Used at 10:30 UTC when 10:00 fetch failed.
Stores entries + start_ms so deduction can run even if vault was deleted after 09:00.
Cache freshness: reject cache if age > CACHE_MAX_AGE_MINS (e.g. 60).
"""
import json
import logging
import time
from datetime import date
from typing import Any, List, Optional, Tuple

import security

logger = logging.getLogger(__name__)

LEDGER_CACHE_TTL_DAYS = 7
LEDGER_CACHE_KEY_PREFIX = "ledger_cache:v1:"
CACHE_MAX_AGE_MINS = 60  # Reject cache older than this (09:00 cache must be ≤60 mins old when used)


def _cache_key(user_id: int, date_utc: date) -> str:
    return f"{LEDGER_CACHE_KEY_PREFIX}{user_id}:{date_utc.isoformat()}"


def _encrypt_payload(obj: dict) -> str:
    """Encrypt JSON payload for storage (no plaintext ledger)."""
    raw = json.dumps(obj, default=str)
    return security.encrypt_key(raw)


def _decrypt_payload(encrypted: str) -> Optional[dict]:
    """Decrypt cached payload to { entries, start_ms }."""
    if not encrypted:
        return None
    try:
        raw = security.decrypt_key(encrypted)
        return json.loads(raw) if raw else None
    except Exception as e:
        logger.warning("ledger_cache decrypt failed: %s", e)
        return None


async def set_ledger_cache(
    redis: Any, user_id: int, date_utc: date, entries: List[Any], start_ms: Optional[int] = None
) -> bool:
    """
    Store full Margin Funding ledger for user/date in Redis. Encrypted, 7-day TTL.
    start_ms and cached_at_ts stored for age check. Returns True on success.
    """
    if not redis or not entries:
        return False
    try:
        key = _cache_key(user_id, date_utc)
        cached_at_ts = int(time.time())
        payload = _encrypt_payload({"entries": entries, "start_ms": start_ms, "cached_at_ts": cached_at_ts})
        ttl_sec = LEDGER_CACHE_TTL_DAYS * 86400
        await redis.set(key, payload, ex=ttl_sec)
        return True
    except Exception as e:
        logger.warning("ledger_cache set failed user_id=%s: %s", user_id, e)
        return False


async def get_ledger_cache(redis: Any, user_id: int, date_utc: date) -> Optional[Tuple[List[Any], Optional[int]]]:
    """
    Retrieve cached ledger entries and start_ms for user/date. Returns (entries, start_ms) or None.
    Rejects cache if cache_age_mins > CACHE_MAX_AGE_MINS (stale cache – skipping).
    """
    if not redis:
        return None
    try:
        key = _cache_key(user_id, date_utc)
        raw = await redis.get(key)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        obj = _decrypt_payload(raw)
        if not obj:
            return None
        cached_at_ts = obj.get("cached_at_ts") or 0
        if cached_at_ts:
            cache_age_mins = (int(time.time()) - cached_at_ts) // 60
            if cache_age_mins > CACHE_MAX_AGE_MINS:
                logger.warning("Stale cache for user_id=%s (age: %s mins) – skipping", user_id, cache_age_mins)
                return None
        entries = obj.get("entries") or []
        start_ms = obj.get("start_ms")
        return (entries, start_ms)
    except Exception as e:
        logger.warning("ledger_cache get failed user_id=%s: %s", user_id, e)
        return None


async def get_ledger_cache_with_fallback(
    redis: Any, db: Any, user_id: int, date_utc: date
) -> Optional[Tuple[Optional[List[Any]], Optional[int], Optional[float]]]:
    """
    Try Redis first. On RedisError: fetch last_cached_daily_gross_usd from user_profit_snapshot (DB fallback).
    Returns (entries, start_ms) from Redis, or (None, None, last_cached_daily_gross_usd) from DB on Redis failure.
    """
    try:
        result = await get_ledger_cache(redis, user_id, date_utc)
        if result is not None:
            entries, start_ms = result
            return (entries, start_ms, None)
    except Exception as e:
        logger.warning("Redis ledger cache failed for user_id=%s: %s", user_id, e)
    # DB fallback: use last_cached_daily_gross_usd from user_profit_snapshot for deduction
    try:
        if db is not None:
            from sqlalchemy.orm import Session
            from models import UserProfitSnapshot
            snap = db.query(UserProfitSnapshot).filter(UserProfitSnapshot.user_id == user_id).first()
            if snap is not None:
                amount = getattr(snap, "last_cached_daily_gross_usd", None)
                if amount is not None and float(amount) > 0:
                    logger.info(
                        "Redis down – using DB cache for user_id=%s (last_cached_daily_gross_usd=%s)",
                        user_id, amount,
                    )
                    return (None, None, float(amount))
    except Exception as db_err:
        logger.warning("DB cache fallback failed for user_id=%s: %s", user_id, db_err)
    return None
