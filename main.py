from datetime import datetime, timedelta
import json
import os
from typing import Any, Dict, Optional

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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


app = FastAPI(title="utrader.io API")

# NextAuth JWT (from /api/auth/token). Set NEXTAUTH_SECRET in env to enable.
NEXTAUTH_SECRET = os.getenv("NEXTAUTH_SECRET", "")


# --- CORS: explicitly allow frontend origins so browser can reach backend ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Redis / ARQ ---
async def get_redis():
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    return await create_pool(RedisSettings.from_dsn(redis_url))


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
        rebalance_interval=3,
        pro_expiry=datetime.utcnow() + timedelta(days=7),
        referred_by=referrer.id if referrer else None,
    )
    # Simple referral code: user email hash suffix
    new_user.referral_code = f"ref-{abs(hash(email)) % 10_000_000}"

    db.add(new_user)
    db.commit()
    db.refresh(new_user)
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


class LendingStatsResponse(BaseModel):
    """Gross = total interest from Bitfinex since registration; Net = Gross × (1 - 15%)."""
    gross_profit: float
    bitfinex_fee: float
    net_profit: float


class UserStatusResponse(BaseModel):
    plan_tier: str
    lending_limit: float
    rebalance_interval: int
    trial_remaining_days: Optional[int]
    utilization_pct: float
    used_amount: float


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


# --- Live Bot Stats Route (existing dashboard) ---
@app.get("/bot-stats/{user_id}")
async def get_all_bot_stats(user_id: int):
    """
    Fetches live heartbeat data from Redis for the utrader.io dashboard.
    """
    redis = await get_redis()

    keys = await redis.keys(f"status:{user_id}:*")

    all_engines = []
    for key in keys:
        raw_data = await redis.get(key)
        if raw_data:
            all_engines.append(json.loads(raw_data))

    if not all_engines:
        return {"active": False, "engines": [], "total_loaned": "0.00"}

    total_val = sum(float(str(e["loaned"]).replace(",", "")) for e in all_engines)

    return {
        "active": True,
        "engines": all_engines,
        "total_loaned": f"{total_val:,.2f}",
    }


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
    current_user.rebalance_interval = 3
    if not current_user.pro_expiry or current_user.pro_expiry < datetime.utcnow():
        current_user.pro_expiry = datetime.utcnow() + timedelta(days=7)

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
        rebalance_interval=3,
        pro_expiry=datetime.utcnow() + timedelta(days=7),
    )
    new_user.referral_code = f"ref-{abs(hash(email)) % 10_000_000}"
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
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
    return {
        "status": "success",
        "message": result.get("message", "Exchange connected and trial activated."),
        "balance": balance,
        "user_id": user.id,
    }


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
    return {
        "status": "success",
        "message": result.get("message", "Exchange connected and trial activated."),
        "balance": balance,
    }


# --- Start / Stop Bot ---
@app.post("/start-bot")
async def start_bot(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    if not current_user.vault:
        raise HTTPException(status_code=404, detail="API keys not found.")

    # Ensure subscription is not expired before starting
    if current_user.pro_expiry and current_user.pro_expiry < datetime.utcnow():
        current_user.status = "expired"
        db.commit()
        raise HTTPException(status_code=402, detail="Subscription expired. Payment required.")

    redis = await get_redis()
    await redis.enqueue_job("run_bot_task", current_user.id, _job_id=f"bot_user_{current_user.id}")
    return {"status": "success", "message": f"Bot queued for user {current_user.id}"}


@app.post("/stop-bot")
async def stop_bot(current_user: models.User = Depends(get_current_user)):
    redis = await get_redis()
    job_id = f"bot_user_{current_user.id}"
    job = await redis.get_job(job_id)
    if job:
        await job.abort()
        return {"status": "success", "message": "Shutdown signal sent"}
    return {"status": "error", "message": "No active bot found"}


# Legacy-style control endpoints that address bots by numeric user_id directly.
# Useful for simple frontends or internal tools without Google auth wiring yet.
@app.post("/start-bot/{user_id}")
async def start_bot_for_user(user_id: int, db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or not user.vault:
        raise HTTPException(status_code=404, detail="API keys not found.")

    if user.pro_expiry and user.pro_expiry < datetime.utcnow():
        user.status = "expired"
        db.commit()
        raise HTTPException(status_code=402, detail="Subscription expired. Payment required.")

    redis = await get_redis()
    await redis.enqueue_job("run_bot_task", user.id, _job_id=f"bot_user_{user.id}")
    return {"status": "success", "message": f"Bot queued for user {user.id}"}


@app.post("/stop-bot/{user_id}")
async def stop_bot_for_user(user_id: int):
    redis = await get_redis()
    job_id = f"bot_user_{user_id}"
    job = await redis.get_job(job_id)
    if job:
        await job.abort()
        return {"status": "success", "message": "Shutdown signal sent"}
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


def _interest_usd_from_trades(trades: Any, ticker_prices: Dict[str, float]) -> float:
    """
    Sum interest from Bitfinex funding trade arrays. Each row: [ID, CURRENCY, MTS_CREATE, OFFER_ID, AMOUNT, RATE, PERIOD, ...].
    Interest per trade = |AMOUNT| * RATE * (PERIOD/365). Convert to USD: USD/USDt/USDT=1, others use ticker_prices (e.g. tBTCUSD last price).
    """
    if not isinstance(trades, list):
        return 0.0
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
    for currency, interest in by_currency.items():
        if currency in ("USD", "USDt", "USDT"):
            total_usd += interest
        else:
            price = ticker_prices.get(f"t{currency}USD", 0.0)
            total_usd += interest * price if price else 0.0
    return total_usd


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


@app.get("/stats/{user_id}/lending", response_model=LendingStatsResponse)
async def get_lending_stats(
    user_id: int,
    response: Response,
    db: Session = Depends(database.get_db),
):
    """
    Gross profit = total interest from Bitfinex lending since connection.
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

    keys = user.vault.get_keys()
    mgr = BitfinexManager(keys["bfx_key"], keys["bfx_secret"])
    start_ms = None
    if getattr(user.vault, "created_at", None) and user.vault.created_at:
        start_ms = int(user.vault.created_at.timestamp() * 1000)
    trades, err = await mgr.funding_trades_hist(start_ms=start_ms, limit=1000)
    if bitfinex_cache.is_rate_limit_error(err):
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
        return LendingStatsResponse(gross_profit=0.0, bitfinex_fee=0.0, net_profit=0.0)
    if err or not trades:
        result = LendingStatsResponse(gross_profit=0.0, bitfinex_fee=0.0, net_profit=0.0)
        await bitfinex_cache.set_cached(user_id, bitfinex_cache.KEY_LENDING, result.model_dump())
        return result
    ticker_prices = _ticker_prices_from_trades(trades)
    gross = _interest_usd_from_trades(trades, ticker_prices)
    fee = gross * BITFINEX_LENDER_FEE_PCT
    net = gross - fee
    result = LendingStatsResponse(gross_profit=round(gross, 2), bitfinex_fee=round(fee, 2), net_profit=round(net, 2))
    await bitfinex_cache.set_cached(user_id, bitfinex_cache.KEY_LENDING, result.model_dump())
    response.headers["X-Data-Source"] = "live"
    exp = await bitfinex_cache.cache_expires_at(user_id, bitfinex_cache.KEY_LENDING)
    if exp is not None:
        response.headers["X-Cache-Expires-At"] = str(int(exp))
    return result


@app.get("/user-status/{user_id}", response_model=UserStatusResponse)
def get_user_status(user_id: int, db: Session = Depends(database.get_db)):
    """
    Lightweight status snapshot for the Settings page and header banner.
    Trial: 7 days from first connection (vault.created_at) or pro_expiry if set.
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    now = datetime.utcnow()
    days_remaining: Optional[int] = None
    if user.pro_expiry:
        delta = (user.pro_expiry - now).days
        days_remaining = max(delta, 0)
    else:
        # Trial users: 7 days from first API key connection
        vault = db.query(models.APIVault).filter(models.APIVault.user_id == user_id).first()
        if vault and getattr(vault, "created_at", None) and vault.created_at:
            trial_end = vault.created_at + timedelta(days=7)
            days_remaining = max((trial_end - now).days, 0)

    # Utilization from latest PerformanceLog, if available.
    log = (
        db.query(models.PerformanceLog)
        .filter(models.PerformanceLog.user_id == user_id)
        .order_by(models.PerformanceLog.timestamp.desc())
        .first()
    )
    total_assets = float(log.total_assets) if log and log.total_assets is not None else 0.0
    used_amount = min(total_assets, user.lending_limit or 0.0)
    utilization_pct = (used_amount / user.lending_limit * 100.0) if user.lending_limit else 0.0

    return UserStatusResponse(
        plan_tier=user.plan_tier or "trial",
        lending_limit=float(user.lending_limit or 0.0),
        rebalance_interval=int(user.rebalance_interval or 0),
        trial_remaining_days=days_remaining,
        utilization_pct=utilization_pct,
        used_amount=used_amount,
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


@app.get("/wallets/{user_id}")
async def wallet_summary(
    user_id: int,
    response: Response,
    db: Session = Depends(database.get_db),
):
    """
    Returns Bitfinex wallet USD totals and currently lent out per currency.
    Cached to respect Bitfinex rate limits (10–90 req/min). Use X-Data-Source and X-Cache-Expires-At headers.
    """
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
            "_rate_limited": True,
        }

    keys = user.vault.get_keys()
    mgr = BitfinexManager(keys["bfx_key"], keys["bfx_secret"])
    summary = await mgr.compute_usd_balances()
    credits, err = await mgr.funding_credits()
    if bitfinex_cache.is_rate_limit_error(err):
        await bitfinex_cache.set_rate_limit_cooldown(user_id, bitfinex_cache.KEY_WALLETS)
        cached = await bitfinex_cache.get_cached(user_id, bitfinex_cache.KEY_WALLETS)
        if cached is not None:
            data, _ = cached
            if data is not None:
                response.headers["X-Data-Source"] = "cache"
                response.headers["X-Rate-Limited"] = "true"
                response.headers["Retry-After"] = "60"
                return data
        response.headers["X-Rate-Limited"] = "true"
        response.headers["Retry-After"] = "60"
        return {
            "total_usd_all": 0.0,
            "usd_only": 0.0,
            "per_currency": {},
            "per_currency_usd": {},
            "lent_per_currency": {},
            "_rate_limited": True,
        }
    lent_per_currency = _aggregate_lent_per_currency(credits) if credits else {}
    summary["lent_per_currency"] = lent_per_currency
    await bitfinex_cache.set_cached(user_id, bitfinex_cache.KEY_WALLETS, summary)
    response.headers["X-Data-Source"] = "live"
    exp = await bitfinex_cache.cache_expires_at(user_id, bitfinex_cache.KEY_WALLETS)
    if exp is not None:
        response.headers["X-Cache-Expires-At"] = str(int(exp))
    return summary


# --- Stripe Webhook (referrals + subscription) ---
stripe.api_key = os.getenv("STRIPE_API_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
# Price IDs for checkout (create in Stripe Dashboard; yearly = 10% off)
STRIPE_PRICE_PRO_MONTHLY = os.getenv("STRIPE_PRICE_PRO_MONTHLY", "")
STRIPE_PRICE_PRO_YEARLY = os.getenv("STRIPE_PRICE_PRO_YEARLY", "")
STRIPE_PRICE_EXPERT_MONTHLY = os.getenv("STRIPE_PRICE_EXPERT_MONTHLY", "")
STRIPE_PRICE_EXPERT_YEARLY = os.getenv("STRIPE_PRICE_EXPERT_YEARLY", "")


class CreateCheckoutPayload(BaseModel):
    plan: str  # "pro" | "expert"
    interval: str  # "monthly" | "yearly"


@app.post("/api/create-checkout-session")
async def create_checkout_session(
    payload: CreateCheckoutPayload,
    current_user: models.User = Depends(get_current_user),
):
    """
    Create a Stripe Checkout Session for the chosen plan/interval. Returns { url } to redirect the user.
    Yearly prices should be configured in Stripe with 10% off (e.g. $15/mo -> $162/year).
    """
    plan = (payload.plan or "").lower()
    interval = (payload.interval or "monthly").lower()
    if plan not in ("pro", "expert") or interval not in ("monthly", "yearly"):
        raise HTTPException(status_code=400, detail="Invalid plan or interval.")
    price_id = None
    if plan == "pro" and interval == "monthly":
        price_id = STRIPE_PRICE_PRO_MONTHLY
    elif plan == "pro" and interval == "yearly":
        price_id = STRIPE_PRICE_PRO_YEARLY
    elif plan == "expert" and interval == "monthly":
        price_id = STRIPE_PRICE_EXPERT_MONTHLY
    elif plan == "expert" and interval == "yearly":
        price_id = STRIPE_PRICE_EXPERT_YEARLY
    if not price_id or not stripe.api_key:
        raise HTTPException(
            status_code=503,
            detail="Subscription is not configured. Please set STRIPE_API_KEY and Stripe Price IDs in the server environment.",
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

    if event["type"] == "invoice.payment_succeeded":
        data = event["data"]["object"]
        customer_id = data.get("customer")
        # We assume you store a mapping from Stripe customer -> user email in metadata
        email = data.get("customer_email") or (data.get("customer_details") or {}).get("email")

        db: Session = next(database.get_db())
        try:
            user = db.query(models.User).filter(models.User.email == email).first()
            if not user:
                return {"received": True}

            # Decide whether it's monthly or annual from the invoice/price metadata.
            # Default: monthly 30 days.
            interval_days = 30
            lines = data.get("lines", {}).get("data", [])
            if lines:
                price = (lines[0].get("price") or {})
                recurring = price.get("recurring") or {}
                if recurring.get("interval") == "year":
                    interval_days = 365

            now = datetime.utcnow()
            base = user.pro_expiry if user.pro_expiry and user.pro_expiry > now else now
            user.pro_expiry = base + timedelta(days=interval_days)

            # Referral bonus
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