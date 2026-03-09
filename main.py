import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
import json
import logging
import os

try:
    from dotenv import load_dotenv
    _root_dir = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(_root_dir, ".env"))
except ImportError:
    pass
import random
import re
import string
import secrets
import threading
import time as _time_module
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel
from sqlalchemy import or_, text
from sqlalchemy.exc import ProgrammingError, SQLAlchemyError
from sqlalchemy.orm import Session

from arq import create_pool
from arq.connections import RedisSettings
import stripe
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

import database
import models
import security
from utils.logging import generate_trace_id, get_trace_id, set_trace_id, configure_logging
configure_logging()
from services.bitfinex_service import BitfinexManager, hash_bitfinex_id
from services import bitfinex_cache  # Short TTL (90s/120s); call invalidate() after mutations so next request is live.
from services.daily_token_deduction import run_daily_token_deduction, run_deduction_for_user_for_date
from services import ledger_cache as ledger_cache_svc
from services import token_ledger_service as token_ledger_svc
from services.referral_rewards import apply_referral_rewards_on_purchase

# Single daily Bitfinex API call at 10:00 UTC (no API before 10:00). One retry at 10:10 if data incomplete.
DAILY_API_FETCH_UTC_HOUR = 10
DAILY_API_FETCH_UTC_MINUTE = 0
DAILY_API_RETRY_UTC_HOUR = 10
DAILY_API_RETRY_UTC_MINUTE = 10
DELAY_BETWEEN_USERS_SEC = 0.5
FETCH_CONCURRENCY = 3  # max concurrent Bitfinex API fetches; kept low because IP-level rate limit is shared with running bots
# Ledger data is "incomplete" if latest entry is newer than this (Bitfinex may still be finalizing).
LEDGER_FRESHNESS_MINUTES = 20

# Token deduction at 10:30 UTC (30-min buffer after 10:00 API fetch; uses stored snapshot only, no API call).
DAILY_DEDUCTION_UTC_HOUR = 10
DAILY_DEDUCTION_UTC_MINUTE = 30
DEDUCTION_RETRY_INTERVAL_SEC = 300  # 5 minutes
DEDUCTION_MAX_RETRIES = 3

# 09:00 UTC pre-window: fetch + cache ledger for all users (7-day TTL); prevents revenue loss if key removed before 10:00.
PREWINDOW_LEDGER_FETCH_UTC_HOUR = 9
PREWINDOW_LEDGER_FETCH_UTC_MINUTE = 0

# API key lock: no delete/modify during fee window (09:55–10:35 UTC).
API_KEY_LOCK_START_UTC_HOUR = 9
API_KEY_LOCK_START_UTC_MINUTE = 55
API_KEY_LOCK_END_UTC_HOUR = 10
API_KEY_LOCK_END_UTC_MINUTE = 35

# 11:15 UTC catch-up for restored keys (failed at 10:30, key restored after).
CATCHUP_DEDUCTION_UTC_HOUR = 11
CATCHUP_DEDUCTION_UTC_MINUTE = 15

# Late fee after N days of invalid key (no restoration). 12:00 UTC job applies fee.
# invalid_key_days is NOT reset after fee; only reset when user restores API key (POST /api/keys).
# Incremental fee: day 3 = 5%, day 4 = 10%, day 5 = 15% (LATE_FEE_PCT_PER_DAY * (invalid_key_days - 2)).
LATE_FEE_DAYS = 3
LATE_FEE_PCT = 0.05  # base 5% at day 3
LATE_FEE_PCT_PER_DAY = 0.05  # extra 5% per day beyond day 2 (day 3→5%, day 4→10%, day 5→15%)
MAX_LATE_FEE_PCT = 0.25  # cap incremental late fee at 25% (e.g. day 7+ = 25%)
LATE_FEE_UTC_HOUR = 12
LATE_FEE_UTC_MINUTE = 0

# 23:00 UTC reconciliation sweep for users who restored key after 11:15 (post-catch-up).
RECONCILIATION_UTC_HOUR = 23
RECONCILIATION_UTC_MINUTE = 0
RECONCILIATION_BATCH_SIZE = 10  # process 10 users per batch; 1s delay between batches

# Exclusive admin: only this email can access /admin/* (set ADMIN_EMAIL in env to override; use ngaiwachoi@gmail.com)
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "ngaiwachoi@gmail.com").strip().lower()

# API failure log for admin panel (in-memory, last N entries)
API_FAILURES_MAX = 200
_api_failures: List[Dict[str, Any]] = []
_api_failures_lock = asyncio.Lock()

# Deduction log for admin (in-memory, last N runs); each entry has user_id, date, tokens_deducted, etc.
DEDUCTION_LOGS_MAX = 5000
_deduction_logs: List[Dict[str, Any]] = []
_deduction_logs_lock = threading.Lock()

# Admin audit log (immutable append-only; no delete). Each entry: ts, email, action, detail.
ADMIN_AUDIT_MAX = 2000
_admin_audit_logs: List[Dict[str, Any]] = []
_admin_audit_lock = threading.Lock()

# Monthly API key deletion count: persisted in users.key_deletions (JSON); in-memory fallback if column missing.
_key_deletions: Dict[tuple, int] = {}
_key_deletions_lock = threading.Lock()


def _admin_audit(email: str, action: str, detail: Optional[Dict[str, Any]] = None) -> None:
    ts = datetime.utcnow()
    entry = {
        "ts": ts.isoformat() + "Z",
        "email": email,
        "action": action,
        "detail": detail or {},
    }
    with _admin_audit_lock:
        _admin_audit_logs.append(entry)
        while len(_admin_audit_logs) > ADMIN_AUDIT_MAX:
            _admin_audit_logs.pop(0)
    try:
        db = database.SessionLocal()
        db.add(models.AdminAuditLog(ts=ts, email=email, action=action, detail=json.dumps(detail or {})))
        db.commit()
        db.close()
    except Exception:
        try:
            db.rollback()
            db.close()
        except Exception:
            pass


async def _record_api_failure(context: str, user_id: Optional[int], error: str) -> str:
    """Record an API failure; returns failure id."""
    from uuid import uuid4
    entry = {
        "id": str(uuid4()),
        "ts": datetime.utcnow().isoformat() + "Z",
        "context": context,
        "user_id": user_id,
        "error": error[:500] if error else "Unknown error",
    }
    async with _api_failures_lock:
        _api_failures.append(entry)
        while len(_api_failures) > API_FAILURES_MAX:
            _api_failures.pop(0)
    return entry["id"]


async def _get_api_failures(limit: int = 100) -> List[Dict[str, Any]]:
    """Return recent failures (newest first)."""
    async with _api_failures_lock:
        copy = list(_api_failures)
    copy.reverse()
    return copy[:limit]


# ────────── In-memory response cache ──────────
# Per-endpoint TTL cache keyed by "endpoint:user_id". Avoids DB round-trips for
# frequently polled GET endpoints. Invalidated on mutations (start/stop bot, token add, etc.).
_response_cache: Dict[str, tuple] = {}  # key -> (monotonic_ts, response_data)
_RESPONSE_CACHE_TTLS = {
    "user-status": 30.0,
    "bot-stats": 10.0,
    "terminal-logs": 8.0,
    "notifications": 60.0,
    "dashboard-fold": 15.0,
    "token-add-history": 30.0,
    "deduction-history": 60.0,
    "wallets": 15.0,
    "token-balance": 15.0,
    "referral-info": 30.0,
    "referral-bundle": 30.0,
    "referral-reward-history": 30.0,
    "admin-users": 15.0,
    "admin-settings": 60.0,
    "admin-health": 30.0,
    "admin-deduction-logs": 30.0,
    "admin-token-add-logs": 30.0,
    "admin-referrals": 30.0,
    "admin-notifications": 60.0,
}
_RESPONSE_CACHE_MAX_SIZE = 5000


def _rcache_get(key: str) -> Any:
    """Return cached response or None if expired/missing."""
    cached = _response_cache.get(key)
    if cached is None:
        return None
    ts, data = cached
    endpoint = key.split(":", 1)[0]
    ttl = _RESPONSE_CACHE_TTLS.get(endpoint, 15.0)
    if _time_module.monotonic() - ts > ttl:
        _response_cache.pop(key, None)
        return None
    return data


def _rcache_set(key: str, data: Any) -> None:
    """Store response in cache."""
    if len(_response_cache) > _RESPONSE_CACHE_MAX_SIZE:
        cutoff = _time_module.monotonic() - 120
        expired = [k for k, (ts, _) in _response_cache.items() if ts < cutoff]
        for k in expired:
            _response_cache.pop(k, None)
    _response_cache[key] = (_time_module.monotonic(), data)


def _rcache_invalidate_user(user_id: int) -> None:
    """Invalidate all cached responses for a user (e.g. after bot start/stop, token add)."""
    keys_to_remove = [k for k in _response_cache if k.endswith(f":{user_id}")]
    for k in keys_to_remove:
        _response_cache.pop(k, None)


def _rcache_invalidate_prefix(prefix: str) -> None:
    """Invalidate all cached responses matching a prefix (e.g. 'admin-users')."""
    keys_to_remove = [k for k in _response_cache if k.startswith(prefix)]
    for k in keys_to_remove:
        _response_cache.pop(k, None)


# ────────── Deduction multiplier cache ──────────
_deduction_multiplier_cache: Optional[tuple] = None  # (monotonic_ts, value)
_DEDUCTION_MULTIPLIER_TTL = 120.0  # 2 minutes


def _get_scheduler_first_wait_sec() -> Optional[float]:
    """If TEST_SCHEDULER_SECONDS is set (e.g. 30), first run is in that many seconds for testing."""
    raw = os.getenv("TEST_SCHEDULER_SECONDS")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _get_scheduler_test_user_id() -> Optional[int]:
    """If TEST_SCHEDULER_USER_ID is set, only run refresh for that user (for tests)."""
    raw = os.getenv("TEST_SCHEDULER_USER_ID")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _is_api_key_lock_window() -> bool:
    """True during 09:55–10:35 UTC when API key delete/modify is disabled (fee calculation window)."""
    now = datetime.utcnow()
    start = now.replace(hour=API_KEY_LOCK_START_UTC_HOUR, minute=API_KEY_LOCK_START_UTC_MINUTE, second=0, microsecond=0)
    end = now.replace(hour=API_KEY_LOCK_END_UTC_HOUR, minute=API_KEY_LOCK_END_UTC_MINUTE, second=0, microsecond=0)
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end


def _get_next_utc_wait_sec(hour: int, minute: int) -> float:
    """Seconds until next given UTC time (hour, minute)."""
    now = datetime.utcnow()
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_run <= now:
        next_run += timedelta(days=1)
    return (next_run - now).total_seconds()


async def _run_09_00_ledger_cache_scheduler() -> None:
    """
    Daily 09:00 UTC: fetch + cache Margin Funding ledger for all users (7-day TTL).
    Validates API keys; sends in-app/email alert for invalid keys.
    Prevents revenue loss if user deletes key at 05:00 UTC (10:30 deduction uses cache).
    """
    while True:
        wait_sec = _get_next_utc_wait_sec(PREWINDOW_LEDGER_FETCH_UTC_HOUR, PREWINDOW_LEDGER_FETCH_UTC_MINUTE)
        set_trace_id(generate_trace_id())
        logger.info("trace_id=%s | Next 09:00 UTC ledger cache run in %.0fs", get_trace_id(), wait_sec)
        await asyncio.sleep(wait_sec)
        db = database.SessionLocal()
        try:
            user_ids = [
                row[0]
                for row in db.query(models.User.id)
                .join(models.APIVault, models.User.id == models.APIVault.user_id)
                .filter(models.User.status != "dormant")
                .distinct()
                .all()
            ]
            test_uid = _get_scheduler_test_user_id()
            if test_uid is not None:
                user_ids = [u for u in user_ids if u == test_uid]
        finally:
            db.close()
        if not user_ids:
            continue
        try:
            redis = await asyncio.wait_for(get_redis(), timeout=REDIS_CONNECT_TIMEOUT)
        except Exception as e:
            logger.warning("09:00 ledger cache: Redis unavailable: %s", e)
            continue
        today_utc = datetime.utcnow().date()
        _cache_sem = asyncio.Semaphore(FETCH_CONCURRENCY)

        async def _cache_one_user_09_00(uid: int) -> None:
            async with _cache_sem:
                await asyncio.sleep(DELAY_BETWEEN_USERS_SEC)
                db_c = database.SessionLocal()
                try:
                    user = db_c.query(models.User).filter(models.User.id == uid).first()
                    vault = db_c.query(models.APIVault).filter(models.APIVault.user_id == uid).first()
                    if not user or not vault:
                        return
                    email = getattr(user, "email", None) or ""
                    try:
                        keys = vault.get_keys()
                        mgr = BitfinexManager(keys["bfx_key"], keys["bfx_secret"])
                        ledger_currencies = await _get_ledger_currencies_for_user(mgr)
                        if not ledger_currencies:
                            ledger_currencies = list(LEDGER_FUNDING_CURRENCIES)
                        entries, _, fetch_err = await _fetch_all_margin_funding_entries(mgr, currencies=ledger_currencies)
                        if fetch_err and not entries:
                            logger.warning("09:00 UTC: Invalid API key for %s – alert sent", email)
                            await _alert_admins_deduction_failure(
                                f"User {email} (ID: {uid}): Bitfinex API key invalid. Update by 10:00 UTC to avoid fee processing with cached data."
                            )
                            return
                        start_ms = int(vault.created_at.timestamp() * 1000) if getattr(vault, "created_at", None) else None
                        ok = await ledger_cache_svc.set_ledger_cache(redis, uid, today_utc, entries or [], start_ms=start_ms)
                        if ok:
                            logger.info("09:00 UTC: Cached ledger data for %s (API key valid)", email)
                    except Exception as e:
                        logger.warning("09:00 UTC: Cache failed for user_id=%s: %s", uid, e)
                        await _alert_admins_deduction_failure(
                            f"User {email or uid} (ID: {uid}): Ledger cache failed – {e!s}"
                        )
                finally:
                    db_c.close()

        await asyncio.gather(*[_cache_one_user_09_00(uid) for uid in user_ids], return_exceptions=True)


async def _run_daily_gross_profit_scheduler() -> None:
    """
    Single daily API run at 10:00 UTC (no API before 10:00). Fetch Margin Funding ledger per user,
    validate completeness (latest entry >= 20 mins old). If incomplete, retry once at 10:10.
    If still incomplete after retry: skip deduction for the day (set daily_gross_profit_usd=0) and alert.
    Max 2 API calls/day per user (10:00 + optional 10:10 retry).
    """
    first_wait = _get_scheduler_first_wait_sec()
    while True:
        if first_wait is not None:
            wait_sec = first_wait
            first_wait = None
            print(f"[scheduler] TEST_SCHEDULER_SECONDS: first run in {wait_sec:.0f}s")
        else:
            wait_sec = _get_next_utc_wait_sec(DAILY_API_FETCH_UTC_HOUR, DAILY_API_FETCH_UTC_MINUTE)
            print(f"[scheduler] Next daily API fetch at 10:00 UTC (in {wait_sec:.0f}s)")
        await asyncio.sleep(wait_sec)
        db = database.SessionLocal()
        try:
            user_ids = [
                row[0]
                for row in db.query(models.User.id)
                .join(models.APIVault, models.User.id == models.APIVault.user_id)
                .filter(models.User.status != "dormant")
                .distinct()
                .all()
            ]
            test_uid = _get_scheduler_test_user_id()
            if test_uid is not None:
                user_ids = [u for u in user_ids if u == test_uid]
        finally:
            db.close()
        if not user_ids:
            continue
        print(f"[scheduler] 10:00 UTC API fetch: {len(user_ids)} user(s)")
        incomplete_after_10_00: List[int] = []
        _fetch_sem = asyncio.Semaphore(FETCH_CONCURRENCY)

        async def _fetch_one_user_10_00(uid: int) -> None:
            async with _fetch_sem:
                await asyncio.sleep(DELAY_BETWEEN_USERS_SEC)
                db_f = database.SessionLocal()
                try:
                    success, data_incomplete, err = await _daily_10_00_fetch_and_save(uid, db_f)
                    if success:
                        snap = db_f.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == uid).first()
                        if snap:
                            cache_data = {
                                "gross_profit": float(snap.gross_profit_usd or 0),
                                "bitfinex_fee": float(snap.bitfinex_fee_usd or 0),
                                "net_profit": float(snap.net_profit_usd or 0),
                            }
                            await bitfinex_cache.set_cached(uid, bitfinex_cache.KEY_LENDING, cache_data)
                        user_obj = db_f.query(models.User).filter(models.User.id == uid).first()
                        logger.info(
                            "daily_10_00_fetch user_id=%s email=%s gross_profit_usd=%s data_complete=1",
                            uid, getattr(user_obj, "email", None), getattr(snap, "gross_profit_usd", None),
                        )
                    elif data_incomplete:
                        incomplete_after_10_00.append(uid)
                        logger.warning("daily_10_00_fetch user_id=%s data_incomplete (latest entry < %s mins)", uid, LEDGER_FRESHNESS_MINUTES)
                    else:
                        if err:
                            await _record_api_failure("daily_10_00_fetch", uid, err)
                finally:
                    db_f.close()

        await asyncio.gather(*[_fetch_one_user_10_00(uid) for uid in user_ids], return_exceptions=True)
        if incomplete_after_10_00:
            wait_retry = _get_next_utc_wait_sec(DAILY_API_RETRY_UTC_HOUR, DAILY_API_RETRY_UTC_MINUTE)
            if wait_retry > 0 and wait_retry < 3600:
                await asyncio.sleep(wait_retry)
            print(f"[scheduler] 10:10 UTC retry: {len(incomplete_after_10_00)} user(s)")
            still_incomplete: List[int] = []
            _retry_sem = asyncio.Semaphore(FETCH_CONCURRENCY)

            async def _retry_one_user_10_10(uid: int) -> None:
                async with _retry_sem:
                    await asyncio.sleep(DELAY_BETWEEN_USERS_SEC)
                    db_r = database.SessionLocal()
                    try:
                        success, data_incomplete, _ = await _daily_10_00_fetch_and_save(uid, db_r)
                        if success:
                            snap = db_r.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == uid).first()
                            if snap:
                                await bitfinex_cache.set_cached(
                                    uid,
                                    bitfinex_cache.KEY_LENDING,
                                    {
                                        "gross_profit": float(snap.gross_profit_usd or 0),
                                        "bitfinex_fee": float(snap.bitfinex_fee_usd or 0),
                                        "net_profit": float(snap.net_profit_usd or 0),
                                    },
                                )
                            logger.info("daily_10_10_retry user_id=%s success", uid)
                        elif data_incomplete:
                            still_incomplete.append(uid)
                    finally:
                        db_r.close()

            await asyncio.gather(*[_retry_one_user_10_10(uid) for uid in incomplete_after_10_00], return_exceptions=True)
            for uid in still_incomplete:
                db = database.SessionLocal()
                try:
                    snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == uid).first()
                    if snap and hasattr(snap, "daily_gross_profit_usd"):
                        snap.daily_gross_profit_usd = 0.0
                        db.commit()
                    user_obj = db.query(models.User).filter(models.User.id == uid).first()
                    email = getattr(user_obj, "email", None) or ""
                    logger.warning(
                        "daily_fetch_incomplete user_id=%s email=%s – skip deduction for the day (no partial data)",
                        uid, email,
                    )
                    await _alert_admins_deduction_failure(
                        f"Incomplete ledger data for user {email} (ID: {uid}) – skipped deduction for the day. Latest entry < {LEDGER_FRESHNESS_MINUTES} mins."
                    )
                finally:
                    db.close()
        # Refresh ranking and referral gain snapshots once per day (after 10:00 profit calculation)
        db_rank = database.SessionLocal()
        try:
            _refresh_ranking_snapshot(db_rank)
            _refresh_referral_gain_snapshot(db_rank)
        finally:
            db_rank.close()


def _get_next_1030_utc_wait_sec() -> float:
    """Seconds until next 10:30 UTC (deduction uses stored snapshot only, no API call)."""
    return _get_next_utc_wait_sec(DAILY_DEDUCTION_UTC_HOUR, DAILY_DEDUCTION_UTC_MINUTE)


def _random_gmail_display(rng: random.Random) -> str:
    """Name-based Gmail style: e.g. alanfhs103@gmail.com (all lowercase, ends with @gmail.com)."""
    name_len = rng.randint(4, 9)
    name_part = "".join(rng.choices(string.ascii_lowercase, k=name_len))
    suffix_len = rng.randint(3, 6)
    suffix = "".join(rng.choices(string.ascii_lowercase + string.digits, k=suffix_len))
    return f"{name_part}{suffix}@gmail.com"


def _refresh_ranking_snapshot(db: Session) -> None:
    """
    Generate top 100 fake ranking (yield 15–32%), replace ranking_snapshot.
    user_display = name-based Gmail (e.g. alanfhs103@gmail.com). All @gmail.com.
    Called once per day after 10:00 UTC profit calculation; also on startup if table empty.
    """
    try:
        today = date.today()
        seed = today.year * 10000 + today.month * 100 + today.day
        rng = random.Random(seed)
        seen_emails: set[str] = set()
        rows = []
        for i in range(100):
            while True:
                user_display = _random_gmail_display(rng)
                if user_display not in seen_emails:
                    seen_emails.add(user_display)
                    break
            rows.append({
                "user_display": user_display,
                "yield_pct": round(15 + rng.uniform(0, 17), 2),
                "lent_usd": round(1000 + rng.uniform(0, 99000), 2),
            })
        rows.sort(key=lambda x: x["yield_pct"], reverse=True)
        # plan_tier by rank: top 5 whales, 6-20 ai_ultra, 21-50 pro, 51-100 trial
        def _plan_tier_for_rank(r: int) -> str:
            if r <= 5:
                return "whales"
            if r <= 20:
                return "ai_ultra"
            if r <= 50:
                return "pro"
            return "trial"
        db.query(models.RankingSnapshot).delete()
        for r, row in enumerate(rows, start=1):
            db.add(models.RankingSnapshot(
                rank=r,
                user_display=row["user_display"],
                yield_pct=row["yield_pct"],
                lent_usd=row["lent_usd"],
                plan_tier=_plan_tier_for_rank(r),
            ))
        db.commit()
        logger.info("ranking_snapshot refreshed: 100 rows (seed=%s)", seed)
    except Exception as e:
        db.rollback()
        logger.warning("_refresh_ranking_snapshot failed: %s", e)


def _refresh_referral_gain_snapshot(db: Session) -> None:
    """
    Generate top 100 fake referral gain (usdt_gain_daily 500–10000), replace referral_gain_snapshot.
    user_display = same Gmail-style as ranking. Called once per day after 10:00 UTC profit calculation;
    also on startup if table empty.
    """
    try:
        today = date.today()
        seed = today.year * 10000 + today.month * 100 + today.day
        rng = random.Random(seed)
        seen_emails: set[str] = set()
        rows = []
        for i in range(100):
            while True:
                user_display = _random_gmail_display(rng)
                if user_display not in seen_emails:
                    seen_emails.add(user_display)
                    break
            rows.append({
                "user_display": user_display,
                "usdt_gain_daily": round(500 + rng.uniform(0, 9500), 2),
            })
        rows.sort(key=lambda x: x["usdt_gain_daily"], reverse=True)
        db.query(models.ReferralGainSnapshot).delete()
        for r, row in enumerate(rows, start=1):
            db.add(models.ReferralGainSnapshot(
                rank=r,
                user_display=row["user_display"],
                usdt_gain_daily=row["usdt_gain_daily"],
            ))
        db.commit()
        logger.info("referral_gain_snapshot refreshed: 100 rows (seed=%s)", seed)
    except Exception as e:
        db.rollback()
        logger.warning("_refresh_referral_gain_snapshot failed: %s", e)


def _is_deduction_processed(db: Session, user_id: int, date_utc: date) -> bool:
    """True if deduction was already processed for this user on date_utc (prevents double-charge)."""
    snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
    if not snap:
        return False
    last_date = getattr(snap, "last_deduction_processed_date", None)
    if last_date is None:
        return False
    if hasattr(last_date, "isoformat"):
        return last_date == date_utc
    return last_date == date_utc


def _mark_deduction_processed(db: Session, user_id: int, date_utc: date) -> None:
    """Mark deduction as processed for this user/date (post-10:30 or post-11:15)."""
    snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
    if not snap:
        return
    if hasattr(snap, "deduction_processed"):
        snap.deduction_processed = True
    if hasattr(snap, "last_deduction_processed_date"):
        snap.last_deduction_processed_date = date_utc
    db.commit()
    logger.info("trace_id=%s | Marked deduction_processed for user_id=%s date_utc=%s", get_trace_id(), user_id, date_utc)


def _reconcile_cached_vs_fresh(db: Session, user_id: int, date_utc: date, dry_run: bool = False) -> bool:
    """
    Compare 09:00 cached daily_gross vs fresh (post-restoration) data. Refund if overcharged, deduct if undercharged.
    Auto-run during 11:15 catch-up. When dry_run=True: log would-be deduction/refund, no DB write; return False if
    would result in negative balance (manual review needed).
    Returns True on success or no-op, False if dry run would fail (e.g. negative balance).
    """
    snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
    token_row = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
    if not snap or not token_row:
        return True
    cached = float(getattr(snap, "last_cached_daily_gross_usd", None) or 0)
    if cached <= 0:
        return True
    fresh = float(getattr(snap, "daily_gross_profit_usd", None) or 0)
    diff_usd = fresh - cached
    if abs(diff_usd) < 1e-9:
        if not dry_run and hasattr(snap, "last_cached_daily_gross_usd"):
            snap.last_cached_daily_gross_usd = None
            db.commit()
        return True
    before = token_ledger_svc.get_tokens_remaining(db, user_id)
    if diff_usd > 0:
        # Undercharged: deduct extra
        after = max(0.0, before - diff_usd)
        log_msg = "Reconciliation: Charged extra %.6f tokens (undercharged)" % diff_usd
        if dry_run:
            logger.info(
                "trace_id=%s | user_id=%s date_utc=%s [DRY RUN] %s balance_before=%.2f would_be_after=%.2f",
                get_trace_id(), user_id, date_utc, log_msg, before, after,
            )
            if before - diff_usd < -1e-9:
                logger.warning(
                    "trace_id=%s | user_id=%s dry run would result in negative balance (before=%.2f deduct=%.6f)",
                    get_trace_id(), user_id, before, diff_usd,
                )
                return False
            return True
        token_ledger_svc.deduct_tokens(db, user_id, diff_usd)
        after = before - diff_usd
    else:
        # Overcharged: do not auto-add tokens; only clear cache and log. Refunds are via admin rollback or scripts only.
        after = before
        log_msg = "Reconciliation: overcharged %.6f tokens (no auto-refund; use admin rollback if needed)" % abs(diff_usd)
        if dry_run:
            logger.info(
                "trace_id=%s | user_id=%s date_utc=%s [DRY RUN] %s balance_before=%.2f",
                get_trace_id(), user_id, date_utc, log_msg, before,
            )
            return True
        logger.warning(
            "trace_id=%s | user_id=%s date_utc=%s %s balance=%.2f",
            get_trace_id(), user_id, date_utc, log_msg, before,
        )
    if hasattr(snap, "last_cached_daily_gross_usd"):
        snap.last_cached_daily_gross_usd = None
    db.commit()
    after_actual = token_ledger_svc.get_tokens_remaining(db, user_id)
    logger.info("trace_id=%s | user_id=%s date_utc=%s %s balance_before=%.2f balance_after=%.2f", get_trace_id(), user_id, date_utc, log_msg, before, after_actual)
    return True


async def _apply_09_00_cache_before_deduction(db: Session, redis: Any) -> None:
    """
    If 10:00 fetch failed (invalid/deleted key), fill snapshot from 09:00 cached ledger so 10:30 deduction can run.
    Uses start_ms from cache (so works even if vault was deleted after 09:00).
    Log: "10:30 UTC: Processed deduction for {email} using 09:00 UTC cached data".
    """
    today_utc = datetime.utcnow().date()
    start_today_ms = int(datetime(today_utc.year, today_utc.month, today_utc.day).timestamp() * 1000)
    end_today_ms = start_today_ms + 86400 * 1000 - 1
    end_ms = int(datetime.utcnow().timestamp() * 1000)
    rows = (
        db.query(models.UserTokenBalance, models.UserProfitSnapshot, models.User)
        .join(models.UserProfitSnapshot, models.UserTokenBalance.user_id == models.UserProfitSnapshot.user_id)
        .join(models.User, models.User.id == models.UserTokenBalance.user_id)
        .filter(
            (models.UserProfitSnapshot.daily_gross_profit_usd == 0) |
            (models.UserProfitSnapshot.daily_gross_profit_usd.is_(None)),
        )
        .all()
    )
    for token_row, snap, user in rows:
        user_id = token_row.user_id
        email = getattr(user, "email", None) or ""
        cached = await ledger_cache_svc.get_ledger_cache_with_fallback(redis, db, user_id, today_utc)
        if not cached:
            continue
        entries, start_ms, db_fallback_daily = cached[0], cached[1], (cached[2] if len(cached) > 2 else None)
        if db_fallback_daily is not None:
            # Redis down – used DB last_cached_daily_gross_usd for deduction
            daily_gross = float(db_fallback_daily)
            if hasattr(snap, "daily_gross_profit_usd"):
                snap.daily_gross_profit_usd = round(daily_gross, 2)
            if hasattr(snap, "last_daily_snapshot_date"):
                snap.last_daily_snapshot_date = today_utc
            if hasattr(snap, "updated_at"):
                snap.updated_at = datetime.utcnow()
            if hasattr(snap, "invalid_key_days"):
                snap.invalid_key_days = (snap.invalid_key_days or 0) + 1
            db.commit()
            logger.info(
                "trace_id=%s | 10:30 UTC: Processed deduction for %s using DB cache (Redis down) last_cached_daily_gross_usd=%.6f",
                get_trace_id(), email or user_id, daily_gross,
            )
            await _notify_user_cached_deduction(email or str(user_id), round(daily_gross, 2))
            continue
        if not entries:
            continue
        start_ms = start_ms or 0
        currencies_in_entries = {str(e[1]).strip() for e in entries if isinstance(e, (list, tuple)) and len(e) > 1 and e[1]}
        usd_prices = _fetch_ticker_prices(currencies_in_entries) if currencies_in_entries else {}
        gross, fees = _gross_and_fees_from_ledger_entries(entries, start_ms=start_ms, end_ms=end_ms, usd_prices=usd_prices)
        daily_gross, _ = _gross_and_fees_from_ledger_entries(entries, start_ms=start_today_ms, end_ms=end_today_ms, usd_prices=usd_prices)
        snap.gross_profit_usd = round(gross, 2)
        snap.net_profit_usd = round(gross - fees, 2)
        snap.bitfinex_fee_usd = round(fees, 2)
        if hasattr(snap, "daily_gross_profit_usd"):
            snap.daily_gross_profit_usd = round(daily_gross, 2)
        if hasattr(snap, "last_daily_snapshot_date"):
            snap.last_daily_snapshot_date = today_utc
        if hasattr(snap, "last_cached_daily_gross_usd"):
            snap.last_cached_daily_gross_usd = round(daily_gross, 6)
        if hasattr(snap, "updated_at"):
            snap.updated_at = datetime.utcnow()
        if hasattr(snap, "invalid_key_days"):
            snap.invalid_key_days = (snap.invalid_key_days or 0) + 1
        db.commit()
        logger.info(
            "trace_id=%s | 10:30 UTC: Processed deduction for %s using 09:00 UTC cached data (API key invalid/deleted)",
            get_trace_id(), email or user_id,
        )
        await _notify_user_cached_deduction(email or str(user_id), round(daily_gross, 2))


async def _run_daily_token_deduction_scheduler() -> None:
    """
    At 10:30 UTC daily: final fetch for users still without daily_gross (Bitfinex data can be late until 10:30),
    then 09:00 cache fill, then deduction. Deduction uses stored snapshot only after this.
    """
    while True:
        wait_sec = _get_next_1030_utc_wait_sec()
        set_trace_id(generate_trace_id())
        logger.info("trace_id=%s | Next daily token deduction at 10:30 UTC in %.0fs", get_trace_id(), wait_sec)
        await asyncio.sleep(wait_sec)
        logger.info("Daily token deduction: scheduler woke at ~10:30 UTC; starting deduction run.")
        last_error: Optional[str] = None
        for attempt in range(DEDUCTION_MAX_RETRIES):
            db = database.SessionLocal()
            try:
                # Final fetch for users whose snapshot is not for today (covers 10:00 missed/failed, new users, stale snapshot).
                try:
                    today_utc = datetime.utcnow().date()
                    user_ids_with_vault = [
                        row[0]
                        for row in db.query(models.User.id)
                        .join(models.APIVault, models.User.id == models.APIVault.user_id)
                        .distinct()
                        .all()
                    ]
                    test_uid = _get_scheduler_test_user_id()
                    if test_uid is not None:
                        user_ids_with_vault = [u for u in user_ids_with_vault if u == test_uid]
                    need_fetch: List[int] = []
                    for uid in user_ids_with_vault:
                        snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == uid).first()
                        if snap is None:
                            need_fetch.append(uid)
                        else:
                            snapshot_date = getattr(snap, "last_daily_snapshot_date", None)
                            if snapshot_date is None or snapshot_date != today_utc:
                                need_fetch.append(uid)
                    if need_fetch:
                        logger.info("trace_id=%s | 10:30 UTC final fetch for %s user(s) with snapshot not for today", get_trace_id(), len(need_fetch))
                        _final_sem = asyncio.Semaphore(FETCH_CONCURRENCY)

                        async def _final_fetch_one(uid: int) -> None:
                            async with _final_sem:
                                await asyncio.sleep(DELAY_BETWEEN_USERS_SEC)
                                db_u = database.SessionLocal()
                                try:
                                    success, _, _ = await _daily_10_00_fetch_and_save(uid, db_u, accept_fresh_data=True)
                                    if success:
                                        logger.info("trace_id=%s | 10:30 final fetch user_id=%s success", get_trace_id(), uid)
                                finally:
                                    db_u.close()

                        await asyncio.gather(*[_final_fetch_one(uid) for uid in need_fetch], return_exceptions=True)
                except Exception as e:
                    logger.warning("10:30 pre-deduction final fetch: %s", e)
                try:
                    redis = await asyncio.wait_for(get_redis(), timeout=REDIS_CONNECT_TIMEOUT)
                    await _apply_09_00_cache_before_deduction(db, redis)
                except Exception as e:
                    logger.warning("09:00 cache fallback before deduction: %s", e)
                # Expire so we see snapshot after final fetch (db_u commits); same safety as manual trigger.
                db.expire_all()
                mult = _get_deduction_multiplier(db)
                log_entries, err = run_daily_token_deduction(db, deduction_multiplier=mult)
                if err:
                    last_error = err
                    logger.warning("Daily token deduction attempt %d/%d failed: %s", attempt + 1, DEDUCTION_MAX_RETRIES, err)
                    if attempt < DEDUCTION_MAX_RETRIES - 1:
                        await asyncio.sleep(DEDUCTION_RETRY_INTERVAL_SEC)
                    continue
                for entry in log_entries:
                    logger.info(
                        "token_deduction user_id=%s gross_profit=%s tokens_deducted=%s new_tokens_remaining=%s ts=%s",
                        entry["user_id"],
                        entry["gross_profit"],
                        entry["tokens_deducted"],
                        entry["tokens_remaining_after"],
                        entry["timestamp"],
                    )
                with _deduction_logs_lock:
                    for e in log_entries:
                        _deduction_logs.append(e)
                        while len(_deduction_logs) > DEDUCTION_LOGS_MAX:
                            _deduction_logs.pop(0)
                if not log_entries:
                    logger.info("Daily token deduction: no users to deduct")
                last_error = None
                break
            except Exception as e:
                last_error = str(e)
                logger.exception("Daily token deduction attempt %d/%d error: %s", attempt + 1, DEDUCTION_MAX_RETRIES, e)
                if attempt < DEDUCTION_MAX_RETRIES - 1:
                    await asyncio.sleep(DEDUCTION_RETRY_INTERVAL_SEC)
            finally:
                db.close()
        if last_error:
            alert_msg = f"Daily token deduction (10:30 UTC) failed after {DEDUCTION_MAX_RETRIES} retries: {last_error}"
            logger.error(alert_msg)
            await _alert_admins_deduction_failure(alert_msg)


def _get_next_1115_utc_wait_sec() -> float:
    """Seconds until next 11:15 UTC (catch-up deduction for restored keys)."""
    return _get_next_utc_wait_sec(CATCHUP_DEDUCTION_UTC_HOUR, CATCHUP_DEDUCTION_UTC_MINUTE)


def _get_next_1200_utc_wait_sec() -> float:
    """Seconds until next 12:00 UTC (late fee application)."""
    return _get_next_utc_wait_sec(LATE_FEE_UTC_HOUR, LATE_FEE_UTC_MINUTE)


def _get_next_2300_utc_wait_sec() -> float:
    """Seconds until next 23:00 UTC (reconciliation sweep for key restored post-11:15)."""
    return _get_next_utc_wait_sec(RECONCILIATION_UTC_HOUR, RECONCILIATION_UTC_MINUTE)


def _late_fee_pct_for_days(invalid_days: int) -> float:
    """Incremental late fee: day 3 = 5%%, day 4 = 10%%, …; capped at MAX_LATE_FEE_PCT (25%%)."""
    if invalid_days < LATE_FEE_DAYS:
        return 0.0
    raw = (invalid_days - 2) * LATE_FEE_PCT_PER_DAY
    return min(raw, MAX_LATE_FEE_PCT)


async def _run_late_fee_scheduler() -> None:
    """12:00 UTC: apply incremental late fee for users with invalid_key_days >= LATE_FEE_DAYS. Do NOT reset invalid_key_days."""
    while True:
        wait_sec = _get_next_1200_utc_wait_sec()
        set_trace_id(generate_trace_id())
        logger.info(
            "trace_id=%s | Next 12:00 UTC late fee run in %.0fs",
            get_trace_id(), wait_sec,
        )
        await asyncio.sleep(wait_sec)
        db = database.SessionLocal()
        try:
            set_trace_id(generate_trace_id())
            rows = (
                db.query(models.UserProfitSnapshot, models.UserTokenBalance, models.User)
                .join(models.UserTokenBalance, models.UserProfitSnapshot.user_id == models.UserTokenBalance.user_id)
                .join(models.User, models.User.id == models.UserTokenBalance.user_id)
                .filter(models.User.status != "dormant")
                .all()
            )
            for snap, token_row, user in rows:
                invalid_days = getattr(snap, "invalid_key_days", None) or 0
                if invalid_days < LATE_FEE_DAYS:
                    continue
                base_fee = float(getattr(snap, "daily_gross_profit_usd", None) or 0)
                if base_fee <= 0:
                    base_fee = 0.01  # minimum so we still apply late fee
                fee_pct = _late_fee_pct_for_days(invalid_days)
                if (invalid_days - 2) * LATE_FEE_PCT_PER_DAY > MAX_LATE_FEE_PCT:
                    logger.info(
                        "trace_id=%s | User %s – late fee capped at 25%% (invalid_key_days=%s)",
                        get_trace_id(), snap.user_id, invalid_days,
                    )
                total_fee = base_fee * (1 + fee_pct)
                user_id = snap.user_id
                email = getattr(user, "email", None) or ""
                before = token_ledger_svc.get_tokens_remaining(db, user_id)
                after = token_ledger_svc.deduct_tokens(db, user_id, total_fee)
                token_row.updated_at = datetime.utcnow()
                # Do NOT reset invalid_key_days; only reset when user restores API key (POST /api/keys)
                db.commit()
                logger.info(
                    "trace_id=%s | 12:00 UTC: Late fee applied user_id=%s email=%s base=%.4f pct=%.0f%% total=%.4f tokens_after=%.2f",
                    get_trace_id(), user_id, email, base_fee, fee_pct * 100, total_fee, after,
                )
                logger.info(
                    "trace_id=%s | User %s – invalid_key_days = %s (key still invalid post-late fee)",
                    get_trace_id(), user_id, invalid_days,
                )
                await _alert_admins_deduction_failure(
                    f"Late fee ({fee_pct*100:.0f}%%) applied – User: {email} (ID: {user_id}), "
                    f"invalid API key for {invalid_days}+ days, deducted {total_fee:.4f} tokens."
                )
        except Exception as e:
            logger.exception("trace_id=%s | Late fee scheduler error: %s", get_trace_id(), e)
        finally:
            db.close()


async def _run_2300_reconciliation_scheduler() -> None:
    """
    23:00 UTC: reconciliation sweep for users who restored key after 11:15 (post-catch-up).
    Runs _reconcile_cached_vs_fresh and marks reconciliation_completed = True.
    """
    while True:
        wait_sec = _get_next_2300_utc_wait_sec()
        set_trace_id(generate_trace_id())
        logger.info(
            "trace_id=%s | Next 23:00 UTC reconciliation sweep in %.0fs",
            get_trace_id(), wait_sec,
        )
        await asyncio.sleep(wait_sec)
        today_utc = datetime.utcnow().date()
        cutoff_1115 = datetime(today_utc.year, today_utc.month, today_utc.day, 11, 15, 0)
        cutoff_ts = cutoff_1115.timestamp()
        db = database.SessionLocal()
        try:
            set_trace_id(generate_trace_id())
            # Users with key restored after 11:15 today and not yet reconciled (reconciliation_completed = False)
            snap_model = models.UserProfitSnapshot
            if not hasattr(snap_model, "reconciliation_completed"):
                rows = []
            else:
                rows = (
                    db.query(models.User.id, models.User.email, models.APIVault.keys_updated_at)
                    .join(models.APIVault, models.APIVault.user_id == models.User.id)
                    .join(models.UserProfitSnapshot, models.UserProfitSnapshot.user_id == models.User.id)
                    .filter(snap_model.reconciliation_completed == False)
                    .filter(models.User.status != "dormant")
                    .all()
                )
            # Filter to users with keys_updated_at after 11:15 today
            to_process = []
            for r in rows:
                user_id, email, keys_updated_at = r[0], r[1], r[2]
                if keys_updated_at is None:
                    continue
                try:
                    kua_ts = keys_updated_at.timestamp() if hasattr(keys_updated_at, "timestamp") else 0
                except Exception:
                    continue
                if kua_ts >= cutoff_ts:
                    to_process.append((user_id, email, keys_updated_at))
            total_batches = (len(to_process) + RECONCILIATION_BATCH_SIZE - 1) // RECONCILIATION_BATCH_SIZE if to_process else 0
            for batch_num, batch_start in enumerate(range(0, len(to_process), RECONCILIATION_BATCH_SIZE), start=1):
                batch = to_process[batch_start : batch_start + RECONCILIATION_BATCH_SIZE]
                for user_id, email, keys_updated_at in batch:
                    ok = _reconcile_cached_vs_fresh(db, user_id, today_utc, dry_run=True)
                    if not ok:
                        logger.warning(
                            "trace_id=%s | 23:00 reconciliation dry run failed for user %s – manual review needed",
                            get_trace_id(), user_id,
                        )
                        await _alert_admins_deduction_failure(
                            f"23:00 reconciliation dry run failed for user {user_id} – manual review needed"
                        )
                        continue
                    _reconcile_cached_vs_fresh(db, user_id, today_utc, dry_run=False)
                    snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
                    if snap and hasattr(snap, "reconciliation_completed"):
                        snap.reconciliation_completed = True
                    db.commit()
                    logger.info(
                        "trace_id=%s | 23:00 UTC reconciliation: Processed user %s (key restored at %s)",
                        get_trace_id(), user_id, keys_updated_at,
                    )
                logger.info(
                    "trace_id=%s | 23:00 reconciliation – batch %s/%s processed (%s users)",
                    get_trace_id(), batch_num, total_batches, len(batch),
                )
                if batch_num < total_batches:
                    await asyncio.sleep(1)
        except Exception as e:
            logger.exception("trace_id=%s | 23:00 reconciliation scheduler error: %s", get_trace_id(), e)
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Scenario A: 02:00 UTC – Stale API key cleanup (zombie accounts)
# ---------------------------------------------------------------------------
def _get_next_0200_utc_wait_sec() -> float:
    now = datetime.utcnow()
    target = now.replace(hour=2, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def _run_stale_key_cleanup_scheduler() -> None:
    """02:00 UTC daily: wipe API keys for zombie accounts."""
    while True:
        wait_sec = _get_next_0200_utc_wait_sec()
        logger.info("Next stale-key cleanup at 02:00 UTC in %.0fs", wait_sec)
        await asyncio.sleep(wait_sec)
        db = database.SessionLocal()
        try:
            invalid_days_threshold = int(_get_setting(db, "stale_key_invalid_days", "30"))
            inactive_days_threshold = int(_get_setting(db, "stale_key_inactive_days", "90"))
            cutoff_date = datetime.utcnow() - timedelta(days=inactive_days_threshold)
            today_utc = datetime.utcnow().date()

            # Users with invalid keys for N+ consecutive days
            stale_invalid = (
                db.query(models.User)
                .join(models.APIVault, models.APIVault.user_id == models.User.id)
                .join(models.UserProfitSnapshot, models.UserProfitSnapshot.user_id == models.User.id)
                .filter(models.UserProfitSnapshot.invalid_key_days >= invalid_days_threshold)
                .all()
            )

            # Users with vault but inactive for N+ days (bot stopped, no recent login or snapshot)
            stale_inactive = (
                db.query(models.User)
                .join(models.APIVault, models.APIVault.user_id == models.User.id)
                .filter(models.User.bot_status == "stopped")
                .filter(
                    (models.User.last_login_at.is_(None)) | (models.User.last_login_at < cutoff_date)
                )
                .all()
            )

            seen_ids: set = set()
            wiped_count = 0
            all_stale = stale_invalid + stale_inactive
            for user in all_stale:
                if user.id in seen_ids:
                    continue
                seen_ids.add(user.id)
                vault = db.query(models.APIVault).filter(models.APIVault.user_id == user.id).first()
                if not vault:
                    continue
                db.delete(vault)
                # Reset invalid_key_days
                snap = db.query(models.UserProfitSnapshot).filter(
                    models.UserProfitSnapshot.user_id == user.id
                ).first()
                if snap and hasattr(snap, "invalid_key_days"):
                    snap.invalid_key_days = 0
                # Stop bot if somehow still running
                if user.bot_status != "stopped":
                    user.bot_status = "stopped"
                    user.bot_desired_state = "stopped"
                # In-app notification
                db.add(models.AdminNotification(
                    title="API Keys Removed",
                    content="Your API keys were removed due to prolonged inactivity or invalid credentials. Re-add them to resume lending.",
                    type="warning",
                    target_user_id=user.id,
                ))
                wiped_count += 1
                logger.info("stale_key_cleanup wiped vault for user_id=%s email=%s", user.id, user.email)

            if wiped_count > 0:
                db.commit()
                _admin_audit("system", "stale_key_cleanup", {"wiped_count": wiped_count, "date": today_utc.isoformat()})
            logger.info("stale_key_cleanup done: wiped=%d (invalid_threshold=%d, inactive_threshold=%d)", wiped_count, invalid_days_threshold, inactive_days_threshold)
        except Exception as e:
            logger.exception("stale_key_cleanup error: %s", e)
            db.rollback()
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Scenario C: Sunday 03:00 UTC – Weekly data cleanup (DB bloat prevention)
# ---------------------------------------------------------------------------
def _get_next_sunday_0300_utc_wait_sec() -> float:
    now = datetime.utcnow()
    days_until_sunday = (6 - now.weekday()) % 7
    if days_until_sunday == 0 and (now.hour > 3 or (now.hour == 3 and now.minute > 0)):
        days_until_sunday = 7
    target = (now + timedelta(days=days_until_sunday)).replace(hour=3, minute=0, second=0, microsecond=0)
    return max(0, (target - now).total_seconds())


def _run_cleanup_queries(db) -> dict:
    """Execute cleanup queries and return counts. Does NOT commit — caller commits."""
    deduction_log_days = int(_get_setting(db, "cleanup_deduction_log_days", "180"))
    token_ledger_days = int(_get_setting(db, "cleanup_token_ledger_days", "365"))
    dormant_days = int(_get_setting(db, "cleanup_dormant_days", "180"))
    now = datetime.utcnow()

    # 1. Prune old deduction logs
    deduction_cutoff = now - timedelta(days=deduction_log_days)
    d1 = db.execute(
        text("DELETE FROM deduction_log WHERE created_at < :cutoff"),
        {"cutoff": deduction_cutoff},
    )
    deduction_pruned = d1.rowcount

    # 2. Prune old token ledger entries for zeroed-out stopped users with no vault
    ledger_cutoff = now - timedelta(days=token_ledger_days)
    d2 = db.execute(
        text("""
            DELETE FROM token_ledger WHERE id IN (
                SELECT tl.id FROM token_ledger tl
                JOIN user_token_balance utb ON utb.user_id = tl.user_id
                JOIN users u ON u.id = tl.user_id
                LEFT JOIN api_vault av ON av.user_id = tl.user_id
                WHERE tl.created_at < :cutoff
                  AND utb.tokens_remaining <= 0
                  AND u.bot_status = 'stopped'
                  AND av.user_id IS NULL
            )
        """),
        {"cutoff": ledger_cutoff},
    )
    ledger_pruned = d2.rowcount

    # 3. Prune stale profit snapshots for users with no vault and old snapshot
    snapshot_cutoff = (now - timedelta(days=90)).date()
    d3 = db.execute(
        text("""
            DELETE FROM user_profit_snapshot WHERE user_id IN (
                SELECT ups.user_id FROM user_profit_snapshot ups
                LEFT JOIN api_vault av ON av.user_id = ups.user_id
                WHERE av.user_id IS NULL
                  AND (ups.last_daily_snapshot_date IS NULL OR ups.last_daily_snapshot_date < :cutoff)
            )
        """),
        {"cutoff": snapshot_cutoff},
    )
    snapshots_pruned = d3.rowcount

    # 4. Mark dormant users
    dormant_cutoff = now - timedelta(days=dormant_days)
    d4 = db.execute(
        text("""
            UPDATE users SET status = 'dormant'
            WHERE status = 'active'
              AND id NOT IN (SELECT user_id FROM api_vault)
              AND created_at < :cutoff
              AND (last_login_at IS NULL OR last_login_at < :cutoff)
              AND id IN (
                  SELECT user_id FROM user_token_balance WHERE tokens_remaining <= 0
              )
        """),
        {"cutoff": dormant_cutoff},
    )
    dormant_marked = d4.rowcount

    return {
        "deduction_logs_pruned": deduction_pruned,
        "token_ledger_pruned": ledger_pruned,
        "snapshots_pruned": snapshots_pruned,
        "dormant_users_marked": dormant_marked,
    }


def _run_cleanup_preview(db) -> dict:
    """Count what WOULD be cleaned up without making changes."""
    deduction_log_days = int(_get_setting(db, "cleanup_deduction_log_days", "180"))
    token_ledger_days = int(_get_setting(db, "cleanup_token_ledger_days", "365"))
    dormant_days = int(_get_setting(db, "cleanup_dormant_days", "180"))
    now = datetime.utcnow()

    deduction_cutoff = now - timedelta(days=deduction_log_days)
    ledger_cutoff = now - timedelta(days=token_ledger_days)
    snapshot_cutoff = (now - timedelta(days=90)).date()
    dormant_cutoff = now - timedelta(days=dormant_days)

    r1 = db.execute(text("SELECT COUNT(*) FROM deduction_log WHERE created_at < :cutoff"), {"cutoff": deduction_cutoff}).scalar()
    r2 = db.execute(text("""
        SELECT COUNT(*) FROM token_ledger tl
        JOIN user_token_balance utb ON utb.user_id = tl.user_id
        JOIN users u ON u.id = tl.user_id
        LEFT JOIN api_vault av ON av.user_id = tl.user_id
        WHERE tl.created_at < :cutoff AND utb.tokens_remaining <= 0 AND u.bot_status = 'stopped' AND av.user_id IS NULL
    """), {"cutoff": ledger_cutoff}).scalar()
    r3 = db.execute(text("""
        SELECT COUNT(*) FROM user_profit_snapshot ups
        LEFT JOIN api_vault av ON av.user_id = ups.user_id
        WHERE av.user_id IS NULL AND (ups.last_daily_snapshot_date IS NULL OR ups.last_daily_snapshot_date < :cutoff)
    """), {"cutoff": snapshot_cutoff}).scalar()
    r4 = db.execute(text("""
        SELECT COUNT(*) FROM users u
        WHERE u.status = 'active'
          AND u.id NOT IN (SELECT user_id FROM api_vault)
          AND u.created_at < :cutoff
          AND (u.last_login_at IS NULL OR u.last_login_at < :cutoff)
          AND u.id IN (SELECT user_id FROM user_token_balance WHERE tokens_remaining <= 0)
    """), {"cutoff": dormant_cutoff}).scalar()

    # Stale key counts
    invalid_days_threshold = int(_get_setting(db, "stale_key_invalid_days", "30"))
    inactive_days_threshold = int(_get_setting(db, "stale_key_inactive_days", "90"))
    inactive_cutoff = now - timedelta(days=inactive_days_threshold)
    r5_invalid = db.execute(text("""
        SELECT COUNT(*) FROM api_vault av
        JOIN user_profit_snapshot ups ON ups.user_id = av.user_id
        WHERE ups.invalid_key_days >= :threshold
    """), {"threshold": invalid_days_threshold}).scalar()
    r5_inactive = db.execute(text("""
        SELECT COUNT(*) FROM api_vault av
        JOIN users u ON u.id = av.user_id
        WHERE u.bot_status = 'stopped'
          AND (u.last_login_at IS NULL OR u.last_login_at < :cutoff)
    """), {"cutoff": inactive_cutoff}).scalar()

    return {
        "deduction_logs_to_prune": r1 or 0,
        "token_ledger_to_prune": r2 or 0,
        "snapshots_to_prune": r3 or 0,
        "dormant_users_to_mark": r4 or 0,
        "stale_keys_invalid": r5_invalid or 0,
        "stale_keys_inactive": r5_inactive or 0,
    }


async def _run_weekly_data_cleanup_scheduler() -> None:
    """Sunday 03:00 UTC: prune old logs, mark dormant users."""
    while True:
        wait_sec = _get_next_sunday_0300_utc_wait_sec()
        logger.info("Next weekly data cleanup (Sunday 03:00 UTC) in %.0fs", wait_sec)
        await asyncio.sleep(wait_sec)
        db = database.SessionLocal()
        try:
            result = _run_cleanup_queries(db)
            db.commit()
            _admin_audit("system", "weekly_cleanup", result)
            logger.info("weekly_cleanup done: %s", result)
        except Exception as e:
            logger.exception("weekly_cleanup error: %s", e)
            db.rollback()
        finally:
            db.close()


async def _run_11_15_catchup_deduction_scheduler() -> None:
    """
    11:15 UTC: catch-up deduction for users who had key restored after 10:30 (had failed at 10:30).
    Re-fetch ledger with restored key, then run deduction for those users.
    """
    while True:
        wait_sec = _get_next_1115_utc_wait_sec()
        set_trace_id(generate_trace_id())
        logger.info("trace_id=%s | Next 11:15 UTC catch-up deduction in %.0fs", get_trace_id(), wait_sec)
        await asyncio.sleep(wait_sec)
        today = datetime.utcnow().date()
        cutoff_1030 = datetime(today.year, today.month, today.day, 10, 30, 0)
        db = database.SessionLocal()
        try:
            rows = (
                db.query(models.User.id, models.User.email, models.APIVault.keys_updated_at)
                .join(models.APIVault, models.APIVault.user_id == models.User.id)
                .join(models.UserProfitSnapshot, models.UserProfitSnapshot.user_id == models.User.id)
                .filter(
                    (models.UserProfitSnapshot.daily_gross_profit_usd == 0) |
                    (models.UserProfitSnapshot.daily_gross_profit_usd.is_(None)),
                )
                .all()
            )
            cutoff_ts = cutoff_1030.timestamp()
            restored = []
            for r in rows:
                if _is_deduction_processed(db, r[0], today):
                    logger.info("trace_id=%s | 11:15 UTC: Skipping user_id=%s – deduction already processed for today (no double-charge)", get_trace_id(), r[0])
                    continue
                kua = r[2]
                if kua is None:
                    continue
                try:
                    kua_ts = kua.timestamp() if hasattr(kua, "timestamp") else 0
                except Exception:
                    continue
                if kua_ts >= cutoff_ts:
                    restored.append((r[0], r[1] or ""))
            if not restored:
                continue
            for uid, email in restored:
                try:
                    success, _, err = await _daily_10_00_fetch_and_save(uid, db)
                    if success:
                        _reconcile_cached_vs_fresh(db, uid, today)
                        snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == uid).first()
                        if snap and hasattr(snap, "invalid_key_days"):
                            snap.invalid_key_days = 0
                        db.commit()
                        logger.info(
                            "trace_id=%s | 11:15 UTC: Catch-up deduction for %s (API key restored – deducted using fresh ledger)",
                            get_trace_id(), email or uid,
                        )
                except Exception as e:
                    logger.warning("11:15 catch-up user_id=%s: %s", uid, e)
            restored_ids = [uid for uid, _ in restored]
            db.close()
            db2 = database.SessionLocal()
            try:
                mult = _get_deduction_multiplier(db2)
                log_entries, err = run_daily_token_deduction(db2, user_ids=restored_ids, deduction_multiplier=mult)
                if err:
                    logger.warning("11:15 catch-up run_daily_token_deduction: %s", err)
                else:
                    with _deduction_logs_lock:
                        for e in log_entries:
                            _deduction_logs.append(e)
                            while len(_deduction_logs) > DEDUCTION_LOGS_MAX:
                                _deduction_logs.pop(0)
            finally:
                db2.close()
        finally:
            try:
                db.close()
            except Exception:
                pass


async def _notify_user_cached_deduction(user_email: str, cached_amount: float) -> None:
    """Notify user when deduction used 09:00 UTC cached data (in-app + optional email)."""
    msg = (
        f"Your daily fee was processed using cached data (API key invalid). "
        f"We will reconcile automatically when you restore your key."
    )
    logger.info("User notification (cached deduction): email=%s amount=%.2f msg=%s", user_email, cached_amount, msg[:80])
    # In-app: store in admin_notifications for target_user_id if we have user_id (caller can pass later)
    # Email: optional integration; for now logging only


async def _alert_admins_deduction_failure(message: str) -> None:
    """Alert admins (e.g. Slack webhook). Set DEDUCTION_ALERT_WEBHOOK_URL in env for Slack."""
    webhook_url = os.getenv("DEDUCTION_ALERT_WEBHOOK_URL", "").strip()
    if webhook_url:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                await session.post(
                    webhook_url,
                    json={"text": f"[bifinexbot] {message}"},
                    timeout=aiohttp.ClientTimeout(total=10),
                )
        except Exception as e:
            logger.warning("Failed to send deduction alert webhook: %s", e)
    # Always recorded in API failures for admin panel
    await _record_api_failure("daily_token_deduction", None, message)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: verify Redis (NEW Upstash server) is reachable
    redis_url = os.getenv("REDIS_URL", "")
    if redis_url.strip().lower().startswith("rediss://"):
        try:
            pool = await asyncio.wait_for(get_redis(), timeout=REDIS_CONNECT_TIMEOUT)
            await pool.ping()
            host = _redis_host_from_url(redis_url)
            logger.info("Connected to Redis server at %s (queue + deduction)", host)
        except Exception as e:
            logger.warning("Redis startup check failed (queue may be unavailable): %s", e)
    # Debug: confirm backend DB sees user_profit_snapshot for user 2 (same SELECT as get_lending_stats)
    try:
        db = database.SessionLocal()
        try:
            row = db.execute(
                text("SELECT gross_profit_usd FROM user_profit_snapshot WHERE user_id = :uid"),
                {"uid": 2},
            ).fetchone()
            val = float(row[0]) if row and row[0] is not None else None
            logger.info("Startup check user_profit_snapshot user_id=2: %s", val if val is not None else "no row")
        finally:
            db.close()
    except Exception as e:
        logger.warning("Startup check user_profit_snapshot failed: %s", e)
    # Seed ranking_snapshot and referral_gain_snapshot if empty (so leaderboard has data before first 10:00 UTC run)
    try:
        db = database.SessionLocal()
        try:
            n = db.query(models.RankingSnapshot).count()
            if n == 0:
                _refresh_ranking_snapshot(db)
            n_ref = db.query(models.ReferralGainSnapshot).count()
            if n_ref == 0:
                _refresh_referral_gain_snapshot(db)
        finally:
            db.close()
    except Exception as e:
        logger.warning("Startup ranking/referral_gain snapshot seed failed: %s", e)
    # Ensure token_ledger table exists (so admin and user token-add logs work)
    try:
        db = database.SessionLocal()
        try:
            r = db.execute(
                text("SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'token_ledger'")
            ).fetchone()
            if not r:
                db.execute(text("""
                    CREATE TABLE token_ledger (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id),
                        activity_type VARCHAR(16) NOT NULL,
                        amount DOUBLE PRECISION NOT NULL,
                        reason VARCHAR(64) NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        metadata JSONB
                    )
                """))
                db.execute(text("CREATE INDEX idx_token_ledger_user_id_created_at ON token_ledger(user_id, created_at)"))
                db.commit()
                logger.info("Startup: created token_ledger table")
            else:
                logger.info("Startup: token_ledger table exists")
        finally:
            db.close()
    except Exception as e:
        logger.warning("Startup token_ledger ensure failed: %s", e)
    # Ensure last_login_at column exists on users table
    try:
        db = database.SessionLocal()
        try:
            db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP"))
            db.commit()
            logger.info("Startup: users.last_login_at column ensured")
        finally:
            db.close()
    except Exception as e:
        logger.warning("Startup last_login_at ensure failed: %s", e)
    # Production safety: warn loudly if dev endpoints are enabled
    if os.getenv("ALLOW_DEV_CONNECT") == "1":
        logger.warning(
            "*** ALLOW_DEV_CONNECT=1 is set. Dev endpoints (/dev/*) are ENABLED. "
            "Unset this variable in production! ***"
        )
    if os.getenv("STRIPE_WEBHOOK_DEBUG") == "1":
        logger.warning("*** STRIPE_WEBHOOK_DEBUG=1 is set. Disable in production. ***")
    # 09:00 UTC ledger cache; 10:00 API fetch; 10:30 deduction; 11:15 catch-up; 12:00 late fee; 23:00 reconciliation
    logger.info(
        "Auto token deduction runs only at 10:30 UTC when the backend is running. "
        "If the server is off at 10:30 UTC, deduction will not run; use Admin Panel → Deduction → Manual trigger or POST /admin/deduction/trigger to run it."
    )
    ledger_cache_task = asyncio.create_task(_run_09_00_ledger_cache_scheduler())
    scheduler_task = asyncio.create_task(_run_daily_gross_profit_scheduler())
    deduction_task = asyncio.create_task(_run_daily_token_deduction_scheduler())
    catchup_task = asyncio.create_task(_run_11_15_catchup_deduction_scheduler())
    late_fee_task = asyncio.create_task(_run_late_fee_scheduler())
    reconciliation_2300_task = asyncio.create_task(_run_2300_reconciliation_scheduler())
    stale_key_task = asyncio.create_task(_run_stale_key_cleanup_scheduler())
    weekly_cleanup_task = asyncio.create_task(_run_weekly_data_cleanup_scheduler())
    yield
    for t in [ledger_cache_task, scheduler_task, deduction_task, catchup_task,
              late_fee_task, reconciliation_2300_task, stale_key_task, weekly_cleanup_task]:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass


app = FastAPI(title="bifinexbot.com API", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# NextAuth JWT (from /api/auth/token). Set NEXTAUTH_SECRET in env to enable.
# Strip so CRLF/whitespace from .env don't break JWT verification.
NEXTAUTH_SECRET = (os.getenv("NEXTAUTH_SECRET", "") or "").strip()

# --- CORS: explicitly allow frontend origins so browser can reach backend ---
# Include 3003 so when frontend runs on 3003 (e.g. port 3000 occupied), API calls are allowed
_cors_origins = [
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://0.0.0.0:3000",
    "http://127.0.0.1:3003",
    "http://localhost:3003",
]
if os.getenv("FRONTEND_ORIGIN"):
    _cors_origins.append(os.getenv("FRONTEND_ORIGIN").strip())
if os.getenv("CORS_ORIGINS"):
    _cors_origins.extend(o.strip() for o in os.getenv("CORS_ORIGINS").split(",") if o.strip())
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Data-Source"],
)


# --- Auth rate limiter: 20 req/min per IP for auth endpoints ---
_auth_rl: Dict[str, List[float]] = {}
_auth_rl_lock = asyncio.Lock()
AUTH_RL_MAX = 20
AUTH_RL_WINDOW_SEC = 60.0


async def _auth_rate_limit(request: Request) -> None:
    """Raise 429 if an IP exceeds AUTH_RL_MAX auth requests per minute."""
    ip = request.client.host if request.client else "unknown"
    now = _time_module.monotonic()
    async with _auth_rl_lock:
        if ip not in _auth_rl:
            _auth_rl[ip] = []
        times = _auth_rl[ip]
        cutoff = now - AUTH_RL_WINDOW_SEC
        times[:] = [t for t in times if t > cutoff]
        if len(times) >= AUTH_RL_MAX:
            raise HTTPException(status_code=429, detail="Too many requests. Please wait.")
        times.append(now)


# --- Public health check (unauthenticated, for load balancers / k8s probes) ---
@app.get("/health")
async def health_check():
    """Lightweight liveness probe. Returns 200 if the process is running."""
    checks = {"status": "ok"}
    try:
        db = database.SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "degraded"
    try:
        rp = await get_redis()
        if rp:
            await rp.ping()
            checks["redis"] = "ok"
        else:
            checks["redis"] = "degraded"
    except Exception:
        checks["redis"] = "degraded"
    return checks


# --- Redis / ARQ (migrated to NEW Upstash server; REDIS_URL in .env, rediss:// only) ---
REDIS_CONNECT_TIMEOUT = 5.0  # seconds; fail fast if Redis unreachable


def _redis_host_from_url(url: str) -> str:
    """Extract host for logging (no credentials)."""
    if not url:
        return "unknown"
    try:
        from urllib.parse import urlparse
        p = urlparse(url)
        return p.hostname or p.netloc or "unknown"
    except Exception:
        return "unknown"


import asyncio
_redis_pool_cache = None
_redis_pool_lock = asyncio.Lock()
_redis_last_healthy: float = 0.0
_REDIS_HEALTH_CHECK_INTERVAL = 30.0

async def get_redis():
    """Return a shared Redis pool (singleton). Creates the pool on first call; reuses it thereafter.
    Includes a periodic ping health check so stale Upstash connections are detected and recreated.
    Returns None on failure."""
    global _redis_pool_cache, _redis_last_healthy
    if _redis_pool_cache is not None:
        if _time_module.monotonic() - _redis_last_healthy < _REDIS_HEALTH_CHECK_INTERVAL:
            return _redis_pool_cache
        try:
            await asyncio.wait_for(_redis_pool_cache.ping(), timeout=3)
            _redis_last_healthy = _time_module.monotonic()
            return _redis_pool_cache
        except Exception:
            logger.warning("Redis pool health check failed; recreating pool.")
            _redis_pool_cache = None

    async with _redis_pool_lock:
        if _redis_pool_cache is not None:
            return _redis_pool_cache
        try:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
            if ".upstash.io" in redis_url and redis_url.startswith("redis://"):
                redis_url = redis_url.replace("redis://", "rediss://", 1)
            settings = RedisSettings.from_dsn(redis_url)
            _redis_pool_cache = await asyncio.wait_for(create_pool(settings), timeout=REDIS_CONNECT_TIMEOUT)
            _redis_last_healthy = _time_module.monotonic()
            return _redis_pool_cache
        except Exception as e:
            logger.error("Failed to create Redis pool: %s", e)
            return None


async def get_redis_or_raise():
    """Get Redis with timeout; raises HTTPException 503 if unavailable (REDIS_URL in .env, e.g. Upstash)."""
    try:
        redis = await asyncio.wait_for(get_redis(), timeout=REDIS_CONNECT_TIMEOUT)
        if redis is None:
            raise HTTPException(
                status_code=503,
                detail="Queue service unavailable. Check REDIS_URL in .env and Redis server reachability.",
            )
        return redis
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=503,
            detail="Queue service unavailable. Check REDIS_URL in .env and Redis server reachability.",
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Queue service unavailable. Check REDIS_URL in .env and Redis server reachability.",
        )


# --- Registration token award ---
REGISTRATION_TOKEN_AWARD = 150


def _award_registration_tokens(user_id: int, db: Session) -> None:
    """
    Award REGISTRATION_TOKEN_AWARD (150) tokens to a new user on registration.
    """
    try:
        token_ledger_svc.add_tokens(db, user_id, float(REGISTRATION_TOKEN_AWARD), "registration")
        db.commit()
        logger.info("token_award user_id=%s amount=%s reason=registration", user_id, REGISTRATION_TOKEN_AWARD)
    except Exception as e:
        logger.exception("token_award failed user_id=%s amount=%s reason=registration error=%s", user_id, REGISTRATION_TOKEN_AWARD, e)
        try:
            db.rollback()
        except Exception:
            pass


# --- Google OAuth ---
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")


class GoogleAuthPayload(BaseModel):
    id_token: str
    referral_code: Optional[str] = None


class BootstrapUserPayload(BaseModel):
    referral_code: Optional[str] = None


def _apply_referral_first_touch(user: models.User, referral_code: Optional[str], db: Session) -> bool:
    """
    First-touch referral policy:
    - only set referrer when user has no referred_by yet
    - ignore invalid/missing code
    - prevent self-referral
    Returns True when referred_by is updated.
    """
    code = (referral_code or "").strip()
    if not code or user.referred_by is not None:
        return False
    referrer = db.query(models.User).filter(models.User.referral_code == code).first()
    if not referrer or referrer.id == user.id:
        return False
    user.referred_by = referrer.id
    db.commit()
    db.refresh(user)
    return True


def _create_user_by_email(email: str, referral_code: Optional[str], db: Session) -> models.User:
    """Create a new Gmail user with optional first-touch referral."""
    if not email or not email.endswith("@gmail.com"):
        raise HTTPException(status_code=400, detail="Only @gmail.com accounts are allowed.")
    referrer: Optional[models.User] = None
    code = (referral_code or "").strip()
    if code:
        referrer = db.query(models.User).filter(models.User.referral_code == code).first()
    new_user = models.User(
        email=email,
        plan_tier="trial",
        rebalance_interval=30,
        referred_by=referrer.id if referrer else None,
    )
    new_user.referral_code = _generate_referral_code(db)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    _award_registration_tokens(new_user.id, db)
    return new_user


def _get_or_create_user_by_email_for_session(email: str, referral_code: Optional[str], db: Session) -> models.User:
    """
    Ensure user exists for an authenticated session.
    Applies referral only with first-touch policy.
    """
    if not email or not email.endswith("@gmail.com"):
        raise HTTPException(status_code=400, detail="Only @gmail.com accounts are allowed.")
    user = db.query(models.User).filter(models.User.email == email).first()
    if user:
        _apply_referral_first_touch(user, referral_code, db)
        try:
            user.last_login_at = datetime.utcnow()
            if getattr(user, "status", None) == "dormant":
                user.status = "active"
            db.commit()
        except Exception:
            db.rollback()
        return user
    return _create_user_by_email(email, referral_code, db)


def _get_or_create_user_from_google(idinfo: dict, referral_code: Optional[str], db: Session) -> models.User:
    email: str = (idinfo.get("email") or "").strip()
    return _get_or_create_user_by_email_for_session(email, referral_code, db)


# ────────── User auth cache (bypasses DB for read-only endpoints) ──────────
_user_auth_cache: Dict[str, tuple] = {}  # email -> (user_id, monotonic_ts)
_user_full_cache: Dict[int, tuple] = {}  # uid -> (monotonic_ts, snapshot_dict)
_USER_AUTH_TTL = 300.0  # 5 minutes
_USER_FULL_CACHE_TTL = 30.0


class _CachedUser:
    """Lightweight read-only stand-in for models.User. Avoids DB round-trip for auth on GET requests."""
    __slots__ = ("_data",)

    def __init__(self, data: dict):
        object.__setattr__(self, "_data", data)

    def __getattr__(self, name):
        d = object.__getattribute__(self, "_data")
        if name in d:
            return d[name]
        return None

    def __setattr__(self, name, value):
        if name == "_data":
            object.__setattr__(self, name, value)
        else:
            object.__getattribute__(self, "_data")[name] = value


def _cache_user_snapshot(user: models.User):
    """Store a serializable snapshot of user fields for fast auth bypass."""
    try:
        vault = getattr(user, "vault", None)
        vault_snapshot = None
        if vault is not None:
            _enc_key = getattr(vault, "encrypted_key", None)
            _enc_secret = getattr(vault, "encrypted_secret", None)
            _enc_gemini = getattr(vault, "encrypted_gemini_key", None)

            def _snapshot_get_keys(_ek=_enc_key, _es=_enc_secret, _eg=_enc_gemini):
                return {
                    "bfx_key": security.decrypt_key(str(_ek)),
                    "bfx_secret": security.decrypt_key(str(_es)),
                    "gemini_key": security.decrypt_key(str(_eg)) if _eg else "",
                }

            vault_snapshot = type("VaultSnapshot", (), {
                "user_id": getattr(vault, "user_id", None),
                "encrypted_key": _enc_key,
                "encrypted_secret": _enc_secret,
                "encrypted_gemini_key": _enc_gemini,
                "created_at": getattr(vault, "created_at", None),
                "last_tested_at": getattr(vault, "last_tested_at", None),
                "last_test_balance": getattr(vault, "last_test_balance", None),
                "keys_updated_at": getattr(vault, "keys_updated_at", None),
                "get_keys": _snapshot_get_keys,
            })()
        data = {
            "id": user.id,
            "email": user.email,
            "plan_tier": user.plan_tier,
            "lending_limit": user.lending_limit,
            "rebalance_interval": user.rebalance_interval,
            "pro_expiry": user.pro_expiry,
            "referral_code": user.referral_code,
            "referred_by": user.referred_by,
            "usdt_withdraw_address": getattr(user, "usdt_withdraw_address", None),
            "status": user.status,
            "bot_status": user.bot_status,
            "bot_desired_state": getattr(user, "bot_desired_state", None),
            "key_deletions": getattr(user, "key_deletions", "{}"),
            "created_at": user.created_at,
            "vault": vault_snapshot,
        }
        _user_full_cache[user.id] = (_time_module.monotonic(), data)
    except Exception as e:
        logger.warning("[CACHE] _cache_user_snapshot failed: %s", e)


def _get_user_by_email(email: str, db: Session) -> models.User:
    if not email or not email.endswith("@gmail.com"):
        raise HTTPException(status_code=400, detail="Only @gmail.com accounts are allowed.")
    try:
        from sqlalchemy.orm import joinedload
        user = db.query(models.User).options(joinedload(models.User.vault)).filter(models.User.email == email).first()
    except Exception as e:
        logger.exception("_get_user_by_email db query failed: %s", e)
        raise HTTPException(status_code=500, detail="Authentication service error. Please try again.")
    if not user:
        raise HTTPException(status_code=401, detail="User not registered.")
    _user_auth_cache[email] = (user.id, _time_module.monotonic())
    _cache_user_snapshot(user)
    return user


async def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(database.get_db),
) -> models.User:
    """
    Verify Bearer token. For GET requests, returns a cached user snapshot when possible
    to avoid DB round-trip. For POST/PUT/DELETE, always loads from DB.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")

    email = _extract_email_from_bearer_token(authorization)
    is_read_only = request.method in ("GET", "HEAD", "OPTIONS")

    if is_read_only:
        cached_entry = _user_auth_cache.get(email)
        if cached_entry:
            uid, ts = cached_entry
            if _time_module.monotonic() - ts < _USER_AUTH_TTL:
                full_cached = _user_full_cache.get(uid)
                if full_cached:
                    fts, data = full_cached
                    if _time_module.monotonic() - fts < _USER_FULL_CACHE_TTL:
                        return _CachedUser(data)

    return _get_user_by_email(email, db)


def _extract_email_from_bearer_token(authorization: Optional[str]) -> str:
    """Extract authenticated email from NextAuth JWT or Google ID token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")

    # 1) Try NextAuth JWT (session token from Upstash/NextAuth flow)
    if NEXTAUTH_SECRET:
        try:
            payload = jwt.decode(
                token,
                NEXTAUTH_SECRET,
                algorithms=["HS256"],
                options={"verify_exp": True},
            )
            email = (payload.get("email") or "").strip()
            if email:
                return email
        except jwt.PyJWTError:
            pass
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("token email extraction JWT failed: %s", e)
            raise HTTPException(status_code=500, detail="Authentication service error. Please try again.")

    # 2) Fallback: Google ID token (legacy)
    try:
        idinfo = id_token.verify_oauth2_token(
            token, google_requests.Request(), GOOGLE_CLIENT_ID
        )
        email = (idinfo.get("email") or "").strip()
        if email:
            return email
    except Exception:
        pass
    raise HTTPException(status_code=401, detail="Session expired. Please log in again.")


def _validate_usdt_address(addr: str) -> bool:
    """Basic validation for USDT wallet (TRC20 T..., or ERC20 0x...)."""
    if not addr or len(addr) > 255:
        return False
    s = addr.strip()
    if re.match(r"^T[1-9A-HJ-NP-Za-km-z]{33}$", s):
        return True
    if re.match(r"^0x[a-fA-F0-9]{40}$", s):
        return True
    return False


def _generate_referral_code(db: Session) -> str:
    """Generate unique 8-char alphanumeric referral code."""
    for _ in range(50):
        code = "".join(secrets.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(8))
        if not db.query(models.User).filter(models.User.referral_code == code).first():
            return code
    return f"ref{secrets.token_hex(3)}"  # fallback


def get_admin_user(current_user: models.User = Depends(get_current_user)) -> models.User:
    """
    Restrict admin endpoints to the exclusive admin email (ADMIN_EMAIL).
    """
    incoming = (current_user.email or "").strip().lower()
    if incoming != ADMIN_EMAIL:
        logger.warning(
            "admin_denied user_id=%s current_email=%r admin_email=%r match=%s",
            getattr(current_user, "id", None),
            current_user.email,
            ADMIN_EMAIL,
            incoming == ADMIN_EMAIL,
        )
        raise HTTPException(status_code=403, detail="Not authorized.")
    return current_user


# --- Pydantic Schemas ---
class APIKeysInput(BaseModel):
    bfx_key: str
    bfx_secret: str
    gemini_key: Optional[str] = None


class StatsResponse(BaseModel):
    gross_profit: float
    fake_fee: float
    net_profit: float


# Bitfinex charges 15% on margin funding income for the lender (see bitfinex.com/fees).
BITFINEX_LENDER_FEE_PCT = 0.15

# Token (credit) system: used_tokens = int(gross_profit_usd × TOKENS_PER_USDT_GROSS). Gross Profit = USD; Used Tokens = USD × 10.
TOKENS_PER_USDT_GROSS = 10
FREE_TIER_TOKENS = 100
PLAN_TOKEN_CREDITS = {
    "trial": FREE_TIER_TOKENS,
    "free": FREE_TIER_TOKENS,
    "pro": 1500,
    "ai_ultra": 9000,
    "whales": 40000,
}


class LendingStatsResponse(BaseModel):
    """Gross = total interest from Bitfinex since registration; Net = Gross × (1 - 15%)."""
    gross_profit: float
    bitfinex_fee: float
    net_profit: float
    trades: Optional[List["FundingTradeRecord"]] = None
    total_trades_count: Optional[int] = None  # cumulative trades synced (for display when trades list not full)
    calculation_breakdown: Optional["CalculationBreakdown"] = None
    db_snapshot_gross: Optional[float] = None  # set when ?source=db so client can verify backend DB read


class FundingTradeRecord(BaseModel):
    """Single repaid funding trade from Bitfinex (POST auth/r/funding/trades/hist)."""
    id: int
    currency: str
    mts_create: int
    offer_id: int
    amount: float
    rate: float
    period: float
    interest_usd: float


class FundingTradesResponse(BaseModel):
    """Funding trades between registration and latest, with gross profit."""
    trades: List[FundingTradeRecord]
    gross_profit: float
    bitfinex_fee: float
    net_profit: float
    calculation_breakdown: Optional["CalculationBreakdown"] = None


class CurrencyBreakdownItem(BaseModel):
    """Per-currency interest used in gross profit calculation."""
    currency: str
    interest_ccy: float
    ticker_price_usd: float
    interest_usd: float


class CalculationBreakdown(BaseModel):
    """Shows how gross profit was computed from funding trades."""
    trades_count: int
    per_currency: List[CurrencyBreakdownItem]
    total_gross_usd: float
    formula_note: str = "Interest per trade = |AMOUNT| * RATE * (PERIOD/365 days). USD/USDt/USDT/UST use 1:1; others use Bitfinex t{CCY}USD price."


# Bitfinex does not expose a single "sum profit for date range" endpoint. We use POST /v2/auth/r/funding/trades/hist
# to fetch all repaid trades in the period and sum interest ourselves. Alternatives: v1 /summary (30-day only);
# v2 /auth/r/ledgers/{currency}/hist for transaction-level data (different format).


class UserStatusResponse(BaseModel):
    plan_tier: str
    rebalance_interval: int
    trial_remaining_days: Optional[int]
    tokens_remaining: Optional[float] = None
    tokens_used: int = 0
    initial_token_credit: int = 0
    gross_profit_usd: float = 0.0
    gross_profit_updated_at: Optional[str] = None  # ISO 8601 UTC; user_profit_snapshot.updated_at (when Bitfinex gross was last refreshed)
    pro_expiry: Optional[str] = None  # ISO 8601 UTC; null for free plan
    created_at: Optional[str] = None  # ISO 8601 UTC; users.created_at (Settings "Registration Date")


class TokenBalanceResponse(BaseModel):
    tokens_remaining: float
    tokens_used: int
    initial_credit: int
    gross_profit_usd: float


class TokenBalanceV1Response(BaseModel):
    """GET /api/v1/users/me/token-balance: remaining = total_tokens_added - total_tokens_deducted."""
    tokens_remaining: float
    total_tokens_added: float
    total_tokens_deducted: float
    last_gross_usd_used: float
    updated_at: Optional[str] = None  # UTC ISO 8601; null if never updated


# In-memory rate limit for token-balance API: 10 requests per minute per user
_token_balance_rl: Dict[int, List[float]] = {}
_token_balance_rl_lock = asyncio.Lock()
TOKEN_BALANCE_RL_MAX = 10
TOKEN_BALANCE_RL_WINDOW_SEC = 60.0


async def _token_balance_rate_limit(user_id: int) -> None:
    """Raise 429 if user exceeds 10 requests per minute."""
    import time
    now = time.monotonic()
    async with _token_balance_rl_lock:
        if user_id not in _token_balance_rl:
            _token_balance_rl[user_id] = []
        times = _token_balance_rl[user_id]
        cutoff = now - TOKEN_BALANCE_RL_WINDOW_SEC
        times[:] = [t for t in times if t > cutoff]
        if len(times) >= TOKEN_BALANCE_RL_MAX:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded: 10 requests per minute",
            )
        times.append(now)


# Rate limit for start-bot / stop-bot: 10 actions per minute per user (prevents spam/abuse)
_bot_action_rl: Dict[int, List[float]] = {}
_bot_action_rl_lock = asyncio.Lock()
BOT_ACTION_RL_MAX = 10
BOT_ACTION_RL_WINDOW_SEC = 60.0

# Per-action cooldown: min time between start or stop (reduces accidental/abuse toggling)
_bot_last_start_ts: Dict[int, float] = {}
_bot_last_stop_ts: Dict[int, float] = {}
BOT_START_COOLDOWN_SEC = 30.0
BOT_STOP_COOLDOWN_SEC = 15.0


async def _bot_action_rate_limit(user_id: int) -> None:
    """Raise 429 if user exceeds 10 start/stop bot requests per minute."""
    import time as _time
    now = _time.monotonic()
    async with _bot_action_rl_lock:
        if user_id not in _bot_action_rl:
            _bot_action_rl[user_id] = []
        times = _bot_action_rl[user_id]
        cutoff = now - BOT_ACTION_RL_WINDOW_SEC
        times[:] = [t for t in times if t > cutoff]
        if len(times) >= BOT_ACTION_RL_MAX:
            raise HTTPException(
                status_code=429,
                detail="Too many start/stop requests. Please wait a minute.",
            )
        times.append(now)


async def _check_start_cooldown(user_id: int) -> None:
    """Raise 429 if user started the bot too recently."""
    import time as _time
    now = _time.monotonic()
    async with _bot_action_rl_lock:
        last = _bot_last_start_ts.get(user_id, 0.0)
        if last > 0 and (now - last) < BOT_START_COOLDOWN_SEC:
            wait = int(BOT_START_COOLDOWN_SEC - (now - last))
            raise HTTPException(
                status_code=429,
                detail=f"Please wait {wait} seconds before starting the bot again.",
            )


async def _check_stop_cooldown(user_id: int) -> None:
    """Raise 429 if user stopped the bot too recently."""
    import time as _time
    now = _time.monotonic()
    async with _bot_action_rl_lock:
        last = _bot_last_stop_ts.get(user_id, 0.0)
        if last > 0 and (now - last) < BOT_STOP_COOLDOWN_SEC:
            wait = int(BOT_STOP_COOLDOWN_SEC - (now - last))
            raise HTTPException(
                status_code=429,
                detail=f"Please wait {wait} seconds before stopping the bot again.",
            )


async def _record_start_success(user_id: int) -> None:
    import time as _time
    async with _bot_action_rl_lock:
        _bot_last_start_ts[user_id] = _time.monotonic()


async def _record_stop_success(user_id: int) -> None:
    import time as _time
    async with _bot_action_rl_lock:
        _bot_last_stop_ts[user_id] = _time.monotonic()


class AdminUserOut(BaseModel):
    id: int
    email: str
    plan_tier: str
    rebalance_interval: int
    pro_expiry: Optional[datetime]
    status: str
    tokens_remaining: Optional[float] = None
    bot_status: Optional[str] = None
    created_at: Optional[str] = None


class DeductionLogEntry(BaseModel):
    user_id: int
    email: Optional[str] = None
    gross_profit: float
    tokens_deducted: float
    tokens_remaining_before: Optional[float] = None
    tokens_remaining_after: Optional[float] = None
    total_used_tokens: Optional[float] = None
    timestamp: str
    account_switch_note: Optional[str] = None


class AdminUserUpdate(BaseModel):
    plan_tier: Optional[str] = None
    pro_expiry: Optional[datetime] = None
    rebalance_interval: Optional[int] = None
    tokens_remaining: Optional[float] = None


class AdminTokenAdjustBody(BaseModel):
    amount: float
    note: Optional[str] = None


class AdminTokenAdjustResponse(BaseModel):
    tokens_remaining: float


def _token_add_detail(reason: str, extra: Any) -> str:
    """Build human-readable detail from reason and extra (token_ledger.metadata) for display in logs."""
    extra = extra if isinstance(extra, dict) else {}
    plan_labels = {"whales": "Whales AI", "ai_ultra": "AI Ultra", "pro": "Pro"}
    if reason in ("subscription_monthly", "subscription_yearly"):
        plan = (extra.get("plan") or "").strip() or "—"
        interval = (extra.get("interval") or "monthly").strip()
        plan_display = plan_labels.get(plan, plan.replace("_", " ").title())
        return f"{plan_display} ({interval})"
    if reason == "deposit_usd":
        usd = extra.get("usd_amount")
        if usd is not None:
            try:
                return f"Deposit ${float(usd):,.2f}"
            except (TypeError, ValueError):
                pass
        return "Deposit"
    if reason == "admin_add":
        note = (extra.get("note") or "").strip()
        if note:
            return f"Admin: {note[:200]}"
        return "Admin adjustment"
    if reason == "admin_bulk_add":
        return "Admin adjustment (bulk)"
    if reason == "deduction_rollback":
        d = extra.get("rollback_date")
        return f"Refund (rollback {d})" if d else "Refund"
    if reason == "registration":
        return "Sign-up bonus"
    if reason == "migration_backfill":
        return "Migration"
    return reason.replace("_", " ").title()


class TokenAddLogEntry(BaseModel):
    """Admin token-add log entry."""
    id: Optional[int] = None
    user_id: int
    email: Optional[str] = None
    amount: float
    reason: str
    created_at: str
    detail: Optional[str] = None


class TokenAddHistoryEntry(BaseModel):
    """User-facing token add history entry (no user_id)."""
    amount: float
    reason: str
    created_at: str
    detail: Optional[str] = None
    balance_before: Optional[float] = None
    balance_after: Optional[float] = None


class MyDeductionLogEntry(BaseModel):
    """User-facing deduction log entry for /api/v1/users/me/deduction-history (no user_id/email)."""
    gross_profit: float
    tokens_deducted: float
    tokens_remaining_before: Optional[float] = None  # derived: remaining_after + deducted
    tokens_remaining_after: Optional[float] = None
    total_used_tokens: Optional[float] = None
    timestamp: str
    account_switch_note: Optional[str] = None


class NotificationResponse(BaseModel):
    """GET /api/v1/users/me/notifications: user-facing notification (admin sent)."""
    id: int
    title: str
    content: Optional[str] = None
    type: str  # info | warning | announcement
    created_at: str  # ISO 8601


class ApiFailureOut(BaseModel):
    id: str
    ts: str
    context: str
    user_id: Optional[int]
    error: str


class AdminRetryBody(BaseModel):
    """Retry a failed API call: by failure id or by user_id."""
    failure_id: Optional[str] = None
    user_id: Optional[int] = None


class AdminAuditEntry(BaseModel):
    ts: str
    email: str
    action: str
    detail: Dict[str, Any]


class AdminApiKeyRow(BaseModel):
    user_id: int
    email: str
    has_keys: bool
    key_masked: Optional[str] = None
    last_tested_at: Optional[str] = None


class BulkTokenItem(BaseModel):
    user_id: int
    amount: float


class BulkTokenBody(BaseModel):
    items: List[BulkTokenItem]


class AdminUsdtCreditRow(BaseModel):
    user_id: int
    email: str
    usdt_credit: float
    total_earned: float
    total_withdrawn: float
    locked_pending: float = 0.0


class UsdtAdjustBody(BaseModel):
    amount: float  # + add, - deduct


class WithdrawalRow(BaseModel):
    id: int
    user_id: int
    email: str
    amount: float
    address: str
    status: str
    created_at: str
    processed_at: Optional[str] = None
    processed_by: Optional[str] = None
    rejection_note: Optional[str] = None


class RankingRow(BaseModel):
    rank: int
    user_display: str
    yield_pct: float
    lent_usd: Optional[float] = None
    plan_tier: Optional[str] = None  # trial, pro, ai_ultra, whales


class RankingSummary(BaseModel):
    total_paid_out_usd: float
    total_payouts: int
    active_traders: int


class RankingResponse(BaseModel):
    items: List[RankingRow]
    total: int
    page: int
    per_page: int
    summary: Optional[RankingSummary] = None


class ReferralGainRow(BaseModel):
    rank: int
    user_display: str
    usdt_gain_daily: float


class ReferralGainResponse(BaseModel):
    items: List[ReferralGainRow]
    total: int
    page: int
    per_page: int


class ReferralRow(BaseModel):
    user_id: int
    email: str
    referral_code: Optional[str] = None
    referrer_id: Optional[int] = None
    referrer_email: Optional[str] = None
    downline_count: int
    referral_earnings: float


class ReferralTreeOut(BaseModel):
    user_id: int
    email: str
    level1_upline: Optional[Dict[str, Any]] = None
    level2_upline: Optional[Dict[str, Any]] = None
    level3_upline: Optional[Dict[str, Any]] = None
    downline_count: int


class NotificationSendBody(BaseModel):
    title: str
    content: Optional[str] = None
    type: str = "info"
    target_user_id: Optional[int] = None  # null = all users


class AdminSettingOut(BaseModel):
    key: str
    value: str


class AdminSettingsUpdateBody(BaseModel):
    registration_bonus_tokens: Optional[int] = None
    min_withdrawal_usdt: Optional[float] = None
    daily_deduction_utc_hour: Optional[int] = None
    deduction_multiplier: Optional[float] = None
    referral_purchase_l1_pct: Optional[float] = None
    referral_purchase_l2_pct: Optional[float] = None
    referral_purchase_l3_pct: Optional[float] = None
    bot_auto_start: Optional[bool] = None
    referral_system_enabled: Optional[bool] = None
    withdrawal_enabled: Optional[bool] = None
    maintenance_mode: Optional[bool] = None
    api_keys_help_url: Optional[str] = None
    stale_key_invalid_days: Optional[int] = None
    stale_key_inactive_days: Optional[int] = None
    cleanup_deduction_log_days: Optional[int] = None
    cleanup_token_ledger_days: Optional[int] = None
    cleanup_dormant_days: Optional[int] = None


class UserOverviewOut(BaseModel):
    user: Dict[str, Any]
    token_balance: Optional[Dict[str, Any]] = None
    usdt_credit: Optional[Dict[str, Any]] = None
    profit_snapshot: Optional[Dict[str, Any]] = None
    referral: Optional[Dict[str, Any]] = None
    api_key_status: Optional[Dict[str, Any]] = None
    withdrawals: List[Dict[str, Any]]
    deduction_history: List[Dict[str, Any]]
    token_add_history: List[Dict[str, Any]] = []
    audit_entries: List[Dict[str, Any]]
    edits_locked: bool = False  # True during daily fee window (09:55–10:35 UTC); admin should not edit then


# --- Google Auth Endpoint ---
@app.post("/auth/google")
async def google_login(request: Request, payload: GoogleAuthPayload, db: Session = Depends(database.get_db)):
    await _auth_rate_limit(request)
    try:
        idinfo = id_token.verify_oauth2_token(
            payload.id_token, google_requests.Request(), GOOGLE_CLIENT_ID
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Google ID token.")

    user = _get_or_create_user_from_google(idinfo, payload.referral_code, db)
    return {"user_id": user.id, "email": user.email, "plan_tier": user.plan_tier}


@app.post("/api/bootstrap-user")
async def bootstrap_user(
    request: Request,
    payload: BootstrapUserPayload,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(database.get_db),
):
    """
    Ensure backend user exists right after auth (before API key save).
    Applies first-touch referral linking once.
    """
    await _auth_rate_limit(request)
    email = _extract_email_from_bearer_token(authorization)
    user = _get_or_create_user_by_email_for_session(email, payload.referral_code, db)
    return {
        "id": user.id,
        "email": user.email,
        "referral_code": user.referral_code,
        "referred_by": user.referred_by,
    }


# --- Live Bot Stats Route (existing dashboard); user end: auth required, own data only ---
async def _get_bot_stats_data(user_id: int, db: Session) -> dict:
    """Shared logic for bot stats (used by GET /bot-stats and dashboard-fold)."""
    redis = await get_redis()
    user = db.query(models.User).filter(models.User.id == user_id).first()
    bot_status = getattr(user, "bot_status", None) if user else None
    vault = getattr(user, "vault", None) if user else None
    has_api_keys = bool(vault and getattr(vault, "encrypted_key", None))

    if redis is None:
        return {
            "active": bot_status in ("running", "starting"),
            "engines": [],
            "total_loaned": "0.00",
            "bot_status": bot_status or "stopped",
            "has_api_keys": has_api_keys,
        }
    keys = await redis.keys(f"status:{user_id}:*")
    all_engines = []
    if keys:
        raw_data_list = await redis.mget(keys)
        for raw_data in raw_data_list:
            if raw_data:
                if isinstance(raw_data, bytes):
                    raw_data = raw_data.decode("utf-8")
                try:
                    all_engines.append(json.loads(raw_data))
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
    active = bot_status in ("running", "starting")
    if not all_engines:
        return {
            "active": active,
            "engines": [],
            "total_loaned": "0.00",
            "bot_status": bot_status or "stopped",
            "has_api_keys": has_api_keys,
        }
    total_val = sum(float(str(e.get("loaned", 0)).replace(",", "") or 0) for e in all_engines)
    return {
        "active": active,
        "engines": all_engines,
        "total_loaned": f"{total_val:,.2f}",
        "bot_status": bot_status or "running",
        "has_api_keys": has_api_keys,
    }


@app.get("/bot-stats/{user_id}")
async def get_all_bot_stats(
    user_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """Fetches live heartbeat data from Redis. Caller must be the same user. Includes bot_status from DB."""
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this user.")

    cache_key = f"bot-stats:{user_id}"
    cached = _rcache_get(cache_key)
    if cached is not None:
        return cached

    try:
        result = await _get_bot_stats_data(user_id, db)
        _rcache_set(cache_key, result)
        return result
    except Exception as e:
        logger.warning("bot-stats user_id=%s error=%s", user_id, e)
        user = db.query(models.User).filter(models.User.id == user_id).first()
        bot_status = getattr(user, "bot_status", None) if user else None
        vault = getattr(user, "vault", None) if user else None
        return {
            "active": bot_status in ("running", "starting"),
            "engines": [],
            "total_loaned": "0.00",
            "bot_status": bot_status or "stopped",
            "has_api_keys": bool(vault and getattr(vault, "encrypted_key", None)),
        }


# --- Whales terminal: cached logs + summary; user end: auth required, own data only ---
TERMINAL_SUMMARY_KEY = "terminal_summary"
TERMINAL_SUMMARY_TTL_SEC = 120


@app.get("/terminal-logs/{user_id}")
async def get_terminal_logs(
    user_id: int,
    current_user: models.User = Depends(get_current_user),
):
    """Returns last 300 terminal log lines and optional summary. Uses response cache."""
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this user.")

    cache_key = f"terminal-logs:{user_id}"
    cached = _rcache_get(cache_key)
    if cached is not None:
        return cached

    try:
        redis = await asyncio.wait_for(get_redis(), timeout=REDIS_CONNECT_TIMEOUT)
    except (asyncio.TimeoutError, Exception):
        return {"lines": [], "summary": None}
    if redis is None:
        return {"lines": [], "summary": None}
    lines_decoded: list = []
    summary_obj: dict | None = None
    try:
        key_logs = f"terminal_logs:{user_id}"
        lines = await asyncio.wait_for(redis.lrange(key_logs, 0, -1), timeout=5.0)
        lines_decoded = [line.decode("utf-8") if isinstance(line, bytes) else line for line in (lines or [])]
    except (asyncio.TimeoutError, Exception):
        pass
    try:
        key_summary = f"{TERMINAL_SUMMARY_KEY}:{user_id}"
        raw = await redis.get(key_summary)
        if raw:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            summary_obj = json.loads(raw)
    except Exception:
        summary_obj = None
    result = {"lines": lines_decoded, "summary": summary_obj}
    _rcache_set(cache_key, result)
    return result


def _detail_invalid_keys(msg: str) -> str:
    """Normalize error messages for frontend (Invalid Keys, Lending Permissions Missing, etc.)."""
    if not msg:
        return "Invalid API keys."
    lower = msg.lower()
    if "permission" in lower or "lending" in lower or "margin funding" in lower or "wallets" in lower:
        return "Lending Permissions Missing. Enable Account History, Margin Funding, and Wallets."
    if "unable" in lower or "verify" in lower or "identity" in lower:
        return "Invalid Keys. Unable to verify Bitfinex account."
    return msg


# --- Connect Exchange (Bitfinex) ---
async def _trigger_bot_start_after_keys_saved(user_id: int, db: Session) -> None:
    """Auto-start bot after first API key save only. Plan C: desired_state; tokens > 0 (Q6)."""
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            return
        if hasattr(user, "bot_desired_state"):
            user.bot_desired_state = "running"
        try:
            db.commit()
        except Exception:
            db.rollback()
            return
        legacy = _get_token_balance_legacy(db, user_id)
        tokens_remaining = float(legacy[0]) if legacy else 0.0
        if tokens_remaining <= 0:
            logger.info("bot_auto_start_after_keys_saved user_id=%s tokens_remaining=%s skip enqueue", user_id, tokens_remaining)
            return
        redis = await asyncio.wait_for(get_redis(), timeout=REDIS_CONNECT_TIMEOUT)
        enqueued = await _enqueue_bot_task(redis, user_id)
        if enqueued and user and hasattr(user, "bot_status"):
            try:
                user.bot_status = "starting"
                db.commit()
            except Exception:
                db.rollback()
    except Exception as e:
        logger.warning("bot_auto_start_after_keys_saved user_id=%s error=%s", user_id, e)
        try:
            db.rollback()
        except Exception:
            pass


@app.post("/connect-exchange")
async def connect_exchange(
    payload: APIKeysInput,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """
    Validate and save Bitfinex API keys. First-time insert allowed anytime.
    Overwrite blocked 09:55–10:35 UTC (daily fee calculation window).
    """
    vault_existing = (
        db.query(models.APIVault)
        .filter(models.APIVault.user_id == current_user.id)
        .first()
    )
    if vault_existing and vault_existing.encrypted_key and _is_api_key_lock_window():
        logger.info("API key lock: POST /connect-exchange (overwrite) blocked for user_id=%s", current_user.id)
        raise HTTPException(
            status_code=403,
            detail="API key modification disabled during daily fee processing (09:55–10:35 UTC).",
        )
    balance, result = await _validate_and_save_bitfinex_keys(
        payload, current_user, db
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    if not vault_existing:
        await _trigger_bot_start_after_keys_saved(current_user.id, db)
    return {
        "status": "success",
        "message": result.get("message", "Exchange connected and trial activated."),
        "balance": balance,
    }


@app.get("/api/version")
async def api_version(response: Response):
    """No-auth endpoint to verify which backend is running (gross-profit DB fallback support)."""
    response.headers["Cache-Control"] = "public, max-age=60"
    return {"version": "gross-profit-db-fallback", "source_db_supported": True}


@app.get("/api/public/api-keys-help-url")
def get_api_keys_help_url(
    db: Session = Depends(database.get_db),
    response: Response = None,
):
    """Public endpoint to get the API keys help URL from admin settings."""
    if response is not None:
        response.headers["Cache-Control"] = "public, max-age=300"
    url = _get_setting(db, "api_keys_help_url", "#")
    return {"url": url}


@app.get("/api/ranking", response_model=RankingResponse)
def get_ranking(
    page: int = Query(1, ge=1, le=10, description="Page 1–10"),
    per_page: int = Query(10, ge=1, le=10, description="Items per page"),
    db: Session = Depends(database.get_db),
):
    """Top 100 leaderboard (fake data). Refreshed daily after 10:00 UTC profit run. Paginated: 10 pages × 10 per page."""
    total = db.query(models.RankingSnapshot).count()
    offset = (page - 1) * per_page
    rows = (
        db.query(models.RankingSnapshot)
        .order_by(models.RankingSnapshot.rank)
        .offset(offset)
        .limit(per_page)
        .all()
    )
    summary = None
    if total > 0:
        today = date.today()
        seed = today.year * 10000 + today.month * 100 + today.day
        rng = random.Random(seed)
        reference_date = date(2024, 1, 1)
        days_since = (today - reference_date).days
        if days_since < 0:
            days_since = 0
        active_traders = rng.randint(3000, 6000)
        total_payouts = 50000 + days_since * 120
        total_paid_out_usd = round(2_000_000 + days_since * 85000, 2)
        summary = RankingSummary(
            total_paid_out_usd=total_paid_out_usd,
            total_payouts=total_payouts,
            active_traders=active_traders,
        )
    return RankingResponse(
        items=[
            RankingRow(
                rank=r.rank,
                user_display=r.user_display,
                yield_pct=r.yield_pct,
                lent_usd=r.lent_usd,
                plan_tier=getattr(r, "plan_tier", None),
            )
            for r in rows
        ],
        total=total,
        page=page,
        per_page=per_page,
        summary=summary,
    )


@app.post("/api/ranking/refresh")
def refresh_ranking_api(db: Session = Depends(database.get_db)):
    """Dev-only: regenerate top 100 fake ranking (same as daily run after 10:00 UTC profit). Set ALLOW_DEV_CONNECT=1."""
    if os.getenv("ALLOW_DEV_CONNECT") != "1":
        raise HTTPException(status_code=404, detail="Not available.")
    _refresh_ranking_snapshot(db)
    return {"status": "ok", "message": "ranking_snapshot refreshed (100 fake rows)."}


@app.get("/api/referral-gain", response_model=ReferralGainResponse)
def get_referral_gain(
    page: int = Query(1, ge=1, le=10, description="Page 1–10"),
    per_page: int = Query(10, ge=1, le=10, description="Items per page"),
    db: Session = Depends(database.get_db),
):
    """Top 100 referral gain (fake data). Refreshed daily after 10:00 UTC profit run. Paginated: 10 pages × 10 per page."""
    total = db.query(models.ReferralGainSnapshot).count()
    offset = (page - 1) * per_page
    rows = (
        db.query(models.ReferralGainSnapshot)
        .order_by(models.ReferralGainSnapshot.rank)
        .offset(offset)
        .limit(per_page)
        .all()
    )
    return ReferralGainResponse(
        items=[
            ReferralGainRow(rank=r.rank, user_display=r.user_display, usdt_gain_daily=r.usdt_gain_daily)
            for r in rows
        ],
        total=total,
        page=page,
        per_page=per_page,
    )


@app.post("/api/referral-gain/refresh")
def refresh_referral_gain_api(db: Session = Depends(database.get_db)):
    """Dev-only: regenerate top 100 fake referral gain (same as daily run after 10:00 UTC profit). Set ALLOW_DEV_CONNECT=1."""
    if os.getenv("ALLOW_DEV_CONNECT") != "1":
        raise HTTPException(status_code=404, detail="Not available.")
    _refresh_referral_gain_snapshot(db)
    return {"status": "ok", "message": "referral_gain_snapshot refreshed (100 fake rows)."}


@app.get("/api/me")
async def get_current_user_info(
    current_user: models.User = Depends(get_current_user),
):
    """
    Returns the currently authenticated user's id and email.
    Used by the frontend to scope all user-specific API calls (wallets, stats, etc.).
    """
    try:
        return {"id": current_user.id, "email": getattr(current_user, "email", "") or ""}
    except Exception as e:
        logger.exception("api/me failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to load user info.")


@app.get("/api/keys")
async def get_api_keys_status(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """
    Returns whether the current user has API keys saved (for Settings "Current Configuration" UI).
    Does not return the actual keys; only has_keys and an optional masked preview.
    """
    vault = (
        db.query(models.APIVault)
        .filter(models.APIVault.user_id == current_user.id)
        .first()
    )
    has_keys = bool(vault and vault.encrypted_key and vault.encrypted_secret)
    created_at = vault.created_at.isoformat() if (vault and getattr(vault, "created_at", None) and vault.created_at) else None
    last_tested_at = vault.last_tested_at.isoformat() if (vault and getattr(vault, "last_tested_at", None) and vault.last_tested_at) else None
    last_test_balance = getattr(vault, "last_test_balance", None) if vault else None
    api_key_modification_locked = _is_api_key_lock_window()
    return {
        "has_keys": has_keys,
        "key_preview": "••••••••" if has_keys else None,
        "created_at": created_at,
        "last_tested_at": last_tested_at,
        "last_test_balance": last_test_balance,
        "api_key_modification_locked": api_key_modification_locked,
    }


async def _get_current_user_for_token_balance(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(database.get_db),
) -> models.User:
    """Requires JWT; raises 401 with detail 'Not authenticated' if missing/invalid (token balance API spec)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return await get_current_user(request=request, authorization=authorization, db=db)
    except HTTPException as e:
        if e.status_code == 401:
            raise HTTPException(status_code=401, detail="Not authenticated")
        raise


@app.get("/api/v1/users/me/token-balance", response_model=TokenBalanceV1Response)
async def get_my_token_balance_v1(
    current_user: models.User = Depends(_get_current_user_for_token_balance),
    db: Session = Depends(database.get_db),
):
    """
    Real-time token balance from user_token_balance (after daily deduction).
    JWT required. Rate limit: 10 requests per minute per user.
    """
    try:
        await _token_balance_rate_limit(current_user.id)
    except HTTPException:
        raise

    cache_key = f"token-balance:{current_user.id}"
    cached = _rcache_get(cache_key)
    if cached is not None:
        return cached

    try:
        legacy = _get_token_balance_legacy_full(db, current_user.id)
        if legacy is not None:
            tokens_remaining = legacy["tokens_remaining"]
            purchased = legacy["purchased_tokens"]
            total_added = purchased
            total_deducted = max(0.0, purchased - tokens_remaining)
            logger.info("token_balance_api user_id=%s tokens_remaining=%s (legacy)", current_user.id, tokens_remaining)
            result = TokenBalanceV1Response(
                tokens_remaining=tokens_remaining,
                total_tokens_added=total_added,
                total_tokens_deducted=total_deducted,
                last_gross_usd_used=legacy["last_gross_usd_used"],
                updated_at=legacy["updated_at"],
            )
            _rcache_set(cache_key, result)
            return result
        row = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == current_user.id).first()
        if not row:
            logger.warning("token_balance_api user_id=%s: token balance row not found", current_user.id)
            raise HTTPException(status_code=404, detail="Token balance not found. Please contact support.")
        tokens_remaining = float(row.tokens_remaining or 0)
        purchased = float(row.purchased_tokens or 0)
        total_added = purchased
        total_deducted = max(0.0, purchased - tokens_remaining)
        last_gross_usd_used = float(row.last_gross_usd_used) if row.last_gross_usd_used is not None else 0.0
        updated_at = None
        if getattr(row, "updated_at", None) and row.updated_at:
            updated_at = row.updated_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        logger.info("token_balance_api user_id=%s tokens_remaining=%s", current_user.id, tokens_remaining)
        result = TokenBalanceV1Response(
            tokens_remaining=tokens_remaining,
            total_tokens_added=total_added,
            total_tokens_deducted=total_deducted,
            last_gross_usd_used=last_gross_usd_used,
            updated_at=updated_at,
        )
        _rcache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("token_balance_api user_id=%s error=%s", current_user.id, e)
        raise HTTPException(status_code=500, detail="Internal error retrieving token balance.")


@app.get("/api/v1/users/me/token-add-history", response_model=List[TokenAddHistoryEntry])
async def get_my_token_add_history(
    limit: int = Query(50, ge=1, le=200),
    current_user: models.User = Depends(_get_current_user_for_token_balance),
    db: Session = Depends(database.get_db),
):
    """Token add history for the current user (newest first). Uses response cache + optimised single query."""
    uid = current_user.id
    cache_key = f"token-add-history:{uid}"
    cached = _rcache_get(cache_key)
    if cached is not None:
        return cached

    out: List[TokenAddHistoryEntry] = []
    try:
        rows = db.execute(
            text("""
                WITH adds AS (
                    SELECT id, amount, reason, created_at, metadata,
                           SUM(amount) OVER (ORDER BY created_at ASC, id ASC) AS running_after
                    FROM token_ledger
                    WHERE user_id = :uid AND activity_type = 'add'
                ),
                bal AS (
                    SELECT tokens_remaining FROM user_token_balance WHERE user_id = :uid
                )
                SELECT a.id, a.amount, a.reason, a.created_at, a.metadata,
                       a.running_after, b.tokens_remaining
                FROM adds a LEFT JOIN bal b ON TRUE
                ORDER BY a.created_at DESC, a.id DESC
                LIMIT :lim
            """),
            {"uid": uid, "lim": limit},
        ).fetchall()
        for row in rows:
            amount_val = float(row[1] or 0)
            reason_val = (row[2] or "").strip()
            created_at_val = row[3]
            extra_val = row[4] if len(row) > 4 else None
            if not isinstance(extra_val, dict):
                extra_val = {}
            if created_at_val and getattr(created_at_val, "isoformat", None):
                created_str = created_at_val.isoformat()
                if created_str and (getattr(created_at_val, "tzinfo", None) is None):
                    created_str += "Z"
            else:
                created_str = "1970-01-01T00:00:00Z"
            detail_str = _token_add_detail(reason_val, extra_val)
            running_after = float(row[5]) if row[5] is not None else None
            bal_before = round(running_after - amount_val, 2) if running_after is not None else None
            bal_after = round(running_after, 2) if running_after is not None else None
            out.append(
                TokenAddHistoryEntry(
                    amount=amount_val,
                    reason=reason_val,
                    created_at=created_str,
                    detail=detail_str,
                    balance_before=bal_before,
                    balance_after=bal_after,
                )
            )
        if out and rows and rows[0][6] is not None:
            tokens_remaining = round(float(rows[0][6]), 2)
            first = out[0]
            out[0] = TokenAddHistoryEntry(
                amount=first.amount,
                reason=first.reason,
                created_at=first.created_at,
                detail=first.detail,
                balance_before=round(tokens_remaining - first.amount, 2),
                balance_after=tokens_remaining,
            )
    except Exception as e:
        logger.warning("get_my_token_add_history user_id=%s error=%s", uid, e)

    _rcache_set(cache_key, out)
    return out


@app.get("/api/v1/users/me/deduction-history", response_model=List[MyDeductionLogEntry])
async def get_my_deduction_history(
    limit: int = Query(100, ge=1, le=200),
    current_user: models.User = Depends(_get_current_user_for_token_balance),
    db: Session = Depends(database.get_db),
):
    """Deduction log for the current user (newest first). Uses response cache."""
    uid = current_user.id
    cache_key = f"deduction-history:{uid}"
    cached = _rcache_get(cache_key)
    if cached is not None:
        return cached

    if not hasattr(models, "DeductionLog"):
        return []
    rows = (
        db.query(models.DeductionLog)
        .filter(models.DeductionLog.user_id == uid)
        .order_by(models.DeductionLog.timestamp_utc.desc())
        .limit(limit)
        .all()
    )
    def _ts_str(row: "models.DeductionLog") -> str:
        if row.timestamp_utc:
            ts = row.timestamp_utc
            return ts.isoformat() if getattr(ts, "tzinfo", None) else ts.isoformat() + "Z"
        created = getattr(row, "created_at", None)
        if created:
            return created.isoformat() if getattr(created, "tzinfo", None) else created.isoformat() + "Z"
        return "1970-01-01T00:00:00Z"

    result = [
        MyDeductionLogEntry(
            gross_profit=float(r.daily_gross_profit_usd or 0),
            tokens_deducted=float(r.tokens_deducted or 0),
            tokens_remaining_before=float((r.tokens_remaining_after or 0) + (r.tokens_deducted or 0)),
            tokens_remaining_after=float(r.tokens_remaining_after) if r.tokens_remaining_after is not None else None,
            total_used_tokens=float(r.total_used_tokens) if r.total_used_tokens is not None else None,
            timestamp=_ts_str(r),
            account_switch_note=r.account_switch_note,
        )
        for r in rows
    ]
    _rcache_set(cache_key, result)
    return result


@app.get("/api/v1/users/me/notifications", response_model=List[NotificationResponse])
async def get_my_notifications(
    limit: int = Query(50, ge=1, le=100),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """Notifications for the current user. Uses response cache (60s TTL)."""
    uid = current_user.id
    cache_key = f"notifications:{uid}"
    cached = _rcache_get(cache_key)
    if cached is not None:
        return cached

    rows = (
        db.query(models.AdminNotification)
        .filter(
            or_(
                models.AdminNotification.target_user_id.is_(None),
                models.AdminNotification.target_user_id == uid,
            )
        )
        .order_by(models.AdminNotification.created_at.desc())
        .limit(limit)
        .all()
    )

    def _created_str(row: "models.AdminNotification") -> str:
        created = getattr(row, "created_at", None)
        if not created:
            return "1970-01-01T00:00:00Z"
        return created.isoformat() + "Z" if getattr(created, "tzinfo", None) is None else created.isoformat()

    result = [
        NotificationResponse(
            id=r.id,
            title=r.title or "",
            content=getattr(r, "content", None),
            type=getattr(r, "type", None) or "info",
            created_at=_created_str(r),
        )
        for r in rows
    ]
    _rcache_set(cache_key, result)
    return result


@app.post("/api/keys/test")
async def test_api_keys(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """
    Test stored API keys: fetch balance from Bitfinex, update last_tested_at, return balance.
    Used by Settings "Test API Keys" button.
    """
    vault = (
        db.query(models.APIVault)
        .filter(models.APIVault.user_id == current_user.id)
        .first()
    )
    if not vault or not vault.encrypted_key or not vault.encrypted_secret:
        raise HTTPException(status_code=404, detail="No API keys stored.")
    keys = vault.get_keys()
    mgr = BitfinexManager(keys["bfx_key"], keys["bfx_secret"])
    wallets, err = await mgr.wallets()
    if err or not wallets:
        raise HTTPException(status_code=400, detail="Invalid or expired API keys. Please update them.")
    summary = await mgr.compute_usd_balances()
    if hasattr(vault, "last_tested_at"):
        vault.last_tested_at = datetime.utcnow()
    if hasattr(vault, "last_test_balance"):
        vault.last_test_balance = summary.get("total_usd_all")
    db.commit()
    return {
        "success": True,
        "message": "API keys verified and ready to use.",
        "balance": summary,
    }


@app.delete("/api/keys")
async def delete_api_keys(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """
    Remove stored API keys for the current user (red bin button).
    User can only have one key; deleting clears it so they can add a new one.
    Blocked 09:55–10:35 UTC (daily fee calculation window).
    """
    if _is_api_key_lock_window():
        logger.info("API key lock: DELETE /api/keys blocked for user_id=%s", current_user.id)
        raise HTTPException(
            status_code=403,
            detail="API key modification disabled during daily fee processing (09:55–10:35 UTC).",
        )
    vault = (
        db.query(models.APIVault)
        .filter(models.APIVault.user_id == current_user.id)
        .first()
    )
    if vault:
        db.delete(vault)
        db.commit()
        current_month = datetime.utcnow().strftime("%Y-%m")
        count = 0
        user_row = db.query(models.User).filter(models.User.id == current_user.id).first()
        if user_row and hasattr(user_row, "key_deletions"):
            raw = getattr(user_row, "key_deletions", None) or "{}"
            try:
                kd = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except json.JSONDecodeError as e:
                logger.error(
                    "trace_id=%s | User %s – key_deletions malformed JSON, reset to empty: %s",
                    get_trace_id(), current_user.id, e,
                )
                kd = {}
            if not isinstance(kd, dict):
                kd = {}
            kd[current_month] = kd.get(current_month, 0) + 1
            count = kd[current_month]
            user_row.key_deletions = json.dumps(kd)
            db.commit()
            logger.info(
                "trace_id=%s | User %s – key_deletions for %s = %s (persisted to DB)",
                get_trace_id(), current_user.id, current_month, count,
            )
        else:
            with _key_deletions_lock:
                k = (current_user.id, current_month)
                _key_deletions[k] = _key_deletions.get(k, 0) + 1
                count = _key_deletions[k]
        if count >= 2:
            email = getattr(current_user, "email", "") or ""
            alert_msg = (
                f"URGENT: Repeated API Key Deletion (Potential Free Rider) – User: {email}, Deletions: {count}"
            )
            logger.warning(
                "trace_id=%s | User deleted key %dx this month – flagged for review: user_id=%s email=%s",
                get_trace_id(), count, current_user.id, email,
            )
            await _alert_admins_deduction_failure(alert_msg)
    return {"success": True, "message": "API keys removed."}


@app.post("/api/keys")
async def api_keys(
    payload: APIKeysInput,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """
    Validate Bitfinex API key and secret, encrypt and save to DB, return balance on success.
    Blocked 09:55–10:35 UTC when overwriting existing keys (daily fee calculation window).
    """
    vault_existing = db.query(models.APIVault).filter(models.APIVault.user_id == current_user.id).first()
    if vault_existing and vault_existing.encrypted_key and _is_api_key_lock_window():
        logger.info("API key lock: POST /api/keys (overwrite) blocked for user_id=%s", current_user.id)
        raise HTTPException(
            status_code=403,
            detail="API key modification disabled during daily fee processing (09:55–10:35 UTC).",
        )
    balance, result = await _validate_and_save_bitfinex_keys(
        payload, current_user, db
    )
    if "error" in result:
        err_msg = result["error"]
        url = result.get("permissions_url")
        if url and "permission" in err_msg.lower():
            err_msg = f"{err_msg} {url}"
        raise HTTPException(status_code=400, detail=err_msg)
    return {
        "success": True,
        "status": "success",
        "message": result.get("message", "Connection successful."),
        "balance": balance,
    }


def _check_permissions_response(perms_data: Any) -> tuple[bool, list[str]]:
    """
    Verify scope: wallets read, funding read+write, history read.
    perms_data can be list of dicts or list of lists from Bitfinex.
    Returns (ok, list_of_missing_descriptions).
    """
    missing: list[str] = []
    # Normalize to list of {scope, read, write}
    items: list[dict] = []
    if isinstance(perms_data, list):
        for p in perms_data:
            if isinstance(p, dict):
                items.append(p)
            elif isinstance(p, (list, tuple)) and len(p) >= 3:
                items.append({"scope": p[0], "read": p[1] if len(p) > 1 else 0, "write": p[2] if len(p) > 2 else 0})
    by_scope: dict[str, dict] = {item.get("scope", ""): item for item in items if item.get("scope")}
    # Required: wallets read, funding read+write, history read
    if not (by_scope.get("wallets") or {}).get("read"):
        missing.append("Wallets (Read)")
    fund = by_scope.get("funding") or {}
    if not fund.get("read"):
        missing.append("Funding (Read)")
    if not fund.get("write"):
        missing.append("Funding (Write)")
    if not (by_scope.get("history") or {}).get("read"):
        missing.append("History (Read)")
    return (len(missing) == 0, missing)


async def _validate_bitfinex_keys_only(payload) -> tuple[Optional[dict], Optional[dict]]:
    """
    Validate Bitfinex keys (auth, permissions, wallets, funding). No DB write.
    Returns (balance, None) on success or (None, {"error": "..."}) on failure.
    """
    mgr = BitfinexManager(payload.bfx_key, payload.bfx_secret)
    user_data, err = await mgr.info_user()
    if err:
        return None, {"error": "Invalid API Key or Secret."}
    if not user_data or not isinstance(user_data, list):
        return None, {"error": "Invalid API Key or Secret."}
    perms_data, err = await mgr.permissions()
    if err:
        return None, {
            "error": "Missing permissions: Could not fetch permissions. Please enable Wallets (Read), Funding (Read/Write), and History (Read) in your Bitfinex API settings.",
            "permissions_url": "https://setting.bitfinex.com/api",
        }
    ok, missing_list = _check_permissions_response(perms_data)
    if not ok:
        missing_str = ", ".join(missing_list)
        return None, {
            "error": f"Missing permissions: {missing_str}. Please enable them in your Bitfinex API settings.",
            "permissions_url": "https://setting.bitfinex.com/api",
        }
    wallets, err = await mgr.wallets()
    if err:
        return None, {"error": "Could not fetch wallets. Please check API permissions."}
    if not wallets or not isinstance(wallets, list):
        return None, {"error": "Could not fetch wallets."}
    has_funding = False
    for w in wallets:
        try:
            if len(w) > 0 and w[0] == "funding":
                has_funding = True
                break
        except (IndexError, TypeError):
            continue
    if not has_funding:
        return None, {"error": "No funding wallet found. Please ensure a Bitfinex funding wallet exists."}
    _, err_offers = await mgr.funding_offers()
    if err_offers:
        return None, {
            "error": "Missing permissions: Funding (Read). Please enable them in your Bitfinex API settings.",
            "permissions_url": "https://setting.bitfinex.com/api",
        }
    _, err_hist = await mgr.funding_trades_hist()
    if err_hist:
        return None, {
            "error": "Missing permissions: Funding history (Read). Please enable them in your Bitfinex API settings.",
            "permissions_url": "https://setting.bitfinex.com/api",
        }
    balance = await mgr.compute_usd_balances()
    return balance, None


async def _validate_and_save_bitfinex_keys(payload, current_user, db):
    """
    5-step validation. Do not save to DB until ALL pass.
    Uses BitfinexManager with strict nonce/signature to fix 10100 invalid token.
    """
    mgr = BitfinexManager(payload.bfx_key, payload.bfx_secret)

    # Step 1: Test connection — POST /v2/auth/r/info/user
    user_data, err = await mgr.info_user()
    if err:
        return None, {"error": "Invalid API Key or Secret."}
    if not user_data or not isinstance(user_data, list):
        return None, {"error": "Invalid API Key or Secret."}
    try:
        master_id = str(user_data[0])
    except (IndexError, TypeError):
        return None, {"error": "Invalid API Key or Secret."}

    # Step 2: Permission check — POST /v2/auth/r/permissions
    perms_data, err = await mgr.permissions()
    if err:
        return None, {
            "error": "Missing permissions: Could not fetch permissions. Please enable Wallets (Read), Funding (Read/Write), and History (Read) in your Bitfinex API settings.",
            "permissions_url": "https://setting.bitfinex.com/api",
        }
    ok, missing_list = _check_permissions_response(perms_data)
    if not ok:
        missing_str = ", ".join(missing_list)
        return None, {
            "error": f"Missing permissions: {missing_str}. Please enable them in your Bitfinex API settings.",
            "permissions_url": "https://setting.bitfinex.com/api",
        }

    # Step 3: Validate lending — wallets (funding with balance), funding/offers, funding/trades/hist
    wallets, err = await mgr.wallets()
    if err:
        return None, {"error": "Could not fetch wallets. Please check API permissions."}
    if not wallets or not isinstance(wallets, list):
        return None, {"error": "Could not fetch wallets."}
    has_funding = False
    for w in wallets:
        try:
            w_type = w[0]
            bal = float(w[2]) if len(w) > 2 else 0
        except (IndexError, TypeError, ValueError):
            continue
        if w_type == "funding":
            has_funding = True
            break
    if not has_funding:
        return None, {"error": "No funding wallet found. Please ensure a Bitfinex funding wallet exists."}
    _, err_offers = await mgr.funding_offers()
    if err_offers:
        return None, {
            "error": "Missing permissions: Funding (Read). Please enable them in your Bitfinex API settings.",
            "permissions_url": "https://setting.bitfinex.com/api",
        }
    _, err_hist = await mgr.funding_trades_hist()
    if err_hist:
        return None, {
            "error": "Missing permissions: Funding history (Read). Please enable them in your Bitfinex API settings.",
            "permissions_url": "https://setting.bitfinex.com/api",
        }

    # Step 4: (Errors returned above with specific messages and link.)

    # Step 5: Save validated key — encrypt API_SECRET (Fernet), save to DB
    balance = await mgr.compute_usd_balances()

    hashed_id = hash_bitfinex_id(master_id)
    existing = (
        db.query(models.TrialHistory)
        .filter(models.TrialHistory.hashed_bitfinex_id == hashed_id)
        .first()
    )
    if existing:
        return None, {
            "error": "This Bitfinex account has already used the Free Trial. Please upgrade.",
        }

    trial_row = models.TrialHistory(hashed_bitfinex_id=hashed_id)
    db.add(trial_row)

    current_user.plan_tier = "trial"
    current_user.rebalance_interval = 30  # free tier: 30-min rebalancing
    # No 7-day trial; free tier uses token credit (100 tokens)

    vault = (
        db.query(models.APIVault)
        .filter(models.APIVault.user_id == current_user.id)
        .first()
    )
    if not vault:
        vault = models.APIVault(user_id=current_user.id)
        db.add(vault)

    vault.encrypted_key = security.encrypt_key(payload.bfx_key)
    vault.encrypted_secret = security.encrypt_key(payload.bfx_secret)
    if payload.gemini_key:
        vault.encrypted_gemini_key = security.encrypt_key(payload.gemini_key)
    vault.keys_updated_at = datetime.utcnow()

    db.commit()
    snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == current_user.id).first()
    if snap:
        if hasattr(snap, "invalid_key_days"):
            snap.invalid_key_days = 0
        if hasattr(snap, "reconciliation_completed"):
            snap.reconciliation_completed = False  # 23:00 sweep will run reconciliation if key restored post-11:15
        db.commit()
    return balance, {"message": "Exchange connected and trial activated."}


# Dev-only: connect exchange by user_id (no Google token). Set ALLOW_DEV_CONNECT=1 to enable.
class ConnectByUserInput(BaseModel):
    user_id: int
    bfx_key: str
    bfx_secret: str
    gemini_key: Optional[str] = None


class ConnectByEmailInput(BaseModel):
    email: str
    bfx_key: str
    bfx_secret: str
    gemini_key: Optional[str] = None


class DevLoginAsInput(BaseModel):
    email: str


class DevJwtForUserInput(BaseModel):
    user_id: int


class DevCreateTestUserInput(BaseModel):
    email: str
    referral_code: Optional[str] = None  # optional; if set, user.referred_by = referrer with this code


def _get_or_create_user_by_email(email: str, db: Session) -> models.User:
    """Find user by email, or create one (dev only). Email must be @gmail.com."""
    email = (email or "").strip().lower()
    if not email or not email.endswith("@gmail.com"):
        raise HTTPException(status_code=400, detail="Only @gmail.com accounts are allowed.")
    user = db.query(models.User).filter(models.User.email == email).first()
    if user:
        return user
    new_user = models.User(
        email=email,
        plan_tier="trial",
        rebalance_interval=30,
    )
    new_user.referral_code = f"ref-{abs(hash(email)) % 10_000_000}"
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    _award_registration_tokens(new_user.id, db)
    return new_user


@app.post("/connect-exchange/by-email")
async def connect_exchange_by_email(
    payload: ConnectByEmailInput,
    db: Session = Depends(database.get_db),
):
    """Dev-only: find or create user by email and save API keys. Set ALLOW_DEV_CONNECT=1."""
    if os.getenv("ALLOW_DEV_CONNECT") != "1":
        raise HTTPException(status_code=404, detail="Not available.")
    user = _get_or_create_user_by_email(payload.email, db)
    vault_existing = (
        db.query(models.APIVault).filter(models.APIVault.user_id == user.id).first()
    )
    keys_payload = APIKeysInput(
        bfx_key=payload.bfx_key,
        bfx_secret=payload.bfx_secret,
        gemini_key=payload.gemini_key,
    )
    balance, result = await _validate_and_save_bitfinex_keys(keys_payload, user, db)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    if not vault_existing:
        await _trigger_bot_start_after_keys_saved(user.id, db)
    return {
        "status": "success",
        "message": result.get("message", "Exchange connected and trial activated."),
        "balance": balance,
        "user_id": user.id,
    }


@app.post("/connect-exchange/update-by-email")
async def connect_exchange_update_by_email(
    payload: ConnectByEmailInput,
    db: Session = Depends(database.get_db),
):
    """Dev-only: update API keys for an existing user by email (skips trial check). Set ALLOW_DEV_CONNECT=1."""
    if os.getenv("ALLOW_DEV_CONNECT") != "1":
        raise HTTPException(status_code=404, detail="Not available.")
    user = db.query(models.User).filter(models.User.email == payload.email.strip().lower()).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    keys_payload = APIKeysInput(
        bfx_key=payload.bfx_key,
        bfx_secret=payload.bfx_secret,
        gemini_key=payload.gemini_key,
    )
    balance, err = await _validate_bitfinex_keys_only(keys_payload)
    if err:
        raise HTTPException(status_code=400, detail=err.get("error", "Validation failed."))
    vault = db.query(models.APIVault).filter(models.APIVault.user_id == user.id).first()
    vault_existing = vault is not None
    if not vault:
        vault = models.APIVault(user_id=user.id)
        db.add(vault)
    vault.encrypted_key = security.encrypt_key(payload.bfx_key)
    vault.encrypted_secret = security.encrypt_key(payload.bfx_secret)
    if payload.gemini_key is not None:
        vault.encrypted_gemini_key = security.encrypt_key(payload.gemini_key) if payload.gemini_key else None
    vault.keys_updated_at = datetime.utcnow()
    db.commit()
    snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user.id).first()
    if snap:
        if hasattr(snap, "invalid_key_days"):
            snap.invalid_key_days = 0
        if hasattr(snap, "reconciliation_completed"):
            snap.reconciliation_completed = False
        db.commit()
    if not vault_existing:
        await _trigger_bot_start_after_keys_saved(user.id, db)
    return {
        "status": "success",
        "message": "API keys updated.",
        "balance": balance,
        "user_id": user.id,
    }


@app.post("/dev/create-test-user")
async def dev_create_test_user(
    payload: DevCreateTestUserInput,
    db: Session = Depends(database.get_db),
):
    """Dev-only: create a new user by email and award registration tokens (no API keys). Optional referral_code links to referrer. Set ALLOW_DEV_CONNECT=1."""
    if os.getenv("ALLOW_DEV_CONNECT") != "1":
        raise HTTPException(status_code=404, detail="Not available.")
    email = (payload.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="email required.")
    user = _get_or_create_user_by_email(email, db)
    if payload.referral_code:
        referrer = db.query(models.User).filter(models.User.referral_code == payload.referral_code.strip()).first()
        if referrer:
            user.referred_by = referrer.id
            db.commit()
            db.refresh(user)
    return {"user_id": user.id, "email": user.email, "referral_code": user.referral_code}


@app.post("/dev/login-as")
async def dev_login_as(
    payload: DevLoginAsInput,
    db: Session = Depends(database.get_db),
):
    """Dev-only: return a backend JWT for the given email (bypass Google). Set ALLOW_DEV_CONNECT=1 and NEXTAUTH_SECRET."""
    if os.getenv("ALLOW_DEV_CONNECT") != "1":
        raise HTTPException(status_code=404, detail="Not available.")
    if not NEXTAUTH_SECRET:
        raise HTTPException(status_code=500, detail="NEXTAUTH_SECRET not set.")
    email = (payload.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="email required.")
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    import time
    now = int(time.time())
    payload = {"email": user.email, "sub": str(user.id), "iat": now, "exp": now + 24 * 3600}
    token = jwt.encode(payload, NEXTAUTH_SECRET, algorithm="HS256")
    return {"token": token}


@app.post("/dev/jwt-for-user")
async def dev_jwt_for_user(
    payload: DevJwtForUserInput,
    db: Session = Depends(database.get_db),
):
    """Dev-only: return a backend JWT for the given user_id. Requires ALLOW_DEV_CONNECT=1."""
    if os.getenv("ALLOW_DEV_CONNECT") != "1":
        raise HTTPException(status_code=404, detail="Not available.")
    if not NEXTAUTH_SECRET:
        raise HTTPException(status_code=500, detail="NEXTAUTH_SECRET not set.")
    user = db.query(models.User).filter(models.User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    import time
    now = int(time.time())
    jwt_payload = {"email": user.email, "sub": str(user.id), "iat": now, "exp": now + 24 * 3600}
    token = jwt.encode(jwt_payload, NEXTAUTH_SECRET, algorithm="HS256")
    return {"token": token}


@app.post("/connect-exchange/by-user")
async def connect_exchange_by_user(
    payload: ConnectByUserInput,
    db: Session = Depends(database.get_db),
):
    if os.getenv("ALLOW_DEV_CONNECT") != "1":
        raise HTTPException(status_code=404, detail="Not available.")
    user = db.query(models.User).filter(models.User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    vault_existing = (
        db.query(models.APIVault).filter(models.APIVault.user_id == user.id).first()
    )
    keys_payload = APIKeysInput(
        bfx_key=payload.bfx_key,
        bfx_secret=payload.bfx_secret,
        gemini_key=payload.gemini_key,
    )
    balance, result = await _validate_and_save_bitfinex_keys(keys_payload, user, db)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    if not vault_existing:
        await _trigger_bot_start_after_keys_saved(user.id, db)
    return {
        "status": "success",
        "message": result.get("message", "Exchange connected and trial activated."),
        "balance": balance,
    }


# --- Start / Stop Bot (idempotent; clear ARQ keys to allow re-enqueue after stop) ---
STOP_BOT_DEBUG_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stop_bot_debug.log")


def _write_stop_bot_debug(user_id: int, status_before: str, aborted: Optional[bool], error: Optional[str]) -> None:
    """Append one line to stop_bot_debug.log for debugging stop-bot failures."""
    try:
        log_dir = os.path.dirname(STOP_BOT_DEBUG_LOG)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat()
        err = f" error={error!r}" if error else ""
        line = f"{ts} user_id={user_id} status_before={status_before} aborted={aborted}{err}\n"
        with open(STOP_BOT_DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
    except Exception as e:
        logger.warning("stop_bot_debug: failed to write %s: %s", STOP_BOT_DEBUG_LOG, e)


ARQ_JOB_PREFIX = "arq:job:"
ARQ_RESULT_PREFIX = "arq:result:"
ARQ_QUEUE_NAME = "arq:queue"
# When stop_bot calls job.abort(), ARQ adds job_id to this sorted set. Clear it on re-enqueue so the new job is not "aborted before start".
try:
    from arq.constants import abort_jobs_ss as ARQ_ABORT_SS
except ImportError:
    ARQ_ABORT_SS = "arq:abort"


async def _clear_arq_job_keys(redis, job_id: str) -> None:
    """Remove ARQ keys for job_id so the same id can be enqueued again (idempotent start after stop).
    Must also remove job_id from the abort sorted set (arq:abort), otherwise the worker sees it as aborted and logs 'aborted before start'."""
    try:
        await redis.delete(ARQ_JOB_PREFIX + job_id, ARQ_RESULT_PREFIX + job_id)
        # Using gather to execute zrem in parallel to save round-trip latency to Upstash
        await asyncio.gather(
            redis.zrem(ARQ_QUEUE_NAME, job_id),
            redis.zrem(ARQ_ABORT_SS, job_id),
            return_exceptions=True
        )
    except Exception:
        pass


async def _enqueue_bot_task(redis, user_id: int) -> bool:
    """Enqueue run_bot_task for user_id. Returns True if enqueued, False if already running/queued.
    Checks the per-user Redis run lock first to prevent enqueue while a previous run is still active.
    """
    job_id = f"bot_user_{user_id}"
    lock_key = f"bot_run_lock:{user_id}"
    try:
        existing_lock = await redis.get(lock_key)
        if existing_lock is not None:
            logger.info("_enqueue_bot_task user_id=%s skipped: run lock held (another instance active)", user_id)
            return False
    except Exception:
        pass
    await _clear_arq_job_keys(redis, job_id)
    job = await redis.enqueue_job("run_bot_task", user_id, _job_id=job_id)
    if job is not None:
        return True
    await _clear_arq_job_keys(redis, job_id)
    job = await redis.enqueue_job("run_bot_task", user_id, _job_id=job_id)
    return job is not None


@app.post("/start-bot")
async def start_bot(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    await _bot_action_rate_limit(current_user.id)
    await _check_start_cooldown(current_user.id)
    # Plan C: set desired state first
    if hasattr(current_user, "bot_desired_state"):
        current_user.bot_desired_state = "running"
    try:
        db.commit()
    except Exception:
        db.rollback()
    legacy = _get_token_balance_legacy(db, current_user.id)
    tokens_remaining = float(legacy[0]) if legacy else 0.0
    if tokens_remaining <= 0:
        return JSONResponse(
            status_code=400,
            content={
                "detail": "Insufficient tokens to run the bot.",
                "code": "INSUFFICIENT_TOKENS",
                "redirect_tab": "subscription",
            },
        )
    status_before = getattr(current_user, "bot_status", None) or "stopped"
    desired = getattr(current_user, "bot_desired_state", None) or "stopped"
    if status_before in ("running", "starting") and desired == "running":
        return {"status": "success", "message": "Bot already running or queued.", "bot_status": status_before}
    redis = await get_redis_or_raise()
    await _record_start_success(current_user.id)  # record so next start is cooldown-limited
    enqueued = await _enqueue_bot_task(redis, current_user.id)
    if enqueued:
        try:
            current_user.bot_status = "starting"
            db.commit()
            logger.info("start_bot user_id=%s action=start enqueued=True bot_status_before=%s bot_status_after=starting", current_user.id, status_before)
            return {"status": "success", "message": f"Bot queued for user {current_user.id}", "bot_status": "starting"}
        except Exception:
            db.rollback()
            logger.warning("start_bot user_id=%s db commit failed", current_user.id)
            return {"status": "success", "message": f"Bot queued for user {current_user.id}", "bot_status": "starting"}
    try:
        current_user.bot_status = current_user.bot_status or "starting"
        db.commit()
    except Exception:
        db.rollback()
    _rcache_invalidate_user(current_user.id)
    logger.info("start_bot user_id=%s action=start enqueued=False (already running/queued) bot_status=%s", current_user.id, getattr(current_user, "bot_status", None))
    return {"status": "success", "message": "Bot already running or queued.", "bot_status": getattr(current_user, "bot_status", None) or "running"}


@app.post("/stop-bot")
async def stop_bot(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    user_id = current_user.id
    logger.info("stop_bot ENTRY user_id=%s", user_id)
    await _bot_action_rate_limit(user_id)
    await _check_stop_cooldown(user_id)
    from arq.jobs import Job
    status_before = getattr(current_user, "bot_status", None) or "stopped"
    logger.info("stop_bot user_id=%s status_before=%s updating DB", user_id, status_before)
    # Plan C: DB first so UI never stuck on "starting" if job aborted before start
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if user:
            if hasattr(user, "bot_desired_state"):
                user.bot_desired_state = "stopped"
            if hasattr(user, "bot_status"):
                user.bot_status = "stopped"
            db.commit()
            logger.info("stop_bot user_id=%s DB updated bot_status=stopped", user_id)
        else:
            logger.warning("stop_bot user_id=%s user not found in DB", user_id)
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.exception("stop_bot user_id=%s DB update failed: %s", user_id, e)
    aborted = False
    job_id = f"bot_user_{user_id}"
    try:
        redis = await get_redis_or_raise()
        await _record_stop_success(user_id)  # record so next stop is cooldown-limited
        logger.info("stop_bot user_id=%s job_id=%s calling job.abort(timeout=5)", user_id, job_id)
        job = Job(job_id=job_id, redis=redis)
        aborted = await job.abort(timeout=5)
        logger.info("stop_bot user_id=%s job.abort() returned aborted=%s", user_id, aborted)
        await _clear_arq_job_keys(redis, job_id)
        # Release the per-user run lock so a fresh start can proceed immediately
        try:
            await redis.delete(f"bot_run_lock:{user_id}")
        except Exception:
            pass
        logger.info("stop_bot user_id=%s ARQ keys + run lock cleared", user_id)
    except asyncio.TimeoutError:
        _write_stop_bot_debug(user_id, status_before, False, "job.abort() timed out (5s)")
        try:
            redis = await get_redis_or_raise()
            await _clear_arq_job_keys(redis, job_id)
            await redis.delete(f"bot_run_lock:{user_id}")
        except Exception as e2:
            logger.exception("stop_bot user_id=%s clear keys after timeout failed: %s", user_id, e2)
        logger.warning("stop_bot user_id=%s abort timed out (5s), cleared keys+lock", user_id)
    except Exception as e:
        logger.exception("stop_bot user_id=%s Redis/job.abort failed: %s", user_id, e)
        _write_stop_bot_debug(user_id, status_before, False, str(e))
        try:
            redis = await get_redis_or_raise()
            await _clear_arq_job_keys(redis, job_id)
            await redis.delete(f"bot_run_lock:{user_id}")
            logger.info("stop_bot user_id=%s ARQ keys + run lock cleared after exception", user_id)
        except Exception as e2:
            logger.exception("stop_bot user_id=%s clear_arq_job_keys failed: %s", user_id, e2)
    _rcache_invalidate_user(user_id)
    logger.info("stop_bot EXIT user_id=%s aborted=%s bot_status_before=%s bot_status_after=stopped", user_id, aborted, status_before)
    _write_stop_bot_debug(user_id, status_before, aborted, None)
    return {"status": "success", "message": "Shutdown signal sent" if aborted else "Bot stopped.", "bot_status": "stopped"}


# Legacy-style control endpoints that address bots by numeric user_id directly.
# Secured: require auth and current_user.id == user_id (prevents abuse / one user controlling another's bot).
@app.post("/start-bot/{user_id}")
async def start_bot_for_user(
    user_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to start bot for another user.")
    await _bot_action_rate_limit(current_user.id)
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user or not user.vault:
            raise HTTPException(status_code=404, detail="API keys not found.")
        # Plan C: set desired state first; keep token check (Q2)
        if hasattr(user, "bot_desired_state"):
            user.bot_desired_state = "running"
        try:
            db.commit()
        except Exception:
            db.rollback()
        legacy = _get_token_balance_legacy(db, user_id)
        tokens_remaining = float(legacy[0]) if legacy else 0.0
        if tokens_remaining <= 0:
            raise HTTPException(status_code=400, detail="Insufficient tokens to run the bot.")
        status_before = getattr(user, "bot_status", None) or "stopped"
        desired = getattr(user, "bot_desired_state", None) or "stopped"
        if status_before in ("running", "starting") and desired == "running":
            return {"status": "success", "message": "Bot already running or queued.", "bot_status": status_before}
        redis = await get_redis_or_raise()
        enqueued = await _enqueue_bot_task(redis, user.id)
        if enqueued:
            try:
                user.bot_status = "starting"
                db.commit()
            except Exception:
                db.rollback()
            logger.info("start_bot_for_user user_id=%s enqueued=True bot_status_before=%s bot_status_after=starting", user_id, status_before)
            return {"status": "success", "message": f"Bot queued for user {user.id}", "bot_status": "starting"}
        try:
            db.refresh(user)
        except Exception:
            pass
        logger.info("start_bot_for_user user_id=%s enqueued=False (already running/queued)", user_id)
        return {"status": "success", "message": "Bot already running or queued.", "bot_status": getattr(user, "bot_status", None) or "running"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("start_bot_failed user_id=%s: %s", user_id, e)
        raise HTTPException(status_code=500, detail="Failed to start bot. Please try again.")


@app.post("/stop-bot/{user_id}")
async def stop_bot_for_user(
    user_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to stop bot for another user.")
    await _bot_action_rate_limit(current_user.id)
    from arq.jobs import Job
    user = db.query(models.User).filter(models.User.id == user_id).first()
    status_before = getattr(user, "bot_status", None) if user else None
    # Plan C: DB first (same logic as authenticated stop)
    if user:
        try:
            if hasattr(user, "bot_desired_state"):
                user.bot_desired_state = "stopped"
            if hasattr(user, "bot_status"):
                user.bot_status = "stopped"
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
    aborted = False
    try:
        redis = await get_redis_or_raise()
        job_id = f"bot_user_{user_id}"
        job = Job(job_id=job_id, redis=redis)
        aborted = await job.abort(timeout=5)
        await _clear_arq_job_keys(redis, job_id)
        try:
            await redis.delete(f"bot_run_lock:{user_id}")
        except Exception:
            pass
    except asyncio.TimeoutError:
        try:
            redis = await get_redis_or_raise()
            await _clear_arq_job_keys(redis, f"bot_user_{user_id}")
            await redis.delete(f"bot_run_lock:{user_id}")
        except Exception:
            pass
        logger.warning("stop_bot_for_user user_id=%s abort timed out (5s), cleared keys+lock", user_id)
    except Exception:
        try:
            redis = await get_redis_or_raise()
            await _clear_arq_job_keys(redis, f"bot_user_{user_id}")
            await redis.delete(f"bot_run_lock:{user_id}")
        except Exception:
            pass
    logger.info("stop_bot_for_user user_id=%s aborted=%s bot_status_before=%s bot_status_after=stopped", user_id, aborted, status_before)
    return {"status": "success", "message": "Shutdown signal sent" if aborted else "Bot stopped.", "bot_status": "stopped"}


@app.post("/dev/run-daily-deduction")
def dev_run_daily_deduction(db: Session = Depends(database.get_db)):
    """Dev-only: run daily token deduction once (same logic as 10:30 UTC scheduler; uses stored snapshot only). Set ALLOW_DEV_CONNECT=1."""
    if os.getenv("ALLOW_DEV_CONNECT") != "1":
        raise HTTPException(status_code=404, detail="Not available.")
    mult = _get_deduction_multiplier(db)
    log_entries, err = run_daily_token_deduction(db, deduction_multiplier=mult)
    if err:
        logger.error("dev_run_daily_deduction failed: %s", err)
        raise HTTPException(status_code=500, detail="Deduction failed. Check server logs.")
    return {"status": "success", "count": len(log_entries), "entries": log_entries}


@app.delete("/dev/users/by-email")
def dev_delete_user_by_email(
    email: str = Query(..., description="Email of test user to delete"),
    db: Session = Depends(database.get_db),
):
    """Dev-only: delete a user by email and all related data (for test cleanup). Set ALLOW_DEV_CONNECT=1."""
    if os.getenv("ALLOW_DEV_CONNECT") != "1":
        raise HTTPException(status_code=404, detail="Not available.")
    email = (email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="email required.")
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        return {"deleted": False, "message": "User not found."}
    uid = user.id
    db.query(models.User).filter(models.User.referred_by == uid).update({models.User.referred_by: None})
    db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == uid).delete()
    db.query(models.UserUsdtCredit).filter(models.UserUsdtCredit.user_id == uid).delete()
    db.query(models.UsdtHistory).filter(models.UsdtHistory.user_id == uid).delete()
    db.query(models.ReferralReward).filter(
        (models.ReferralReward.burning_user_id == uid) |
        (models.ReferralReward.level_1_id == uid) |
        (models.ReferralReward.level_2_id == uid) |
        (models.ReferralReward.level_3_id == uid),
    ).delete(synchronize_session=False)
    if hasattr(models, "DeductionLog"):
        db.query(models.DeductionLog).filter(models.DeductionLog.user_id == uid).delete()
    db.query(models.WithdrawalRequest).filter(models.WithdrawalRequest.user_id == uid).delete()
    db.query(models.PerformanceLog).filter(models.PerformanceLog.user_id == uid).delete()
    db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == uid).delete()
    db.query(models.APIVault).filter(models.APIVault.user_id == uid).delete()
    db.query(models.User).filter(models.User.id == uid).delete()
    db.commit()
    return {"deleted": True, "user_id": uid, "email": email}


# --- Stats Endpoint ---
@app.get("/stats/{user_id}", response_model=StatsResponse)
def get_stats(
    user_id: int,
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this user.")
    """
    Returns Choice A style stats:
    - Gross Profit
    - Fake Fee (20% of Gross)
    - Net Profit

    For now we interpret PerformanceLog.waroc as a gross PnL-style figure per user,
    aggregated over an optional date range.
    """
    try:
        q = db.query(models.PerformanceLog).filter(models.PerformanceLog.user_id == user_id)
        if start:
            q = q.filter(models.PerformanceLog.timestamp >= start)
        if end:
            q = q.filter(models.PerformanceLog.timestamp <= end)

        logs = q.all()
        gross = float(sum((log.waroc or 0.0) for log in logs)) if logs else 0.0
        fake_fee = gross * 0.2
        net = gross - fake_fee
        return StatsResponse(gross_profit=gross, fake_fee=fake_fee, net_profit=net)
    except (ProgrammingError, SQLAlchemyError):
        return StatsResponse(gross_profit=0.0, fake_fee=0.0, net_profit=0.0)


@app.get("/stats/{user_id}/history")
def get_stats_history(
    user_id: int,
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this user.")
    """
    Returns time-series for Gross Profit / True ROI charts from performance_logs (and trial/funding data).
    When tables are empty, returns [] so the frontend can show "No data yet".
    """
    try:
        q = db.query(models.PerformanceLog).filter(models.PerformanceLog.user_id == user_id).order_by(models.PerformanceLog.timestamp.asc())
        if start:
            q = q.filter(models.PerformanceLog.timestamp >= start)
        if end:
            q = q.filter(models.PerformanceLog.timestamp <= end)
        logs = q.all()
        out = []
        cumulative = 0.0
        for log in logs:
            ts = getattr(log, "timestamp", None)
            date_str = ts.strftime("%m-%d") if ts else ""
            waroc = float(getattr(log, "waroc", 0) or 0.0)
            cumulative += waroc
            out.append({
                "date": date_str,
                "volume": float(getattr(log, "total_assets", 0) or 0.0),
                "interest": waroc,
                "cumulative": cumulative,
            })
        return out
    except (ProgrammingError, SQLAlchemyError):
        return []
    except Exception as e:
        logger.exception("stats/%s/history failed: %s", user_id, e)
        return []


async def _fetch_all_funding_trades(
    mgr: BitfinexManager,
    start_ms: Optional[int],
    end_ms: Optional[int] = None,
    limit_per_request: int = 1000,
) -> tuple[list, Optional[str]]:
    """
    Fetch all repaid lending trades between start_ms and end_ms (or now) from Bitfinex.
    Uses POST /v2/auth/r/funding/trades/hist (Bitfinex auth uses POST; this is the funding trades endpoint).
    Paginates until no more results.
    """
    if end_ms is None:
        end_ms = int(datetime.utcnow().timestamp() * 1000)
    all_trades: list = []
    current_end = end_ms
    while True:
        trades, err = await mgr.funding_trades_hist(
            start_ms=start_ms,
            end_ms=current_end,
            limit=limit_per_request,
        )
        if err:
            return all_trades, err
        if not isinstance(trades, list) or len(trades) == 0:
            break
        all_trades.extend(trades)
        if len(trades) < limit_per_request:
            break
        min_mts = min(
            (row[2] for row in trades if isinstance(row, (list, tuple)) and len(row) > 2),
            default=0,
        )
        if min_mts <= (start_ms or 0):
            break
        current_end = min_mts - 1
        await asyncio.sleep(0.2)
    return all_trades, None


# Stablecoins: use 1:1 USD when Bitfinex ticker missing or zero (e.g. tUSTUSD may be delisted)
_STABLECOINS_1TO1 = frozenset(("USD", "USDt", "USDT", "UST", "USDC", "DAI", "TUSD", "BUSD", "FRAX"))


def _usd_price_for_currency(currency: str, ticker_prices: Dict[str, float]) -> float:
    """Return USD price for a currency: 1 for stablecoins (USD, USDt, USDT, UST, etc.), else from ticker t{CCY}USD."""
    if currency in _STABLECOINS_1TO1:
        return 1.0
    return ticker_prices.get(f"t{currency}USD", 0.0) or 0.0


def _interest_usd_from_trades(trades: Any, ticker_prices: Dict[str, float]) -> float:
    """Sum interest from Bitfinex funding trade arrays. See _interest_usd_from_trades_with_breakdown for formula."""
    total, _ = _interest_usd_from_trades_with_breakdown(trades, ticker_prices)
    return total


def _interest_usd_from_trades_with_breakdown(
    trades: Any, ticker_prices: Dict[str, float]
) -> tuple[float, List[CurrencyBreakdownItem]]:
    """
    Sum interest from Bitfinex funding trade arrays. Each row: [ID, CURRENCY, MTS_CREATE, OFFER_ID, AMOUNT, RATE, PERIOD, ...].
    Interest per trade = |AMOUNT| * RATE * (PERIOD/365 days). Convert to USD: stablecoins=1:1, others use ticker_prices.
    Returns (total_usd, per_currency_breakdown).
    """
    breakdown: List[CurrencyBreakdownItem] = []
    if not isinstance(trades, list):
        return 0.0, breakdown
    by_currency: Dict[str, float] = {}
    for row in trades:
        try:
            if not isinstance(row, (list, tuple)) or len(row) < 7:
                continue
            currency = (row[1] or "").strip().upper()
            if currency.startswith("F"):
                currency = currency[1:]
            amount = float(row[4]) if row[4] is not None else 0.0
            rate = float(row[5]) if row[5] is not None else 0.0
            period = float(row[6]) if row[6] is not None else 0.0
            if not currency or period <= 0:
                continue
            interest_ccy = abs(amount) * rate * (period / 365.0)
            if interest_ccy > 0:
                by_currency[currency] = by_currency.get(currency, 0.0) + interest_ccy
        except (TypeError, ValueError, IndexError):
            continue
    total_usd = 0.0
    for currency, interest_ccy in sorted(by_currency.items()):
        price = _usd_price_for_currency(currency, ticker_prices)
        interest_usd = interest_ccy * price if price else 0.0
        total_usd += interest_usd
        breakdown.append(CurrencyBreakdownItem(
            currency=currency,
            interest_ccy=round(interest_ccy, 6),
            ticker_price_usd=price,
            interest_usd=round(interest_usd, 6),
        ))
    return total_usd, breakdown


def _trades_with_interest_usd(trades: Any, ticker_prices: Dict[str, float]) -> List[FundingTradeRecord]:
    """
    Convert Bitfinex funding trade arrays to FundingTradeRecord with interest_usd per trade.
    Same formula as _interest_usd_from_trades: |AMOUNT| * RATE * (PERIOD/365), then to USD.
    """
    out: List[FundingTradeRecord] = []
    if not isinstance(trades, list):
        return out
    for row in trades:
        try:
            if not isinstance(row, (list, tuple)) or len(row) < 7:
                continue
            trade_id = int(row[0]) if row[0] is not None else 0
            currency = (row[1] or "").strip()
            if currency.startswith("f") or currency.startswith("F"):
                currency = currency[1:]
            currency = currency.upper() if currency else ""
            mts_create = int(row[2]) if row[2] is not None else 0
            offer_id = int(row[3]) if row[3] is not None else 0
            amount = float(row[4]) if row[4] is not None else 0.0
            rate = float(row[5]) if row[5] is not None else 0.0
            period = float(row[6]) if row[6] is not None else 0.0
            interest_ccy = abs(amount) * rate * (period / 365.0) if period > 0 else 0.0
            price = _usd_price_for_currency(currency, ticker_prices)
            interest_usd = interest_ccy * price if price else 0.0
            out.append(FundingTradeRecord(
                id=trade_id,
                currency=currency or row[1],
                mts_create=mts_create,
                offer_id=offer_id,
                amount=amount,
                rate=rate,
                period=period,
                interest_usd=round(interest_usd, 6),
            ))
        except (TypeError, ValueError, IndexError):
            continue
    return out


def _currencies_from_trades(trades: Any) -> set:
    """Collect unique non-USD currencies from trades (for fold ticker union)."""
    need_price = set()
    if isinstance(trades, list):
        for row in trades:
            try:
                if isinstance(row, (list, tuple)) and len(row) >= 2:
                    c = (row[1] or "").strip().upper()
                    if c.startswith("F"):
                        c = c[1:]
                    if c and c not in ("USD", "USDt", "USDT"):
                        need_price.add(c)
            except (TypeError, IndexError):
                pass
    return need_price


def _ticker_prices_from_trades(trades: Any) -> Dict[str, float]:
    """Collect unique non-USD currencies from trades and fetch their USD prices."""
    need_price = _currencies_from_trades(trades)
    if not need_price:
        return {}
    from services.bitfinex_service import _get_tickers_sync
    symbols = [f"t{c}USD" for c in need_price]
    tickers, _ = _get_tickers_sync(symbols)
    out: Dict[str, float] = {}
    if tickers:
        for row in tickers:
            try:
                if isinstance(row, (list, tuple)) and len(row) >= 8:
                    sym = (row[0] or "").strip()
                    price = float(row[7]) if row[7] is not None else 0.0
                    if sym:
                        out[sym] = price
            except (TypeError, ValueError, IndexError):
                continue
    return out


def _max_mts_from_trades(trades: list) -> Optional[int]:
    """Return max MTS_CREATE (index 2) from trade rows, or None if empty."""
    if not trades:
        return None
    mts_list = [
        row[2] for row in trades
        if isinstance(row, (list, tuple)) and len(row) > 2 and row[2] is not None
    ]
    return max(mts_list) if mts_list else None


# --- Ledgers-based gross profit (Margin Funding Payment): from user registration to latest ---
MARGIN_FUNDING_PAYMENT_DESC = "Margin Funding Payment"

# All lending market profit: fetch ledgers for these currencies when Option B (credits+wallets) is not used.
# Stablecoins first; then common funding currencies so we never miss a market (Option A fallback).
LEDGER_FUNDING_CURRENCIES = (
    "USD", "USDT", "USDt", "UST",
    "BTC", "ETH", "XRP", "LTC", "EOS", "XLM",
    "SOL", "AVAX", "DOT", "MATIC", "LINK", "UNI", "AAVE", "ATOM", "DOGE", "ADA",
)
# Always include these in ledger fetch so stablecoin profit is never missed (Option B minimum).
_LEDGER_STABLECOINS_ALWAYS = frozenset(("USD", "USDT", "USDt", "UST"))


async def _get_ledger_currencies_for_user(mgr: BitfinexManager) -> Optional[List[str]]:
    """
    Option B: Get currencies the user has funding activity in (credits + wallets), so we fetch
    ledgers only for those and minimize API calls. Returns sorted list or None on error.
    Always includes USD, USDT, USDt, UST so stablecoin profit is never missed.
    """
    try:
        credits, err_c = await mgr.funding_credits(symbol=None)
        wallets, err_w = await mgr.wallets()
        currencies: set = set(_LEDGER_STABLECOINS_ALWAYS)
        if isinstance(credits, list):
            for row in credits:
                try:
                    if isinstance(row, (list, tuple)) and len(row) > 1:
                        sym = (row[1] or "").strip().upper()
                        if sym.startswith("F"):
                            sym = sym[1:]
                        if sym:
                            currencies.add(sym)
                except (TypeError, IndexError):
                    pass
        if isinstance(wallets, list):
            for w in wallets:
                try:
                    if isinstance(w, (list, tuple)) and len(w) > 2 and (w[0] or "").strip().lower() == "funding":
                        c = (w[1] or "").strip().upper()
                        if c:
                            currencies.add(c)
                except (TypeError, IndexError):
                    pass
        return sorted(currencies) if currencies else list(_LEDGER_STABLECOINS_ALWAYS)
    except Exception:
        return None


def _gross_and_fees_from_ledger_entries(
    entries: list,
    start_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
    usd_prices: Optional[Dict[str, float]] = None,
) -> tuple[float, float]:
    """
    Parse Bitfinex ledger entries. Entry format: [0]=ID, [1]=CURRENCY, [2]=WALLET, [3]=MTS, [4]=None, [5]=AMOUNT, [6]=BALANCE, [7]=None, [8]=DESCRIPTION.
    Margin Funding Payment: positive = gross earned, negative = fees paid.
    If start_ms/end_ms are set, only count entries where start_ms <= entry[3] <= end_ms.
    If usd_prices is provided (dict keyed by tCCYUSD e.g. tBTCUSD), convert each entry to USD using entry[1] and _usd_price_for_currency; else sum raw amounts (1:1 for stablecoins only).
    Returns (gross_usd, fees_usd).
    """
    gross = 0.0
    fees = 0.0
    for entry in entries:
        try:
            if not isinstance(entry, (list, tuple)) or len(entry) < 9:
                continue
            raw_ts = entry[3]
            ts_ms = int(raw_ts) if raw_ts is not None else None
            if start_ms is not None and (ts_ms is None or ts_ms < start_ms):
                continue
            if end_ms is not None and (ts_ms is None or ts_ms > end_ms):
                continue
            amount = entry[5] if entry[4] is None else entry[4]
            amount = float(amount) if amount is not None else 0.0
            desc = str(entry[8]) if len(entry) > 8 and entry[8] is not None else ""
            if MARGIN_FUNDING_PAYMENT_DESC not in desc:
                if "fee" in desc.lower() and amount < 0:
                    rate_fee = 1.0 if usd_prices is None else _usd_price_for_currency(str(entry[1]) if len(entry) > 1 else "USD", usd_prices)
                    fees += abs(amount) * rate_fee
                continue
            rate = 1.0 if usd_prices is None else _usd_price_for_currency(str(entry[1]) if len(entry) > 1 else "USD", usd_prices)
            if amount > 0:
                gross += amount * rate
            else:
                fees += abs(amount) * rate
        except (TypeError, ValueError, IndexError):
            continue
    return gross, fees


async def _fetch_ledgers_script_style(
    mgr: BitfinexManager,
    currency: str,
    limit: int = 100,
) -> tuple[list, Optional[str]]:
    """Fetch ledger entries with same API call as user script: POST body {"limit": limit} only (no start/end)."""
    data, err = await mgr.ledgers_hist(currency=currency, limit=limit)
    if err:
        return [], err
    if not isinstance(data, list):
        return [], None
    return data, None


def _is_ledger_data_complete(latest_entry_mts: Optional[int]) -> bool:
    """True if ledger is complete: latest entry is at least LEDGER_FRESHNESS_MINUTES old (Bitfinex finalized)."""
    if latest_entry_mts is None:
        return True
    now_ms = int(datetime.utcnow().timestamp() * 1000)
    return (now_ms - latest_entry_mts) >= (LEDGER_FRESHNESS_MINUTES * 60 * 1000)


async def _fetch_all_margin_funding_entries(
    mgr: BitfinexManager,
    currencies: Optional[List[str]] = None,
) -> tuple[list, Optional[int], Optional[str]]:
    """
    Fetch Margin Funding ledger for the given currencies (or LEDGER_FUNDING_CURRENCIES if None).
    Returns (merged_entries, latest_mts, err). Each entry has entry[1]=CURRENCY, entry[3]=MTS, entry[5]=AMOUNT.
    All amounts must be converted to USD by caller via _gross_and_fees_from_ledger_entries(..., usd_prices=...).
    """
    to_fetch = list(currencies) if currencies else list(LEDGER_FUNDING_CURRENCIES)
    all_entries: list = []
    latest_mts: Optional[int] = None
    last_err: Optional[str] = None
    for i, currency in enumerate(to_fetch):
        if i > 0:
            await asyncio.sleep(0.2)
        entries, err = await _fetch_ledgers_script_style(mgr, currency, limit=100)
        if err:
            last_err = err
            continue
        for e in entries:
            if isinstance(e, (list, tuple)) and len(e) > 3 and e[3] is not None:
                try:
                    ts = int(e[3])
                    if latest_mts is None or ts > latest_mts:
                        latest_mts = ts
                except (TypeError, ValueError):
                    pass
        all_entries.extend(entries)
    return all_entries, latest_mts, last_err


async def _daily_10_00_fetch_and_save(
    user_id: int,
    db: Session,
    accept_fresh_data: bool = False,
) -> tuple[bool, bool, Optional[str]]:
    """
    Single 10:00-style API call: fetch Margin Funding ledger, validate completeness, then save.
    Returns (success, data_incomplete, error_message).
    If data_incomplete (latest entry < 20 mins old) and not accept_fresh_data: do not save; return (False, True, None). Caller may retry at 10:10 or 10:30.
    When accept_fresh_data=True (e.g. 10:30 final fetch): skip completeness check so late-released Bitfinex data is saved.
    If complete: compute gross_profit_usd and daily_gross_profit_usd, save to user_profit_snapshot, return (True, False, None).
    If API error: return (False, False, err).
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or not user.vault:
        return False, False, "No user or vault"
    keys = user.vault.get_keys()
    mgr = BitfinexManager(keys["bfx_key"], keys["bfx_secret"])
    start_ms = None
    if getattr(user.vault, "created_at", None) and user.vault.created_at:
        start_ms = int(user.vault.created_at.timestamp() * 1000)
    if start_ms is None:
        return False, False, "No vault created_at"
    end_ms = int(datetime.utcnow().timestamp() * 1000)
    # Option B: fetch ledgers only for currencies user has activity in (credits + wallets); fallback to full list.
    ledger_currencies = await _get_ledger_currencies_for_user(mgr)
    if not ledger_currencies:
        ledger_currencies = list(LEDGER_FUNDING_CURRENCIES)
    entries, latest_mts, fetch_err = await _fetch_all_margin_funding_entries(mgr, currencies=ledger_currencies)
    if fetch_err and not entries:
        return False, False, fetch_err
    if not accept_fresh_data and not _is_ledger_data_complete(latest_mts):
        return False, True, None
    currencies_in_entries = {str(e[1]).strip() for e in entries if isinstance(e, (list, tuple)) and len(e) > 1 and e[1]}
    usd_prices = _fetch_ticker_prices(currencies_in_entries) if currencies_in_entries else {}
    gross, fees = _gross_and_fees_from_ledger_entries(entries, start_ms=start_ms, end_ms=end_ms, usd_prices=usd_prices)
    today = datetime.utcnow().date()
    start_today_ms = int(datetime(today.year, today.month, today.day).timestamp() * 1000)
    end_today_ms = start_today_ms + 86400 * 1000 - 1
    daily_gross, _ = _gross_and_fees_from_ledger_entries(entries, start_ms=start_today_ms, end_ms=end_today_ms, usd_prices=usd_prices)
    snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
    net = gross - fees
    if snap:
        snap.gross_profit_usd = round(gross, 2)
        snap.net_profit_usd = round(net, 2)
        snap.bitfinex_fee_usd = round(fees, 2)
        snap.updated_at = datetime.utcnow()
        if hasattr(snap, "daily_gross_profit_usd"):
            snap.daily_gross_profit_usd = round(daily_gross, 2)
        if hasattr(snap, "last_daily_cumulative_gross"):
            snap.last_daily_cumulative_gross = gross
        if hasattr(snap, "last_daily_snapshot_date"):
            snap.last_daily_snapshot_date = today
        if hasattr(snap, "account_switch_note"):
            snap.account_switch_note = None
        vault = db.query(models.APIVault).filter(models.APIVault.user_id == user_id).first()
        if vault and hasattr(snap, "last_vault_updated_at"):
            vault_updated = getattr(vault, "keys_updated_at", None)
            last_seen = getattr(snap, "last_vault_updated_at", None)

            def _ts(d):
                if d is None:
                    return 0
                return d.timestamp() if hasattr(d, "timestamp") and callable(getattr(d, "timestamp")) else 0

            if vault_updated and (last_seen is None or _ts(vault_updated) > _ts(last_seen)):
                if hasattr(snap, "account_switch_note"):
                    snap.account_switch_note = "Bitfinex account switched – new ledger data pulled"
                user_for_alert = db.query(models.User).filter(models.User.id == user_id).first()
                alert_email = getattr(user_for_alert, "email", None) if user_for_alert else None
                logger.warning(
                    "Bitfinex account switched: user_id=%s email=%s – daily deductions now use new account",
                    user_id, alert_email,
                )
                await _alert_admins_deduction_failure(
                    f"User {alert_email or user_id} (ID: {user_id}) switched Bitfinex accounts – daily deductions now use new ledger."
                )
            snap.last_vault_updated_at = vault_updated
    else:
        new_snap = models.UserProfitSnapshot(
            user_id=user_id,
            gross_profit_usd=round(gross, 2),
            net_profit_usd=round(net, 2),
            bitfinex_fee_usd=round(fees, 2),
        )
        db.add(new_snap)
        db.flush()
        if hasattr(new_snap, "daily_gross_profit_usd"):
            new_snap.daily_gross_profit_usd = round(daily_gross, 2)
        if hasattr(new_snap, "last_daily_cumulative_gross"):
            new_snap.last_daily_cumulative_gross = gross
        if hasattr(new_snap, "last_daily_snapshot_date"):
            new_snap.last_daily_snapshot_date = today
    db.commit()
    return True, False, None


async def _gross_profit_from_ledgers(
    mgr: BitfinexManager,
    start_ms: Optional[int] = None,
    fold_ticker_state: Optional[dict] = None,
) -> tuple[float, float, Optional[str]]:
    """
    Sum gross profit and fees from ledgers (Margin Funding Payment) for all lending currencies.
    Uses Option B: fetch only currencies user has activity in (credits + wallets); fallback to full list.
    Converts every currency to USD via ticker prices (stablecoins 1:1). No start_ms/end_ms filter (cumulative).
    """
    ledger_currencies = await _get_ledger_currencies_for_user(mgr)
    if not ledger_currencies:
        ledger_currencies = list(LEDGER_FUNDING_CURRENCIES)
    all_entries, _, last_err = await _fetch_all_margin_funding_entries(mgr, currencies=ledger_currencies)
    currencies_in_entries = {str(e[1]).strip() for e in all_entries if isinstance(e, (list, tuple)) and len(e) > 1 and e[1]}
    if currencies_in_entries:
        if fold_ticker_state:
            usd_prices = await _get_fold_ticker_prices(currencies_in_entries, fold_ticker_state)
        else:
            usd_prices = _fetch_ticker_prices(currencies_in_entries)
    else:
        usd_prices = {}
    total_gross, total_fees = _gross_and_fees_from_ledger_entries(all_entries, start_ms=None, end_ms=None, usd_prices=usd_prices)
    return round(total_gross, 6), round(total_fees, 6), last_err if (last_err is not None and total_gross == 0 and total_fees == 0) else None


async def _refresh_user_lending_snapshot(
    user_id: int, db: Session, fold_ticker_state: Optional[dict] = None
) -> tuple[LendingStatsResponse, bool, List[FundingTradeRecord]]:
    """
    Compute gross profit from Bitfinex: prefer ledgers (Margin Funding Payment from registration to latest),
    then fall back to funding trades. Persist to user_profit_snapshot and return (result, rate_limited, trade_records).
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or not user.vault:
        return LendingStatsResponse(gross_profit=0.0, bitfinex_fee=0.0, net_profit=0.0), False, []
    keys = user.vault.get_keys()
    mgr = BitfinexManager(keys["bfx_key"], keys["bfx_secret"])
    start_ms = None
    if getattr(user.vault, "created_at", None) and user.vault.created_at:
        start_ms = int(user.vault.created_at.timestamp() * 1000)
    snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()

    # Prefer ledgers-based gross profit (Margin Funding Payment between registration and latest)
    if start_ms is not None:
        gross_ledgers, fees_ledgers, err_ledgers = await _gross_profit_from_ledgers(mgr, start_ms, fold_ticker_state)
        if err_ledgers and bitfinex_cache.is_rate_limit_error(err_ledgers):
            if snap and snap.gross_profit_usd is not None:
                gross = float(snap.gross_profit_usd)
                return LendingStatsResponse(
                    gross_profit=gross, bitfinex_fee=round(gross * BITFINEX_LENDER_FEE_PCT, 2),
                    net_profit=round(gross * (1 - BITFINEX_LENDER_FEE_PCT), 2),
                    total_trades_count=getattr(snap, "total_trades_count", None),
                ), True, []
            return LendingStatsResponse(gross_profit=0.0, bitfinex_fee=0.0, net_profit=0.0), True, []
        if not err_ledgers:
            net_ledgers = gross_ledgers - fees_ledgers
            result = LendingStatsResponse(
                gross_profit=round(gross_ledgers, 2),
                bitfinex_fee=round(fees_ledgers, 2),
                net_profit=round(net_ledgers, 2),
            )
            if snap:
                snap.gross_profit_usd = result.gross_profit
                snap.net_profit_usd = result.net_profit
                snap.bitfinex_fee_usd = result.bitfinex_fee
                snap.updated_at = datetime.utcnow()
            else:
                db.add(models.UserProfitSnapshot(
                    user_id=user_id,
                    gross_profit_usd=result.gross_profit,
                    net_profit_usd=result.net_profit,
                    bitfinex_fee_usd=result.bitfinex_fee,
                ))
            db.commit()
            return result, False, []

    # Fallback: funding trades (repaid lending trades)
    last_mts = getattr(snap, "last_trade_mts", None) if snap else None
    incremental = last_mts is not None

    if incremental:
        # Only fetch new trades since last sync (one small batch → fewer API calls)
        fetch_start = last_mts + 1
        trades, err = await _fetch_all_funding_trades(mgr, fetch_start, end_ms=None, limit_per_request=500)
    else:
        # Full backfill from registration
        trades, err = await _fetch_all_funding_trades(mgr, start_ms)

    if bitfinex_cache.is_rate_limit_error(err):
        if snap and snap.gross_profit_usd is not None:
            gross = float(snap.gross_profit_usd)
            return LendingStatsResponse(
                gross_profit=gross, bitfinex_fee=round(gross * BITFINEX_LENDER_FEE_PCT, 2),
                net_profit=round(gross * (1 - BITFINEX_LENDER_FEE_PCT), 2),
                total_trades_count=getattr(snap, "total_trades_count", None),
            ), True, []
        return LendingStatsResponse(gross_profit=0.0, bitfinex_fee=0.0, net_profit=0.0), True, []
    records: List[FundingTradeRecord] = []
    breakdown_obj: Optional[CalculationBreakdown] = None
    if err:
        result = LendingStatsResponse(gross_profit=0.0, bitfinex_fee=0.0, net_profit=0.0)
        if snap:
            result = LendingStatsResponse(
                gross_profit=float(snap.gross_profit_usd or 0),
                bitfinex_fee=float(snap.bitfinex_fee_usd or 0),
                net_profit=float(snap.net_profit_usd or 0),
                total_trades_count=getattr(snap, "total_trades_count", None),
            )
    elif incremental and (not trades or len(trades) == 0):
        # No new trades; return current snapshot
        existing_gross = float(snap.gross_profit_usd or 0) if snap else 0.0
        result = LendingStatsResponse(
            gross_profit=round(existing_gross, 2),
            bitfinex_fee=round(existing_gross * BITFINEX_LENDER_FEE_PCT, 2),
            net_profit=round(existing_gross * (1 - BITFINEX_LENDER_FEE_PCT), 2),
            total_trades_count=getattr(snap, "total_trades_count", None) if snap else None,
        )
    else:
        if fold_ticker_state:
            currencies_trades = _currencies_from_trades(trades)
            ticker_prices = await _get_fold_ticker_prices(currencies_trades, fold_ticker_state) if currencies_trades else {}
        else:
            ticker_prices = _ticker_prices_from_trades(trades)
        gross_delta, per_currency_breakdown = _interest_usd_from_trades_with_breakdown(trades, ticker_prices)
        fee_delta = gross_delta * BITFINEX_LENDER_FEE_PCT
        net_delta = gross_delta - fee_delta
        if incremental and snap:
            existing_gross = float(snap.gross_profit_usd or 0)
            existing_net = float(snap.net_profit_usd or 0)
            existing_fee = float(snap.bitfinex_fee_usd or 0)
            gross = existing_gross + gross_delta
            net = existing_net + net_delta
            fee = existing_fee + fee_delta
            total_count = (getattr(snap, "total_trades_count", None) or 0) + len(trades)
            breakdown_obj = CalculationBreakdown(
                trades_count=len(trades),
                per_currency=per_currency_breakdown,
                total_gross_usd=round(gross_delta, 6),
                formula_note="Incremental: new interest added to stored gross. Interest per trade = |AMOUNT| * RATE * (PERIOD/365).",
            )
            result = LendingStatsResponse(
                gross_profit=round(gross, 2),
                bitfinex_fee=round(fee, 2),
                net_profit=round(net, 2),
                total_trades_count=total_count,
                calculation_breakdown=breakdown_obj,
            )
            records = _trades_with_interest_usd(trades, ticker_prices)
        else:
            gross = gross_delta
            fee = gross * BITFINEX_LENDER_FEE_PCT
            net = gross - fee
            breakdown_obj = CalculationBreakdown(
                trades_count=len(trades),
                per_currency=per_currency_breakdown,
                total_gross_usd=round(gross, 6),
                formula_note="Interest per trade = |AMOUNT| * RATE * (PERIOD/365 days). USD/USDt/USDT/UST use 1:1; others use Bitfinex t{CCY}USD price.",
            )
            result = LendingStatsResponse(
                gross_profit=round(gross, 2),
                bitfinex_fee=round(fee, 2),
                net_profit=round(net, 2),
                total_trades_count=len(trades),
                calculation_breakdown=breakdown_obj,
            )
            records = _trades_with_interest_usd(trades, ticker_prices)

    # Persist snapshot
    if snap:
        snap.gross_profit_usd = result.gross_profit
        snap.net_profit_usd = result.net_profit
        snap.bitfinex_fee_usd = result.bitfinex_fee
        snap.updated_at = datetime.utcnow()
        if hasattr(snap, "last_trade_mts"):
            new_max = _max_mts_from_trades(trades) if trades else None
            if new_max is not None:
                snap.last_trade_mts = new_max
        if hasattr(snap, "total_trades_count"):
            snap.total_trades_count = result.total_trades_count
    else:
        new_row = models.UserProfitSnapshot(
            user_id=user_id,
            gross_profit_usd=result.gross_profit,
            net_profit_usd=result.net_profit,
            bitfinex_fee_usd=result.bitfinex_fee,
            total_trades_count=result.total_trades_count,
        )
        new_max = _max_mts_from_trades(trades) if trades else None
        if new_max is not None and hasattr(models.UserProfitSnapshot, "last_trade_mts"):
            new_row.last_trade_mts = new_max
        db.add(new_row)
    db.commit()
    return result, False, records


async def _get_lending_stats_data(
    user_id: int, db: Session, source: Optional[str] = None, fold_ticker_state: Optional[dict] = None
) -> tuple[LendingStatsResponse, dict]:
    """
    Shared logic for lending stats. Returns (response, headers_dict).
    Used by GET /stats/{user_id}/lending and dashboard-fold.
    When fold_ticker_state is provided (from dashboard_fold), ticker is shared with wallets for single fetch.
    """
    out: dict = {}
    try:
        try:
            row = db.execute(
                text("SELECT gross_profit_usd, net_profit_usd, bitfinex_fee_usd FROM user_profit_snapshot WHERE user_id = :uid"),
                {"uid": user_id},
            ).fetchone()
        except Exception:
            row = None
        fallback_gross = float(row[0]) if row and row[0] is not None else None
        fallback_net = float(row[1]) if row and row[1] is not None else None
        fallback_fee = float(row[2]) if row and row[2] is not None else None
        if source == "db":
            db_snap = float(fallback_gross) if fallback_gross is not None else None
            if fallback_gross is not None and fallback_gross > 0:
                out["X-Data-Source"] = "db"
                return (
                    LendingStatsResponse(
                        gross_profit=round(fallback_gross, 2),
                        bitfinex_fee=round(fallback_fee or fallback_gross * BITFINEX_LENDER_FEE_PCT, 2),
                        net_profit=round(fallback_net or fallback_gross * (1 - BITFINEX_LENDER_FEE_PCT), 2),
                        db_snapshot_gross=db_snap,
                    ),
                    out,
                )
            return (LendingStatsResponse(gross_profit=0.0, bitfinex_fee=0.0, net_profit=0.0, db_snapshot_gross=db_snap), out)
        try:
            has_vault = db.execute(
                text("SELECT 1 FROM users u INNER JOIN api_vault v ON v.user_id = u.id WHERE u.id = :uid"),
                {"uid": user_id},
            ).fetchone() is not None
        except Exception:
            has_vault = False
        if not has_vault:
            db_snap = float(fallback_gross) if fallback_gross is not None else None
            if fallback_gross is not None and fallback_gross > 0:
                out["X-Data-Source"] = "db"
                return (
                    LendingStatsResponse(
                        gross_profit=round(fallback_gross, 2),
                        bitfinex_fee=round(fallback_fee or fallback_gross * BITFINEX_LENDER_FEE_PCT, 2),
                        net_profit=round(fallback_net or fallback_gross * (1 - BITFINEX_LENDER_FEE_PCT), 2),
                        db_snapshot_gross=db_snap,
                    ),
                    out,
                )
            return (LendingStatsResponse(gross_profit=0.0, bitfinex_fee=0.0, net_profit=0.0, db_snapshot_gross=db_snap), out)
        cached = await bitfinex_cache.get_cached(user_id, bitfinex_cache.KEY_LENDING)
        if cached is not None:
            data, from_cache = cached
            if from_cache and data is not None:
                cached_gross = data.get("gross_profit")
                if (cached_gross is None or cached_gross == 0) and fallback_gross is not None and fallback_gross > 0:
                    out["X-Data-Source"] = "db"
                    return (
                        LendingStatsResponse(
                            gross_profit=round(fallback_gross, 2),
                            bitfinex_fee=round(fallback_fee or fallback_gross * BITFINEX_LENDER_FEE_PCT, 2),
                            net_profit=round(fallback_net or fallback_gross * (1 - BITFINEX_LENDER_FEE_PCT), 2),
                        ),
                        out,
                    )
                out["X-Data-Source"] = "cache"
                exp = await bitfinex_cache.cache_expires_at(user_id, bitfinex_cache.KEY_LENDING)
                if exp is not None:
                    out["X-Cache-Expires-At"] = str(int(exp))
                return (LendingStatsResponse(**{**data, "db_snapshot_gross": fallback_gross}), out)
        if fallback_gross is not None and fallback_gross > 0:
            out["X-Data-Source"] = "db"
            db_snap = float(fallback_gross)
            resp = LendingStatsResponse(
                gross_profit=round(fallback_gross, 2),
                bitfinex_fee=round(fallback_fee or fallback_gross * BITFINEX_LENDER_FEE_PCT, 2),
                net_profit=round(fallback_net or fallback_gross * (1 - BITFINEX_LENDER_FEE_PCT), 2),
                db_snapshot_gross=db_snap,
            )
            cache_data = resp.model_dump()
            cache_data.pop("trades", None)
            cache_data.pop("calculation_breakdown", None)
            await bitfinex_cache.set_cached(user_id, bitfinex_cache.KEY_LENDING, cache_data)
            return (resp, out)
        if await bitfinex_cache.is_in_cooldown(user_id, bitfinex_cache.KEY_LENDING):
            if fallback_gross is not None:
                out["X-Data-Source"] = "db"
                return (
                    LendingStatsResponse(
                        gross_profit=round(fallback_gross, 2),
                        bitfinex_fee=round(fallback_fee or fallback_gross * BITFINEX_LENDER_FEE_PCT, 2),
                        net_profit=round(fallback_net or fallback_gross * (1 - BITFINEX_LENDER_FEE_PCT), 2),
                    ),
                    out,
                )
            out["X-Data-Source"] = "cache"
            out["X-Rate-Limited"] = "true"
            out["Retry-After"] = "60"
            db_snap = float(fallback_gross) if fallback_gross is not None else None
            return (LendingStatsResponse(gross_profit=0.0, bitfinex_fee=0.0, net_profit=0.0, db_snapshot_gross=db_snap), out)
        try:
            result, rate_limited, records = await _refresh_user_lending_snapshot(user_id, db, fold_ticker_state)
        except Exception:
            if fallback_gross is not None:
                out["X-Data-Source"] = "db"
                return (
                    LendingStatsResponse(
                        gross_profit=round(fallback_gross, 2),
                        bitfinex_fee=round(fallback_fee or fallback_gross * BITFINEX_LENDER_FEE_PCT, 2),
                        net_profit=round(fallback_net or fallback_gross * (1 - BITFINEX_LENDER_FEE_PCT), 2),
                    ),
                    out,
                )
            result = LendingStatsResponse(gross_profit=0.0, bitfinex_fee=0.0, net_profit=0.0)
            rate_limited = False
            records = []
        if rate_limited:
            await bitfinex_cache.set_rate_limit_cooldown(user_id, bitfinex_cache.KEY_LENDING)
            cached = await bitfinex_cache.get_cached(user_id, bitfinex_cache.KEY_LENDING)
            if cached is not None:
                data, _ = cached
                if data is not None:
                    out["X-Data-Source"] = "cache"
                    out["X-Rate-Limited"] = "true"
                    out["Retry-After"] = "60"
                    return (LendingStatsResponse(**data), out)
            if fallback_gross is not None:
                out["X-Data-Source"] = "db"
                out["X-Rate-Limited"] = "true"
                return (
                    LendingStatsResponse(
                        gross_profit=round(fallback_gross, 2),
                        bitfinex_fee=round(fallback_fee or fallback_gross * BITFINEX_LENDER_FEE_PCT, 2),
                        net_profit=round(fallback_net or fallback_gross * (1 - BITFINEX_LENDER_FEE_PCT), 2),
                    ),
                    out,
                )
            out["X-Rate-Limited"] = "true"
            out["Retry-After"] = "60"
            db_snap = float(fallback_gross) if fallback_gross is not None else None
            return (LendingStatsResponse(gross_profit=0.0, bitfinex_fee=0.0, net_profit=0.0, db_snapshot_gross=db_snap), out)
        if (result.gross_profit == 0 or result.gross_profit is None) and fallback_gross is not None and fallback_gross > 0:
            out["X-Data-Source"] = "db"
            resp = LendingStatsResponse(
                gross_profit=round(fallback_gross, 2),
                bitfinex_fee=round(fallback_fee or fallback_gross * BITFINEX_LENDER_FEE_PCT, 2),
                net_profit=round(fallback_net or fallback_gross * (1 - BITFINEX_LENDER_FEE_PCT), 2),
            )
            cache_data = resp.model_dump()
            cache_data.pop("trades", None)
            cache_data.pop("calculation_breakdown", None)
            await bitfinex_cache.set_cached(user_id, bitfinex_cache.KEY_LENDING, cache_data)
            return (resp, out)
        cache_data = result.model_dump()
        cache_data.pop("trades", None)
        cache_data.pop("calculation_breakdown", None)
        await bitfinex_cache.set_cached(user_id, bitfinex_cache.KEY_LENDING, cache_data)
        out["X-Data-Source"] = "live"
        exp = await bitfinex_cache.cache_expires_at(user_id, bitfinex_cache.KEY_LENDING)
        if exp is not None:
            out["X-Cache-Expires-At"] = str(int(exp))
        if records:
            result.trades = records
            result.total_trades_count = result.total_trades_count if result.total_trades_count is not None else len(records)
        return (result, out)
    except (ProgrammingError, SQLAlchemyError):
        out["X-Debug-Fallback-Gross"] = str(fallback_gross) if fallback_gross is not None else "none"
        if fallback_gross is not None and fallback_gross > 0:
            return (
                LendingStatsResponse(
                    gross_profit=round(fallback_gross, 2),
                    bitfinex_fee=round(fallback_fee or fallback_gross * BITFINEX_LENDER_FEE_PCT, 2),
                    net_profit=round(fallback_net or fallback_gross * (1 - BITFINEX_LENDER_FEE_PCT), 2),
                ),
                out,
            )
        return (LendingStatsResponse(gross_profit=0.0, bitfinex_fee=0.0, net_profit=0.0), out)


@app.get("/stats/{user_id}/lending", response_model=LendingStatsResponse)
async def get_lending_stats(
    user_id: int,
    response: Response,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
    source: Optional[str] = Query(None, description="If 'db', return persisted snapshot only (bypass cache)."),
):
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this user.")
    """
    Gross profit = sum of interest from Bitfinex funding trades between registration date and latest.
    Net = Gross × (1 - 15%). Cached to respect Bitfinex rate limits.
    """
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    result, headers = await _get_lending_stats_data(user_id, db, source)
    for k, v in headers.items():
        response.headers[k] = v
    return result


async def _fetch_funding_trade_records_for_user(user: "models.User") -> List[dict]:
    """
    Fetch repaid funding trades from Bitfinex for the user and return list of trade records as dicts.
    Used by dashboard_fold to attach trades when lending has gross but no trades (avoids second frontend request).
    """
    if not getattr(user, "vault", None):
        return []
    try:
        keys = user.vault.get_keys()
        mgr = BitfinexManager(keys["bfx_key"], keys["bfx_secret"])
        start_ms = None
        if getattr(user.vault, "created_at", None) and user.vault.created_at:
            start_ms = int(user.vault.created_at.timestamp() * 1000)
        trades, err = await _fetch_all_funding_trades(mgr, start_ms)
        if err or not trades:
            return []
        ticker_prices = _ticker_prices_from_trades(trades)
        records = _trades_with_interest_usd(trades, ticker_prices)
        return [r.model_dump() for r in records]
    except Exception as e:
        logger.debug("_fetch_funding_trade_records_for_user user_id=%s: %s", user.id, e)
        return []


@app.get("/api/funding-trades", response_model=FundingTradesResponse)
async def get_funding_trades(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """
    Fetch all repaid lending trades from Bitfinex between registration (vault.created_at) and latest.
    Uses POST /v2/auth/r/funding/trades/all/hist. Returns trade records so UI can show trading record extracted.
    """
    if not current_user.vault:
        return FundingTradesResponse(trades=[], gross_profit=0.0, bitfinex_fee=0.0, net_profit=0.0)
    try:
        keys = current_user.vault.get_keys()
        mgr = BitfinexManager(keys["bfx_key"], keys["bfx_secret"])
        start_ms = None
        if getattr(current_user.vault, "created_at", None) and current_user.vault.created_at:
            start_ms = int(current_user.vault.created_at.timestamp() * 1000)
        trades, err = await _fetch_all_funding_trades(mgr, start_ms)
    except Exception as e:
        logger.warning("get_funding_trades user_id=%s failed to load keys/trades: %s", current_user.id, e)
        return FundingTradesResponse(trades=[], gross_profit=0.0, bitfinex_fee=0.0, net_profit=0.0)
    if err or not trades:
        return FundingTradesResponse(trades=[], gross_profit=0.0, bitfinex_fee=0.0, net_profit=0.0)
    ticker_prices = _ticker_prices_from_trades(trades)
    gross, per_currency_breakdown = _interest_usd_from_trades_with_breakdown(trades, ticker_prices)
    fee = gross * BITFINEX_LENDER_FEE_PCT
    net = gross - fee
    records = _trades_with_interest_usd(trades, ticker_prices)
    breakdown = CalculationBreakdown(
        trades_count=len(trades),
        per_currency=per_currency_breakdown,
        total_gross_usd=round(gross, 6),
        formula_note="Interest per trade = |AMOUNT| * RATE * (PERIOD/365 days). USD/USDt/USDT/UST use 1:1; others use Bitfinex t{CCY}USD price.",
    )
    return FundingTradesResponse(
        trades=records,
        gross_profit=round(gross, 2),
        bitfinex_fee=round(fee, 2),
        net_profit=round(net, 2),
        calculation_breakdown=breakdown,
    )


@app.post("/api/refresh-lending-stats", response_model=LendingStatsResponse)
async def refresh_lending_stats(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """
    Force refresh gross profit from Bitfinex for the current user (e.g. on login/dashboard load).
    Invalidates lending cache then recomputes from funding trades since registration.
    Falls back to persisted user_profit_snapshot when API fails or returns 0.
    """
    await bitfinex_cache.invalidate(current_user.id, bitfinex_cache.KEY_LENDING)
    try:
        row = db.execute(
            text("SELECT gross_profit_usd, net_profit_usd, bitfinex_fee_usd FROM user_profit_snapshot WHERE user_id = :uid"),
            {"uid": current_user.id},
        ).fetchone()
    except Exception:
        row = None
    fallback_gross = float(row[0]) if row and row[0] is not None else None
    fallback_net = float(row[1]) if row and row[1] is not None else None
    fallback_fee = float(row[2]) if row and row[2] is not None else None
    try:
        result, rate_limited, records = await _refresh_user_lending_snapshot(current_user.id, db)
    except Exception:
        result = LendingStatsResponse(gross_profit=0.0, bitfinex_fee=0.0, net_profit=0.0)
        rate_limited = False
        records = []
    if rate_limited:
        await bitfinex_cache.set_rate_limit_cooldown(current_user.id, bitfinex_cache.KEY_LENDING)
    else:
        cache_data = result.model_dump()
        cache_data.pop("trades", None)
        await bitfinex_cache.set_cached(current_user.id, bitfinex_cache.KEY_LENDING, cache_data)
    # Use DB fallback when API returned 0 but we have persisted gross (e.g. after API failure)
    if (result.gross_profit == 0 or result.gross_profit is None) and fallback_gross is not None and fallback_gross > 0:
        return LendingStatsResponse(
            gross_profit=round(fallback_gross, 2),
            bitfinex_fee=round(fallback_fee or fallback_gross * BITFINEX_LENDER_FEE_PCT, 2),
            net_profit=round(fallback_net or fallback_gross * (1 - BITFINEX_LENDER_FEE_PCT), 2),
            trades=[],
            calculation_breakdown=None,
        )
    return LendingStatsResponse(
        gross_profit=result.gross_profit,
        bitfinex_fee=result.bitfinex_fee,
        net_profit=result.net_profit,
        trades=records,
        calculation_breakdown=result.calculation_breakdown,
    )


class CronRefreshBody(BaseModel):
    user_id: int


@app.post("/api/cron/refresh-lending-stats", response_model=LendingStatsResponse)
async def cron_refresh_lending_stats(
    body: CronRefreshBody,
    x_cron_secret: Optional[str] = Header(None, alias="X-Cron-Secret"),
    db: Session = Depends(database.get_db),
):
    """
    Internal cron: refresh gross profit for a given user_id. Requires X-Cron-Secret header.
    Used by hourly script to update all users with vaults (staggered).
    """
    secret = os.getenv("CRON_SECRET")
    if not secret or x_cron_secret != secret:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        result, rate_limited, _ = await _refresh_user_lending_snapshot(body.user_id, db)
    except Exception as e:
        await _record_api_failure("cron_refresh", body.user_id, str(e))
        result = LendingStatsResponse(gross_profit=0.0, bitfinex_fee=0.0, net_profit=0.0)
    if not rate_limited:
        cache_data = result.model_dump()
        cache_data.pop("trades", None)
        await bitfinex_cache.set_cached(body.user_id, bitfinex_cache.KEY_LENDING, cache_data)
    return result


@app.get("/user-token-balance/{user_id}", response_model=TokenBalanceResponse)
def get_user_token_balance(user_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(database.get_db)):
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this user.")
    """
    Token balance: remaining = total_tokens_added - total_tokens_deducted (no Bitfinex call).
    """
    row = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
    if not row:
        logger.error("user_token_balance user_id=%s: token balance row not found", user_id)
        raise HTTPException(status_code=404, detail="Token balance not found. Please contact support.")
    tokens_remaining = float(row.tokens_remaining or 0)
    purchased = float(row.purchased_tokens or 0)
    tokens_used = 0  # not tracked in balance-only schema
    snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
    gross = float(snap.gross_profit_usd) if snap and snap.gross_profit_usd is not None else 0.0
    return TokenBalanceResponse(
        tokens_remaining=tokens_remaining,
        tokens_used=tokens_used,
        initial_credit=int(purchased),
        gross_profit_usd=round(gross, 2),
    )


# --- Bitfinex Public Funding Ledger (no auth) ---
def _parse_funding_stats_row(row: Any) -> Optional[Dict[str, Any]]:
    """Parse one row from Bitfinex funding/stats/hist. [MTS, _, _, FRR, AVG_PERIOD, _, _, FUNDING_AMOUNT, FUNDING_AMOUNT_USED, ...]"""
    if not isinstance(row, (list, tuple)) or len(row) < 9:
        return None
    try:
        mts = int(row[0]) if row[0] is not None else 0
        frr = float(row[3]) if row[3] is not None else 0.0
        avg_period = float(row[4]) if row[4] is not None else 0.0
        funding_amount = float(row[7]) if row[7] is not None else 0.0
        funding_used = float(row[8]) if row[8] is not None else 0.0
    except (TypeError, ValueError, IndexError):
        return None
    # FRR is 1/365th of annual rate; APR % = FRR * 365 * 100, daily = FRR * 365
    apr_pct = round(frr * 365 * 100, 4)
    from datetime import datetime as dt
    d = dt.utcfromtimestamp(mts / 1000.0)
    time_str = d.strftime("%m-%d %H:%M")
    return {
        "time": time_str,
        "rateRange": f"{apr_pct}%",
        "maxDays": round(avg_period),
        "cumulative": funding_amount,
        "rate": f"{apr_pct}%",
        "amount": funding_used,
        "count": 1,
        "total": funding_amount,
    }


# In-memory cache for funding symbols list (Bitfinex conf); refresh occasionally
_funding_symbols_cache: Optional[list] = None
_funding_symbols_cache_time: float = 0
FUNDING_SYMBOLS_CACHE_TTL = 300  # 5 min


@app.get("/api/funding-symbols")
async def get_funding_symbols():
    """
    Returns all Bitfinex lending (funding) currencies as { value: "fUSD", label: "USD" } for dropdown.
    Uses Bitfinex public conf pub:list:currency; funding symbol is "f" + currency code.
    """
    import time as _time
    from services.bitfinex_service import _get_currency_list_sync
    global _funding_symbols_cache, _funding_symbols_cache_time
    now = _time.monotonic()
    if _funding_symbols_cache is not None and (now - _funding_symbols_cache_time) < FUNDING_SYMBOLS_CACHE_TTL:
        return _funding_symbols_cache
    loop = asyncio.get_event_loop()
    currencies, err = await loop.run_in_executor(None, _get_currency_list_sync)
    if err or not currencies:
        return [{"value": "fUSD", "label": "USD"}, {"value": "fUST", "label": "USDt"}, {"value": "fBTC", "label": "BTC"}, {"value": "fETH", "label": "ETH"}, {"value": "fXRP", "label": "XRP"}]
    priority = ("USD", "UST", "USDt", "USDT", "BTC", "ETH", "XRP", "LTC", "EOS", "XLM")
    def sort_key(item: dict) -> tuple:
        label = item["label"]
        return (0, priority.index(label)) if label in priority else (1, label)
    symbols = [{"value": f"f{c}", "label": c} for c in currencies if isinstance(c, str) and c]
    symbols.sort(key=sort_key)
    _funding_symbols_cache = symbols
    _funding_symbols_cache_time = now
    return symbols


@app.get("/api/funding-ledger")
async def get_funding_ledger(symbol: str = Query("fUSD", description="Funding symbol (fUSD, fUST, etc.)")):
    """
    Returns Bitfinex lending ledger from public funding stats: current rate and hourly history.
    No auth required (Bitfinex public API).
    """
    from services.bitfinex_service import _get_funding_stats_sync
    import asyncio
    loop = asyncio.get_event_loop()
    raw, err = await loop.run_in_executor(None, lambda: _get_funding_stats_sync(symbol=symbol, limit=24))
    if err or not raw:
        return {"currentRate": None, "dailyRate": None, "rows": [], "error": err or "No data"}
    rows_parsed = []
    for r in raw:
        p = _parse_funding_stats_row(r)
        if p:
            rows_parsed.append(p)
    current = rows_parsed[0] if rows_parsed else None
    current_rate = current.get("rate") if current else None
    daily_rate = None
    if raw and isinstance(raw[0], (list, tuple)) and len(raw[0]) > 3 and raw[0][3] is not None:
        try:
            daily_rate = round(float(raw[0][3]) * 365, 6)
        except (TypeError, ValueError):
            pass
    for p in rows_parsed:
        p["cumulative"] = f"${p['cumulative']:,.2f}"
        p["amount"] = f"${p['amount']:,.0f}" if p.get("amount") else "—"
        p["total"] = f"${p['total']:,.2f}"
    return {
        "currentRate": current_rate,
        "dailyRate": daily_rate,
        "rows": rows_parsed,
    }


def _get_token_balance_legacy(db: Session, user_id: int) -> Optional[tuple]:
    """Raw SQL for legacy user_token_balance (tokens_remaining, purchased_tokens). Returns (tokens_remaining, purchased_tokens) or None."""
    try:
        r = db.execute(
            text("SELECT tokens_remaining, purchased_tokens FROM user_token_balance WHERE user_id = :uid"),
            {"uid": user_id},
        ).fetchone()
        if r is None:
            return None
        return (float(r[0] or 0), float(r[1] or 0))
    except Exception:
        return None


def _get_token_balance_legacy_full(db: Session, user_id: int) -> Optional[dict]:
    """Raw SQL for legacy user_token_balance: tokens_remaining, purchased_tokens, last_gross_usd_used, updated_at. Returns dict or None."""
    try:
        r = db.execute(
            text("""
                SELECT tokens_remaining, purchased_tokens, last_gross_usd_used, updated_at
                FROM user_token_balance WHERE user_id = :uid
            """),
            {"uid": user_id},
        ).fetchone()
        if r is None:
            return None
        return {
            "tokens_remaining": float(r[0] or 0),
            "purchased_tokens": float(r[1] or 0),
            "last_gross_usd_used": float(r[2] or 0) if r[2] is not None else 0.0,
            "updated_at": r[3].strftime("%Y-%m-%dT%H:%M:%SZ") if getattr(r[3], "strftime", None) and r[3] else None,
        }
    except Exception:
        return None


def _get_token_balance_for_fold(db: Session, user_id: int) -> dict:
    """Return token balance dict for dashboard-fold (no rate limit). Same source as GET /api/v1/users/me/token-balance."""
    legacy = _get_token_balance_legacy_full(db, user_id)
    if legacy is not None:
        tokens_remaining = legacy["tokens_remaining"]
        total_added = legacy["purchased_tokens"]
        total_deducted = max(0.0, total_added - tokens_remaining)
        return {
            "tokens_remaining": tokens_remaining,
            "total_tokens_added": total_added,
            "total_tokens_deducted": total_deducted,
        }
    row = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
    if not row:
        return {"tokens_remaining": 0.0, "total_tokens_added": 0.0, "total_tokens_deducted": 0.0}
    tokens_remaining = float(row.tokens_remaining or 0)
    total_added = float(row.purchased_tokens or 0)
    total_deducted = max(0.0, total_added - tokens_remaining)
    return {
        "tokens_remaining": tokens_remaining,
        "total_tokens_added": total_added,
        "total_tokens_deducted": total_deducted,
    }


def _get_user_status_data(user_id: int, db: Session) -> UserStatusResponse:
    """Shared logic for user status (used by GET /user-status and dashboard-fold). Raises HTTPException on error."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    legacy = _get_token_balance_legacy(db, user_id)
    if legacy is not None:
        tokens_remaining, purchased_tokens = legacy
        total_added = purchased_tokens
        tokens_used = 0
    else:
        token_row = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
        if not token_row:
            tokens_remaining = 0.0
            total_added = 0.0
            tokens_used = 0
        else:
            tokens_remaining = float(token_row.tokens_remaining or 0)
            total_added = float(getattr(token_row, "purchased_tokens", 0) or 0)
            tokens_used = 0
    snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
    gross = float(snap.gross_profit_usd) if snap and snap.gross_profit_usd is not None else 0.0
    gross_profit_updated_at_iso = None
    if snap and getattr(snap, "updated_at", None) and snap.updated_at:
        gross_profit_updated_at_iso = snap.updated_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    pro_expiry_iso = None
    if getattr(user, "pro_expiry", None) and user.pro_expiry:
        pro_expiry_iso = user.pro_expiry.strftime("%Y-%m-%dT%H:%M:%SZ")
    created_at_iso = None
    if getattr(user, "created_at", None) and user.created_at:
        created_at_iso = user.created_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    return UserStatusResponse(
        plan_tier=user.plan_tier or "trial",
        rebalance_interval=int(user.rebalance_interval or 0),
        trial_remaining_days=None,
        tokens_remaining=tokens_remaining,
        tokens_used=tokens_used,
        initial_token_credit=int(total_added),
        gross_profit_usd=round(gross, 2),
        gross_profit_updated_at=gross_profit_updated_at_iso,
        pro_expiry=pro_expiry_iso,
        created_at=created_at_iso,
    )


@app.get("/user-status/{user_id}", response_model=UserStatusResponse)
def get_user_status(
    user_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Lightweight status snapshot for the Settings page and header banner.
    User end only: caller must be the same user.
    """
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this user.")

    cache_key = f"user-status:{user_id}"
    cached = _rcache_get(cache_key)
    if cached is not None:
        return cached

    try:
        result = _get_user_status_data(user_id, db)
        _rcache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except (ProgrammingError, SQLAlchemyError) as e:
        logger.exception("user_status user_id=%s database error: %s", user_id, e)
        raise HTTPException(status_code=500, detail="Database error retrieving user status.")
    except Exception as e:
        logger.exception("user_status user_id=%s error: %s", user_id, e)
        raise HTTPException(status_code=500, detail="Internal error retrieving user status.")


@app.get("/admin/users", response_model=list[AdminUserOut])
def list_users(
    _: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    cache_key = "admin-users:all"
    cached = _rcache_get(cache_key)
    if cached is not None:
        return cached

    users = db.query(models.User).all()
    balance_rows = db.query(models.UserTokenBalance).all()
    balances = {b.user_id: float(b.tokens_remaining or 0) for b in balance_rows}
    result = [
        AdminUserOut(
            id=u.id,
            email=u.email,
            plan_tier=u.plan_tier or "trial",
            rebalance_interval=int(u.rebalance_interval or 0),
            pro_expiry=u.pro_expiry,
            status=u.status or "active",
            tokens_remaining=balances.get(u.id),
            bot_status=getattr(u, "bot_status", None) or "stopped",
            created_at=u.created_at.isoformat() + "Z" if getattr(u, "created_at", None) and u.created_at else None,
        )
        for u in users
    ]
    _rcache_set(cache_key, result)
    return result


@app.patch("/admin/users/{user_id}", response_model=AdminUserOut)
def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    admin_user: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if payload.plan_tier is not None:
        tier = payload.plan_tier.lower()
        user.plan_tier = tier
        # Rebalance intervals (minutes) must match worker PLAN_CONFIG
        rebalance_by_tier = {"trial": 40, "free": 40, "pro": 20, "ai_ultra": 10, "whales": 3}
        user.rebalance_interval = payload.rebalance_interval if payload.rebalance_interval is not None else rebalance_by_tier.get(tier, 40)
    elif payload.rebalance_interval is not None:
        user.rebalance_interval = payload.rebalance_interval

    if payload.pro_expiry is not None:
        user.pro_expiry = payload.pro_expiry

    if payload.tokens_remaining is not None:
        val = float(payload.tokens_remaining)
        if val < 0:
            raise HTTPException(status_code=400, detail="tokens_remaining cannot be negative.")
        row = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
        if not row:
            row = models.UserTokenBalance(
                user_id=user_id,
                tokens_remaining=val,
                purchased_tokens=0.0,
            )
            db.add(row)
            db.flush()
        else:
            row.tokens_remaining = val
            row.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(user)
    _admin_audit(admin_user.email or "", "update_user", {"user_id": user_id, "plan_tier": payload.plan_tier, "tokens_remaining": payload.tokens_remaining})
    tokens_remaining = token_ledger_svc.get_tokens_remaining(db, user_id)
    return AdminUserOut(
        id=user.id,
        email=user.email,
        plan_tier=user.plan_tier or "trial",
        rebalance_interval=int(user.rebalance_interval or 0),
        pro_expiry=user.pro_expiry,
        status=user.status or "active",
        tokens_remaining=tokens_remaining,
        bot_status=getattr(user, "bot_status", None) or "stopped",
        created_at=user.created_at.isoformat() + "Z" if getattr(user, "created_at", None) and user.created_at else None,
    )


@app.post("/admin/users/{user_id}/tokens/add", response_model=AdminTokenAdjustResponse)
def admin_add_tokens(
    user_id: int,
    payload: AdminTokenAdjustBody,
    admin_user: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    """Add tokens to a user's balance. Uses token_ledger_svc.add_tokens with reason 'admin_add' (updates purchased_tokens for consistency)."""
    logger.info("admin_token_add process_start user_id=%s amount=%s admin_email=%s", user_id, payload.amount, admin_user.email or "")
    if payload.amount <= 0:
        logger.warning("admin_token_add validation_failed user_id=%s amount=%s reason=amount_not_positive", user_id, payload.amount)
        raise HTTPException(status_code=400, detail="amount must be positive.")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        logger.warning("admin_token_add user_not_found user_id=%s", user_id)
        raise HTTPException(status_code=404, detail="User not found.")
    before = token_ledger_svc.get_tokens_remaining(db, user_id)
    logger.info("admin_token_add before_amend user_id=%s tokens_remaining_before=%s", user_id, before)
    extra_admin = {"added_by": admin_user.email or ""}
    if payload.note:
        extra_admin["note"] = payload.note[:500]
    new_remaining = token_ledger_svc.add_tokens(db, user_id, float(payload.amount), "admin_add", extra=extra_admin or None)
    db.commit()
    logger.info("admin_token_add db_amended user_id=%s amount_added=%s tokens_remaining_after=%s", user_id, payload.amount, new_remaining)
    _admin_audit(admin_user.email or "", "admin_token_add", {"user_id": user_id, "amount": payload.amount})
    _rcache_invalidate_user(user_id)
    return AdminTokenAdjustResponse(tokens_remaining=new_remaining)


@app.post("/admin/users/{user_id}/tokens/deduct", response_model=AdminTokenAdjustResponse)
def admin_deduct_tokens(
    user_id: int,
    payload: AdminTokenAdjustBody,
    admin_user: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    """Deduct tokens from a user's balance. Uses token_ledger_svc.deduct_tokens (balance floors at 0)."""
    logger.info("admin_token_deduct process_start user_id=%s amount=%s admin_email=%s", user_id, payload.amount, admin_user.email or "")
    if payload.amount <= 0:
        logger.warning("admin_token_deduct validation_failed user_id=%s amount=%s reason=amount_not_positive", user_id, payload.amount)
        raise HTTPException(status_code=400, detail="amount must be positive.")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        logger.warning("admin_token_deduct user_not_found user_id=%s", user_id)
        raise HTTPException(status_code=404, detail="User not found.")
    before = token_ledger_svc.get_tokens_remaining(db, user_id)
    logger.info("admin_token_deduct before_amend user_id=%s tokens_remaining_before=%s", user_id, before)
    new_remaining = token_ledger_svc.deduct_tokens(db, user_id, float(payload.amount))
    db.commit()
    logger.info("admin_token_deduct db_amended user_id=%s amount_deducted=%s tokens_remaining_after=%s", user_id, payload.amount, new_remaining)
    _admin_audit(admin_user.email or "", "admin_token_deduct", {"user_id": user_id, "amount": payload.amount})
    _rcache_invalidate_user(user_id)
    return AdminTokenAdjustResponse(tokens_remaining=new_remaining)


@app.get("/admin/api-failures", response_model=List[ApiFailureOut])
async def list_api_failures(
    limit: int = Query(100, ge=1, le=200),
    _: models.User = Depends(get_admin_user),
):
    """Recent API failures (e.g. daily gross refresh, Bitfinex errors) for admin panel."""
    raw = await _get_api_failures(limit=limit)
    return [ApiFailureOut(id=e["id"], ts=e["ts"], context=e["context"], user_id=e.get("user_id"), error=e["error"]) for e in raw]


@app.post("/admin/api-failures/retry")
async def retry_api_failure(
    body: AdminRetryBody,
    _: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    """Retry a failed gross profit refresh for a user (by failure_id or user_id)."""
    user_id: Optional[int] = None
    if body.user_id is not None:
        user_id = body.user_id
    elif body.failure_id:
        async with _api_failures_lock:
            for e in _api_failures:
                if e.get("id") == body.failure_id:
                    user_id = e.get("user_id")
                    break
        if user_id is None:
            raise HTTPException(status_code=404, detail="Failure not found or has no user_id.")
    else:
        raise HTTPException(status_code=400, detail="Provide failure_id or user_id.")
    try:
        result, rate_limited, _ = await _refresh_user_lending_snapshot(user_id, db)
        if not rate_limited:
            cache_data = result.model_dump()
            cache_data.pop("trades", None)
            await bitfinex_cache.set_cached(user_id, bitfinex_cache.KEY_LENDING, cache_data)
        return {"ok": True, "user_id": user_id, "gross_profit": result.gross_profit}
    except Exception as e:
        await _record_api_failure("admin_retry", user_id, str(e))
        raise HTTPException(status_code=502, detail="Retry failed. Check admin API failures.")


# --- Admin: User export CSV ---
@app.get("/admin/users/export")
def admin_export_users(
    _: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    """Export users as CSV (admin only)."""
    import csv
    import io
    users = db.query(models.User).all()
    balance_rows = db.query(models.UserTokenBalance).all()
    balances = {b.user_id: float(b.tokens_remaining or 0) for b in balance_rows}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "email", "plan_tier", "rebalance_interval", "pro_expiry", "status", "tokens_remaining", "bot_status", "created_at"])
    for u in users:
        w.writerow([
            u.id,
            u.email or "",
            u.plan_tier or "trial",
            int(u.rebalance_interval or 0),
            u.pro_expiry.isoformat() if u.pro_expiry else "",
            u.status or "active",
            balances.get(u.id, ""),
            getattr(u, "bot_status", None) or "stopped",
            u.created_at.isoformat() if getattr(u, "created_at", None) and u.created_at else "",
        ])
    buf.seek(0)
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=users_export.csv"},
    )


# --- Admin: Bot control ---
@app.post("/admin/bot/start/{user_id}")
async def admin_bot_start(
    user_id: int,
    admin_user: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    """Admin-only: start bot for any user. Plan C: desired state; skip token check (Q2)."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or not user.vault:
        raise HTTPException(status_code=404, detail="User or API keys not found.")
    if hasattr(user, "bot_desired_state"):
        user.bot_desired_state = "running"
    try:
        db.commit()
    except Exception:
        db.rollback()
    status_before = getattr(user, "bot_status", None) or "stopped"
    desired = getattr(user, "bot_desired_state", None) or "stopped"
    if status_before in ("running", "starting") and desired == "running":
        return {"status": "success", "message": "Bot already running or queued.", "bot_status": status_before}
    redis = await get_redis_or_raise()
    enqueued = await _enqueue_bot_task(redis, user_id)
    if enqueued:
        try:
            user.bot_status = "starting"
            db.commit()
        except Exception:
            db.rollback()
        _admin_audit(admin_user.email or "", "bot_start", {"user_id": user_id})
        return {"status": "success", "message": f"Bot queued for user {user_id}", "bot_status": "starting"}
    return {"status": "success", "message": "Bot already running or queued.", "bot_status": getattr(user, "bot_status", None) or "running"}


@app.post("/admin/bot/stop/{user_id}")
async def admin_bot_stop(
    user_id: int,
    admin_user: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    """Admin-only: stop bot for any user. Plan C: DB first."""
    from arq.jobs import Job
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user:
        try:
            if hasattr(user, "bot_desired_state"):
                user.bot_desired_state = "stopped"
            if hasattr(user, "bot_status"):
                user.bot_status = "stopped"
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
    aborted = False
    try:
        redis = await get_redis_or_raise()
        job_id = f"bot_user_{user_id}"
        job = Job(job_id=job_id, redis=redis)
        aborted = await job.abort(timeout=5)
        await _clear_arq_job_keys(redis, job_id)
        try:
            await redis.delete(f"bot_run_lock:{user_id}")
        except Exception:
            pass
    except asyncio.TimeoutError:
        try:
            redis = await get_redis_or_raise()
            await _clear_arq_job_keys(redis, f"bot_user_{user_id}")
            await redis.delete(f"bot_run_lock:{user_id}")
        except Exception:
            pass
        logger.warning("admin_bot_stop user_id=%s abort timed out (5s), cleared keys+lock", user_id)
    except Exception:
        try:
            redis = await get_redis_or_raise()
            await _clear_arq_job_keys(redis, f"bot_user_{user_id}")
            await redis.delete(f"bot_run_lock:{user_id}")
        except Exception:
            pass
    _admin_audit(admin_user.email or "", "bot_stop", {"user_id": user_id})
    return {"status": "success", "message": "Shutdown signal sent" if aborted else "Bot stopped.", "bot_status": "stopped"}


@app.get("/admin/bot/logs/{user_id}")
async def admin_bot_logs(
    user_id: int,
    _: models.User = Depends(get_admin_user),
):
    """Admin-only: terminal logs for any user."""
    try:
        redis = await asyncio.wait_for(get_redis(), timeout=REDIS_CONNECT_TIMEOUT)
    except (asyncio.TimeoutError, Exception):
        return {"lines": []}
    if redis is None:
        return {"lines": []}
    try:
        key = f"terminal_logs:{user_id}"
        lines = await asyncio.wait_for(redis.lrange(key, 0, -1), timeout=5.0)
    except (asyncio.TimeoutError, Exception):
        return {"lines": []}
    decoded = [line.decode("utf-8") if isinstance(line, bytes) else line for line in (lines or [])]
    return {"lines": decoded}


@app.post("/admin/arq/restart")
async def admin_arq_restart(_: models.User = Depends(get_admin_user)):
    """Admin: signal ARQ restart (no-op in API; worker must be restarted externally). Returns OK."""
    return {"ok": True, "message": "ARQ worker must be restarted externally (e.g. systemd or process manager)."}


# --- Admin: Deduction oversight ---
@app.post("/admin/deduction/clear-cache")
def admin_deduction_clear_cache(_: models.User = Depends(get_admin_user)):
    """Admin: clear the in-memory deduction log cache (_deduction_logs). DB deduction_log is unchanged."""
    with _deduction_logs_lock:
        _deduction_logs.clear()
    return {"ok": True, "message": "In-memory deduction log cache cleared."}


@app.get("/admin/deduction/logs", response_model=List[DeductionLogEntry])
def admin_deduction_logs(
    limit: int = Query(100, ge=1, le=500),
    start_date: Optional[str] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Filter to date (YYYY-MM-DD)"),
    _: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    """Recent deduction log entries (newest first). Cached 30s."""
    cache_key = f"admin-deduction-logs:{limit}:{start_date}:{end_date}"
    cached = _rcache_get(cache_key)
    if cached is not None:
        return cached
    try:
        q = db.query(models.DeductionLog).order_by(models.DeductionLog.timestamp_utc.desc())
        if start_date:
            q = q.filter(models.DeductionLog.timestamp_utc >= datetime.fromisoformat(start_date + "T00:00:00"))
        if end_date:
            q = q.filter(models.DeductionLog.timestamp_utc <= datetime.fromisoformat(end_date + "T23:59:59.999999"))
        rows = q.limit(limit).all()
        def _deduction_ts(row: "models.DeductionLog") -> str:
            if row.timestamp_utc:
                t = row.timestamp_utc
                return t.isoformat() if getattr(t, "tzinfo", None) else t.isoformat() + "Z"
            c = getattr(row, "created_at", None)
            if c:
                return c.isoformat() if getattr(c, "tzinfo", None) else c.isoformat() + "Z"
            return "1970-01-01T00:00:00Z"

        result = [
            DeductionLogEntry(
                user_id=r.user_id,
                email=r.email,
                gross_profit=r.daily_gross_profit_usd or 0,
                tokens_deducted=r.tokens_deducted or 0,
                tokens_remaining_before=float((r.tokens_remaining_after or 0) + (r.tokens_deducted or 0)),
                tokens_remaining_after=r.tokens_remaining_after,
                total_used_tokens=r.total_used_tokens,
                timestamp=_deduction_ts(r),
                account_switch_note=r.account_switch_note,
            )
            for r in rows
        ]
        _rcache_set(cache_key, result)
        return result
    except Exception:
        with _deduction_logs_lock:
            copy = list(_deduction_logs)
        copy.reverse()
        if start_date:
            copy = [e for e in copy if (e.get("timestamp") or "")[:10] >= start_date]
        if end_date:
            copy = [e for e in copy if (e.get("timestamp") or "")[:10] <= end_date]
        out = copy[:limit]
        result = [
            DeductionLogEntry(
                user_id=e["user_id"],
                email=e.get("email"),
                gross_profit=e.get("gross_profit", 0),
                tokens_deducted=e.get("tokens_deducted", 0),
                tokens_remaining_before=e.get("tokens_remaining_before"),
                tokens_remaining_after=e.get("tokens_remaining_after"),
                total_used_tokens=e.get("total_used_tokens"),
                timestamp=e.get("timestamp", ""),
                account_switch_note=e.get("account_switch_note"),
            )
            for e in out
        ]
        _rcache_set(cache_key, result)
        return result


@app.get("/admin/token-add/logs", response_model=List[TokenAddLogEntry])
def admin_token_add_logs(
    limit: int = Query(100, ge=1, le=500),
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    start_date: Optional[str] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Filter to date (YYYY-MM-DD)"),
    _: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    """Recent token add log entries (newest first). Cached 30s for default queries."""
    cache_key = f"admin-token-add-logs:{limit}:{user_id}:{start_date}:{end_date}"
    cached = _rcache_get(cache_key)
    if cached is not None:
        return cached

    out: List[TokenAddLogEntry] = []
    try:
        sql = """
            SELECT tl.id, tl.user_id, u.email, tl.amount, tl.reason, tl.created_at, tl.metadata
            FROM token_ledger tl
            LEFT JOIN users u ON u.id = tl.user_id
            WHERE tl.activity_type = 'add'
        """
        params: Dict[str, Any] = {"lim": limit}
        if user_id is not None:
            sql += " AND tl.user_id = :uid"
            params["uid"] = user_id
        if start_date:
            sql += " AND tl.created_at >= :start_dt"
            params["start_dt"] = datetime.fromisoformat(start_date + "T00:00:00")
        if end_date:
            sql += " AND tl.created_at <= :end_dt"
            params["end_dt"] = datetime.fromisoformat(end_date + "T23:59:59.999999")
        sql += " ORDER BY tl.created_at DESC LIMIT :lim"
        rows = db.execute(text(sql), params).fetchall()
        for row in rows:
            row_id = row[0]
            uid_val = row[1]
            email_val = row[2] if len(row) > 2 else None
            amount_val = float(row[3] or 0)
            reason_val = (row[4] or "").strip()
            created_at_val = row[5]
            extra_val = row[6] if len(row) > 6 else None
            if not isinstance(extra_val, dict):
                extra_val = {}
            created_str = created_at_val.isoformat() + "Z" if created_at_val and getattr(created_at_val, "isoformat", None) else ""
            detail_str = _token_add_detail(reason_val, extra_val)
            out.append(
                TokenAddLogEntry(
                    id=row_id,
                    user_id=uid_val,
                    email=(email_val.strip() if isinstance(email_val, str) else None),
                    amount=amount_val,
                    reason=reason_val,
                    created_at=created_str,
                    detail=detail_str,
                )
            )
    except Exception as e:
        logger.warning("admin_token_add_logs error=%s", e)
    _rcache_set(cache_key, out)
    return out


@app.post("/admin/deduction/trigger")
async def admin_deduction_trigger(
    refresh_first: bool = Query(True, description="Refresh snapshots from Bitfinex (and 09:00 cache) before deducting. Use true when 10:00 failed or server was down (soft pad)."),
    admin_user: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    """
    Admin: run daily token deduction manually.
    When refresh_first=True (default): refresh snapshots from Bitfinex for all users with vault,
    then apply 09:00 cache for any still missing daily_gross, then run deduction. Use this when
    server was down or 10:00 API run failed so deduction uses up-to-date profit (100% accuracy).
    When refresh_first=False: only run deduction from existing snapshot (no API calls).
    When refresh_first=True, backfill any missed snapshot day (last_deduction_processed_date < last_daily_snapshot_date)
    before refreshing so users who were not deducted (e.g. server down) get that day deducted.
    """
    refreshed = 0
    backfill_entries: List[Dict[str, Any]] = []
    if refresh_first:
        # Backfill: deduct any user whose snapshot day was never processed (e.g. 10:00 ran but 10:30 didn't).
        # Only backfill PAST dates (snapshot_date < today); today is always deducted once in run_daily_token_deduction below.
        today_utc = datetime.utcnow().date()
        try:
            rows = (
                db.query(models.UserTokenBalance, models.UserProfitSnapshot, models.User)
                .join(
                    models.UserProfitSnapshot,
                    models.UserTokenBalance.user_id == models.UserProfitSnapshot.user_id,
                )
                .join(models.User, models.User.id == models.UserTokenBalance.user_id)
                .all()
            )
            for token_row, snap, user in rows:
                last_ded = getattr(snap, "last_deduction_processed_date", None)
                snapshot_date = getattr(snap, "last_daily_snapshot_date", None)
                if snapshot_date is None:
                    continue
                if snapshot_date >= today_utc:
                    continue  # never backfill "today"; run_daily_token_deduction handles today once after refresh
                if last_ded is not None and last_ded >= snapshot_date:
                    continue
                daily_gross = getattr(snap, "daily_gross_profit_usd", None)
                if daily_gross is None or float(daily_gross) <= 0:
                    continue
                uid = token_row.user_id
                mult = _get_deduction_multiplier(db)
                log_entry, _ = run_deduction_for_user_for_date(
                    db, uid, snapshot_date, float(daily_gross), deduction_multiplier=mult
                )
                if log_entry:
                    backfill_entries.append(log_entry)
                    logger.info(
                        "trace_id=%s | Manual trigger backfill: user_id=%s for_date=%s deducted %.2f",
                        get_trace_id(), uid, snapshot_date, float(daily_gross),
                    )
            if backfill_entries:
                db.commit()
                with _deduction_logs_lock:
                    for e in backfill_entries:
                        _deduction_logs.append(e)
                        while len(_deduction_logs) > DEDUCTION_LOGS_MAX:
                            _deduction_logs.pop(0)
        except Exception as e:
            logger.warning("Manual trigger backfill: %s", e)
            db.rollback()
        db_refresh = database.SessionLocal()
        try:
            user_ids = [
                row[0]
                for row in db_refresh.query(models.User.id)
                .join(models.APIVault, models.User.id == models.APIVault.user_id)
                .distinct()
                .all()
            ]
        finally:
            db_refresh.close()
        test_uid = _get_scheduler_test_user_id()
        if test_uid is not None:
            user_ids = [u for u in user_ids if u == test_uid]
        for i, uid in enumerate(user_ids):
            if i > 0:
                await asyncio.sleep(DELAY_BETWEEN_USERS_SEC)
            db_u = database.SessionLocal()
            try:
                success, _, _ = await _daily_10_00_fetch_and_save(uid, db_u)
                if success:
                    refreshed += 1
                    snap = db_u.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == uid).first()
                    if snap:
                        await bitfinex_cache.set_cached(
                            uid,
                            bitfinex_cache.KEY_LENDING,
                            {
                                "gross_profit": float(snap.gross_profit_usd or 0),
                                "bitfinex_fee": float(snap.bitfinex_fee_usd or 0),
                                "net_profit": float(snap.net_profit_usd or 0),
                            },
                        )
            except Exception as e:
                logger.warning("Manual trigger: refresh failed for user_id=%s: %s", uid, e)
            finally:
                db_u.close()
        try:
            redis = await asyncio.wait_for(get_redis(), timeout=REDIS_CONNECT_TIMEOUT)
            await _apply_09_00_cache_before_deduction(db, redis)
        except Exception as e:
            logger.warning("Manual trigger: 09:00 cache fallback skipped: %s", e)
    if refresh_first:
        db.expire_all()  # see post-refresh snapshot so we deduct today's amount, not stale yesterday's
    mult = _get_deduction_multiplier(db)
    log_entries, err = run_daily_token_deduction(db, deduction_multiplier=mult)
    if err:
        logger.error("admin_deduction_trigger failed: %s", err)
        raise HTTPException(status_code=500, detail="Deduction failed. Check server logs.")
    with _deduction_logs_lock:
        for e in log_entries:
            _deduction_logs.append(e)
            while len(_deduction_logs) > DEDUCTION_LOGS_MAX:
                _deduction_logs.pop(0)
    _admin_audit(admin_user.email or "", "deduction_trigger", {"count": len(log_entries), "refreshed": refreshed})
    return {
        "status": "success",
        "count": len(log_entries),
        "entries": log_entries,
        "refreshed": refreshed,
    }


@app.post("/admin/deduction/rollback/{user_id}/{date}")
def admin_deduction_rollback(
    user_id: int,
    date: str,
    admin_user: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    """Admin: add back tokens for a user for a given date (YYYY-MM-DD). Uses deduction_log (DB) or in-memory log."""
    entries: List[Dict[str, Any]] = []
    try:
        day_start = datetime.fromisoformat(date + "T00:00:00")
        day_end = datetime.fromisoformat(date + "T23:59:59.999999")
        db_rows = (
            db.query(models.DeductionLog)
            .filter(
                models.DeductionLog.user_id == user_id,
                models.DeductionLog.timestamp_utc >= day_start,
                models.DeductionLog.timestamp_utc <= day_end,
            )
            .all()
        )
        if db_rows:
            entries = [{"tokens_deducted": float(r.tokens_deducted or 0)} for r in db_rows]
    except Exception:
        pass
    if not entries:
        with _deduction_logs_lock:
            entries = [e for e in _deduction_logs if e.get("user_id") == user_id and (e.get("timestamp") or "").startswith(date)]
    if not entries:
        raise HTTPException(status_code=404, detail=f"No deduction entries for user_id={user_id} and date={date}")
    total_add_back = sum(e.get("tokens_deducted", 0) for e in entries)
    new_remaining = token_ledger_svc.add_tokens(db, user_id, total_add_back, "deduction_rollback", extra={"rollback_date": date})
    # Clear last_deduction_processed_date so the next deduction run will process this user again for this date
    snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
    if snap and hasattr(snap, "last_deduction_processed_date"):
        snap.last_deduction_processed_date = None
    db.commit()
    _admin_audit(admin_user.email or "", "deduction_rollback", {"user_id": user_id, "date": date, "tokens_added_back": total_add_back})
    return {"status": "success", "user_id": user_id, "date": date, "tokens_added_back": total_add_back, "new_tokens_remaining": new_remaining}


# --- Admin: Cleanup (Scenario A + C) ---
@app.post("/admin/cleanup/preview")
def admin_cleanup_preview(
    admin_user: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    """Preview what the cleanup would do without making changes."""
    return _run_cleanup_preview(db)


@app.post("/admin/cleanup/run")
def admin_cleanup_run(
    admin_user: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    """Execute data cleanup: prune old logs, mark dormant users."""
    result = _run_cleanup_queries(db)
    db.commit()
    _admin_audit(admin_user.email or "", "admin_cleanup_run", result)
    return {"status": "success", **result}


# --- Admin: System health ---
@app.get("/admin/health")
async def admin_health(_: models.User = Depends(get_admin_user)):
    """Basic health: Redis and DB connectivity."""
    health: Dict[str, Any] = {"redis": "unknown", "db": "unknown"}
    try:
        redis = await asyncio.wait_for(get_redis(), timeout=2.0)
        await redis.ping()
        health["redis"] = "ok"
    except Exception as e:
        health["redis"] = f"error: {type(e).__name__}"
    try:
        db = database.SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        health["db"] = "ok"
    except Exception as e:
        health["db"] = f"error: {type(e).__name__}"
    return health


@app.get("/admin/stripe-config-check")
def admin_stripe_config_check(_: models.User = Depends(get_admin_user)):
    """
    Resolve each STRIPE_PRICE_* env to product id and return (for verifying Whales/Pro/AI Ultra mapping).
    Logs results at info level.
    """
    result: Dict[str, str] = {}
    for key, env_val in [
        ("STRIPE_PRICE_PRO_MONTHLY", STRIPE_PRICE_PRO_MONTHLY),
        ("STRIPE_PRICE_PRO_YEARLY", STRIPE_PRICE_PRO_YEARLY),
        ("STRIPE_PRICE_AI_ULTRA_MONTHLY", STRIPE_PRICE_AI_ULTRA_MONTHLY),
        ("STRIPE_PRICE_AI_ULTRA_YEARLY", STRIPE_PRICE_AI_ULTRA_YEARLY),
        ("STRIPE_PRICE_WHALES_MONTHLY", STRIPE_PRICE_WHALES_MONTHLY),
        ("STRIPE_PRICE_WHALES_YEARLY", STRIPE_PRICE_WHALES_YEARLY),
    ]:
        try:
            resolved = _resolve_stripe_env_to_product_id(env_val or "")
            result[key] = resolved or "(empty or unresolved)"
            logger.info("stripe_config_check %s -> %s", key, result[key])
        except Exception as e:
            result[key] = f"error: {e!s}"
            logger.warning("stripe_config_check %s error=%s", key, e)
    return result


@app.get("/admin/logs/errors", response_model=List[ApiFailureOut])
async def admin_logs_errors(
    limit: int = Query(100, ge=1, le=200),
    _: models.User = Depends(get_admin_user),
):
    """Error log (same as api-failures). Filter by severity not implemented; use limit."""
    raw = await _get_api_failures(limit=limit)
    return [ApiFailureOut(id=e["id"], ts=e["ts"], context=e["context"], user_id=e.get("user_id"), error=e["error"]) for e in raw]


# --- Admin: API Keys ---
def _mask_key(key: str) -> str:
    if not key or len(key) < 9:
        return "****"
    return key[:4] + "****" + key[-4:]


@app.get("/admin/api-keys", response_model=List[AdminApiKeyRow])
def admin_list_api_keys(
    _: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    users = db.query(models.User).all()
    out = []
    for u in users:
        vault = db.query(models.APIVault).filter(models.APIVault.user_id == u.id).first()
        has_keys = vault is not None
        key_masked = None
        last_tested_at = None
        if vault:
            try:
                keys = vault.get_keys()
                key_masked = _mask_key((keys.get("bfx_key") or "")[:20])
            except Exception:
                key_masked = "****"
            if getattr(vault, "last_tested_at", None):
                last_tested_at = vault.last_tested_at.isoformat() + "Z"
        out.append(AdminApiKeyRow(user_id=u.id, email=u.email or "", has_keys=has_keys, key_masked=key_masked, last_tested_at=last_tested_at))
    return out


@app.get("/admin/api-keys/{user_id}", response_model=AdminApiKeyRow)
def admin_get_api_key(
    user_id: int,
    _: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    vault = db.query(models.APIVault).filter(models.APIVault.user_id == user_id).first()
    if not vault:
        raise HTTPException(status_code=404, detail="User has no API keys.")
    key_masked = "****"
    last_tested_at = None
    try:
        keys = vault.get_keys()
        key_masked = _mask_key((keys.get("bfx_key") or "")[:20])
    except Exception:
        pass
    if getattr(vault, "last_tested_at", None):
        last_tested_at = vault.last_tested_at.isoformat() + "Z"
    return AdminApiKeyRow(user_id=user_id, email=user.email or "", has_keys=True, key_masked=key_masked, last_tested_at=last_tested_at)


@app.post("/admin/api-keys/{user_id}/reset")
def admin_reset_api_keys(
    user_id: int,
    admin_user: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    vault = db.query(models.APIVault).filter(models.APIVault.user_id == user_id).first()
    if not vault:
        raise HTTPException(status_code=404, detail="User has no API keys.")
    db.delete(vault)
    db.commit()
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user and hasattr(user, "bot_status"):
        user.bot_status = "stopped"
        db.commit()
    _admin_audit(admin_user.email or "", "api_keys_reset", {"user_id": user_id})
    return {"ok": True, "message": "API keys cleared."}


# --- Admin: Subscriptions / Plan ---
@app.get("/admin/subscriptions", response_model=List[AdminUserOut])
def admin_list_subscriptions(
    _: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    return list_users(_=_, db=db)


@app.get("/admin/subscriptions/{user_id}")
def admin_get_subscription(
    user_id: int,
    _: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return {
        "user_id": user_id,
        "email": user.email,
        "plan_tier": user.plan_tier or "trial",
        "pro_expiry": user.pro_expiry.isoformat() if user.pro_expiry else None,
    }


class SetPlanBody(BaseModel):
    plan_tier: str
    rebalance_interval: Optional[int] = None


class ExtendExpiryBody(BaseModel):
    days: int  # positive = extend, negative = reduce


@app.post("/admin/users/{user_id}/set-plan", response_model=AdminUserOut)
def admin_set_plan(
    user_id: int,
    body: SetPlanBody,
    admin_user: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    tier = (body.plan_tier or "trial").lower()
    user.plan_tier = tier
    # Rebalance intervals (minutes) must match worker PLAN_CONFIG
    rebalance_by_tier = {"trial": 40, "free": 40, "pro": 20, "ai_ultra": 10, "whales": 3}
    user.rebalance_interval = body.rebalance_interval if body.rebalance_interval is not None else rebalance_by_tier.get(tier, 40)
    db.commit()
    db.refresh(user)
    _admin_audit(admin_user.email or "", "set_plan", {"user_id": user_id, "plan_tier": user.plan_tier})
    balance_rows = db.query(models.UserTokenBalance).all()
    balances = {b.user_id: float(b.tokens_remaining or 0) for b in balance_rows}
    return _admin_user_out(user, balances.get(user.id))


@app.post("/admin/users/{user_id}/extend-expiry")
def admin_extend_expiry(
    user_id: int,
    body: ExtendExpiryBody,
    admin_user: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    from datetime import timedelta
    base = user.pro_expiry or datetime.utcnow()
    user.pro_expiry = base + timedelta(days=body.days)
    if user.pro_expiry < datetime.utcnow():
        user.status = "expired"
    else:
        user.status = "active"
    db.commit()
    _admin_audit(admin_user.email or "", "extend_expiry", {"user_id": user_id, "days": body.days, "new_expiry": user.pro_expiry.isoformat()})
    return {"ok": True, "pro_expiry": user.pro_expiry.isoformat()}


def _admin_user_out(user: models.User, tokens_remaining: Optional[float]) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        email=user.email or "",
        plan_tier=user.plan_tier or "trial",
        rebalance_interval=int(user.rebalance_interval or 0),
        pro_expiry=user.pro_expiry,
        status=user.status or "active",
        tokens_remaining=tokens_remaining,
        bot_status=getattr(user, "bot_status", None) or "stopped",
        created_at=user.created_at.isoformat() + "Z" if getattr(user, "created_at", None) and user.created_at else None,
    )


# --- Admin: Bulk token adjustment ---
@app.post("/admin/tokens/bulk-add")
def admin_bulk_add_tokens(
    body: BulkTokenBody,
    admin_user: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    success = 0
    failed = 0
    l1_pct, l2_pct, l3_pct = _get_referral_purchase_pct(db)
    for item in body.items:
        if item.amount <= 0:
            failed += 1
            continue
        token_ledger_svc.add_tokens(db, item.user_id, float(item.amount), "admin_bulk_add", extra={"batch": True})
        usd_value = float(item.amount) / 100.0  # 1 USD = 100 tokens
        apply_referral_rewards_on_purchase(db, item.user_id, usd_value, reward_purchase_l1=l1_pct, reward_purchase_l2=l2_pct, reward_purchase_l3=l3_pct)
        db.commit()
        success += 1
        _admin_audit(admin_user.email or "", "bulk_token_add", {"user_id": item.user_id, "amount": item.amount})
    return {"ok": True, "success_count": success, "failed_count": failed}


# --- Admin: USDT Credit ---
def _get_or_create_usdt_credit(user_id: int, db: Session) -> models.UserUsdtCredit:
    row = db.query(models.UserUsdtCredit).filter(models.UserUsdtCredit.user_id == user_id).first()
    if row:
        return row
    row = models.UserUsdtCredit(user_id=user_id, usdt_credit=0.0, total_earned=0.0, total_withdrawn=0.0)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.get("/admin/usdt-credit", response_model=List[AdminUsdtCreditRow])
def admin_list_usdt_credit(
    user_id: Optional[int] = Query(None),
    email: Optional[str] = Query(None),
    min_balance: Optional[float] = Query(None),
    max_balance: Optional[float] = Query(None),
    _: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    q = db.query(models.User, models.UserUsdtCredit).outerjoin(
        models.UserUsdtCredit, models.User.id == models.UserUsdtCredit.user_id
    )
    if user_id is not None:
        q = q.filter(models.User.id == user_id)
    if email:
        q = q.filter(models.User.email.ilike(f"%{email}%"))
    rows = q.all()
    pending_by_user: Dict[int, float] = {}
    for r in db.query(models.WithdrawalRequest).filter(models.WithdrawalRequest.status == "pending").all():
        pending_by_user[r.user_id] = pending_by_user.get(r.user_id, 0.0) + float(r.amount)
    out = []
    for user, uc in rows:
        if uc is None:
            uc_balance, uc_earned, uc_withdrawn = 0.0, 0.0, 0.0
        else:
            uc_balance = float(uc.usdt_credit or 0)
            uc_earned = float(uc.total_earned or 0)
            uc_withdrawn = float(uc.total_withdrawn or 0)
        locked = pending_by_user.get(user.id, 0.0)
        if min_balance is not None and uc_balance < min_balance:
            continue
        if max_balance is not None and uc_balance > max_balance:
            continue
        out.append(AdminUsdtCreditRow(user_id=user.id, email=user.email or "", usdt_credit=uc_balance, total_earned=uc_earned, total_withdrawn=uc_withdrawn, locked_pending=locked))
    return out


@app.get("/admin/usdt-credit/{user_id}")
def admin_get_usdt_credit(
    user_id: int,
    _: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    uc = _get_or_create_usdt_credit(user_id, db)
    return {
        "user_id": user_id,
        "email": user.email,
        "usdt_credit": float(uc.usdt_credit or 0),
        "total_earned": float(uc.total_earned or 0),
        "total_withdrawn": float(uc.total_withdrawn or 0),
    }


@app.post("/admin/usdt-credit/{user_id}/adjust")
def admin_adjust_usdt_credit(
    user_id: int,
    body: UsdtAdjustBody,
    admin_user: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    uc = _get_or_create_usdt_credit(user_id, db)
    new_balance = float(uc.usdt_credit or 0) + body.amount
    if new_balance < 0:
        raise HTTPException(status_code=400, detail="Resulting balance cannot be negative.")
    uc.usdt_credit = new_balance
    if body.amount > 0:
        uc.total_earned = float(uc.total_earned or 0) + body.amount
    else:
        uc.total_withdrawn = float(uc.total_withdrawn or 0) + abs(body.amount)
    db.add(models.UsdtHistory(user_id=user_id, amount=body.amount, reason="admin_adjust", admin_email=admin_user.email))
    db.commit()
    _admin_audit(admin_user.email or "", "usdt_adjust", {"user_id": user_id, "amount": body.amount, "new_balance": new_balance})
    return {"ok": True, "usdt_credit": new_balance}


@app.get("/admin/usdt-history")
def admin_usdt_history(
    user_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    _: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    q = db.query(models.UsdtHistory).order_by(models.UsdtHistory.created_at.desc())
    if user_id is not None:
        q = q.filter(models.UsdtHistory.user_id == user_id)
    rows = q.limit(limit).all()
    return [
        {"id": r.id, "user_id": r.user_id, "amount": r.amount, "reason": r.reason, "created_at": r.created_at.isoformat() + "Z" if r.created_at else None, "admin_email": r.admin_email}
        for r in rows
    ]


# --- Admin: Withdrawals (and /admin/usdt-withdrawals alias) ---
@app.get("/admin/withdrawals", response_model=List[WithdrawalRow])
@app.get("/admin/usdt-withdrawals", response_model=List[WithdrawalRow])
def admin_list_withdrawals(
    status: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    _: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    q = db.query(models.WithdrawalRequest).order_by(models.WithdrawalRequest.created_at.desc())
    if status:
        q = q.filter(models.WithdrawalRequest.status == status)
    if user_id is not None:
        q = q.filter(models.WithdrawalRequest.user_id == user_id)
    rows = q.all()
    out = []
    for r in rows:
        user = db.query(models.User).filter(models.User.id == r.user_id).first()
        out.append(WithdrawalRow(
            id=r.id,
            user_id=r.user_id,
            email=user.email if user else "",
            amount=r.amount,
            address=r.address,
            status=r.status,
            created_at=r.created_at.isoformat() + "Z" if r.created_at else None,
            processed_at=r.processed_at.isoformat() + "Z" if r.processed_at else None,
            processed_by=getattr(r, "processed_by", None),
            rejection_note=getattr(r, "rejection_note", None),
        ))
    return out


@app.post("/admin/withdrawals/{wid}/approve")
@app.post("/admin/usdt-withdrawals/{wid}/approve")
def admin_approve_withdrawal(
    wid: int,
    admin_user: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    w = db.query(models.WithdrawalRequest).filter(models.WithdrawalRequest.id == wid).first()
    if not w or w.status != "pending":
        raise HTTPException(status_code=404, detail="Withdrawal not found or not pending.")
    uc = _get_or_create_usdt_credit(w.user_id, db)
    if float(uc.usdt_credit or 0) < w.amount:
        raise HTTPException(status_code=400, detail="Insufficient USDT credit.")
    uc.usdt_credit = float(uc.usdt_credit or 0) - w.amount
    uc.total_withdrawn = float(uc.total_withdrawn or 0) + w.amount
    w.status = "approved"
    w.processed_at = datetime.utcnow()
    w.processed_by = admin_user.email
    db.add(models.UsdtHistory(user_id=w.user_id, amount=-w.amount, reason="withdrawal", admin_email=admin_user.email))
    db.commit()
    _admin_audit(admin_user.email or "", "withdrawal_approve", {"withdrawal_id": wid, "user_id": w.user_id, "amount": w.amount})
    return {"ok": True}


class WithdrawalRejectBody(BaseModel):
    rejection_note: Optional[str] = None


@app.post("/admin/withdrawals/{wid}/reject")
@app.post("/admin/usdt-withdrawals/{wid}/reject")
def admin_reject_withdrawal(
    wid: int,
    body: Optional[WithdrawalRejectBody] = None,
    admin_user: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    w = db.query(models.WithdrawalRequest).filter(models.WithdrawalRequest.id == wid).first()
    if not w or w.status != "pending":
        raise HTTPException(status_code=404, detail="Withdrawal not found or not pending.")
    w.status = "rejected"
    w.processed_at = datetime.utcnow()
    w.processed_by = admin_user.email
    if body and body.rejection_note is not None:
        w.rejection_note = (body.rejection_note or "")[:500]
    db.commit()
    _admin_audit(admin_user.email or "", "withdrawal_reject", {"withdrawal_id": wid, "user_id": w.user_id, "rejection_note": getattr(w, "rejection_note", None)})
    return {"ok": True}


# --- User: Referral & USDT Credit (spec endpoints) ---
def _mask_email(email: str | None) -> str:
    """Mask email for display (e.g. a***@b.com)."""
    if not email or "@" not in email:
        return "—"
    local, domain = email.rsplit("@", 1)
    if len(local) <= 2:
        return f"{local[0]}***@{domain}"
    return f"{local[0]}***{local[-1]}@{domain}"


@app.get("/api/v1/user/referral-info")
def user_referral_info(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """Referral code, upline info, total USDT Credit earned, referred users count, saved USDT address."""
    ri_cache_key = f"referral-info:{current_user.id}"
    ri_cached = _rcache_get(ri_cache_key)
    if ri_cached is not None:
        return ri_cached
    uc = db.query(models.UserUsdtCredit).filter(models.UserUsdtCredit.user_id == current_user.id).first()
    total_earned = float(uc.total_earned or 0) if uc else 0.0
    level1 = db.query(models.User).filter(models.User.id == current_user.referred_by).first() if current_user.referred_by else None
    referred_count = db.query(models.User).filter(models.User.referred_by == current_user.id).count()
    ri_result = {
        "referral_code": current_user.referral_code or "",
        "referrer_id": current_user.referred_by,
        "referrer_email": level1.email if level1 else None,
        "total_usdt_credit_earned": total_earned,
        "referred_users_count": referred_count,
        "usdt_withdraw_address": (current_user.usdt_withdraw_address or "").strip() or None,
    }
    _rcache_set(ri_cache_key, ri_result)
    return ri_result


@app.get("/api/v1/user/referral-downline")
def user_referral_downline(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """List users who signed up with current user's referral code, with masked email and USDT Credit earned from each (L1: from their purchases and token burns)."""
    from sqlalchemy import func
    referred = (
        db.query(models.User.id, models.User.email, models.User.created_at)
        .filter(models.User.referred_by == current_user.id)
        .order_by(models.User.created_at.desc())
        .all()
    )
    referred_ids = [uid for uid, _, _ in referred]
    earned_map: dict = {}
    if referred_ids:
        earned_rows = (
            db.query(
                models.ReferralReward.burning_user_id,
                func.coalesce(func.sum(models.ReferralReward.reward_l1), 0),
            )
            .filter(
                models.ReferralReward.level_1_id == current_user.id,
                models.ReferralReward.burning_user_id.in_(referred_ids),
            )
            .group_by(models.ReferralReward.burning_user_id)
            .all()
        )
        earned_map = {uid: float(amt) for uid, amt in earned_rows}
    out = [
        {
            "user_id": uid,
            "email_masked": _mask_email(email),
            "created_at": created_at.isoformat() + "Z" if created_at else None,
            "total_usdt_earned_from_them": earned_map.get(uid, 0.0),
        }
        for uid, email, created_at in referred
    ]
    return out


@app.get("/api/v1/user/referral-reward-history")
def user_referral_reward_history(
    limit: int = Query(50, ge=1, le=200),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """List reward history for current user (earned as L1/L2/L3 from downline token burns)."""
    rrh_cache_key = f"referral-reward-history:{current_user.id}"
    rrh_cached = _rcache_get(rrh_cache_key)
    if rrh_cached is not None:
        return rrh_cached
    rows = (
        db.query(models.ReferralReward, models.User)
        .join(models.User, models.User.id == models.ReferralReward.burning_user_id)
        .filter(
            (models.ReferralReward.level_1_id == current_user.id)
            | (models.ReferralReward.level_2_id == current_user.id)
            | (models.ReferralReward.level_3_id == current_user.id)
        )
        .order_by(models.ReferralReward.created_at.desc())
        .limit(limit)
        .all()
    )
    out = []
    for rr, burning_user in rows:
        if rr.level_1_id == current_user.id:
            amount = float(rr.reward_l1 or 0)
            level = 1
        elif rr.level_2_id == current_user.id:
            amount = float(rr.reward_l2 or 0)
            level = 2
        else:
            amount = float(rr.reward_l3 or 0)
            level = 3
        if amount <= 0:
            continue
        out.append({
            "created_at": rr.created_at.isoformat() + "Z" if rr.created_at else None,
            "burning_user_id": rr.burning_user_id,
            "downline_email": burning_user.email if burning_user else None,
            "amount_usdt_credit": amount,
            "level": level,
        })
    _rcache_set(rrh_cache_key, out)
    return out


@app.get("/api/v1/user/usdt-credit")
def user_usdt_credit(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """Current USDT Credit balance and locked (pending withdrawal) amount."""
    uc = _get_or_create_usdt_credit(current_user.id, db)
    balance = float(uc.usdt_credit or 0)
    pending_rows = db.query(models.WithdrawalRequest).filter(
        models.WithdrawalRequest.user_id == current_user.id,
        models.WithdrawalRequest.status == "pending",
    ).all()
    locked = sum(float(r.amount) for r in pending_rows)
    return {
        "usdt_credit": balance,
        "locked_pending": locked,
        "available": max(0.0, balance - locked),
    }


class UsdtWithdrawAddressBody(BaseModel):
    address: str


@app.post("/api/v1/user/usdt-withdraw-address")
def user_save_usdt_address(
    body: UsdtWithdrawAddressBody,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """Save/update USDT withdrawal address (TRC20 or ERC20 format)."""
    addr = (body.address or "").strip()
    if not _validate_usdt_address(addr):
        raise HTTPException(status_code=400, detail="Invalid USDT wallet address (TRC20 T... or ERC20 0x...).")
    current_user.usdt_withdraw_address = addr
    db.commit()
    return {"ok": True, "address": addr}


class UsdtWithdrawBody(BaseModel):
    amount: float


@app.post("/api/v1/user/usdt-withdraw")
def user_usdt_withdraw(
    body: UsdtWithdrawBody,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """Submit withdrawal request (uses saved address; one pending at a time; locks funds)."""
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive.")
    row = db.query(models.AdminSetting).filter(models.AdminSetting.key == "withdrawal_enabled").first()
    if row and row.value and row.value.lower() == "false":
        raise HTTPException(status_code=403, detail="Withdrawals are currently disabled.")
    min_row = db.query(models.AdminSetting).filter(models.AdminSetting.key == "min_withdrawal_usdt").first()
    min_usdt = float(min_row.value) if min_row and min_row.value else 1.0
    if body.amount < min_usdt:
        raise HTTPException(status_code=400, detail=f"Minimum withdrawal is {min_usdt} USDT Credit.")
    addr = (current_user.usdt_withdraw_address or "").strip()
    if not addr or not _validate_usdt_address(addr):
        raise HTTPException(status_code=400, detail="Please set a valid USDT withdrawal address in Settings first.")
    uc = _get_or_create_usdt_credit(current_user.id, db)
    pending_rows = db.query(models.WithdrawalRequest).filter(
        models.WithdrawalRequest.user_id == current_user.id,
        models.WithdrawalRequest.status == "pending",
    ).all()
    locked = sum(float(r.amount) for r in pending_rows)
    available = float(uc.usdt_credit or 0) - locked
    if body.amount > available:
        raise HTTPException(status_code=400, detail="Insufficient available USDT Credit (including locked pending).")
    existing = db.query(models.WithdrawalRequest).filter(
        models.WithdrawalRequest.user_id == current_user.id,
        models.WithdrawalRequest.status == "pending",
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="You already have a pending withdrawal. Wait for admin approval or rejection.")
    w = models.WithdrawalRequest(user_id=current_user.id, amount=body.amount, address=addr, status="pending")
    db.add(w)
    db.commit()
    db.refresh(w)
    return {"ok": True, "id": w.id, "status": "pending", "amount": body.amount, "to_address": addr}


@app.get("/api/v1/user/usdt-withdraw-history")
def user_usdt_withdraw_history(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """List user's withdrawal requests (status, amount, date, address, rejection_note)."""
    rows = db.query(models.WithdrawalRequest).filter(
        models.WithdrawalRequest.user_id == current_user.id,
    ).order_by(models.WithdrawalRequest.created_at.desc()).limit(100).all()
    return [
        {
            "id": r.id,
            "amount": r.amount,
            "to_address": r.address,
            "status": r.status,
            "created_at": r.created_at.isoformat() + "Z" if r.created_at else None,
            "processed_at": r.processed_at.isoformat() + "Z" if r.processed_at else None,
            "rejection_note": r.rejection_note,
        }
        for r in rows
    ]


@app.get("/api/v1/user/usdt-history")
def user_usdt_history(
    limit: int = Query(50, ge=1, le=200),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """List current user's USDT credit history (rewards, withdrawals, admin adjusts). Same data as admin usdt_history but scoped to current user."""
    rows = (
        db.query(models.UsdtHistory)
        .filter(models.UsdtHistory.user_id == current_user.id)
        .order_by(models.UsdtHistory.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "amount": float(r.amount or 0),
            "reason": r.reason or "",
            "created_at": r.created_at.isoformat() + "Z" if r.created_at else None,
            "admin_email": r.admin_email,
        }
        for r in rows
    ]


@app.get("/api/v1/user/referral-bundle")
def user_referral_bundle(
    limit: int = Query(50, ge=1, le=200),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """
    Single response with referral-info, usdt-credit, usdt-withdraw-history, referral-reward-history,
    referral-downline, and usdt-history. Same shapes as the individual endpoints; use when loading
    Referral & USDT tab to avoid six separate requests.
    """
    rb_cache_key = f"referral-bundle:{current_user.id}"
    rb_cached = _rcache_get(rb_cache_key)
    if rb_cached is not None:
        return rb_cached
    from sqlalchemy import func
    uc = db.query(models.UserUsdtCredit).filter(models.UserUsdtCredit.user_id == current_user.id).first()
    total_earned = float(uc.total_earned or 0) if uc else 0.0
    level1 = db.query(models.User).filter(models.User.id == current_user.referred_by).first() if current_user.referred_by else None
    referred_count = db.query(models.User).filter(models.User.referred_by == current_user.id).count()
    referral_info = {
        "referral_code": current_user.referral_code or "",
        "referrer_id": current_user.referred_by,
        "referrer_email": level1.email if level1 else None,
        "total_usdt_credit_earned": total_earned,
        "referred_users_count": referred_count,
        "usdt_withdraw_address": (current_user.usdt_withdraw_address or "").strip() or None,
    }
    # usdtCredit
    uc_balance = _get_or_create_usdt_credit(current_user.id, db)
    balance = float(uc_balance.usdt_credit or 0)
    pending_rows = db.query(models.WithdrawalRequest).filter(
        models.WithdrawalRequest.user_id == current_user.id,
        models.WithdrawalRequest.status == "pending",
    ).all()
    locked = sum(float(r.amount) for r in pending_rows)
    usdt_credit = {
        "usdt_credit": balance,
        "locked_pending": locked,
        "available": max(0.0, balance - locked),
    }
    # usdt-withdraw-history (withdrawals)
    w_rows = db.query(models.WithdrawalRequest).filter(
        models.WithdrawalRequest.user_id == current_user.id,
    ).order_by(models.WithdrawalRequest.created_at.desc()).limit(100).all()
    withdrawals = [
        {
            "id": r.id,
            "amount": r.amount,
            "to_address": r.address,
            "status": r.status,
            "created_at": r.created_at.isoformat() + "Z" if r.created_at else None,
            "processed_at": r.processed_at.isoformat() + "Z" if r.processed_at else None,
            "rejection_note": r.rejection_note,
        }
        for r in w_rows
    ]
    # referral-reward-history
    rr_rows = (
        db.query(models.ReferralReward, models.User)
        .join(models.User, models.User.id == models.ReferralReward.burning_user_id)
        .filter(
            (models.ReferralReward.level_1_id == current_user.id)
            | (models.ReferralReward.level_2_id == current_user.id)
            | (models.ReferralReward.level_3_id == current_user.id)
        )
        .order_by(models.ReferralReward.created_at.desc())
        .limit(limit)
        .all()
    )
    reward_history = []
    for rr, burning_user in rr_rows:
        if rr.level_1_id == current_user.id:
            amount = float(rr.reward_l1 or 0)
            level = 1
        elif rr.level_2_id == current_user.id:
            amount = float(rr.reward_l2 or 0)
            level = 2
        else:
            amount = float(rr.reward_l3 or 0)
            level = 3
        if amount <= 0:
            continue
        reward_history.append({
            "created_at": rr.created_at.isoformat() + "Z" if rr.created_at else None,
            "burning_user_id": rr.burning_user_id,
            "downline_email": burning_user.email if burning_user else None,
            "amount_usdt_credit": amount,
            "level": level,
        })
    # referral-downline (batched to avoid N+1)
    referred = (
        db.query(models.User.id, models.User.email, models.User.created_at)
        .filter(models.User.referred_by == current_user.id)
        .order_by(models.User.created_at.desc())
        .all()
    )
    referred_ids = [uid for uid, _, _ in referred]
    earned_map: dict = {}
    if referred_ids:
        earned_rows = (
            db.query(
                models.ReferralReward.burning_user_id,
                func.coalesce(func.sum(models.ReferralReward.reward_l1), 0),
            )
            .filter(
                models.ReferralReward.level_1_id == current_user.id,
                models.ReferralReward.burning_user_id.in_(referred_ids),
            )
            .group_by(models.ReferralReward.burning_user_id)
            .all()
        )
        earned_map = {uid: float(amt) for uid, amt in earned_rows}
    downline = [
        {
            "user_id": uid,
            "email_masked": _mask_email(email),
            "created_at": created_at.isoformat() + "Z" if created_at else None,
            "total_usdt_earned_from_them": earned_map.get(uid, 0.0),
        }
        for uid, email, created_at in referred
    ]
    # usdt-history
    uh_rows = (
        db.query(models.UsdtHistory)
        .filter(models.UsdtHistory.user_id == current_user.id)
        .order_by(models.UsdtHistory.created_at.desc())
        .limit(limit)
        .all()
    )
    usdt_history = [
        {
            "id": r.id,
            "user_id": r.user_id,
            "amount": float(r.amount or 0),
            "reason": r.reason or "",
            "created_at": r.created_at.isoformat() + "Z" if r.created_at else None,
            "admin_email": r.admin_email,
        }
        for r in uh_rows
    ]
    rb_result = {
        "referralInfo": referral_info,
        "usdtCredit": usdt_credit,
        "withdrawals": withdrawals,
        "rewardHistory": reward_history,
        "downline": downline,
        "usdtHistory": usdt_history,
    }
    _rcache_set(rb_cache_key, rb_result)
    return rb_result


# --- User: Create withdrawal request (legacy; uses body address) ---
class WithdrawalRequestCreate(BaseModel):
    amount: float
    address: Optional[str] = None


@app.post("/api/v1/withdrawal-request")
def create_withdrawal_request(
    body: WithdrawalRequestCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """User submits a withdrawal request. Uses saved address if body.address omitted; one pending at a time."""
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive.")
    row = db.query(models.AdminSetting).filter(models.AdminSetting.key == "withdrawal_enabled").first()
    if row and row.value and row.value.lower() == "false":
        raise HTTPException(status_code=403, detail="Withdrawals are currently disabled.")
    min_row = db.query(models.AdminSetting).filter(models.AdminSetting.key == "min_withdrawal_usdt").first()
    min_usdt = float(min_row.value) if min_row and min_row.value else 1.0
    if body.amount < min_usdt:
        raise HTTPException(status_code=400, detail=f"Minimum withdrawal is {min_usdt} USDT.")
    addr = (body.address or "").strip() if body.address else (current_user.usdt_withdraw_address or "").strip()
    if not addr:
        raise HTTPException(status_code=400, detail="Set USDT withdrawal address in Settings or provide address.")
    if not _validate_usdt_address(addr):
        raise HTTPException(status_code=400, detail="Invalid USDT wallet address.")
    uc = _get_or_create_usdt_credit(current_user.id, db)
    pending_rows = db.query(models.WithdrawalRequest).filter(
        models.WithdrawalRequest.user_id == current_user.id,
        models.WithdrawalRequest.status == "pending",
    ).all()
    locked = sum(float(r.amount) for r in pending_rows)
    available = float(uc.usdt_credit or 0) - locked
    if body.amount > available:
        raise HTTPException(status_code=400, detail="Insufficient available USDT Credit.")
    existing = db.query(models.WithdrawalRequest).filter(
        models.WithdrawalRequest.user_id == current_user.id,
        models.WithdrawalRequest.status == "pending",
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="One pending withdrawal at a time.")
    w = models.WithdrawalRequest(user_id=current_user.id, amount=body.amount, address=addr, status="pending")
    db.add(w)
    db.commit()
    db.refresh(w)
    return {"ok": True, "id": w.id, "status": "pending", "amount": body.amount}


# --- Admin: Referrals ---
@app.get("/admin/referrals", response_model=List[ReferralRow])
def admin_list_referrals(
    _: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    cache_key = "admin-referrals:all"
    cached = _rcache_get(cache_key)
    if cached is not None:
        return cached

    users = db.query(models.User).all()
    user_map = {u.id: u for u in users}
    from collections import Counter
    downline_counts = Counter(u.referred_by for u in users if u.referred_by is not None)
    out = []
    for u in users:
        referrer = user_map.get(u.referred_by) if u.referred_by else None
        out.append(ReferralRow(
            user_id=u.id,
            email=u.email or "",
            referral_code=u.referral_code,
            referrer_id=u.referred_by,
            referrer_email=referrer.email if referrer else None,
            downline_count=downline_counts.get(u.id, 0),
            referral_earnings=0.0,
        ))
    _rcache_set(cache_key, out)
    return out


@app.get("/admin/referrals/{user_id}/tree", response_model=ReferralTreeOut)
def admin_referral_tree(
    user_id: int,
    _: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    level1 = db.query(models.User).filter(models.User.id == user.referred_by).first() if user.referred_by else None
    level2 = db.query(models.User).filter(models.User.id == level1.referred_by).first() if level1 and level1.referred_by else None
    level3 = db.query(models.User).filter(models.User.id == level2.referred_by).first() if level2 and level2.referred_by else None
    downline = db.query(models.User).filter(models.User.referred_by == user_id).count()
    return ReferralTreeOut(
        user_id=user_id,
        email=user.email or "",
        level1_upline={"user_id": level1.id, "email": level1.email} if level1 else None,
        level2_upline={"user_id": level2.id, "email": level2.email} if level2 else None,
        level3_upline={"user_id": level3.id, "email": level3.email} if level3 else None,
        downline_count=downline,
    )


# --- Admin: Notifications ---
@app.post("/admin/notifications/send")
def admin_send_notification(
    body: NotificationSendBody,
    admin_user: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    n = models.AdminNotification(
        title=body.title,
        content=body.content or "",
        type=body.type or "info",
        target_user_id=body.target_user_id,
    )
    db.add(n)
    db.commit()
    _admin_audit(admin_user.email or "", "notification_send", {"title": body.title, "target_user_id": body.target_user_id})
    return {"ok": True, "id": n.id}


@app.get("/admin/notifications")
def admin_list_notifications(
    limit: int = Query(50, ge=1, le=200),
    _: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    cache_key = f"admin-notifications:{limit}"
    cached = _rcache_get(cache_key)
    if cached is not None:
        return cached

    rows = db.query(models.AdminNotification).order_by(models.AdminNotification.created_at.desc()).limit(limit).all()
    result = [
        {"id": r.id, "title": r.title, "content": r.content, "type": r.type, "target_user_id": r.target_user_id, "created_at": r.created_at.isoformat() + "Z" if r.created_at else None}
        for r in rows
    ]
    _rcache_set(cache_key, result)
    return result


# --- Admin: Settings ---
def _get_setting(db: Session, key: str, default: str) -> str:
    row = db.query(models.AdminSetting).filter(models.AdminSetting.key == key).first()
    return row.value if row and row.value else default


def _get_deduction_multiplier(db: Session) -> float:
    """Read deduction_multiplier from admin_settings; default 1.0. Clamp to [0.01, 100]. Cached for 2 min."""
    global _deduction_multiplier_cache
    if _deduction_multiplier_cache is not None:
        ts, val = _deduction_multiplier_cache
        if _time_module.monotonic() - ts < _DEDUCTION_MULTIPLIER_TTL:
            return val
    raw = _get_setting(db, "deduction_multiplier", "1")
    try:
        v = float(raw)
        result = max(0.01, min(100.0, v))
    except (ValueError, TypeError):
        result = 1.0
    _deduction_multiplier_cache = (_time_module.monotonic(), result)
    return result


def _get_referral_purchase_pct(db: Session) -> tuple[float, float, float]:
    """Read L1/L2/L3 purchase reward percentages from admin_settings; defaults 10, 5, 2. Return as decimals (0.10, 0.05, 0.02)."""
    def pct(key: str, default: float) -> float:
        raw = _get_setting(db, key, str(default))
        try:
            return max(0.0, min(100.0, float(raw))) / 100.0
        except (ValueError, TypeError):
            return default / 100.0
    return (pct("referral_purchase_l1_pct", 10.0), pct("referral_purchase_l2_pct", 5.0), pct("referral_purchase_l3_pct", 2.0))


@app.get("/admin/settings", response_model=List[AdminSettingOut])
def admin_get_settings(
    _: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    cache_key = "admin-settings:all"
    cached = _rcache_get(cache_key)
    if cached is not None:
        return cached

    keys = [
        "registration_bonus_tokens", "min_withdrawal_usdt", "daily_deduction_utc_hour",
        "deduction_multiplier",
        "referral_purchase_l1_pct", "referral_purchase_l2_pct", "referral_purchase_l3_pct",
        "bot_auto_start", "referral_system_enabled", "withdrawal_enabled", "maintenance_mode",
        "api_keys_help_url",
    ]
    defaults = {
        "registration_bonus_tokens": "150", "min_withdrawal_usdt": "10", "daily_deduction_utc_hour": "10",
        "deduction_multiplier": "1",
        "referral_purchase_l1_pct": "10", "referral_purchase_l2_pct": "5", "referral_purchase_l3_pct": "2",
        "bot_auto_start": "true", "referral_system_enabled": "true", "withdrawal_enabled": "true", "maintenance_mode": "false",
        "api_keys_help_url": "#",
    }
    all_settings = db.query(models.AdminSetting).filter(models.AdminSetting.key.in_(keys)).all()
    settings_map = {s.key: s.value for s in all_settings if s.value}
    result = [AdminSettingOut(key=k, value=settings_map.get(k, defaults.get(k, ""))) for k in keys]
    _rcache_set(cache_key, result)
    return result


@app.post("/admin/settings/update")
def admin_update_settings(
    body: AdminSettingsUpdateBody,
    admin_user: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    updates = []
    if body.registration_bonus_tokens is not None:
        updates.append(("registration_bonus_tokens", str(body.registration_bonus_tokens)))
    if body.min_withdrawal_usdt is not None:
        updates.append(("min_withdrawal_usdt", str(body.min_withdrawal_usdt)))
    if body.daily_deduction_utc_hour is not None:
        updates.append(("daily_deduction_utc_hour", str(body.daily_deduction_utc_hour)))
    if body.deduction_multiplier is not None:
        mult = max(0.01, min(100.0, float(body.deduction_multiplier)))
        updates.append(("deduction_multiplier", str(mult)))
    if body.referral_purchase_l1_pct is not None:
        v = max(0.0, min(100.0, float(body.referral_purchase_l1_pct)))
        updates.append(("referral_purchase_l1_pct", str(v)))
    if body.referral_purchase_l2_pct is not None:
        v = max(0.0, min(100.0, float(body.referral_purchase_l2_pct)))
        updates.append(("referral_purchase_l2_pct", str(v)))
    if body.referral_purchase_l3_pct is not None:
        v = max(0.0, min(100.0, float(body.referral_purchase_l3_pct)))
        updates.append(("referral_purchase_l3_pct", str(v)))
    if body.bot_auto_start is not None:
        updates.append(("bot_auto_start", "true" if body.bot_auto_start else "false"))
    if body.referral_system_enabled is not None:
        updates.append(("referral_system_enabled", "true" if body.referral_system_enabled else "false"))
    if body.withdrawal_enabled is not None:
        updates.append(("withdrawal_enabled", "true" if body.withdrawal_enabled else "false"))
    if body.maintenance_mode is not None:
        updates.append(("maintenance_mode", "true" if body.maintenance_mode else "false"))
    if body.api_keys_help_url is not None:
        updates.append(("api_keys_help_url", str(body.api_keys_help_url).strip()))
    if body.stale_key_invalid_days is not None:
        updates.append(("stale_key_invalid_days", str(max(1, int(body.stale_key_invalid_days)))))
    if body.stale_key_inactive_days is not None:
        updates.append(("stale_key_inactive_days", str(max(1, int(body.stale_key_inactive_days)))))
    if body.cleanup_deduction_log_days is not None:
        updates.append(("cleanup_deduction_log_days", str(max(30, int(body.cleanup_deduction_log_days)))))
    if body.cleanup_token_ledger_days is not None:
        updates.append(("cleanup_token_ledger_days", str(max(30, int(body.cleanup_token_ledger_days)))))
    if body.cleanup_dormant_days is not None:
        updates.append(("cleanup_dormant_days", str(max(30, int(body.cleanup_dormant_days)))))
    for k, v in updates:
        row = db.query(models.AdminSetting).filter(models.AdminSetting.key == k).first()
        if row:
            row.value = v
        else:
            db.add(models.AdminSetting(key=k, value=v))
    db.commit()
    _admin_audit(admin_user.email or "", "settings_update", {"keys": [u[0] for u in updates]})
    _rcache_invalidate_prefix("admin-settings")
    global _deduction_multiplier_cache
    _deduction_multiplier_cache = None
    return {"ok": True}


# --- Admin: Persistent audit logs (with filters and export) ---
@app.get("/admin/audit-logs", response_model=List[AdminAuditEntry])
def admin_audit_logs(
    limit: int = Query(100, ge=1, le=500),
    action: Optional[str] = Query(None),
    email: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    _: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    """Persistent audit log with filters. Falls back to in-memory if DB table empty."""
    try:
        q = db.query(models.AdminAuditLog).order_by(models.AdminAuditLog.ts.desc())
        if action:
            q = q.filter(models.AdminAuditLog.action == action)
        if email:
            q = q.filter(models.AdminAuditLog.email.ilike(f"%{email}%"))
        if start_date:
            q = q.filter(models.AdminAuditLog.ts >= datetime.fromisoformat(start_date.replace("Z", "+00:00")))
        if end_date:
            q = q.filter(models.AdminAuditLog.ts <= datetime.fromisoformat(end_date.replace("Z", "+00:00")))
        rows = q.limit(limit).all()
        if rows:
            return [
                AdminAuditEntry(ts=r.ts.isoformat() + "Z" if r.ts else "", email=r.email or "", action=r.action or "", detail=json.loads(r.detail) if r.detail else {})
                for r in rows
            ]
    except Exception:
        pass
    with _admin_audit_lock:
        copy = list(_admin_audit_logs)
    copy.reverse()
    if action:
        copy = [e for e in copy if e.get("action") == action]
    if email:
        copy = [e for e in copy if email.lower() in (e.get("email") or "").lower()]
    if start_date:
        copy = [e for e in copy if (e.get("ts") or "") >= start_date]
    if end_date:
        copy = [e for e in copy if (e.get("ts") or "") <= end_date]
    return [AdminAuditEntry(**e) for e in copy[:limit]]


@app.get("/admin/audit-logs/export")
def admin_audit_logs_export(
    action: Optional[str] = Query(None),
    email: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(1000, ge=1, le=5000),
    _: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    """Export audit logs as CSV."""
    import csv
    import io
    try:
        q = db.query(models.AdminAuditLog).order_by(models.AdminAuditLog.ts.desc())
        if action:
            q = q.filter(models.AdminAuditLog.action == action)
        if email:
            q = q.filter(models.AdminAuditLog.email.ilike(f"%{email}%"))
        if start_date:
            q = q.filter(models.AdminAuditLog.ts >= datetime.fromisoformat(start_date.replace("Z", "+00:00")))
        if end_date:
            q = q.filter(models.AdminAuditLog.ts <= datetime.fromisoformat(end_date.replace("Z", "+00:00")))
        rows = q.limit(limit).all()
        if not rows:
            with _admin_audit_lock:
                copy = list(_admin_audit_logs)
            copy.reverse()
            rows = [type("R", (), {"ts": e.get("ts"), "email": e.get("email"), "action": e.get("action"), "detail": json.dumps(e.get("detail") or {})})() for e in copy[:limit]]
    except Exception:
        with _admin_audit_lock:
            copy = list(_admin_audit_logs)
        copy.reverse()
        rows = [type("R", (), {"ts": e.get("ts"), "email": e.get("email"), "action": e.get("action"), "detail": json.dumps(e.get("detail") or {})})() for e in copy[:limit]]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ts", "email", "action", "detail"])
    for r in rows:
        ts = r.ts.isoformat() + "Z" if hasattr(r.ts, "isoformat") else r.ts
        w.writerow([ts, getattr(r, "email", ""), getattr(r, "action", ""), getattr(r, "detail", "")])
    buf.seek(0)
    from fastapi.responses import StreamingResponse
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=audit_logs.csv"})


# --- Admin: User detail overview ---
@app.get("/admin/users/{user_id}/overview", response_model=UserOverviewOut)
def admin_user_overview(
    user_id: int,
    _: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    vault = db.query(models.APIVault).filter(models.APIVault.user_id == user_id).first()
    created_at = getattr(user, "created_at", None) or (vault.created_at if vault else None)
    user_dict = {
        "id": user.id,
        "email": user.email,
        "plan_tier": user.plan_tier or "trial",
        "pro_expiry": user.pro_expiry.isoformat() if user.pro_expiry else None,
        "status": user.status,
        "bot_status": getattr(user, "bot_status", None),
        "referral_code": user.referral_code,
        "referred_by": user.referred_by,
        "created_at": created_at.isoformat() + "Z" if created_at else None,
    }
    token_balance = None
    tb = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
    if tb:
        rem = float(tb.tokens_remaining or 0)
        purchased = float(tb.purchased_tokens or 0)
        token_balance = {
            "tokens_remaining": rem,
            "total_tokens_added": purchased,
            "total_tokens_deducted": max(0.0, purchased - rem),
            "last_gross_usd_used": tb.last_gross_usd_used,
            "updated_at": tb.updated_at.isoformat() + "Z" if tb.updated_at else None,
        }
    usdt_credit = None
    uc = db.query(models.UserUsdtCredit).filter(models.UserUsdtCredit.user_id == user_id).first()
    if uc:
        usdt_credit = {"usdt_credit": uc.usdt_credit, "total_earned": uc.total_earned, "total_withdrawn": uc.total_withdrawn}
    profit_snapshot = None
    ps = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
    if ps:
        profit_snapshot = {"gross_profit_usd": ps.gross_profit_usd, "daily_gross_profit_usd": ps.daily_gross_profit_usd, "updated_at": ps.updated_at.isoformat() + "Z" if ps.updated_at else None}
    referral = None
    level1 = db.query(models.User).filter(models.User.id == user.referred_by).first() if user.referred_by else None
    downline = db.query(models.User).filter(models.User.referred_by == user_id).count()
    referral = {"referrer_id": user.referred_by, "referrer_email": level1.email if level1 else None, "downline_count": downline}
    api_key_status = None
    vault = db.query(models.APIVault).filter(models.APIVault.user_id == user_id).first()
    if vault:
        api_key_status = {"has_keys": True, "last_tested_at": vault.last_tested_at.isoformat() + "Z" if getattr(vault, "last_tested_at", None) else None}
    else:
        api_key_status = {"has_keys": False}
    withdrawals = []
    for w in db.query(models.WithdrawalRequest).filter(models.WithdrawalRequest.user_id == user_id).order_by(models.WithdrawalRequest.created_at.desc()).limit(50).all():
        withdrawals.append({"id": w.id, "amount": w.amount, "address": w.address, "status": w.status, "created_at": w.created_at.isoformat() + "Z" if w.created_at else None, "processed_at": w.processed_at.isoformat() + "Z" if w.processed_at else None, "rejection_note": getattr(w, "rejection_note", None)})
    deduction_history = []
    with _deduction_logs_lock:
        deduction_history = [e for e in _deduction_logs if e.get("user_id") == user_id][-50:]
    token_add_history = []
    if hasattr(models, "TokenLedger"):
        for ledger in (
            db.query(models.TokenLedger)
            .filter(
                models.TokenLedger.user_id == user_id,
                models.TokenLedger.activity_type == "add",
            )
            .order_by(models.TokenLedger.created_at.desc())
            .limit(50)
            .all()
        ):
            token_add_history.append({
                "amount": float(ledger.amount or 0),
                "reason": ledger.reason or "",
                "created_at": ledger.created_at.isoformat() + "Z" if ledger.created_at else "",
                "detail": _token_add_detail(ledger.reason or "", getattr(ledger, "extra", None)),
            })
    audit_entries = []
    try:
        for a in db.query(models.AdminAuditLog).order_by(models.AdminAuditLog.ts.desc()).limit(200).all():
            if not a.detail:
                continue
            try:
                d = json.loads(a.detail)
                if d.get("user_id") == user_id:
                    audit_entries.append({"ts": a.ts.isoformat() + "Z" if a.ts else "", "email": a.email, "action": a.action, "detail": d})
            except Exception:
                if str(user_id) in (a.detail or ""):
                    audit_entries.append({"ts": a.ts.isoformat() + "Z" if a.ts else "", "email": a.email, "action": a.action, "detail": a.detail})
    except Exception:
        pass
    audit_entries = audit_entries[:30]
    edits_locked = _is_api_key_lock_window()
    return UserOverviewOut(user=user_dict, token_balance=token_balance, usdt_credit=usdt_credit, profit_snapshot=profit_snapshot, referral=referral, api_key_status=api_key_status, withdrawals=withdrawals, deduction_history=deduction_history, token_add_history=token_add_history, audit_entries=audit_entries, edits_locked=edits_locked)


def _aggregate_lent_per_currency(credits_data: Any) -> dict:
    """Aggregate Bitfinex funding credits into lent amount per currency.
    credits_data is list of arrays: [ID, SYMBOL, SIDE, ..., AMOUNT at idx 5, ...].
    SYMBOL is like fUSD, fUST; we normalize to USD, UST, etc.
    """
    result: dict = {}
    if not isinstance(credits_data, list):
        return result
    for row in credits_data:
        try:
            if isinstance(row, (list, tuple)) and len(row) > 5:
                symbol = (row[1] or "").strip().upper()
                if symbol.startswith("F"):
                    symbol = symbol[1:]  # fUSD -> USD
                amount = float(row[5]) if row[5] is not None else 0.0
                if symbol:
                    result[symbol] = result.get(symbol, 0.0) + amount
        except (TypeError, ValueError, IndexError):
            continue
    return result


def _parse_credits_detail(credits_data: Any, prices: Dict[str, float], stablecoins: tuple = ("USD", "USDt", "USDT", "UST")) -> list:
    """Parse credits into list of { id, symbol, amount, rate, period, amount_usd }. Rate at idx 11, period at 12."""
    out: list = []
    if not isinstance(credits_data, list):
        return out
    for row in credits_data:
        try:
            if not isinstance(row, (list, tuple)) or len(row) < 12:
                continue
            sym = (row[1] or "").strip().upper()
            if sym.startswith("F"):
                sym = sym[1:]
            amount = float(row[5]) if row[5] is not None else 0.0
            rate = float(row[11]) if row[11] is not None else 0.0
            period = int(row[12]) if row[12] is not None else 0
            if sym in stablecoins:
                amount_usd = amount
            else:
                amount_usd = amount * prices.get(f"t{sym}USD", 0.0)
            out.append({
                "id": row[0],
                "symbol": sym,
                "amount": round(amount, 8),
                "rate": rate,
                "period": period,
                "amount_usd": round(amount_usd, 2),
            })
        except (TypeError, ValueError, IndexError):
            continue
    return out


def _parse_offers_detail(offers_data: Any, prices: Dict[str, float], stablecoins: tuple = ("USD", "USDt", "USDT", "UST")) -> list:
    """Parse offers into list of { id, symbol, amount, rate, period, amount_usd }. Amount idx 4, rate idx 14, period idx 15."""
    out: list = []
    if not isinstance(offers_data, list):
        return out
    for row in offers_data:
        try:
            if not isinstance(row, (list, tuple)) or len(row) < 16:
                continue
            sym = (row[1] or "").strip().upper()
            if sym.startswith("F"):
                sym = sym[1:]
            amount = float(row[4]) if row[4] is not None else 0.0
            rate = float(row[14]) if row[14] is not None else 0.0
            period = int(row[15]) if row[15] is not None else 0
            if sym in stablecoins:
                amount_usd = amount
            else:
                amount_usd = amount * prices.get(f"t{sym}USD", 0.0)
            out.append({
                "id": row[0],
                "symbol": sym,
                "amount": round(amount, 8),
                "rate": rate,
                "period": period,
                "amount_usd": round(amount_usd, 2),
            })
        except (TypeError, ValueError, IndexError):
            continue
    return out


def _aggregate_offers_per_currency(offers_data: Any) -> dict:
    """Aggregate Bitfinex funding offers into amount per currency.
    offers_data is list of arrays: [ID, SYMBOL, MTS_CREATED, MTS_UPDATED, AMOUNT, ...]. AMOUNT at idx 4.
    """
    result: dict = {}
    if not isinstance(offers_data, list):
        return result
    for row in offers_data:
        try:
            if isinstance(row, (list, tuple)) and len(row) > 4:
                symbol = (row[1] or "").strip().upper()
                if symbol.startswith("F"):
                    symbol = symbol[1:]
                amount = float(row[4]) if row[4] is not None else 0.0
                if symbol:
                    result[symbol] = result.get(symbol, 0.0) + amount
        except (TypeError, ValueError, IndexError):
            continue
    return result


def _per_currency_to_usd(per_currency: dict, prices: Dict[str, float], stablecoins: tuple = ("USD", "USDt", "USDT", "UST")) -> float:
    """Sum amount × price per currency; stablecoins = 1.0."""
    total = 0.0
    for currency, amount in (per_currency or {}).items():
        if currency in stablecoins:
            total += amount
        else:
            total += amount * prices.get(f"t{currency}USD", 0.0)
    return total


def _per_currency_usd_dict(
    per_currency: dict, prices: Dict[str, float], stablecoins: tuple = ("USD", "USDt", "USDT", "UST")
) -> Dict[str, float]:
    """Convert per-currency amounts to per-currency USD (for bar breakdown)."""
    out: Dict[str, float] = {}
    for currency, amount in (per_currency or {}).items():
        if currency in stablecoins:
            out[currency] = amount
        else:
            out[currency] = amount * prices.get(f"t{currency}USD", 0.0)
    return out


def _total_lent_usd(lent_per_currency: dict, ticker_prices: Optional[Dict[str, float]] = None) -> float:
    """Convert lent_per_currency to total USD. USD/USDt/USDT/UST = 1:1; others use ticker_prices (tCCYUSD)."""
    stablecoins = ("USD", "USDt", "USDT", "UST")
    prices = ticker_prices if ticker_prices else _fetch_ticker_prices(set(lent_per_currency or {}))
    return _per_currency_to_usd(lent_per_currency, prices, stablecoins)


# Minimum native amount to request ticker for (avoid API abuse for dust; ~$150 equiv).
MIN_NATIVE_FOR_TICKER: Dict[str, float] = {
    "BTC": 0.002,
    "ETH": 0.05,
    "XRP": 50.0,
}
DEFAULT_MIN_NATIVE_FOR_TICKER = 0.0001


def _currencies_above_ticker_threshold(
    all_currencies: set,
    funding_balances: Dict[str, float],
    credits_per_currency: Dict[str, float],
    offers_per_currency: Dict[str, float],
) -> set:
    """Return subset of currencies we should request ticker for (above min native amount)."""
    stablecoins = {"USD", "USDt", "USDT", "UST"}
    out: set = set()
    for c in all_currencies:
        if c in stablecoins:
            continue
        total_native = (funding_balances.get(c, 0.0) or 0) + (credits_per_currency.get(c, 0.0) or 0) + (offers_per_currency.get(c, 0.0) or 0)
        min_native = MIN_NATIVE_FOR_TICKER.get(c, DEFAULT_MIN_NATIVE_FOR_TICKER)
        if total_native >= min_native:
            out.add(c)
    return out


import time

_ticker_cache: Dict[tuple, tuple] = {}  # (symbols_tuple) -> (prices_dict, cached_at)
TICKER_CACHE_TTL_SEC = 60
TICKER_CACHE_MAX_ENTRIES = 2000  # Cap so many symbol sets don't grow unbounded


def _evict_oldest_ticker_entry() -> None:
    """Evict one oldest ticker cache entry when over limit."""
    if len(_ticker_cache) <= TICKER_CACHE_MAX_ENTRIES:
        return
    oldest_key = min(_ticker_cache.keys(), key=lambda k: _ticker_cache[k][1])
    del _ticker_cache[oldest_key]


def _fetch_ticker_prices(currencies: set) -> Dict[str, float]:
    """Fetch tCCYUSD prices for all non-stablecoins. Returns dict keyed by tCCYUSD. Cached 60s to reduce API calls."""
    from services.bitfinex_service import _get_tickers_sync
    need = sorted([c for c in currencies if c and c not in _STABLECOINS_1TO1])
    if not need:
        return {}
    symbols = [f"t{c}USD" for c in need]
    cache_key = tuple(symbols)
    now = time.monotonic()
    if cache_key in _ticker_cache:
        out, cached_at = _ticker_cache[cache_key]
        if now - cached_at < TICKER_CACHE_TTL_SEC:
            return dict(out)
        del _ticker_cache[cache_key]
    tickers, _ = _get_tickers_sync(symbols)
    out: Dict[str, float] = {}
    if tickers:
        for row in tickers:
            try:
                if isinstance(row, (list, tuple)) and len(row) >= 8:
                    sym = (row[0] or "").strip()
                    if sym:
                        out[sym] = float(row[7]) if row[7] is not None else 0.0
            except (TypeError, ValueError, IndexError):
                continue
    _evict_oldest_ticker_entry()
    _ticker_cache[cache_key] = (out, now)
    return out


async def _get_fold_ticker_prices(currencies: set, fold_state: dict) -> Dict[str, float]:
    """
    Request-scoped ticker for dashboard_fold: merge symbols from both wallets and lending,
    then fetch once for the union. fold_state: {requested, prices, lock, event, arrived}.
    """
    if not currencies:
        return {}
    lock = fold_state["lock"]
    event = fold_state["event"]
    async with lock:
        fold_state["requested"] |= currencies
        fold_state["arrived"] += 1
        if fold_state["arrived"] == 2:
            event.set()
    try:
        await asyncio.wait_for(event.wait(), timeout=2.0)
    except asyncio.TimeoutError:
        pass
    async with lock:
        if not fold_state["prices"]:
            fold_state["prices"] = _fetch_ticker_prices(fold_state["requested"])
        return dict(fold_state["prices"])


def _funding_balances_from_wallets(wallets: Any) -> Dict[str, float]:
    """Extract funding wallet balance per currency from /v2/auth/r/wallets response."""
    result: Dict[str, float] = {}
    if not isinstance(wallets, list):
        return result
    for w in wallets:
        try:
            w_type = (w[0] or "").strip().lower()
            currency = w[1]
            balance = float(w[2])
        except (IndexError, TypeError, ValueError):
            continue
        if w_type != "funding":
            continue
        currency = (currency or "").strip().upper()
        if currency:
            result[currency] = result.get(currency, 0.0) + balance
    return result


async def _portfolio_allocation_snapshot(mgr: BitfinexManager, fold_ticker_state: Optional[dict] = None) -> tuple:
    """
    Wallets, credits, offers in rapid succession; one ticker fetch (or shared fold ticker when fold_ticker_state provided).
    Retries up to 3 times with backoff on transient failures (stable logic like other platforms).
    Returns (summary_dict, log_str, rate_limited: bool).
    Actively Earning = credits USD (from offers API); Pending = offers USD (from credits API); Idle = Total - credits - offers.
    """
    max_attempts = 3
    wallets, credits, offers = None, None, None
    for attempt in range(max_attempts):
        wallets = await mgr.wallets()
        credits = await mgr.funding_credits()
        offers = await mgr.funding_offers()
        
        w_err = wallets[1] if isinstance(wallets, tuple) else None
        c_err = credits[1] if isinstance(credits, tuple) else None
        o_err = offers[1] if isinstance(offers, tuple) else None
        if bitfinex_cache.is_rate_limit_error(w_err) or bitfinex_cache.is_rate_limit_error(c_err) or bitfinex_cache.is_rate_limit_error(o_err):
            break
        if w_err or c_err or o_err:
            if attempt < max_attempts - 1:
                await asyncio.sleep(1.0 * (attempt + 1))
                continue
        break
    w_err = wallets[1] if isinstance(wallets, tuple) else None
    c_err = credits[1] if isinstance(credits, tuple) else None
    o_err = offers[1] if isinstance(offers, tuple) else None
    rate_limited = bitfinex_cache.is_rate_limit_error(w_err) or bitfinex_cache.is_rate_limit_error(c_err) or bitfinex_cache.is_rate_limit_error(o_err)
    wallets_data = wallets[0] if isinstance(wallets, tuple) else None
    credits_data = credits[0] if isinstance(credits, tuple) else None
    offers_data = offers[0] if isinstance(offers, tuple) else None

    # Only compute when we have all three; otherwise return None so caller can serve cache or 200+incomplete.
    if wallets_data is None or credits_data is None or offers_data is None:
        log_incomplete = (
            f"Portfolio Allocation: incomplete (wallets={wallets_data is not None}, "
            f"credits={credits_data is not None}, offers={offers_data is not None}); "
            f"errors: wallets={w_err!r}, credits={c_err!r}, offers={o_err!r}"
        )
        return None, log_incomplete, rate_limited

    funding_balances = _funding_balances_from_wallets(wallets_data) if wallets_data else {}
    # Actively Earning = /funding/credits (funds lent out); Pending = /funding/offers (in order book).
    credits_per_currency = _aggregate_lent_per_currency(credits_data) if credits_data else {}
    offers_per_currency = _aggregate_offers_per_currency(offers_data) if offers_data else {}

    all_currencies = set(funding_balances) | set(credits_per_currency) | set(offers_per_currency)
    # Only request ticker for currencies above min native amount (~$150 equiv) to reduce API usage.
    currencies_for_ticker = _currencies_above_ticker_threshold(
        all_currencies, funding_balances, credits_per_currency, offers_per_currency
    )
    if fold_ticker_state:
        prices = await _get_fold_ticker_prices(currencies_for_ticker, fold_ticker_state)
    else:
        prices = _fetch_ticker_prices(currencies_for_ticker)
    stablecoins = ("USD", "USDt", "USDT", "UST")

    total_wallet_usd = _per_currency_to_usd(funding_balances, prices, stablecoins)
    credits_usd = _per_currency_to_usd(credits_per_currency, prices, stablecoins)
    offers_usd = _per_currency_to_usd(offers_per_currency, prices, stablecoins)
    idle_usd = total_wallet_usd - credits_usd - offers_usd
    idle_usd = max(0.0, idle_usd)  # avoid negative from rounding

    # Per-currency USD for wallet (for frontend)
    per_currency_usd: Dict[str, float] = {}
    for c, amt in funding_balances.items():
        if c in stablecoins:
            per_currency_usd[c] = amt
        else:
            per_currency_usd[c] = amt * prices.get(f"t{c}USD", 0.0)

    lent_per_currency_usd = _per_currency_usd_dict(credits_per_currency, prices, stablecoins)
    offers_per_currency_usd = _per_currency_usd_dict(offers_per_currency, prices, stablecoins)
    idle_per_currency_usd: Dict[str, float] = {}
    for c in all_currencies:
        w = per_currency_usd.get(c, 0.0)
        l = lent_per_currency_usd.get(c, 0.0)
        o = offers_per_currency_usd.get(c, 0.0)
        idle_per_currency_usd[c] = round(max(0.0, w - l - o), 2)
    lent_per_currency_usd = {c: round(v, 2) for c, v in lent_per_currency_usd.items()}
    offers_per_currency_usd = {c: round(v, 2) for c, v in offers_per_currency_usd.items()}

    # Performance metrics: weighted avg APR and est. daily from credits (Actively Earning).
    credits_detail = _parse_credits_detail(credits_data, prices, stablecoins)
    offers_detail = _parse_offers_detail(offers_data, prices, stablecoins)
    sum_amount_usd = sum(c["amount_usd"] for c in credits_detail)
    sum_rate_weighted = sum(c["amount_usd"] * c["rate"] for c in credits_detail)
    # Bitfinex rate is daily (FRR); APR % = rate * 365 * 100.
    if sum_amount_usd > 0:
        weighted_avg_apr_pct = round((sum_rate_weighted / sum_amount_usd) * 365 * 100, 4)
        est_daily_earnings_usd = round(sum_rate_weighted, 2)
    else:
        weighted_avg_apr_pct = 0.0
        est_daily_earnings_usd = 0.0
    # Yield / Total Wallet % = weighted_avg_apr * (credits_usd / total_wallet_usd)
    yield_over_total_pct = round(weighted_avg_apr_pct * (credits_usd / total_wallet_usd), 4) if total_wallet_usd > 0 else 0.0
    credits_count = len(credits_data) if isinstance(credits_data, list) else 0
    offers_count = len(offers_data) if isinstance(offers_data, list) else 0

    # Include a currency in per-currency breakdown only if total value > $150 (same logic as ticker threshold).
    MIN_DISPLAY_USD = 150.0
    allowed_currencies = {
        c for c in all_currencies
        if (per_currency_usd.get(c, 0.0) + lent_per_currency_usd.get(c, 0.0) + offers_per_currency_usd.get(c, 0.0)) > MIN_DISPLAY_USD
    }
    def _filter_per_currency(d: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in (d or {}).items() if k in allowed_currencies}

    summary = {
        "total_usd_all": round(total_wallet_usd, 2),
        "usd_only": funding_balances.get("USD", 0.0) + funding_balances.get("USDt", 0.0) + funding_balances.get("USDT", 0.0),
        "per_currency": _filter_per_currency(funding_balances),
        "per_currency_usd": _filter_per_currency(per_currency_usd),
        "lent_per_currency": _filter_per_currency(credits_per_currency),
        "offers_per_currency": _filter_per_currency(offers_per_currency),
        "lent_per_currency_usd": _filter_per_currency(lent_per_currency_usd),
        "offers_per_currency_usd": _filter_per_currency(offers_per_currency_usd),
        "idle_per_currency_usd": _filter_per_currency(idle_per_currency_usd),
        "total_lent_usd": round(credits_usd, 2),       # Actively Earning
        "total_offers_usd": round(offers_usd, 2),      # Pending Deployment (In Order Book)
        "idle_usd": round(idle_usd, 2),               # Idle Funds (Cash Drag)
        "weighted_avg_apr_pct": weighted_avg_apr_pct,
        "est_daily_earnings_usd": est_daily_earnings_usd,
        "yield_over_total_pct": yield_over_total_pct,
        "credits_count": credits_count,
        "offers_count": offers_count,
        "credits_detail": credits_detail,
        "offers_detail": offers_detail,
    }
    log_str = (
        f"Portfolio Allocation: Total Wallet USD: ${total_wallet_usd:,.2f} | "
        f"Credits USD: ${credits_usd:,.2f} | Offers USD: ${offers_usd:,.2f} | "
        f"Resulting Idle: ${idle_usd:,.2f} (X - Y - Z)"
    )
    return summary, log_str, rate_limited


def _empty_wallet_response():
    return {
        "message": "No data yet",
        "total_usd_all": 0.0,
        "usd_only": 0.0,
        "per_currency": {},
        "per_currency_usd": {},
        "lent_per_currency": {},
        "offers_per_currency": {},
        "lent_per_currency_usd": {},
        "offers_per_currency_usd": {},
        "idle_per_currency_usd": {},
        "total_lent_usd": 0.0,
        "total_offers_usd": 0.0,
        "idle_usd": 0.0,
        "weighted_avg_apr_pct": 0.0,
        "est_daily_earnings_usd": 0.0,
        "yield_over_total_pct": 0.0,
        "credits_count": 0,
        "offers_count": 0,
        "credits_detail": [],
        "offers_detail": [],
    }


async def _get_wallet_data(
    user_id: int, user: "models.User", db: Session, fold_ticker_state: Optional[dict] = None
) -> tuple[dict, str]:
    """
    Shared logic for wallet summary. Returns (data_dict, source) where source is "cache" or "live".
    On error returns (_empty_wallet_response(), "live", incomplete). Raises HTTPException only for auth/404.
    When snapshot is incomplete and no cache, returns 200 with empty data and incomplete=True so dashboard still loads.
    When fold_ticker_state is provided (from dashboard_fold), ticker is shared with lending path for single fetch.
    """
    try:
        cached = await bitfinex_cache.get_cached(user_id, bitfinex_cache.KEY_WALLETS)
    except Exception as e:
        logger.exception("wallets/%s cache get failed: %s", user_id, e)
        return _empty_wallet_response(), "live", False
    try:
        if cached is not None:
            data, from_cache = cached
            if from_cache and data is not None:
                return data, "cache", False
        in_cooldown = await bitfinex_cache.is_in_cooldown(user_id, bitfinex_cache.KEY_WALLETS)
    except Exception as e:
        logger.exception("wallets/%s cache/cooldown failed: %s", user_id, e)
        return _empty_wallet_response(), "live", False
    if in_cooldown:
        return {
            "total_usd_all": 0.0,
            "usd_only": 0.0,
            "per_currency": {},
            "per_currency_usd": {},
            "lent_per_currency": {},
            "offers_per_currency": {},
            "lent_per_currency_usd": {},
            "offers_per_currency_usd": {},
            "idle_per_currency_usd": {},
            "total_lent_usd": 0.0,
            "total_offers_usd": 0.0,
            "idle_usd": 0.0,
            "weighted_avg_apr_pct": 0.0,
            "est_daily_earnings_usd": 0.0,
            "yield_over_total_pct": 0.0,
            "credits_count": 0,
            "offers_count": 0,
            "credits_detail": [],
            "offers_detail": [],
            "_rate_limited": True,
        }, "cache", False
    keys = user.vault.get_keys()
    mgr = BitfinexManager(keys["bfx_key"], keys["bfx_secret"])
    try:
        summary, log_str, rate_limited = await _portfolio_allocation_snapshot(mgr, fold_ticker_state)
        if os.getenv("LOG_PORTFOLIO_ALLOCATION"):
            print(f"[user_id={user_id}] {log_str}")
        if rate_limited:
            await bitfinex_cache.set_rate_limit_cooldown(user_id, bitfinex_cache.KEY_WALLETS)
        if summary is None:
            logger.warning("wallets/%s snapshot incomplete: %s", user_id, log_str)
            cached = await bitfinex_cache.get_cached(user_id, bitfinex_cache.KEY_WALLETS)
            if cached is not None:
                data, _ = cached
                if data is not None:
                    return data, "cache", False
            return _empty_wallet_response(), "live", True
    except HTTPException:
        raise
    except Exception as e:
        if bitfinex_cache.is_rate_limit_error(str(e)):
            try:
                await bitfinex_cache.set_rate_limit_cooldown(user_id, bitfinex_cache.KEY_WALLETS)
            except Exception:
                pass
        logger.exception("wallets/%s Bitfinex snapshot failed: %s", user_id, e)
        return _empty_wallet_response(), "live", False
    try:
        await bitfinex_cache.set_cached(user_id, bitfinex_cache.KEY_WALLETS, summary)
    except Exception:
        pass
    return summary, "live", False


@app.get("/wallets/{user_id}")
async def wallet_summary(
    user_id: int,
    response: Response,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Returns Bitfinex wallet USD totals and currently lent out per currency.
    User end only: caller must be the same user. Cached to respect Bitfinex rate limits.
    """
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this user.")

    wcache_key = f"wallets:{user_id}"
    wcached = _rcache_get(wcache_key)
    if wcached is not None:
        return wcached

    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        vault = getattr(user, "vault", None)
        if not vault:
            raise HTTPException(status_code=404, detail="API keys not found.")
    except HTTPException:
        raise
    except (ProgrammingError, SQLAlchemyError):
        return _empty_wallet_response()
    except Exception as e:
        logger.exception("wallets/%s load user/vault failed: %s", user_id, e)
        return _empty_wallet_response()
    data, source, incomplete = await _get_wallet_data(user_id, user, db)
    response.headers["X-Data-Source"] = source
    response.headers["X-Authenticated-User-Id"] = str(current_user.id)
    if incomplete:
        response.headers["X-Data-Incomplete"] = "true"
    if source == "cache":
        exp = await bitfinex_cache.cache_expires_at(user_id, bitfinex_cache.KEY_WALLETS)
        if exp is not None:
            response.headers["X-Cache-Expires-At"] = str(int(exp))
    elif source == "live" and data.get("_rate_limited"):
        response.headers["X-Rate-Limited"] = "true"
        response.headers["Retry-After"] = "60"
    elif source == "live":
        exp = await bitfinex_cache.cache_expires_at(user_id, bitfinex_cache.KEY_WALLETS)
        if exp is not None:
            response.headers["X-Cache-Expires-At"] = str(int(exp))
    _rcache_set(wcache_key, data)
    return data


@app.get("/api/dashboard-fold")
async def dashboard_fold(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """
    Single response with wallets, botStats, userStatus, and lending for the dashboard.
    Uses response cache (15s TTL). Sets X-Authenticated-User-Id header.
    """
    uid = current_user.id
    cache_key = f"dashboard-fold:{uid}"
    cached = _rcache_get(cache_key)
    if cached is not None:
        return JSONResponse(
            content=cached,
            headers={"X-Authenticated-User-Id": str(uid)},
        )

    try:
        result = await _dashboard_fold_impl(current_user, db)
        _rcache_set(cache_key, result)
        return JSONResponse(
            content=result,
            headers={"X-Authenticated-User-Id": str(uid)},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("dashboard_fold user_id=%s error=%s", uid, e)
        raise HTTPException(status_code=500, detail="Internal server error loading dashboard.")


async def _dashboard_fold_impl(current_user: models.User, db: Session):
    user_id = current_user.id
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    vault = getattr(user, "vault", None)
    default_user_status = {
        "plan_tier": "trial",
        "rebalance_interval": 0,
        "tokens_remaining": 0.0,
        "tokens_used": 0,
        "initial_token_credit": 0,
        "gross_profit_usd": 0.0,
        "pro_expiry": None,
        "created_at": None,
    }

    # Shared ticker state so wallets and lending do one Bitfinex ticker fetch for the union of currencies
    fold_ticker_state = {
        "requested": set(),
        "prices": {},
        "lock": asyncio.Lock(),
        "event": asyncio.Event(),
        "arrived": 0,
    }

    async def _wallets():
        if not vault:
            return _empty_wallet_response()
        db_w = database.SessionLocal()
        try:
            user_w = db_w.query(models.User).filter(models.User.id == user_id).first()
            if not user_w:
                return _empty_wallet_response()
            data, _, _ = await _get_wallet_data(user_id, user_w, db_w, fold_ticker_state)
            return data
        except HTTPException:
            raise
        except Exception:
            return _empty_wallet_response()
        finally:
            db_w.close()

    async def _bot_stats():
        db_b = database.SessionLocal()
        try:
            return await _get_bot_stats_data(user_id, db_b)
        except Exception:
            return {"active": False, "engines": [], "total_loaned": "0.00", "bot_status": "stopped", "has_api_keys": bool(vault)}
        finally:
            db_b.close()

    async def _lending():
        db_l = database.SessionLocal()
        try:
            lending_resp, _ = await _get_lending_stats_data(user_id, db_l, fold_ticker_state=fold_ticker_state)
            return lending_resp.model_dump()
        except Exception:
            return {"gross_profit": 0.0, "bitfinex_fee": 0.0, "net_profit": 0.0}
        finally:
            db_l.close()

    wallets_data, bot_stats, lending_data = await asyncio.gather(_wallets(), _bot_stats(), _lending())

    # When lending has gross profit but no trades (e.g. from cache/DB), fill trades in fold so frontend skips GET /api/funding-trades
    if (
        vault
        and (lending_data.get("gross_profit") or 0) > 0
        and not (lending_data.get("trades") and len(lending_data.get("trades", [])) > 0)
    ):
        try:
            trade_records = await _fetch_funding_trade_records_for_user(user)
            if trade_records:
                FOLD_TRADES_CAP = 100
                lending_data["total_trades_count"] = len(trade_records)
                lending_data["trades"] = trade_records[-FOLD_TRADES_CAP:]
        except Exception:
            pass

    try:
        user_status = _get_user_status_data(user_id, db)
        user_status_data = user_status.model_dump()
    except HTTPException:
        raise
    except Exception:
        user_status_data = default_user_status

    deduction_multiplier = _get_deduction_multiplier(db)
    try:
        token_balance = _get_token_balance_for_fold(db, user_id)
    except Exception:
        token_balance = {"tokens_remaining": 0.0, "total_tokens_added": 0.0, "total_tokens_deducted": 0.0}
    return {
        "wallets": wallets_data,
        "botStats": bot_stats,
        "userStatus": user_status_data,
        "lending": lending_data,
        "deduction_multiplier": deduction_multiplier,
        "token_balance": token_balance,
    }


# --- Stripe Webhook (referrals + subscription) ---
stripe.api_key = os.getenv("STRIPE_API_KEY", "")
_raw_webhook_secret = (os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip().strip('"').strip("'")
STRIPE_WEBHOOK_SECRET = _raw_webhook_secret
if STRIPE_WEBHOOK_SECRET:
    logger.info("Stripe webhook secret loaded (len=%d, prefix=%s)", len(STRIPE_WEBHOOK_SECRET), STRIPE_WEBHOOK_SECRET[:7] if len(STRIPE_WEBHOOK_SECRET) >= 7 else "?")
else:
    logger.warning("STRIPE_WEBHOOK_SECRET is empty; webhook signature verification will fail.")
# Price IDs: monthly and yearly (create in Stripe Dashboard)
STRIPE_PRICE_PRO_MONTHLY = os.getenv("STRIPE_PRICE_PRO_MONTHLY", "")
STRIPE_PRICE_AI_ULTRA_MONTHLY = os.getenv("STRIPE_PRICE_AI_ULTRA_MONTHLY", "")
STRIPE_PRICE_WHALES_MONTHLY = os.getenv("STRIPE_PRICE_WHALES_MONTHLY", "")
STRIPE_PRICE_PRO_YEARLY = os.getenv("STRIPE_PRICE_PRO_YEARLY", "")
STRIPE_PRICE_AI_ULTRA_YEARLY = os.getenv("STRIPE_PRICE_AI_ULTRA_YEARLY", "")
STRIPE_PRICE_WHALES_YEARLY = os.getenv("STRIPE_PRICE_WHALES_YEARLY", "")

# Plan limits and rebalance (minutes) for webhook
PLAN_REBALANCE_MIN = {"pro": 30, "ai_ultra": 3, "whales": 1}

# Tier order for no-downgrade: trial/free < pro < ai_ultra < whales
PLAN_TIER_RANK = {"trial": 0, "free": 0, "pro": 1, "ai_ultra": 2, "whales": 3}


def _plan_tier_no_downgrade(current: str, new_from_payment: str) -> str:
    """Return the higher of current and new plan (no downgrade). Used in subscription flows only."""
    c = (current or "").strip().lower() or "trial"
    n = (new_from_payment or "").strip().lower() or "trial"
    rank_c = PLAN_TIER_RANK.get(c, 0)
    rank_n = PLAN_TIER_RANK.get(n, 0)
    return n if rank_n >= rank_c else c


# Token award per subscription payment (added to purchased_tokens in webhook)
PLAN_TOKEN_AWARD_MONTHLY = {"pro": 2000, "ai_ultra": 9000, "whales": 40000}
PLAN_TOKEN_AWARD_YEARLY = {"pro": 24000, "ai_ultra": 108000, "whales": 480000}

# Actual USD price per plan/interval (for referral reward base only; docstring: Pro 20/192, AI Ultra 60/576, Whales 200/1920)
PLAN_USD_PRICE_MONTHLY = {"pro": 20, "ai_ultra": 60, "whales": 200}
PLAN_USD_PRICE_YEARLY = {"pro": 192, "ai_ultra": 576, "whales": 1920}


def _get_subscription_usd_price(plan: str, interval: str) -> float:
    """Return actual USD price for plan/interval (for referral reward base). Default 0.0 if unknown."""
    if (plan or "").lower() not in ("pro", "ai_ultra", "whales") or (interval or "").lower() not in ("monthly", "yearly"):
        return 0.0
    plan = (plan or "").lower()
    interval = (interval or "monthly").lower()
    if interval == "yearly":
        return float(PLAN_USD_PRICE_YEARLY.get(plan, 0))
    return float(PLAN_USD_PRICE_MONTHLY.get(plan, 0))


class CreateCheckoutPayload(BaseModel):
    plan: str  # "pro" | "ai_ultra" | "whales"
    interval: str  # "monthly" | "yearly"


class SubscriptionBypassPayload(BaseModel):
    plan: str  # "pro" | "ai_ultra" | "whales"
    interval: str  # "monthly" | "yearly"


class CreateCheckoutTokensPayload(BaseModel):
    amount_usd: float  # e.g. 10 → user gets 1000 tokens (1 USD = 100 tokens)


# --- Token deposit (Add tokens): 1 USD = 100 tokens, min $1 (Stripe checkout or dev bypass) ---
class TokenDepositPayload(BaseModel):
    usd_amount: float
    bypass_payment: Optional[bool] = False  # Dev only: when True and ALLOW_DEV_CONNECT=1, credit tokens without Stripe


@app.post("/api/v1/tokens/deposit")
def token_deposit(
    payload: TokenDepositPayload,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """
    Validate USD amount and compute tokens to award (1 USD = 100 tokens).
    Minimum $1. When bypass_payment=True and ALLOW_DEV_CONNECT=1, credits tokens immediately (no Stripe).
    """
    usd_amount = payload.usd_amount
    user_id = current_user.id

    # Validation: must be a number and >= 1
    try:
        amount_float = float(usd_amount)
    except (TypeError, ValueError):
        msg = "Please enter a valid USD amount"
        logger.warning("token_deposit_validation_failed user_id=%s usd_amount=%s error=%s", user_id, usd_amount, msg)
        return JSONResponse(status_code=400, content={"status": "error", "message": msg})

    if isinstance(usd_amount, bool) or (not isinstance(usd_amount, (int, float))):
        msg = "Please enter a valid USD amount"
        logger.warning("token_deposit_validation_failed user_id=%s usd_amount=%s error=%s", user_id, usd_amount, msg)
        return JSONResponse(status_code=400, content={"status": "error", "message": msg})

    if amount_float < 1:
        msg = "Minimum deposit is $1"
        logger.warning("token_deposit_validation_failed user_id=%s usd_amount=%s error=%s", user_id, usd_amount, msg)
        return JSONResponse(status_code=400, content={"status": "error", "message": msg})

    # 1 USD = 100 tokens (same as create-checkout-session-tokens)
    tokens_to_award = int(amount_float * 100)
    logger.info("token_deposit_calculation user_id=%s usd_amount=%s tokens_to_award=%s", user_id, amount_float, tokens_to_award)

    # Dev bypass: credit tokens without Stripe (ALLOW_DEV_CONNECT=1 and bypass_payment=True)
    if payload.bypass_payment and os.getenv("ALLOW_DEV_CONNECT") == "1":
        try:
            token_ledger_svc.add_tokens(db, user_id, float(tokens_to_award), "deposit_usd", extra={"usd_amount": amount_float})
            l1_pct, l2_pct, l3_pct = _get_referral_purchase_pct(db)
            apply_referral_rewards_on_purchase(db, user_id, amount_float, reward_purchase_l1=l1_pct, reward_purchase_l2=l2_pct, reward_purchase_l3=l3_pct)
            db.commit()
            logger.info("token_deposit_bypass user_id=%s usd=%s tokens_added=%s", user_id, amount_float, tokens_to_award)
            _rcache_invalidate_user(user_id)
        except Exception as e:
            db.rollback()
            logger.exception("token_deposit_bypass failed: %s", e)
            return JSONResponse(status_code=500, content={"status": "error", "message": "Token deposit failed."})
        return {
            "status": "success",
            "usd_amount": amount_float,
            "tokens_to_award": tokens_to_award,
            "message": f"{tokens_to_award} tokens added (dev bypass).",
        }

    # TODO: Add Stripe checkout session creation here
    return {
        "status": "success",
        "usd_amount": amount_float,
        "tokens_to_award": tokens_to_award,
        "message": "Stripe checkout setup pending (add later)",
    }


@app.post("/api/create-checkout-session-tokens")
async def create_checkout_session_tokens(
    payload: CreateCheckoutTokensPayload,
    current_user: models.User = Depends(get_current_user),
):
    """
    One-time payment to add tokens. 1 USD = 100 tokens.
    """
    amount_usd = max(0.5, min(1000.0, float(payload.amount_usd)))
    amount_cents = int(round(amount_usd * 100))
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="Payments not configured.")
    origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
    tokens = int(amount_usd * 100)
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            customer_email=current_user.email,
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": f"Token pack ({tokens} tokens)", "description": "1 USD = 100 tokens"},
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }],
            success_url=origin + "/dashboard?tokens=success",
            cancel_url=origin + "/dashboard?subscription=cancel",
            metadata={"type": "tokens", "user_id": str(current_user.id), "amount_usd": str(amount_usd), "tokens": str(tokens)},
        )
        return {"url": session.url}
    except Exception as e:
        logger.exception("stripe_token_checkout failed user_id=%s: %s", current_user.id, e)
        raise HTTPException(status_code=500, detail="Payment setup failed. Please try again.")


def _get_stripe_price_id(plan: str, interval: str) -> str:
    """Return Stripe Price ID for plan + interval. Empty string if not configured."""
    raw = ""
    if interval == "yearly":
        if plan == "pro":
            raw = STRIPE_PRICE_PRO_YEARLY or ""
        elif plan == "ai_ultra":
            raw = STRIPE_PRICE_AI_ULTRA_YEARLY or ""
        elif plan == "whales":
            raw = STRIPE_PRICE_WHALES_YEARLY or ""
    else:
        if plan == "pro":
            raw = STRIPE_PRICE_PRO_MONTHLY or ""
        elif plan == "ai_ultra":
            raw = STRIPE_PRICE_AI_ULTRA_MONTHLY or ""
        elif plan == "whales":
            raw = STRIPE_PRICE_WHALES_MONTHLY or ""
    if not raw:
        return ""
    raw = (raw or "").strip().strip('"').strip("'")
    return _resolve_stripe_price_id(raw, interval)


def _resolve_stripe_price_id(env_value: str, interval: str) -> str:
    """
    Resolve env value to a Stripe Price ID. If env_value is already price_xxx, return it.
    If it is prod_xxx, fetch the product's price for the given interval (monthly -> month, yearly -> year).
    """
    if not env_value or not stripe.api_key:
        return ""
    val = (env_value or "").strip().strip('"').strip("'")
    if val.startswith("price_"):
        return val
    if val.startswith("prod_"):
        try:
            want_interval = "year" if interval == "yearly" else "month"
            for p in stripe.Price.list(product=val, active=True).auto_paging_iter():
                if getattr(p, "recurring", None) and getattr(p.recurring, "interval", None) == want_interval:
                    return p.id
            # Fallback: use product default_price if available (e.g. single recurring price)
            prod = stripe.Product.retrieve(val)
            if getattr(prod, "default_price", None):
                return prod.default_price if isinstance(prod.default_price, str) else prod.default_price.id
        except Exception as e:
            logger.warning("stripe_resolve_product_to_price product=%s interval=%s error=%s", val, interval, e)
    return ""


# Cache for resolving STRIPE_PRICE_* env (price id or product id) to product id for comparison
_stripe_env_product_id_cache: dict = {}


def _resolve_stripe_env_to_product_id(env_value: str) -> str:
    """
    Resolve env value (product id prod_xxx or price id price_xxx) to normalized product id for comparison.
    Uses module-level cache to avoid repeated Stripe API calls.
    """
    if not env_value:
        return ""
    key = (env_value or "").strip().strip('"').strip("'")
    if not key:
        return ""
    if key in _stripe_env_product_id_cache:
        return _stripe_env_product_id_cache[key]
    try:
        if key.startswith("price_"):
            price = stripe.Price.retrieve(key)
            product = price.get("product")
            resolved = product.get("id") if isinstance(product, dict) else (product or "")
            resolved = (resolved or "").strip()
        else:
            resolved = key
        _stripe_env_product_id_cache[key] = resolved
        return resolved
    except Exception as e:
        logger.warning("_resolve_stripe_env_to_product_id key=%s error=%s", key[:20], e)
        _stripe_env_product_id_cache[key] = ""
        return ""


def _plan_interval_from_invoice(invoice_data: dict) -> tuple:
    """
    Derive (plan, interval) from invoice line items (canonical source for subscription invoices).
    Uses the first line's price -> product id and recurring interval, mapped to our plan/interval via STRIPE_PRICE_* env (product or price id).
    Returns ("pro", "monthly") if we cannot determine.
    Supports both legacy line item "price" and newer "pricing.price_details.price" / "pricing.price_details.product".
    """
    plan, interval = "pro", "monthly"
    try:
        lines = invoice_data.get("lines") or {}
        data_list = lines.get("data") if isinstance(lines, dict) else []
        # If webhook payload has no line items, retrieve invoice with expand (Stripe may not include lines in event)
        if not data_list and invoice_data.get("id"):
            try:
                inv = stripe.Invoice.retrieve(
                    invoice_data["id"],
                    expand=["lines.data.price"],
                )
                lines = inv.get("lines") or {}
                data_list = lines.get("data") if isinstance(lines, dict) else []
            except Exception as e:
                logger.warning("stripe_webhook invoice retrieve expand error=%s", e)
        if not data_list:
            logger.warning("_plan_interval_from_invoice default invoice_id=%s reason=no_line_items", invoice_data.get("id"))
            return plan, interval
        first = data_list[0]
        price_obj = first.get("price")
        price_id = price_obj if isinstance(price_obj, str) else (price_obj.get("id") if price_obj else None)
        # Newer Stripe API: line item has pricing.price_details.price and optionally .product
        if not price_id:
            pricing = first.get("pricing") or {}
            price_details = pricing.get("price_details") or {}
            price_id = price_details.get("price")
            if isinstance(price_id, dict):
                price_id = price_id.get("id")
        if not price_id:
            logger.warning("_plan_interval_from_invoice default invoice_id=%s reason=no_price_or_pricing", invoice_data.get("id"))
            return plan, interval
        price = stripe.Price.retrieve(price_id)
        product_id = price.get("product")
        if isinstance(product_id, dict):
            product_id = product_id.get("id")
        if not product_id:
            logger.warning("_plan_interval_from_invoice default invoice_id=%s reason=no_product_on_price", invoice_data.get("id"))
            return plan, interval
        product_id = (product_id or "").strip()
        recur = price.get("recurring") or {}
        interval_unit = recur.get("interval", "month")
        interval = "yearly" if interval_unit == "year" else "monthly"
        # Compare to env values (each may be product id or price id; resolve price -> product)
        whales_m = _resolve_stripe_env_to_product_id(STRIPE_PRICE_WHALES_MONTHLY)
        whales_y = _resolve_stripe_env_to_product_id(STRIPE_PRICE_WHALES_YEARLY)
        ai_ultra_m = _resolve_stripe_env_to_product_id(STRIPE_PRICE_AI_ULTRA_MONTHLY)
        ai_ultra_y = _resolve_stripe_env_to_product_id(STRIPE_PRICE_AI_ULTRA_YEARLY)
        pro_m = _resolve_stripe_env_to_product_id(STRIPE_PRICE_PRO_MONTHLY)
        pro_y = _resolve_stripe_env_to_product_id(STRIPE_PRICE_PRO_YEARLY)
        if product_id == whales_m or product_id == whales_y:
            plan = "whales"
        elif product_id == ai_ultra_m or product_id == ai_ultra_y:
            plan = "ai_ultra"
        elif product_id == pro_m or product_id == pro_y:
            plan = "pro"
        else:
            logger.warning("_plan_interval_from_invoice default invoice_id=%s reason=unknown_product_id product_id=%s", invoice_data.get("id"), product_id)
    except Exception as e:
        logger.warning("_plan_interval_from_invoice error=%s invoice_id=%s", e, invoice_data.get("id"))
    return plan, interval


@app.post("/api/v1/subscription/bypass")
def subscription_bypass(
    payload: SubscriptionBypassPayload,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """
    Dev-only: apply subscription (plan_tier, pro_expiry, token award) without Stripe.
    Requires ALLOW_DEV_CONNECT=1. Whales monthly = 200 USD equivalent, 40000 tokens.
    """
    if os.getenv("ALLOW_DEV_CONNECT") != "1":
        raise HTTPException(status_code=404, detail="Not available.")
    plan = (payload.plan or "").lower()
    interval = (payload.interval or "monthly").lower()
    if plan not in ("pro", "ai_ultra", "whales") or interval not in ("monthly", "yearly"):
        raise HTTPException(status_code=400, detail="Invalid plan or interval.")
    interval_days = 365 if interval == "yearly" else 30
    effective_plan = _plan_tier_no_downgrade(current_user.plan_tier or "trial", plan)
    if effective_plan in PLAN_REBALANCE_MIN:
        current_user.plan_tier = effective_plan
        current_user.rebalance_interval = PLAN_REBALANCE_MIN[effective_plan]
    now = datetime.utcnow()
    base = current_user.pro_expiry if current_user.pro_expiry and current_user.pro_expiry > now else now
    current_user.pro_expiry = base + timedelta(days=interval_days)
    tokens_to_award = (
        PLAN_TOKEN_AWARD_YEARLY.get(plan, 0)
        if interval == "yearly"
        else PLAN_TOKEN_AWARD_MONTHLY.get(plan, 0)
    )
    if tokens_to_award > 0:
        reason = "subscription_yearly" if interval == "yearly" else "subscription_monthly"
        token_ledger_svc.add_tokens(db, current_user.id, float(tokens_to_award), reason, extra={"plan": plan, "interval": interval})
        referral_usd = _get_subscription_usd_price(plan, interval)
        l1_pct, l2_pct, l3_pct = _get_referral_purchase_pct(db)
        apply_referral_rewards_on_purchase(db, current_user.id, referral_usd, reward_purchase_l1=l1_pct, reward_purchase_l2=l2_pct, reward_purchase_l3=l3_pct)
        logger.info(
            "subscription_bypass user_id=%s plan=%s interval=%s tokens_added=%s",
            current_user.id, plan, interval, tokens_to_award,
        )
    if current_user.referred_by:
        referrer = db.query(models.User).filter(models.User.id == current_user.referred_by).first()
        if referrer:
            ref_base = referrer.pro_expiry if referrer.pro_expiry and referrer.pro_expiry > now else now
            referrer.pro_expiry = ref_base + timedelta(days=7)
    db.commit()
    _rcache_invalidate_user(current_user.id)
    return {
        "status": "success",
        "plan": plan,
        "interval": interval,
        "tokens_awarded": tokens_to_award,
        "message": f"Subscription applied. {tokens_to_award} tokens added.",
    }


@app.post("/api/create-checkout-session")
async def create_checkout_session(
    payload: CreateCheckoutPayload,
    current_user: models.User = Depends(get_current_user),
):
    """
    Create a Stripe Checkout Session. Monthly: Pro 20, AI Ultra 60, Whales 200 USDT/mo.
    Yearly: Pro 192, AI Ultra 576, Whales 1920 USDT/year.
    """
    plan = (payload.plan or "").lower()
    interval = (payload.interval or "monthly").lower()
    if plan not in ("pro", "ai_ultra", "whales") or interval not in ("monthly", "yearly"):
        raise HTTPException(status_code=400, detail="Invalid plan or interval. Use plan: pro|ai_ultra|whales, interval: monthly|yearly.")
    price_id = _get_stripe_price_id(plan, interval)
    if not price_id or not stripe.api_key:
        raise HTTPException(
            status_code=503,
            detail="Subscription is not configured. Please set STRIPE_API_KEY and Stripe Price IDs (monthly and/or yearly) in the server environment.",
        )
    origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer_email=current_user.email,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=origin + "/dashboard?subscription=success",
            cancel_url=origin + "/dashboard?subscription=cancel",
            metadata={"user_id": str(current_user.id), "plan": plan, "interval": interval},
            subscription_data={"metadata": {"plan": plan, "user_id": str(current_user.id), "interval": interval}},
        )
        return {"url": session.url}
    except Exception as e:
        logger.exception("stripe_checkout_create failed for user_id=%s: %s", current_user.id, e)
        raise HTTPException(status_code=500, detail="Failed to create checkout session. Please try again.")


STRIPE_WEBHOOK_DEBUG_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stripe_webhook_debug.log")


def _stripe_webhook_log(msg: str, *args) -> None:
    """Log to app logger; if STRIPE_WEBHOOK_DEBUG=1, also append to stripe_webhook_debug.log."""
    line = msg % args if args else msg
    logger.info("stripe_webhook %s", line)
    if os.getenv("STRIPE_WEBHOOK_DEBUG") == "1":
        try:
            with open(STRIPE_WEBHOOK_DEBUG_LOG, "a", encoding="utf-8") as f:
                f.write(f"{datetime.utcnow().isoformat()}Z | {line}\n")
        except Exception as e:
            logger.warning("stripe_webhook_debug: failed to write log: %s", e)


@app.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature", "")
    _stripe_webhook_log("webhook_request_received body_len=%s has_sig=%s", len(payload), bool(sig_header))

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=STRIPE_WEBHOOK_SECRET,
        )
    except Exception as e:
        _stripe_webhook_log("signature_invalid error=%s", str(e))
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook signature.")

    ev_type = event.get("type", "")
    ev_id = event.get("id", "")
    _stripe_webhook_log("event type=%s id=%s", ev_type, ev_id)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        meta = session.get("metadata") or {}
        _stripe_webhook_log("checkout.session.completed metadata=%s", str(meta))
        if meta.get("type") == "tokens":
            user_id = int(meta.get("user_id") or 0)
            tokens = int(meta.get("tokens") or 0)
            session_id = (session.get("id") if hasattr(session, "get") else None) or getattr(session, "id", None)
            session_id = (session_id or "").strip() if isinstance(session_id, str) else ""
            if user_id and tokens > 0:
                db = next(database.get_db())
                try:
                    if not token_ledger_svc.try_register_checkout_session(db, session_id):
                        _stripe_webhook_log("tokens_deposit already_processed session_id=%s", session_id)
                        return {"received": True}
                    amount_usd = float(meta.get("amount_usd") or 0) or (tokens / 100.0)
                    token_ledger_svc.add_tokens(
                        db, user_id, float(tokens), "deposit_usd",
                        extra={"usd_amount": amount_usd, "stripe_session_id": session_id},
                    )
                    l1_pct, l2_pct, l3_pct = _get_referral_purchase_pct(db)
                    apply_referral_rewards_on_purchase(db, user_id, amount_usd, reward_purchase_l1=l1_pct, reward_purchase_l2=l2_pct, reward_purchase_l3=l3_pct)
                    db.commit()
                    new_bal = token_ledger_svc.get_tokens_remaining(db, user_id)
                    _stripe_webhook_log("tokens_deposit user_id=%s tokens_added=%s new_balance=%s", user_id, tokens, new_bal)
                    _rcache_invalidate_user(user_id)
                finally:
                    db.close()
            else:
                _stripe_webhook_log("tokens_deposit_skip user_id=%s tokens=%s", user_id, tokens)
            return {"received": True}
        # Subscription checkout: award tokens from session metadata (or subscription metadata fallback)
        sub_id = session.get("subscription") or getattr(session, "subscription", None)
        if isinstance(sub_id, dict):
            sub_id = (sub_id.get("id") or "").strip() or None
        elif sub_id and not isinstance(sub_id, str):
            sub_id = getattr(sub_id, "id", None)
        plan = (meta.get("plan") or "").strip().lower()
        interval = (meta.get("interval") or "monthly").strip().lower()
        uid_str = (meta.get("user_id") or "").strip()
        # If session metadata is empty (Stripe may attach only to subscription), get from Subscription
        if sub_id and (not plan or not uid_str):
            try:
                sub_obj = stripe.Subscription.retrieve(sub_id)
                sub_meta = (sub_obj.metadata or {}) if hasattr(sub_obj, "metadata") else {}
                if not plan and sub_meta.get("plan"):
                    plan = (sub_meta.get("plan") or "").strip().lower()
                if not interval and sub_meta.get("interval"):
                    interval = (sub_meta.get("interval") or "monthly").strip().lower()
                if not uid_str and sub_meta.get("user_id"):
                    uid_str = (sub_meta.get("user_id") or "").strip()
                _stripe_webhook_log("checkout.session.completed fallback from subscription metadata plan=%s interval=%s user_id=%s", plan, interval, uid_str)
            except Exception as e:
                _stripe_webhook_log("checkout.session.completed subscription retrieve error=%s", str(e))
        if sub_id and uid_str and plan in ("pro", "ai_ultra", "whales") and interval in ("monthly", "yearly"):
            session_id = (session.get("id") if hasattr(session, "get") else None) or getattr(session, "id", None)
            session_id = (session_id or "").strip() if isinstance(session_id, str) else ""
            db = next(database.get_db())
            try:
                if not session_id:
                    _stripe_webhook_log("checkout.session.completed subscription skip empty session_id")
                    return {"received": True}
                if not token_ledger_svc.try_register_checkout_session(db, session_id):
                    _stripe_webhook_log("checkout.session.completed subscription already_processed session_id=%s", session_id)
                    return {"received": True}
                if token_ledger_svc.subscription_session_already_processed(db, session_id):
                    _stripe_webhook_log("checkout.session.completed subscription already_in_ledger session_id=%s", session_id)
                    return {"received": True}
                user = db.query(models.User).filter(models.User.id == int(uid_str)).first()
                if not user:
                    _stripe_webhook_log("checkout.session.completed subscription no_user user_id=%s", uid_str)
                    return {"received": True}
                interval_days = 365 if interval == "yearly" else 30
                effective_plan = _plan_tier_no_downgrade(user.plan_tier or "trial", plan)
                if effective_plan in PLAN_REBALANCE_MIN:
                    user.plan_tier = effective_plan
                    user.rebalance_interval = PLAN_REBALANCE_MIN[effective_plan]
                now = datetime.utcnow()
                base = user.pro_expiry if user.pro_expiry and user.pro_expiry > now else now
                user.pro_expiry = base + timedelta(days=interval_days)
                tokens_to_award = (
                    PLAN_TOKEN_AWARD_YEARLY.get(plan, 0) if interval == "yearly"
                    else PLAN_TOKEN_AWARD_MONTHLY.get(plan, 0)
                )
                if tokens_to_award > 0:
                    reason = "subscription_yearly" if interval == "yearly" else "subscription_monthly"
                    sub_extra = {"plan": plan, "interval": interval, "stripe_session_id": session_id}
                    if sub_id:
                        sub_extra["stripe_subscription_id"] = sub_id if isinstance(sub_id, str) else getattr(sub_id, "id", None)
                    token_ledger_svc.add_tokens(db, user.id, float(tokens_to_award), reason, extra=sub_extra)
                    referral_usd = _get_subscription_usd_price(plan, interval)
                    l1_pct, l2_pct, l3_pct = _get_referral_purchase_pct(db)
                    apply_referral_rewards_on_purchase(db, user.id, referral_usd, reward_purchase_l1=l1_pct, reward_purchase_l2=l2_pct, reward_purchase_l3=l3_pct)
                    new_bal = token_ledger_svc.get_tokens_remaining(db, user.id)
                    _stripe_webhook_log(
                        "checkout.session.completed subscription_token_award user_id=%s plan=%s interval=%s tokens_added=%s new_balance=%s",
                        user.id, plan, interval, tokens_to_award, new_bal,
                    )
                    logger.info(
                        "stripe_webhook checkout.session.completed subscription user_id=%s plan=%s interval=%s tokens=%s",
                        user.id, plan, interval, tokens_to_award,
                    )
                db.commit()
                _rcache_invalidate_user(user.id)
            except Exception as e:
                _stripe_webhook_log("checkout.session.completed subscription error=%s", str(e))
                logger.exception("stripe_webhook checkout.session.completed subscription: %s", e)
                raise
            finally:
                db.close()
            return {"received": True}

    if event["type"] == "invoice.payment_succeeded":
        data = event["data"]["object"]
        email = data.get("customer_email") or (data.get("customer_details") or {}).get("email")
        sub_id_raw = data.get("subscription")
        if isinstance(sub_id_raw, dict):
            sub_id = (sub_id_raw.get("id") or "").strip() or None
        elif isinstance(sub_id_raw, str) and sub_id_raw.strip():
            sub_id = sub_id_raw.strip()
        else:
            sub_id = None

        # If payload had no subscription id (e.g. some webhook payloads omit it), get it from the invoice
        if not sub_id and data.get("id"):
            try:
                inv = stripe.Invoice.retrieve(data["id"], expand=["subscription"])
                sub_raw = getattr(inv, "subscription", None)
                if isinstance(sub_raw, str) and sub_raw.strip():
                    sub_id = sub_raw.strip()
                    logger.info("stripe_webhook invoice sub_id_from_retrieve sub_id=%s invoice_id=%s", sub_id, data.get("id"))
                    _stripe_webhook_log("invoice sub_id resolved from Invoice.retrieve sub_id=%s", sub_id)
                elif sub_raw and getattr(sub_raw, "id", None):
                    sub_id = sub_raw.id
                    logger.info("stripe_webhook invoice sub_id_from_retrieve sub_id=%s invoice_id=%s", sub_id, data.get("id"))
                    _stripe_webhook_log("invoice sub_id resolved from Invoice.retrieve sub_id=%s", sub_id)
            except Exception as e:
                logger.warning("stripe_webhook invoice retrieve for sub_id error=%s", str(e))
                _stripe_webhook_log("invoice retrieve for sub_id error=%s", str(e))

        db: Session = next(database.get_db())
        sub_for_metadata = None  # reused for plan/interval fallback if needed
        try:
            user = None
            # Prefer subscription metadata when it's a subscription invoice (our checkout sets user_id there)
            if sub_id:
                try:
                    sub_for_metadata = stripe.Subscription.retrieve(sub_id)
                    meta = sub_for_metadata.metadata or {}
                    uid_str = meta.get("user_id")
                    if uid_str:
                        user = db.query(models.User).filter(models.User.id == int(uid_str)).first()
                        if user:
                            logger.info("stripe_webhook invoice user_resolution by_sub_metadata user_id=%s sub_id=%s", user.id, sub_id)
                            _stripe_webhook_log("invoice user_lookup by_sub_metadata user_id=%s email=%s", user.id, email)
                except Exception as e:
                    logger.warning("stripe_webhook invoice sub_retrieve sub_id=%s error=%s", sub_id, str(e))
                    _stripe_webhook_log("invoice sub_retrieve sub_id=%s error=%s", sub_id, str(e))
            if not user and email:
                user = db.query(models.User).filter(models.User.email == email).first()
                if user:
                    logger.info("stripe_webhook invoice user_resolution by_email user_id=%s email=%s", user.id, email)
                    _stripe_webhook_log("invoice user_lookup by_email user_id=%s", user.id)

            _stripe_webhook_log(
                "invoice.payment_succeeded email=%s sub_id=%s user_id=%s",
                email, sub_id, user.id if user else None,
            )
            if not user:
                logger.warning("stripe_webhook invoice skip no_user email=%s sub_id=%s", email, sub_id)
                _stripe_webhook_log("invoice skip no_user_for_email")
                return {"received": True}

            invoice_id = (data.get("id") or "").strip()
            if invoice_id and token_ledger_svc.subscription_invoice_already_processed(db, user.id, invoice_id):
                _stripe_webhook_log("invoice idempotent_skip already_processed invoice_id=%s user_id=%s", invoice_id, user.id)
                logger.info("stripe_webhook invoice already processed invoice_id=%s user_id=%s", invoice_id, user.id)
                return {"received": True}

            # Plan/interval: prefer subscription metadata (our checkout sets it); fallback to invoice line items
            plan, interval = "pro", "monthly"
            if sub_id:
                try:
                    sub = sub_for_metadata if sub_for_metadata is not None else stripe.Subscription.retrieve(sub_id)
                    meta = (sub.metadata or {}) if hasattr(sub, "metadata") else {}
                    meta_plan = (meta.get("plan") or "").strip().lower()
                    meta_interval = (meta.get("interval") or "monthly").strip().lower()
                    if meta_plan in ("pro", "ai_ultra", "whales") and meta_interval in ("monthly", "yearly"):
                        plan, interval = meta_plan, meta_interval
                        logger.info("stripe_webhook invoice plan_interval from sub metadata plan=%s interval=%s", plan, interval)
                        _stripe_webhook_log("invoice plan from sub_metadata plan=%s interval=%s", plan, interval)
                except Exception as e:
                    logger.warning("stripe_webhook invoice sub metadata error=%s", str(e))
            if (plan, interval) == ("pro", "monthly"):
                plan, interval = _plan_interval_from_invoice(data)
                logger.info("stripe_webhook invoice plan_from_invoice plan=%s interval=%s", plan, interval)
                _stripe_webhook_log("invoice plan from invoice lines plan=%s interval=%s", plan, interval)
            interval_days = 365 if interval == "yearly" else 30

            effective_plan = _plan_tier_no_downgrade(user.plan_tier or "trial", plan)
            if effective_plan in PLAN_REBALANCE_MIN:
                user.plan_tier = effective_plan
                user.rebalance_interval = PLAN_REBALANCE_MIN[effective_plan]

            now = datetime.utcnow()
            base = user.pro_expiry if user.pro_expiry and user.pro_expiry > now else now
            user.pro_expiry = base + timedelta(days=interval_days)

            tokens_to_award = (
                PLAN_TOKEN_AWARD_YEARLY.get(plan, 0)
                if interval == "yearly"
                else PLAN_TOKEN_AWARD_MONTHLY.get(plan, 0)
            )
            _stripe_webhook_log(
                "invoice plan=%s interval=%s tokens_to_award=%s user_id=%s",
                plan, interval, tokens_to_award, user.id,
            )
            # Only add tokens in invoice when we have sub_id (so we can idempotency-check). When sub_id is None,
            # tokens were (or will be) awarded in checkout.session.completed; do not add here (avoids 2–4x over-credit on retries).
            already_awarded = sub_id and token_ledger_svc.subscription_id_already_awarded(db, user.id, sub_id)
            if already_awarded:
                _stripe_webhook_log("invoice skip_token_add already_awarded_via_checkout sub_id=%s user_id=%s", sub_id, user.id)
                logger.info("stripe_webhook invoice skip token add (already awarded via checkout) sub_id=%s user_id=%s", sub_id, user.id)
            if sub_id is None:
                _stripe_webhook_log("invoice skip_token_add sub_id_is_none user_id=%s (tokens from checkout.session.completed only)", user.id)
                logger.info("stripe_webhook invoice skip token add (sub_id None) user_id=%s", user.id)
            if tokens_to_award > 0 and not already_awarded and sub_id is not None:
                reason = "subscription_yearly" if interval == "yearly" else "subscription_monthly"
                sub_extra = {"plan": plan, "interval": interval}
                if invoice_id:
                    sub_extra["stripe_invoice_id"] = invoice_id
                logger.info("stripe_webhook invoice about_to_add_tokens user_id=%s amount=%s", user.id, tokens_to_award)
                token_ledger_svc.add_tokens(db, user.id, float(tokens_to_award), reason, extra=sub_extra)
                logger.info("stripe_webhook invoice add_tokens_done user_id=%s", user.id)
                referral_usd = _get_subscription_usd_price(plan, interval)
                l1_pct, l2_pct, l3_pct = _get_referral_purchase_pct(db)
                apply_referral_rewards_on_purchase(db, user.id, referral_usd, reward_purchase_l1=l1_pct, reward_purchase_l2=l2_pct, reward_purchase_l3=l3_pct)
                new_bal = token_ledger_svc.get_tokens_remaining(db, user.id)
                _stripe_webhook_log(
                    "subscription_token_award user_id=%s plan=%s interval=%s tokens_added=%s new_balance=%s",
                    user.id, plan, interval, tokens_to_award, new_bal,
                )
                logger.info(
                    "subscription_token_award user_id=%s plan=%s interval=%s tokens_added=%s timestamp=%s",
                    user.id, plan, interval, tokens_to_award, now.isoformat(),
                )

            # Commit token award and user/pro_expiry so they persist even if referrer logic fails
            db.commit()
            logger.info("stripe_webhook invoice commit_done user_id=%s", user.id)
            _stripe_webhook_log("invoice commit_ok user_id=%s", user.id)

            # Referrer update in separate try so webhook still returns 200 on referrer failure
            if user.referred_by:
                try:
                    referrer = db.query(models.User).filter(models.User.id == user.referred_by).first()
                    if referrer:
                        ref_base = (
                            referrer.pro_expiry
                            if referrer.pro_expiry and referrer.pro_expiry > now
                            else now
                        )
                        referrer.pro_expiry = ref_base + timedelta(days=7)
                        db.commit()
                except Exception as ref_e:
                    logger.warning("stripe_webhook invoice referrer_update_failed user_id=%s error=%s", user.id, str(ref_e))
        except Exception as e:
            _stripe_webhook_log("invoice exception user_id=%s error=%s", getattr(user, "id", None), str(e))
            logger.exception("stripe_webhook invoice.payment_succeeded: %s", e)
            raise
        finally:
            db.close()

    return {"received": True}
