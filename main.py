import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from arq import create_pool
from arq.connections import RedisSettings
import stripe
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

import database
import models
import security
from services.bitfinex_service import BitfinexManager, hash_bitfinex_id
from services import bitfinex_cache
from services.daily_token_deduction import run_daily_token_deduction

# Daily gross profit refresh: run at 09:40 UTC (in-process; no cron needed)
DAILY_GROSS_REFRESH_UTC_HOUR = 9
DAILY_GROSS_REFRESH_UTC_MINUTE = 40
DELAY_BETWEEN_USERS_SEC = 3.0

# Daily token deduction: 10:15 UTC (15-min buffer after Bitfinex refresh at 10:00; gross stored at 09:40)
DAILY_DEDUCTION_UTC_HOUR = 10
DAILY_DEDUCTION_UTC_MINUTE = 15
DEDUCTION_RETRY_INTERVAL_SEC = 300  # 5 minutes
DEDUCTION_MAX_RETRIES = 3

# API failure log for admin panel (in-memory, last N entries)
API_FAILURES_MAX = 200
_api_failures: List[Dict[str, Any]] = []
_api_failures_lock = asyncio.Lock()


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


async def _run_daily_gross_profit_scheduler() -> None:
    """Background task: at 09:40 UTC every day, refresh gross profit for all users with vaults."""
    first_wait = _get_scheduler_first_wait_sec()
    while True:
        if first_wait is not None:
            wait_sec = first_wait
            first_wait = None
            print(f"[scheduler] TEST_SCHEDULER_SECONDS: first run in {wait_sec:.0f}s")
        else:
            now = datetime.utcnow()
            next_run = now.replace(
                hour=DAILY_GROSS_REFRESH_UTC_HOUR,
                minute=DAILY_GROSS_REFRESH_UTC_MINUTE,
                second=0,
                microsecond=0,
            )
            if next_run <= now:
                next_run += timedelta(days=1)
            wait_sec = (next_run - now).total_seconds()
            print(f"[scheduler] Next daily gross profit refresh at {next_run.isoformat()}Z (in {wait_sec:.0f}s)")
        await asyncio.sleep(wait_sec)
        db = database.SessionLocal()
        try:
            user_ids = [
                row[0]
                for row in db.query(models.User.id)
                .join(models.APIVault, models.User.id == models.APIVault.user_id)
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
        print(f"[scheduler] Daily gross profit refresh: {len(user_ids)} user(s)")
        for i, uid in enumerate(user_ids):
            if i > 0:
                await asyncio.sleep(DELAY_BETWEEN_USERS_SEC)
            db = database.SessionLocal()
            try:
                err_msg: Optional[str] = None
                for attempt in range(3):
                    try:
                        result, rate_limited, _ = await _refresh_user_lending_snapshot(uid, db)
                        if not rate_limited:
                            cache_data = result.model_dump()
                            cache_data.pop("trades", None)
                            await bitfinex_cache.set_cached(uid, bitfinex_cache.KEY_LENDING, cache_data)
                            # Store daily_gross_profit_usd for 10:15 token deduction (same UTC day)
                            snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == uid).first()
                            if snap and hasattr(snap, "daily_gross_profit_usd"):
                                today_utc = datetime.utcnow().date()
                                yesterday_utc = today_utc - timedelta(days=1)
                                current = float(result.gross_profit)
                                last_cum = getattr(snap, "last_daily_cumulative_gross", None)
                                last_date = getattr(snap, "last_daily_snapshot_date", None)
                                if last_date == yesterday_utc and last_cum is not None:
                                    daily = current - last_cum
                                else:
                                    daily = current
                                snap.daily_gross_profit_usd = daily
                                snap.last_daily_cumulative_gross = current
                                snap.last_daily_snapshot_date = today_utc
                                db.commit()
                        print(f"[scheduler] user_id={uid} gross_profit={result.gross_profit}")
                        err_msg = None
                        break
                    except Exception as e:
                        err_msg = str(e)
                        print(f"[scheduler] user_id={uid} attempt {attempt + 1}/3 error: {e}")
                        if attempt < 2:
                            await asyncio.sleep(10.0)
                if err_msg:
                    await _record_api_failure("daily_gross_refresh", uid, err_msg)
            finally:
                db.close()


def _get_next_1015_utc_wait_sec() -> float:
    """Seconds until next 10:15 UTC."""
    now = datetime.utcnow()
    next_run = now.replace(
        hour=DAILY_DEDUCTION_UTC_HOUR,
        minute=DAILY_DEDUCTION_UTC_MINUTE,
        second=0,
        microsecond=0,
    )
    if next_run <= now:
        next_run += timedelta(days=1)
    return (next_run - now).total_seconds()


async def _run_daily_token_deduction_scheduler() -> None:
    """At 10:15 UTC daily, deduct tokens by daily_gross_profit_usd. Retry 3x at 5-min intervals; alert on failure."""
    while True:
        wait_sec = _get_next_1015_utc_wait_sec()
        logger.info("Next daily token deduction at 10:15 UTC in %.0fs", wait_sec)
        await asyncio.sleep(wait_sec)
        last_error: Optional[str] = None
        for attempt in range(DEDUCTION_MAX_RETRIES):
            db = database.SessionLocal()
            try:
                log_entries, err = run_daily_token_deduction(db)
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
            alert_msg = f"Daily token deduction failed after {DEDUCTION_MAX_RETRIES} retries: {last_error}"
            logger.error(alert_msg)
            await _alert_admins_deduction_failure(alert_msg)


async def _alert_admins_deduction_failure(message: str) -> None:
    """Alert admins (e.g. Slack webhook). Set DEDUCTION_ALERT_WEBHOOK_URL in env for Slack."""
    webhook_url = os.getenv("DEDUCTION_ALERT_WEBHOOK_URL", "").strip()
    if webhook_url:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                await session.post(
                    webhook_url,
                    json={"text": f"[uTrader] {message}"},
                    timeout=aiohttp.ClientTimeout(total=10),
                )
        except Exception as e:
            logger.warning("Failed to send deduction alert webhook: %s", e)
    # Always recorded in API failures for admin panel
    await _record_api_failure("daily_token_deduction", None, message)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start in-process daily 09:40 UTC gross profit refresh (dev and prod; no cron needed)
    scheduler_task = asyncio.create_task(_run_daily_gross_profit_scheduler())
    deduction_task = asyncio.create_task(_run_daily_token_deduction_scheduler())
    yield
    scheduler_task.cancel()
    deduction_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    try:
        await deduction_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="utrader.io API", lifespan=lifespan)

# NextAuth JWT (from /api/auth/token). Set NEXTAUTH_SECRET in env to enable.
NEXTAUTH_SECRET = os.getenv("NEXTAUTH_SECRET", "")


# --- CORS: explicitly allow frontend origins so browser can reach backend ---
_cors_origins = [
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://0.0.0.0:3000",
]
if os.getenv("CORS_ORIGINS"):
    _cors_origins.extend(o.strip() for o in os.getenv("CORS_ORIGINS").split(",") if o.strip())
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Redis / ARQ ---
REDIS_CONNECT_TIMEOUT = 5.0  # seconds; avoid hanging the request if Redis is down


async def get_redis():
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    return await create_pool(RedisSettings.from_dsn(redis_url))


async def get_redis_or_raise():
    """Get Redis with timeout; raises HTTPException 503 if unavailable."""
    try:
        return await asyncio.wait_for(get_redis(), timeout=REDIS_CONNECT_TIMEOUT)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=503,
            detail="Queue service unavailable. Make sure Redis is running (e.g. redis-server) and REDIS_URL is set.",
        )
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Queue service unavailable. Make sure Redis is running (e.g. redis-server) and REDIS_URL is set.",
        )


# --- Registration token award ---
REGISTRATION_TOKEN_AWARD = 150


def _award_registration_tokens(user_id: int, db: Session) -> None:
    """
    Award REGISTRATION_TOKEN_AWARD (150) tokens to a new user on registration.
    Uses user_token_balance: create row if missing, else add 150 to tokens_remaining.
    Logs for audit; on failure logs error and does not raise (do not block registration).
    """
    # Trial initial_credit is 100; we award 150, so store +50 as purchased so formula (initial_credit + purchased - used) = 150.
    registration_bonus_purchased = max(0, REGISTRATION_TOKEN_AWARD - FREE_TIER_TOKENS)  # 50
    try:
        row = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
        now = datetime.utcnow()
        if row is None:
            row = models.UserTokenBalance(
                user_id=user_id,
                tokens_remaining=float(REGISTRATION_TOKEN_AWARD),
                last_gross_usd_used=0.0,
                purchased_tokens=float(registration_bonus_purchased),
                updated_at=now,
            )
            db.add(row)
        else:
            row.tokens_remaining = float(row.tokens_remaining or 0) + REGISTRATION_TOKEN_AWARD
            row.purchased_tokens = float(row.purchased_tokens or 0) + registration_bonus_purchased
            row.updated_at = now
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


def _get_or_create_user_from_google(idinfo: dict, referral_code: Optional[str], db: Session) -> models.User:
    email: str = idinfo.get("email", "")
    hd = email.split("@")[-1] if "@" in email else ""
    if not email or not email.endswith("@gmail.com"):
        raise HTTPException(status_code=400, detail="Only @gmail.com accounts are allowed.")

    user = db.query(models.User).filter(models.User.email == email).first()
    if user:
        return user

    # New user – optional referral association
    referrer: Optional[models.User] = None
    if referral_code:
        referrer = db.query(models.User).filter(models.User.referral_code == referral_code).first()

    new_user = models.User(
        email=email,
        plan_tier="trial",
        lending_limit=250_000.0,
        rebalance_interval=30,
        referred_by=referrer.id if referrer else None,
    )
    # Simple referral code: user email hash suffix
    new_user.referral_code = f"ref-{abs(hash(email)) % 10_000_000}"

    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    _award_registration_tokens(new_user.id, db)
    return new_user


def _get_user_by_email(email: str, db: Session) -> models.User:
    if not email or not email.endswith("@gmail.com"):
        raise HTTPException(status_code=400, detail="Only @gmail.com accounts are allowed.")
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not registered.")
    return user


async def get_current_user(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(database.get_db),
) -> models.User:
    """
    Verify Bearer token: either NextAuth JWT (from /api/auth/token) or Google ID token.
    User is looked up by email from the token. If no valid session, return 401 with friendly message.
    """
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
                return _get_user_by_email(email, db)
        except jwt.PyJWTError:
            pass
        except Exception:
            pass

    # 2) Fallback: Google ID token (legacy)
    try:
        idinfo = id_token.verify_oauth2_token(
            token, google_requests.Request(), GOOGLE_CLIENT_ID
        )
        email = idinfo.get("email")
        return _get_user_by_email(email or "", db)
    except Exception:
        pass

    raise HTTPException(status_code=401, detail="Session expired. Please log in again.")


def get_admin_user(current_user: models.User = Depends(get_current_user)) -> models.User:
    """
    Restrict admin endpoints to a single Gmail account.
    """
    if current_user.email != "ngaiwachoi@gmail.com":
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

# Token (credit) system: 1 USDT gross profit = 10 tokens used.
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
    lending_limit: float
    rebalance_interval: int
    trial_remaining_days: Optional[int]
    utilization_pct: float
    used_amount: float
    tokens_remaining: Optional[float] = None
    tokens_used: int = 0
    initial_token_credit: int = 0
    gross_profit_usd: float = 0.0


class TokenBalanceResponse(BaseModel):
    tokens_remaining: float
    tokens_used: int
    initial_credit: int
    gross_profit_usd: float


class AdminUserOut(BaseModel):
    id: int
    email: str
    plan_tier: str
    lending_limit: float
    rebalance_interval: int
    pro_expiry: Optional[datetime]
    status: str


class AdminUserUpdate(BaseModel):
    plan_tier: Optional[str] = None
    pro_expiry: Optional[datetime] = None
    lending_limit: Optional[float] = None
    rebalance_interval: Optional[int] = None


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


# --- Google Auth Endpoint ---
@app.post("/auth/google")
def google_login(payload: GoogleAuthPayload, db: Session = Depends(database.get_db)):
    try:
        idinfo = id_token.verify_oauth2_token(
            payload.id_token, google_requests.Request(), GOOGLE_CLIENT_ID
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Google ID token.")

    user = _get_or_create_user_from_google(idinfo, payload.referral_code, db)
    return {"user_id": user.id, "email": user.email, "plan_tier": user.plan_tier}


# --- Live Bot Stats Route (existing dashboard); user end: auth required, own data only ---
@app.get("/bot-stats/{user_id}")
async def get_all_bot_stats(
    user_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """Fetches live heartbeat data from Redis. Caller must be the same user. Includes bot_status from DB."""
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this user.")
    redis = await get_redis()
    user = db.query(models.User).filter(models.User.id == user_id).first()
    bot_status = getattr(user, "bot_status", None) if user else None

    keys = await redis.keys(f"status:{user_id}:*")

    all_engines = []
    for key in keys:
        raw_data = await redis.get(key)
        if raw_data:
            all_engines.append(json.loads(raw_data))

    if not all_engines:
        return {
            "active": False,
            "engines": [],
            "total_loaned": "0.00",
            "bot_status": bot_status or "stopped",
        }

    total_val = sum(float(str(e["loaned"]).replace(",", "")) for e in all_engines)

    return {
        "active": True,
        "engines": all_engines,
        "total_loaned": f"{total_val:,.2f}",
        "bot_status": bot_status or "running",
    }


# --- Whales terminal: cached logs; user end: auth required, own data only ---
@app.get("/terminal-logs/{user_id}")
async def get_terminal_logs(
    user_id: int,
    current_user: models.User = Depends(get_current_user),
):
    """Returns last 500 terminal log lines for the user (from worker). Caller must be the same user."""
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this user.")
    try:
        redis = await asyncio.wait_for(get_redis(), timeout=REDIS_CONNECT_TIMEOUT)
    except (asyncio.TimeoutError, Exception):
        return {"lines": []}
    try:
        key = f"terminal_logs:{user_id}"
        lines = await asyncio.wait_for(redis.lrange(key, 0, -1), timeout=5.0)
    except (asyncio.TimeoutError, Exception):
        return {"lines": []}
    decoded = [line.decode("utf-8") if isinstance(line, bytes) else line for line in (lines or [])]
    return {"lines": decoded}


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
    """Auto-start bot after API keys are saved (idempotent). Does not raise; logs on failure."""
    try:
        redis = await asyncio.wait_for(get_redis(), timeout=REDIS_CONNECT_TIMEOUT)
        enqueued = await _enqueue_bot_task(redis, user_id)
        if enqueued:
            user = db.query(models.User).filter(models.User.id == user_id).first()
            if user and hasattr(user, "bot_status"):
                user.bot_status = "starting"
                db.commit()
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
    balance, result = await _validate_and_save_bitfinex_keys(
        payload, current_user, db
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    await _trigger_bot_start_after_keys_saved(current_user.id, db)
    return {
        "status": "success",
        "message": result.get("message", "Exchange connected and trial activated."),
        "balance": balance,
    }


@app.get("/api/me")
async def get_current_user_info(
    current_user: models.User = Depends(get_current_user),
):
    """
    Returns the currently authenticated user's id and email.
    Used by the frontend to scope all user-specific API calls (wallets, stats, etc.).
    """
    return {"id": current_user.id, "email": current_user.email}


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
    return {
        "has_keys": has_keys,
        "key_preview": "••••••••" if has_keys else None,
        "created_at": created_at,
        "last_tested_at": last_tested_at,
        "last_test_balance": float(last_test_balance) if last_test_balance is not None else None,
    }


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
    """
    vault = (
        db.query(models.APIVault)
        .filter(models.APIVault.user_id == current_user.id)
        .first()
    )
    if vault:
        db.delete(vault)
        db.commit()
    return {"success": True, "message": "API keys removed."}


@app.post("/api/keys")
async def api_keys(
    payload: APIKeysInput,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """
    Validate Bitfinex API key and secret, encrypt and save to DB, return balance on success.
    get_current_user ensures the user exists in the database before proceeding.
    Returns 200 OK with saved key metadata and balance when successful.
    Only one key per user; saving overwrites any existing key.
    """
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
    current_user.lending_limit = 250_000.0
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
        lending_limit=250_000.0,
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
    keys_payload = APIKeysInput(
        bfx_key=payload.bfx_key,
        bfx_secret=payload.bfx_secret,
        gemini_key=payload.gemini_key,
    )
    balance, result = await _validate_and_save_bitfinex_keys(keys_payload, user, db)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
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
    if not vault:
        vault = models.APIVault(user_id=user.id)
        db.add(vault)
    vault.encrypted_key = security.encrypt_key(payload.bfx_key)
    vault.encrypted_secret = security.encrypt_key(payload.bfx_secret)
    if payload.gemini_key is not None:
        vault.encrypted_gemini_key = security.encrypt_key(payload.gemini_key) if payload.gemini_key else None
    db.commit()
    await _trigger_bot_start_after_keys_saved(user.id, db)
    return {
        "status": "success",
        "message": "API keys updated.",
        "balance": balance,
        "user_id": user.id,
    }


@app.post("/dev/create-test-user")
async def dev_create_test_user(
    payload: DevLoginAsInput,
    db: Session = Depends(database.get_db),
):
    """Dev-only: create a new user by email and award registration tokens (no API keys). For E2E testing. Set ALLOW_DEV_CONNECT=1."""
    if os.getenv("ALLOW_DEV_CONNECT") != "1":
        raise HTTPException(status_code=404, detail="Not available.")
    email = (payload.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="email required.")
    user = _get_or_create_user_by_email(email, db)
    return {"user_id": user.id, "email": user.email}


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
    token = jwt.encode(
        {"email": user.email, "sub": str(user.id)},
        NEXTAUTH_SECRET,
        algorithm="HS256",
    )
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
    keys_payload = APIKeysInput(
        bfx_key=payload.bfx_key,
        bfx_secret=payload.bfx_secret,
        gemini_key=payload.gemini_key,
    )
    balance, result = await _validate_and_save_bitfinex_keys(keys_payload, user, db)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    await _trigger_bot_start_after_keys_saved(user.id, db)
    return {
        "status": "success",
        "message": result.get("message", "Exchange connected and trial activated."),
        "balance": balance,
    }


# --- Start / Stop Bot (idempotent; clear ARQ keys to allow re-enqueue after stop) ---
ARQ_JOB_PREFIX = "arq:job:"
ARQ_RESULT_PREFIX = "arq:result:"
ARQ_QUEUE_NAME = "arq:queue"


async def _clear_arq_job_keys(redis, job_id: str) -> None:
    """Remove ARQ keys for job_id so the same id can be enqueued again (idempotent start after stop)."""
    try:
        await redis.delete(ARQ_JOB_PREFIX + job_id)
        await redis.delete(ARQ_RESULT_PREFIX + job_id)
        await redis.zrem(ARQ_QUEUE_NAME, job_id)
    except Exception:
        pass


async def _enqueue_bot_task(redis, user_id: int) -> bool:
    """Enqueue run_bot_task for user_id. Returns True if enqueued, False if already running/queued."""
    job_id = f"bot_user_{user_id}"
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
    if not current_user.vault:
        raise HTTPException(status_code=404, detail="API keys not found.")

    if current_user.pro_expiry and current_user.pro_expiry < datetime.utcnow():
        current_user.status = "expired"
        db.commit()
        raise HTTPException(status_code=402, detail="Subscription expired. Payment required.")

    redis = await get_redis_or_raise()
    enqueued = await _enqueue_bot_task(redis, current_user.id)
    if enqueued:
        try:
            current_user.bot_status = "starting"
            db.commit()
        except Exception:
            db.rollback()
        return {"status": "success", "message": f"Bot queued for user {current_user.id}"}
    return {"status": "success", "message": "Bot already running or queued."}


@app.post("/stop-bot")
async def stop_bot(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    from arq.jobs import Job
    redis = await get_redis_or_raise()
    job_id = f"bot_user_{current_user.id}"
    job = Job(job_id=job_id, redis=redis)
    try:
        aborted = await job.abort()
        await _clear_arq_job_keys(redis, job_id)  # so next Start enqueues reliably
        try:
            current_user.bot_status = "stopped"
            db.commit()
        except Exception:
            db.rollback()
        if aborted:
            return {"status": "success", "message": "Shutdown signal sent"}
    except Exception:
        pass
    await _clear_arq_job_keys(redis, job_id)
    try:
        current_user.bot_status = "stopped"
        db.commit()
    except Exception:
        db.rollback()
    return {"status": "error", "message": "No active bot found"}


# Legacy-style control endpoints that address bots by numeric user_id directly.
@app.post("/start-bot/{user_id}")
async def start_bot_for_user(user_id: int, db: Session = Depends(database.get_db)):
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user or not user.vault:
            raise HTTPException(status_code=404, detail="API keys not found.")

        if user.pro_expiry and user.pro_expiry < datetime.utcnow():
            user.status = "expired"
            db.commit()
            raise HTTPException(status_code=402, detail="Subscription expired. Payment required.")

        redis = await get_redis_or_raise()
        enqueued = await _enqueue_bot_task(redis, user.id)
        if enqueued:
            try:
                user.bot_status = "starting"
                db.commit()
            except Exception:
                db.rollback()
            return {"status": "success", "message": f"Bot queued for user {user.id}"}
        return {"status": "success", "message": "Bot already running or queued."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Start bot failed: {type(e).__name__}: {e}")


@app.post("/stop-bot/{user_id}")
async def stop_bot_for_user(user_id: int, db: Session = Depends(database.get_db)):
    from arq.jobs import Job
    redis = await get_redis_or_raise()
    job_id = f"bot_user_{user_id}"
    job = Job(job_id=job_id, redis=redis)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    try:
        aborted = await job.abort()
        await _clear_arq_job_keys(redis, job_id)
        if user and hasattr(user, "bot_status"):
            user.bot_status = "stopped"
            db.commit()
        if aborted:
            return {"status": "success", "message": "Shutdown signal sent"}
    except Exception:
        pass
    await _clear_arq_job_keys(redis, job_id)
    if user and hasattr(user, "bot_status"):
        user.bot_status = "stopped"
        db.commit()
    return {"status": "error", "message": "No active bot found"}


# --- Stats Endpoint ---
@app.get("/stats/{user_id}", response_model=StatsResponse)
def get_stats(
    user_id: int,
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    db: Session = Depends(database.get_db),
):
    """
    Returns Choice A style stats:
    - Gross Profit
    - Fake Fee (20% of Gross)
    - Net Profit

    For now we interpret PerformanceLog.waroc as a gross PnL-style figure per user,
    aggregated over an optional date range.
    """
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


@app.get("/stats/{user_id}/history")
def get_stats_history(
    user_id: int,
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    db: Session = Depends(database.get_db),
):
    """
    Returns time-series for Gross Profit / True ROI charts from performance_logs (and trial/funding data).
    When tables are empty, returns [] so the frontend can show "No data yet".
    """
    q = db.query(models.PerformanceLog).filter(models.PerformanceLog.user_id == user_id).order_by(models.PerformanceLog.timestamp.asc())
    if start:
        q = q.filter(models.PerformanceLog.timestamp >= start)
    if end:
        q = q.filter(models.PerformanceLog.timestamp <= end)
    logs = q.all()
    out = []
    cumulative = 0.0
    for log in logs:
        ts = log.timestamp
        date_str = ts.strftime("%m-%d") if ts else ""
        waroc = float(log.waroc or 0.0)
        cumulative += waroc
        out.append({
            "date": date_str,
            "volume": float(log.total_assets or 0.0),
            "interest": waroc,
            "cumulative": cumulative,
        })
    return out


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


def _ticker_prices_from_trades(trades: Any) -> Dict[str, float]:
    """Collect unique non-USD currencies from trades and fetch their USD prices."""
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


def _gross_and_fees_from_ledger_entries(
    entries: list,
    start_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
) -> tuple[float, float]:
    """
    Parse Bitfinex ledger entries (same logic as user script).
    Entry format: entry[3]=MTS, entry[4] or entry[5]=amount, entry[8]=description.
    Margin Funding Payment: positive = gross earned, negative = fees paid.
    If start_ms/end_ms are set, only count entries where start_ms <= entry[3] <= end_ms.
    Returns (gross_usd, fees_usd).
    """
    gross = 0.0
    fees = 0.0
    for entry in entries:
        try:
            if not isinstance(entry, (list, tuple)) or len(entry) < 9:
                continue
            # User script: raw_ts = entry[3]; amount = entry[5] if entry[4] is None else entry[4]; desc = entry[8]
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
                    fees += abs(amount)
                continue
            if amount > 0:
                gross += amount
            else:
                fees += abs(amount)
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


async def _gross_profit_from_ledgers(
    mgr: BitfinexManager,
    start_ms: int,
) -> tuple[float, float, Optional[str]]:
    """
    Sum gross profit and fees from ledgers (Margin Funding Payment), same API as user script.
    Fetches USD first (matches user script); then USDT, USDt. Skips a currency on error so one
    failure (e.g. no USDT ledger) does not discard USD result.
    Window: [registration (start_ms), end_ms]. Only entries with start_ms <= entry[3] <= end_ms are counted.
    """
    end_ms = int(datetime.utcnow().timestamp() * 1000)
    total_gross = 0.0
    total_fees = 0.0
    last_err: Optional[str] = None
    # Bitfinex ~10 req/s per IP: space ledger calls to stay under limit
    for i, currency in enumerate(("USD", "USDT", "USDt")):
        if i > 0:
            await asyncio.sleep(0.2)
        entries, err = await _fetch_ledgers_script_style(mgr, currency, limit=100)
        if err:
            last_err = err
            continue
        g, f = _gross_and_fees_from_ledger_entries(entries, start_ms=start_ms, end_ms=end_ms)
        total_gross += g
        total_fees += f
    return round(total_gross, 6), round(total_fees, 6), last_err if (last_err is not None and total_gross == 0 and total_fees == 0) else None


async def _refresh_user_lending_snapshot(user_id: int, db: Session) -> tuple[LendingStatsResponse, bool, List[FundingTradeRecord]]:
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
        gross_ledgers, fees_ledgers, err_ledgers = await _gross_profit_from_ledgers(mgr, start_ms)
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
            tier = (user.plan_tier or "trial").lower()
            initial_credit = PLAN_TOKEN_CREDITS.get(tier, FREE_TIER_TOKENS)
            token_row = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
            purchased = float(token_row.purchased_tokens) if token_row and token_row.purchased_tokens is not None else 0.0
            gross = float(result.gross_profit)
            tokens_used = int(gross * TOKENS_PER_USDT_GROSS)
            tokens_remaining = max(0.0, float(initial_credit) + purchased - tokens_used)
            if token_row:
                token_row.tokens_remaining = tokens_remaining
                token_row.last_gross_usd_used = gross
                token_row.updated_at = datetime.utcnow()
            else:
                db.add(models.UserTokenBalance(
                    user_id=user_id,
                    tokens_remaining=tokens_remaining,
                    last_gross_usd_used=gross,
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
    tier = (user.plan_tier or "trial").lower()
    initial_credit = PLAN_TOKEN_CREDITS.get(tier, FREE_TIER_TOKENS)
    token_row = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
    purchased = float(token_row.purchased_tokens) if token_row and token_row.purchased_tokens is not None else 0.0
    gross = float(result.gross_profit)
    tokens_used = int(gross * TOKENS_PER_USDT_GROSS)
    tokens_remaining = max(0.0, float(initial_credit) + purchased - tokens_used)
    if token_row:
        token_row.tokens_remaining = tokens_remaining
        token_row.last_gross_usd_used = gross
        token_row.updated_at = datetime.utcnow()
    else:
        db.add(models.UserTokenBalance(
            user_id=user_id,
            tokens_remaining=tokens_remaining,
            last_gross_usd_used=gross,
        ))
    db.commit()
    return result, False, records


@app.get("/stats/{user_id}/lending", response_model=LendingStatsResponse)
async def get_lending_stats(
    user_id: int,
    response: Response,
    db: Session = Depends(database.get_db),
):
    """
    Gross profit = sum of interest from Bitfinex funding trades between registration date and latest.
    Net = Gross × (1 - 15%). Cached to respect Bitfinex rate limits.
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or not user.vault:
        return LendingStatsResponse(gross_profit=0.0, bitfinex_fee=0.0, net_profit=0.0)

    cached = await bitfinex_cache.get_cached(user_id, bitfinex_cache.KEY_LENDING)
    if cached is not None:
        data, from_cache = cached
        if from_cache and data is not None:
            response.headers["X-Data-Source"] = "cache"
            exp = await bitfinex_cache.cache_expires_at(user_id, bitfinex_cache.KEY_LENDING)
            if exp is not None:
                response.headers["X-Cache-Expires-At"] = str(int(exp))
            return LendingStatsResponse(**data)

    if await bitfinex_cache.is_in_cooldown(user_id, bitfinex_cache.KEY_LENDING):
        response.headers["X-Data-Source"] = "cache"
        response.headers["X-Rate-Limited"] = "true"
        response.headers["Retry-After"] = "60"
        return LendingStatsResponse(gross_profit=0.0, bitfinex_fee=0.0, net_profit=0.0)

    try:
        result, rate_limited, _ = await _refresh_user_lending_snapshot(user_id, db)
    except Exception:
        result = LendingStatsResponse(gross_profit=0.0, bitfinex_fee=0.0, net_profit=0.0)
        rate_limited = False
    if rate_limited:
        await bitfinex_cache.set_rate_limit_cooldown(user_id, bitfinex_cache.KEY_LENDING)
        cached = await bitfinex_cache.get_cached(user_id, bitfinex_cache.KEY_LENDING)
        if cached is not None:
            data, _ = cached
            if data is not None:
                response.headers["X-Data-Source"] = "cache"
                response.headers["X-Rate-Limited"] = "true"
                response.headers["Retry-After"] = "60"
                return LendingStatsResponse(**data)
        response.headers["X-Rate-Limited"] = "true"
        response.headers["Retry-After"] = "60"
    cache_data = result.model_dump()
    cache_data.pop("trades", None)
    cache_data.pop("calculation_breakdown", None)
    await bitfinex_cache.set_cached(user_id, bitfinex_cache.KEY_LENDING, cache_data)
    response.headers["X-Data-Source"] = "live"
    exp = await bitfinex_cache.cache_expires_at(user_id, bitfinex_cache.KEY_LENDING)
    if exp is not None:
        response.headers["X-Cache-Expires-At"] = str(int(exp))
    return result


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
    keys = current_user.vault.get_keys()
    mgr = BitfinexManager(keys["bfx_key"], keys["bfx_secret"])
    start_ms = None
    if getattr(current_user.vault, "created_at", None) and current_user.vault.created_at:
        start_ms = int(current_user.vault.created_at.timestamp() * 1000)
    trades, err = await _fetch_all_funding_trades(mgr, start_ms)
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
    """
    await bitfinex_cache.invalidate(current_user.id, bitfinex_cache.KEY_LENDING)
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
def get_user_token_balance(user_id: int, db: Session = Depends(database.get_db)):
    """
    Token balance from stored profit snapshot (no Bitfinex call). 1 USDT gross = 10 tokens used.
    Checked on login and optionally daily; prefer snapshot to minimize API.
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    tier = (user.plan_tier or "trial").lower()
    if tier not in PLAN_TOKEN_CREDITS:
        tier = "trial"
    initial_credit = PLAN_TOKEN_CREDITS[tier]
    row = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
    purchased = float(row.purchased_tokens) if row and row.purchased_tokens is not None else 0.0

    snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
    gross = float(snap.gross_profit_usd) if snap and snap.gross_profit_usd is not None else 0.0
    tokens_used = int(gross * TOKENS_PER_USDT_GROSS)
    tokens_remaining = max(0.0, float(initial_credit) + purchased - tokens_used)

    if row:
        row.tokens_remaining = tokens_remaining
        row.last_gross_usd_used = gross
        row.updated_at = datetime.utcnow()
    else:
        db.add(models.UserTokenBalance(
            user_id=user_id,
            tokens_remaining=tokens_remaining,
            last_gross_usd_used=gross,
        ))
    db.commit()

    return TokenBalanceResponse(
        tokens_remaining=tokens_remaining,
        tokens_used=tokens_used,
        initial_credit=int(initial_credit) + int(purchased),
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
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # Token balance (from stored snapshot, no Bitfinex call). Include purchased_tokens.
    tier = (user.plan_tier or "trial").lower()
    initial_credit = PLAN_TOKEN_CREDITS.get(tier, FREE_TIER_TOKENS)
    token_row = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
    purchased = float(token_row.purchased_tokens) if token_row and token_row.purchased_tokens is not None else 0.0
    snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
    gross = float(snap.gross_profit_usd) if snap and snap.gross_profit_usd is not None else 0.0
    tokens_used = int(gross * TOKENS_PER_USDT_GROSS)
    tokens_remaining = max(0.0, float(initial_credit) + purchased - tokens_used)

    # Utilization from latest PerformanceLog, if available (table may lack waroc column).
    total_assets = 0.0
    used_amount = 0.0
    utilization_pct = 0.0
    try:
        log = (
            db.query(models.PerformanceLog)
            .filter(models.PerformanceLog.user_id == user_id)
            .order_by(models.PerformanceLog.timestamp.desc())
            .first()
        )
        if log and log.total_assets is not None:
            total_assets = float(log.total_assets)
        used_amount = min(total_assets, user.lending_limit or 0.0)
        utilization_pct = (used_amount / user.lending_limit * 100.0) if user.lending_limit else 0.0
    except ProgrammingError:
        pass

    return UserStatusResponse(
        plan_tier=user.plan_tier or "trial",
        lending_limit=float(user.lending_limit or 0.0),
        rebalance_interval=int(user.rebalance_interval or 0),
        trial_remaining_days=None,
        utilization_pct=utilization_pct,
        used_amount=used_amount,
        tokens_remaining=tokens_remaining,
        tokens_used=tokens_used,
        initial_token_credit=int(initial_credit) + int(purchased),
        gross_profit_usd=round(gross, 2),
    )


@app.get("/admin/users", response_model=list[AdminUserOut])
def list_users(
    _: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    users = db.query(models.User).all()
    return [
        AdminUserOut(
            id=u.id,
            email=u.email,
            plan_tier=u.plan_tier or "trial",
            lending_limit=float(u.lending_limit or 0.0),
            rebalance_interval=int(u.rebalance_interval or 0),
            pro_expiry=u.pro_expiry,
            status=u.status or "active",
        )
        for u in users
    ]


@app.patch("/admin/users/{user_id}", response_model=AdminUserOut)
def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    _: models.User = Depends(get_admin_user),
    db: Session = Depends(database.get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if payload.plan_tier is not None:
        tier = payload.plan_tier.lower()
        user.plan_tier = tier
        # Apply default limits if not explicitly overridden in payload
        if tier == "pro":
            user.lending_limit = payload.lending_limit or 50_000.0
            user.rebalance_interval = payload.rebalance_interval or 30
        elif tier == "expert":
            user.lending_limit = payload.lending_limit or 250_000.0
            user.rebalance_interval = payload.rebalance_interval or 3
        elif tier == "guru":
            user.lending_limit = payload.lending_limit or 1_500_000.0
            user.rebalance_interval = payload.rebalance_interval or 1
        else:
            user.lending_limit = payload.lending_limit or 250_000.0
            user.rebalance_interval = payload.rebalance_interval or 3
    else:
        if payload.lending_limit is not None:
            user.lending_limit = payload.lending_limit
        if payload.rebalance_interval is not None:
            user.rebalance_interval = payload.rebalance_interval

    if payload.pro_expiry is not None:
        user.pro_expiry = payload.pro_expiry

    db.commit()
    db.refresh(user)
    return AdminUserOut(
        id=user.id,
        email=user.email,
        plan_tier=user.plan_tier or "trial",
        lending_limit=float(user.lending_limit or 0.0),
        rebalance_interval=int(user.rebalance_interval or 0),
        pro_expiry=user.pro_expiry,
        status=user.status or "active",
    )


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
        raise HTTPException(status_code=502, detail=f"Retry failed: {e}")


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


def _fetch_ticker_prices(currencies: set) -> Dict[str, float]:
    """Fetch tCCYUSD prices for all non-stablecoins. Returns dict keyed by tCCYUSD. Cached 60s to reduce API calls."""
    from services.bitfinex_service import _get_tickers_sync
    stablecoins = {"USD", "USDt", "USDT", "UST"}
    need = sorted([c for c in currencies if c and c not in stablecoins])
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
    _ticker_cache[cache_key] = (out, now)
    return out


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


async def _portfolio_allocation_snapshot(mgr: BitfinexManager) -> tuple:
    """
    Wallets, credits, offers in rapid succession; one ticker fetch.
    Retries up to 3 times with backoff on transient failures (stable logic like other platforms).
    Returns (summary_dict, log_str, rate_limited: bool).
    Actively Earning = credits USD (from offers API); Pending = offers USD (from credits API); Idle = Total - credits - offers.
    """
    max_attempts = 3
    wallets, credits, offers = None, None, None
    for attempt in range(max_attempts):
        wallets, credits, offers = await asyncio.gather(
            mgr.wallets(),
            mgr.funding_credits(),
            mgr.funding_offers(),
        )
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

    # Only compute when we have all three; otherwise return None so caller can serve cache or 503.
    if wallets_data is None or credits_data is None or offers_data is None:
        log_incomplete = (
            f"Portfolio Allocation: incomplete (wallets={wallets_data is not None}, "
            f"credits={credits_data is not None}, offers={offers_data is not None})"
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
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or not user.vault:
        raise HTTPException(status_code=404, detail="API keys not found.")

    cached = await bitfinex_cache.get_cached(user_id, bitfinex_cache.KEY_WALLETS)
    if cached is not None:
        data, from_cache = cached
        if from_cache and data is not None:
            response.headers["X-Data-Source"] = "cache"
            exp = await bitfinex_cache.cache_expires_at(user_id, bitfinex_cache.KEY_WALLETS)
            if exp is not None:
                response.headers["X-Cache-Expires-At"] = str(int(exp))
            return data

    if await bitfinex_cache.is_in_cooldown(user_id, bitfinex_cache.KEY_WALLETS):
        response.headers["X-Data-Source"] = "cache"
        response.headers["X-Rate-Limited"] = "true"
        response.headers["Retry-After"] = "60"
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
        }

    keys = user.vault.get_keys()
    mgr = BitfinexManager(keys["bfx_key"], keys["bfx_secret"])
    try:
        summary, log_str, rate_limited = await _portfolio_allocation_snapshot(mgr)
        if os.getenv("LOG_PORTFOLIO_ALLOCATION"):
            print(f"[user_id={user_id}] {log_str}")
        if rate_limited:
            await bitfinex_cache.set_rate_limit_cooldown(user_id, bitfinex_cache.KEY_WALLETS)
        if summary is None:
            # Incomplete data: do not cache; return cached if available, else 503.
            cached = await bitfinex_cache.get_cached(user_id, bitfinex_cache.KEY_WALLETS)
            if cached is not None:
                data, _ = cached
                if data is not None:
                    response.headers["X-Data-Source"] = "cache"
                    response.headers["X-Data-Incomplete"] = "true"
                    return data
            raise HTTPException(status_code=503, detail="Wallet data incomplete; try again shortly.")
    except HTTPException:
        raise
    except Exception as e:
        if bitfinex_cache.is_rate_limit_error(str(e)):
            await bitfinex_cache.set_rate_limit_cooldown(user_id, bitfinex_cache.KEY_WALLETS)
        raise
    await bitfinex_cache.set_cached(user_id, bitfinex_cache.KEY_WALLETS, summary)
    response.headers["X-Data-Source"] = "live"
    exp = await bitfinex_cache.cache_expires_at(user_id, bitfinex_cache.KEY_WALLETS)
    if exp is not None:
        response.headers["X-Cache-Expires-At"] = str(int(exp))
    return summary


# --- Stripe Webhook (referrals + subscription) ---
stripe.api_key = os.getenv("STRIPE_API_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
# Price IDs: monthly and yearly (create in Stripe Dashboard)
STRIPE_PRICE_PRO_MONTHLY = os.getenv("STRIPE_PRICE_PRO_MONTHLY", "")
STRIPE_PRICE_AI_ULTRA_MONTHLY = os.getenv("STRIPE_PRICE_AI_ULTRA_MONTHLY", "")
STRIPE_PRICE_WHALES_MONTHLY = os.getenv("STRIPE_PRICE_WHALES_MONTHLY", "")
STRIPE_PRICE_PRO_YEARLY = os.getenv("STRIPE_PRICE_PRO_YEARLY", "")
STRIPE_PRICE_AI_ULTRA_YEARLY = os.getenv("STRIPE_PRICE_AI_ULTRA_YEARLY", "")
STRIPE_PRICE_WHALES_YEARLY = os.getenv("STRIPE_PRICE_WHALES_YEARLY", "")

# Plan limits and rebalance (minutes) for webhook
PLAN_REBALANCE_MIN = {"pro": 30, "ai_ultra": 3, "whales": 1}
PLAN_LENDING_LIMIT = {"pro": 250_000.0, "ai_ultra": 250_000.0, "whales": 1_500_000.0}

# Token award per subscription payment (added to purchased_tokens in webhook)
PLAN_TOKEN_AWARD_MONTHLY = {"pro": 2000, "ai_ultra": 9000, "whales": 40000}
PLAN_TOKEN_AWARD_YEARLY = {"pro": 24000, "ai_ultra": 108000, "whales": 480000}


class CreateCheckoutPayload(BaseModel):
    plan: str  # "pro" | "ai_ultra" | "whales"
    interval: str  # "monthly" | "yearly"


class CreateCheckoutTokensPayload(BaseModel):
    amount_usd: float  # e.g. 10 → user gets 1000 tokens (1 USD = 100 tokens)


# --- Token deposit (Add tokens): USD × 10 = tokens, min $1 (Stripe checkout placeholder) ---
class TokenDepositPayload(BaseModel):
    usd_amount: float


@app.post("/api/v1/tokens/deposit")
def token_deposit(
    payload: TokenDepositPayload,
    current_user: models.User = Depends(get_current_user),
):
    """
    Validate USD amount and compute tokens to award (tokens = round(usd_amount × 10)).
    Minimum $1. No Stripe checkout yet; returns calculation only.
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

    # int() so $10.99 → 109 tokens (spec); use round() for true nearest-integer if preferred
    tokens_to_award = int(amount_float * 10)
    logger.info("token_deposit_calculation user_id=%s usd_amount=%s tokens_to_award=%s", user_id, amount_float, tokens_to_award)

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
        raise HTTPException(status_code=500, detail=str(e))


def _get_stripe_price_id(plan: str, interval: str) -> str:
    """Return Stripe Price ID for plan + interval. Empty string if not configured."""
    if interval == "yearly":
        if plan == "pro":
            return STRIPE_PRICE_PRO_YEARLY or ""
        if plan == "ai_ultra":
            return STRIPE_PRICE_AI_ULTRA_YEARLY or ""
        if plan == "whales":
            return STRIPE_PRICE_WHALES_YEARLY or ""
    else:
        if plan == "pro":
            return STRIPE_PRICE_PRO_MONTHLY or ""
        if plan == "ai_ultra":
            return STRIPE_PRICE_AI_ULTRA_MONTHLY or ""
        if plan == "whales":
            return STRIPE_PRICE_WHALES_MONTHLY or ""
    return ""


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
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=STRIPE_WEBHOOK_SECRET,
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook signature.")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        meta = session.get("metadata") or {}
        if meta.get("type") == "tokens":
            user_id = int(meta.get("user_id") or 0)
            tokens = int(meta.get("tokens") or 0)
            if user_id and tokens > 0:
                db = next(database.get_db())
                try:
                    row = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
                    if row:
                        row.purchased_tokens = (row.purchased_tokens or 0) + tokens
                        row.updated_at = datetime.utcnow()
                    else:
                        db.add(models.UserTokenBalance(user_id=user_id, purchased_tokens=float(tokens)))
                    db.commit()
                finally:
                    db.close()
            return {"received": True}

    if event["type"] == "invoice.payment_succeeded":
        data = event["data"]["object"]
        email = data.get("customer_email") or (data.get("customer_details") or {}).get("email")

        db: Session = next(database.get_db())
        try:
            user = db.query(models.User).filter(models.User.email == email).first()
            if not user:
                return {"received": True}

            interval_days = 30
            plan = "pro"
            interval = "monthly"
            sub_id = data.get("subscription")
            if sub_id:
                try:
                    sub = stripe.Subscription.retrieve(sub_id)
                    meta = sub.metadata or {}
                    plan = meta.get("plan") or "pro"
                    interval = (meta.get("interval") or "monthly").lower()
                    interval_days = 365 if interval == "yearly" else 30
                except Exception:
                    pass

            if plan in PLAN_REBALANCE_MIN:
                user.plan_tier = plan
                user.rebalance_interval = PLAN_REBALANCE_MIN[plan]
                user.lending_limit = PLAN_LENDING_LIMIT.get(plan, 250_000.0)

            now = datetime.utcnow()
            base = user.pro_expiry if user.pro_expiry and user.pro_expiry > now else now
            user.pro_expiry = base + timedelta(days=interval_days)

            # Award plan-specific tokens to purchased_tokens (add, do not overwrite)
            tokens_to_award = (
                PLAN_TOKEN_AWARD_YEARLY.get(plan, 0)
                if interval == "yearly"
                else PLAN_TOKEN_AWARD_MONTHLY.get(plan, 0)
            )
            if tokens_to_award > 0:
                token_row = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user.id).first()
                if token_row:
                    token_row.purchased_tokens = float(token_row.purchased_tokens or 0) + tokens_to_award
                    token_row.updated_at = now
                else:
                    db.add(models.UserTokenBalance(
                        user_id=user.id,
                        purchased_tokens=float(tokens_to_award),
                        tokens_remaining=0.0,
                        last_gross_usd_used=0.0,
                        updated_at=now,
                    ))
                logger.info(
                    "subscription_token_award user_id=%s plan=%s interval=%s tokens_added=%s timestamp=%s",
                    user.id, plan, interval, tokens_to_award, now.isoformat(),
                )

            if user.referred_by:
                referrer = db.query(models.User).filter(models.User.id == user.referred_by).first()
                if referrer:
                    ref_base = (
                        referrer.pro_expiry
                        if referrer.pro_expiry and referrer.pro_expiry > now
                        else now
                    )
                    referrer.pro_expiry = ref_base + timedelta(days=7)

            db.commit()
        finally:
            db.close()

    return {"received": True}