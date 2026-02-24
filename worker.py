import asyncio
import os
from arq import worker
from arq.connections import RedisSettings
from database import SessionLocal
import models
import security
from bot_engine import WallStreet_Omni_FullEngine, PortfolioManager
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def run_bot_task(ctx, user_id: int):
    """
    ARQ Background Task: Decrypts keys and starts the lending loop.
    Now passes the Redis context to enable the Live Dashboard Heartbeat.
    """
    print(f"[{ctx['job_id']}] 🚀 Booting Lending Engine for User {user_id}...")
    
    db = SessionLocal()
    try:
        # 1. Fetch user vault from Neon
        vault = db.query(models.APIKeyVault).filter(models.APIKeyVault.user_id == user_id).first()
        if not vault:
            print(f"[ERROR] No API keys found in Neon for User {user_id}")
            return

        # 2. Decrypt keys using our security module
        keys = vault.get_keys()
        
        # 3. Launch the Portfolio Manager
        # 🟢 CRITICAL: We pass ctx['redis'] so the bot can write live stats to the dashboard
        manager = PortfolioManager(
            user_id=user_id,
            api_key=keys['bfx_key'],
            api_secret=keys['bfx_secret'],
            gemini_key=keys['gemini_key'],
            redis_pool=ctx['redis'] 
        )
        
        # 4. Start the infinite lending loop
        # This will now broadcast WAROC and Loaned amounts to Redis every 60 seconds
        await manager.scan_and_launch()

    except asyncio.CancelledError:
        print(f"[SHUTDOWN] Task for User {user_id} was cancelled gracefully.")
    except Exception as e:
        print(f"[CRITICAL] Worker failed for User {user_id}: {e}")
    finally:
        db.close()
        print(f"[INFO] Cleanup complete for User {user_id}")

# --- ARQ Configuration ---
REDIS_URL = os.getenv("REDIS_URL")

class WorkerSettings:
    functions = [run_bot_task]
    
    # Initialization for Upstash/Redis
    if REDIS_URL:
        redis_settings = RedisSettings.from_dsn(REDIS_URL)
    else:
        redis_settings = RedisSettings()
        
    # --- THE "IMMORTAL" SETTINGS ---
    # job_timeout=None prevents ARQ from killing the bot after 5 minutes
    job_timeout = None 
    queue_name = 'arq:queue'
    health_check_interval = 30