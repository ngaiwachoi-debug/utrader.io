import asyncio
import contextlib
import os
from datetime import datetime

from arq.connections import RedisSettings

from database import SessionLocal
import models
from bot_engine import PortfolioManager
from dotenv import load_dotenv


load_dotenv()


PLAN_CONFIG = {
    "trial": {"limit": 250_000.0, "sleep_minutes": 3},
    "pro": {"limit": 50_000.0, "sleep_minutes": 30},
    "expert": {"limit": 250_000.0, "sleep_minutes": 3},
    "guru": {"limit": 1_500_000.0, "sleep_minutes": 1},
}


async def run_bot_task(ctx, user_id: int):
    """
    ARQ Background Task for a single user.

    Enforces:
    - Subscription tiers (limits + rebalance interval)
    - Kill switch based on pro_expiry
    """
    print(f"[{ctx['job_id']}] 🚀 Booting Lending Engine for User {user_id}...")

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user or not user.vault:
            print(f"[ERROR] No API keys found for User {user_id}")
            return

        # Initialize plan config on each start (in case plan changed)
        tier = (user.plan_tier or "trial").lower()
        cfg = PLAN_CONFIG.get(tier, PLAN_CONFIG["trial"])
        user.lending_limit = cfg["limit"]
        user.rebalance_interval = cfg["sleep_minutes"]
        db.commit()

        vault = user.vault
        keys = vault.get_keys()

        manager = PortfolioManager(
            user_id=user_id,
            api_key=keys["bfx_key"],
            api_secret=keys["bfx_secret"],
            gemini_key=keys.get("gemini_key", ""),
            redis_pool=ctx["redis"],
        )

        # Launch portfolio engines in the background
        engine_task = asyncio.create_task(manager.scan_and_launch())

        # Kill-switch loop – periodically checks expiry and cancels engines if needed.
        try:
            while True:
                now = datetime.utcnow()
                if user.pro_expiry and user.pro_expiry < now:
                    print(f"[KILL] User {user_id} subscription expired. Cancelling all activity.")
                    user.status = "expired"
                    db.commit()
                    engine_task.cancel()
                    break

                # Sleep according to tier config, then refresh user record
                await asyncio.sleep(user.rebalance_interval * 60)
                db.expire(user)
                user = db.query(models.User).filter(models.User.id == user_id).first()
        finally:
            with contextlib.suppress(Exception):
                await engine_task

    except asyncio.CancelledError:
        print(f"[SHUTDOWN] Task for User {user_id} was cancelled gracefully.")
    except Exception as e:
        print(f"[CRITICAL] Worker failed for User {user_id}: {e}")
    finally:
        db.close()
        print(f"[INFO] Cleanup complete for User {user_id}")


REDIS_URL = os.getenv("REDIS_URL")


class WorkerSettings:
    functions = [run_bot_task]

    if REDIS_URL:
        redis_settings = RedisSettings.from_dsn(REDIS_URL)
    else:
        redis_settings = RedisSettings()

    job_timeout = None
    queue_name = "arq:queue"
    health_check_interval = 30