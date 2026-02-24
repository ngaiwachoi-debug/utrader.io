from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware  # 🟢 Added for Frontend connection
from sqlalchemy.orm import Session
import models, database, security
from pydantic import BaseModel
import aiohttp
import time
import hmac
import hashlib
import os
import json  # 🟢 Added for parsing Redis status

# Redis and ARQ imports
from arq import create_pool
from arq.connections import RedisSettings

app = FastAPI(title="utrader.io API")

# --- 🟢 CORS Configuration ---
# This allows your Next.js frontend (port 3000) to securely talk to this API (port 8000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Redis Setup ---
async def get_redis():
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    return await create_pool(RedisSettings.from_dsn(redis_url))

# --- Pydantic Schemas ---
class UserCreate(BaseModel):
    email: str
    password: str

class APIKeysInput(BaseModel):
    user_id: int
    bfx_key: str
    bfx_secret: str
    gemini_key: str

# --- Helper: Verify Keys ---
async def verify_bfx_connectivity(key: str, secret: str):
    nonce = str(int(time.time() * 1000000))
    path = "/api/v2/auth/r/wallets"
    signature_payload = f"/api/v2/auth/r/wallets{nonce}{{}}"
    sig = hmac.new(secret.encode(), signature_payload.encode(), hashlib.sha384).hexdigest()
    
    headers = {
        "bfx-nonce": nonce, 
        "bfx-apikey": key, 
        "bfx-signature": sig,
        "Content-Type": "application/json"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(f"https://api.bitfinex.com/v2/auth/r/wallets", headers=headers, json={}) as r:
            return r.status == 200

# --- 🟢 NEW: Live Bot Stats Route ---
@app.get("/bot-stats/{user_id}")
async def get_all_bot_stats(user_id: int):
    """
    Fetches live heartbeat data from Redis for the utrader.io dashboard.
    """
    redis = await get_redis()
    
    # Search for all active engines for this user (e.g., status:1:USD, status:1:UST)
    keys = await redis.keys(f"status:{user_id}:*")
    
    all_engines = []
    for key in keys:
        raw_data = await redis.get(key)
        if raw_data:
            all_engines.append(json.loads(raw_data))
            
    if not all_engines:
        return {"active": False, "engines": [], "total_loaned": "0.00"}

    # Calculate total loaned across all assets
    total_val = sum(float(str(e['loaned']).replace(',', '')) for e in all_engines)

    return {
        "active": True,
        "engines": all_engines,
        "total_loaned": f"{total_val:,.2f}"
    }

# --- Standard Routes ---

@app.post("/register")
def register_user(user: UserCreate, db: Session = Depends(database.get_db)):
    db_user = models.User(email=user.email, hashed_password=user.password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return {"message": "User created", "user_id": db_user.id}

@app.post("/connect-exchange")
async def connect_exchange(data: APIKeysInput, db: Session = Depends(database.get_db)):
    if not await verify_bfx_connectivity(data.bfx_key, data.bfx_secret):
        raise HTTPException(status_code=400, detail="Invalid Bitfinex API keys")

    vault = db.query(models.APIKeyVault).filter(models.APIKeyVault.user_id == data.user_id).first()
    if not vault:
        vault = models.APIKeyVault(user_id=data.user_id)
        db.add(vault)
    
    vault.encrypted_bfx_key = security.encrypt_key(data.bfx_key)
    vault.encrypted_bfx_secret = security.encrypt_key(data.bfx_secret)
    vault.encrypted_gemini_key = security.encrypt_key(data.gemini_key)
    
    db.commit()
    return {"status": "success", "message": "Exchange keys vaulted"}

@app.post("/start-bot/{user_id}")
async def start_bot(user_id: int, db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or not user.vault:
        raise HTTPException(status_code=404, detail="API keys not found")
    
    redis = await get_redis()
    await redis.enqueue_job('run_bot_task', user_id, _job_id=f"bot_user_{user_id}")
    return {"status": "success", "message": f"Bot queued for user {user_id}"}

@app.post("/stop-bot/{user_id}")
async def stop_bot(user_id: int):
    redis = await get_redis()
    job_id = f"bot_user_{user_id}"
    job = await redis.get_job(job_id)
    if job:
        await job.abort()
        return {"status": "success", "message": f"Shutdown signal sent"}
    return {"status": "error", "message": "No active bot found"}