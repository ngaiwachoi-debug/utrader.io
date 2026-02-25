from datetime import datetime, timedelta
import json
import os
from typing import Optional

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
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
from services import bitfinex as bfx_service


app = FastAPI(title="utrader.io API")

# NextAuth JWT (from /api/auth/token). Set NEXTAUTH_SECRET in env to enable.
NEXTAUTH_SECRET = os.getenv("NEXTAUTH_SECRET", "")


# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
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
    authorization: str = Header(..., alias="Authorization"),
    db: Session = Depends(database.get_db),
) -> models.User:
    """
    Verify Bearer token: either NextAuth JWT (from /api/auth/token) or Google ID token.
    NextAuth JWT is verified against NEXTAUTH_SECRET; then user is looked up by email.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header.")

    token = authorization.split(" ", 1)[1]

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
        raise HTTPException(status_code=401, detail="Invalid or expired token.")


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


# --- Connect Exchange (Bitfinex) ---
@app.post("/connect-exchange")
async def connect_exchange(
    payload: APIKeysInput,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    # 1. Anti-abuse: Bitfinex master identity check
    master_id = await bfx_service.get_master_user_id(payload.bfx_key, payload.bfx_secret)
    if not master_id:
        raise HTTPException(status_code=400, detail="Unable to verify Bitfinex account identity.")

    hashed_id = bfx_service.hash_bitfinex_id(master_id)
    existing = (
        db.query(models.TrialHistory)
        .filter(models.TrialHistory.hashed_bitfinex_id == hashed_id)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail="This Bitfinex account has already used the Free Trial. Please upgrade.",
        )

    # 2. Permission validation
    ok, error_msg = await bfx_service.validate_api_permissions(
        payload.bfx_key, payload.bfx_secret
    )
    if not ok:
        raise HTTPException(status_code=400, detail=error_msg or "Bitfinex API key permissions invalid.")

    # 3. Store trial usage
    trial_row = models.TrialHistory(hashed_bitfinex_id=hashed_id)
    db.add(trial_row)

    # 4. Grant 7‑day trial window on first connect, aligned with "Expert" tier limits
    current_user.plan_tier = "trial"
    current_user.lending_limit = 250_000.0
    current_user.rebalance_interval = 3
    if not current_user.pro_expiry or current_user.pro_expiry < datetime.utcnow():
        current_user.pro_expiry = datetime.utcnow() + timedelta(days=7)

    # 5. Save encrypted keys in APIVault
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
    return {"status": "success", "message": "Exchange connected and trial activated."}


# Dev-only: connect exchange by user_id (no Google token). Set ALLOW_DEV_CONNECT=1 to enable.
class ConnectByUserInput(BaseModel):
    user_id: int
    bfx_key: str
    bfx_secret: str
    gemini_key: Optional[str] = None


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
    # Reuse same validation and storage logic
    master_id = await bfx_service.get_master_user_id(payload.bfx_key, payload.bfx_secret)
    if not master_id:
        raise HTTPException(status_code=400, detail="Unable to verify Bitfinex account identity.")
    hashed_id = bfx_service.hash_bitfinex_id(master_id)
    existing = (
        db.query(models.TrialHistory)
        .filter(models.TrialHistory.hashed_bitfinex_id == hashed_id)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail="This Bitfinex account has already used the Free Trial. Please upgrade.",
        )
    ok, error_msg = await bfx_service.validate_api_permissions(
        payload.bfx_key, payload.bfx_secret
    )
    if not ok:
        raise HTTPException(status_code=400, detail=error_msg or "Bitfinex API key permissions invalid.")
    trial_row = models.TrialHistory(hashed_bitfinex_id=hashed_id)
    db.add(trial_row)
    user.plan_tier = "trial"
    user.lending_limit = 250_000.0
    user.rebalance_interval = 3
    if not user.pro_expiry or user.pro_expiry < datetime.utcnow():
        user.pro_expiry = datetime.utcnow() + timedelta(days=7)
    vault = (
        db.query(models.APIVault)
        .filter(models.APIVault.user_id == user.id)
        .first()
    )
    if not vault:
        vault = models.APIVault(user_id=user.id)
        db.add(vault)
    vault.encrypted_key = security.encrypt_key(payload.bfx_key)
    vault.encrypted_secret = security.encrypt_key(payload.bfx_secret)
    if payload.gemini_key:
        vault.encrypted_gemini_key = security.encrypt_key(payload.gemini_key)
    db.commit()
    return {"status": "success", "message": "Exchange connected and trial activated."}


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


@app.get("/user-status/{user_id}", response_model=UserStatusResponse)
def get_user_status(user_id: int, db: Session = Depends(database.get_db)):
    """
    Lightweight status snapshot for the Settings page and header banner.
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    now = datetime.utcnow()
    days_remaining: Optional[int] = None
    if user.pro_expiry:
        delta = (user.pro_expiry - now).days
        days_remaining = max(delta, 0)

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


@app.get("/wallets/{user_id}")
async def wallet_summary(user_id: int, db: Session = Depends(database.get_db)):
    """
    Returns Bitfinex wallet USD totals for header currency selector.
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or not user.vault:
        raise HTTPException(status_code=404, detail="API keys not found.")

    keys = user.vault.get_keys()
    summary = await bfx_service.compute_usd_balances(
        keys["bfx_key"],
        keys["bfx_secret"],
    )
    return summary


# --- Stripe Webhook (referrals + subscription) ---
stripe.api_key = os.getenv("STRIPE_API_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")


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