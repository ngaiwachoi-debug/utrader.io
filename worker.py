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


# Pro 20 USDT, AI Ultra 60 USDT, Whales 200 USDT. Token credits: 100 free, 1500, 9000, 40000.
PLAN_CONFIG = {
    "trial": {"limit": 250_000.0, "sleep_minutes": 30},
    "free": {"limit": 250_000.0, "sleep_minutes": 30},
    "pro": {"limit": 250_000.0, "sleep_minutes": 30},
    "ai_ultra": {"limit": 250_000.0, "sleep_minutes": 3},
    "whales": {"limit": 1_500_000.0, "sleep_minutes": 1},
}
TOKENS_PER_USDT_GROSS = 10
PLAN_TOKEN_CREDITS = {"trial": 100, "free": 100, "pro": 1500, "ai_ultra": 9000, "whales": 40000}


async def run_bot_task(ctx, user_id: int):
    """
    ARQ Background Task for a single user.

    Enforces:
    - Subscription tiers (limits + rebalance interval)
    - Kill switch based on pro_expiry
    """
    print(f"[{ctx['job_id']}] Booting Lending Engine for User {user_id}...")

    # Push one line to Redis immediately so the Terminal tab shows output on next poll
    redis = ctx.get("redis")
    if redis:
        key = f"terminal_logs:{user_id}"
        boot_msg = f"[{datetime.now().strftime('%H:%M:%S')}] Bot started for user {user_id}. Loading..."
        await redis.rpush(key, boot_msg)
        await redis.ltrim(key, -500, -1)

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

        # Balance check right before bot executes (user-end requested). Bypass on low token balance for now.
        snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
        gross = float(snap.gross_profit_usd) if snap and snap.gross_profit_usd is not None else 0.0
        tier = (user.plan_tier or "trial").lower()
        initial = PLAN_TOKEN_CREDITS.get(tier, 100)
        token_row = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
        purchased = float(token_row.purchased_tokens) if token_row and token_row.purchased_tokens is not None else 0.0
        tokens_remaining = max(0.0, float(initial) + purchased - int(gross * TOKENS_PER_USDT_GROSS))
        if tokens_remaining < 0.1:
            print(f"[INFO] User {user_id} token balance below 0.1 (bypassing). Bot will run.")

        vault = user.vault
        keys = vault.get_keys()

        log_lines: list[str] = []
        manager = PortfolioManager(
            user_id=user_id,
            api_key=keys["bfx_key"],
            api_secret=keys["bfx_secret"],
            gemini_key=keys.get("gemini_key", ""),
            redis_pool=ctx["redis"],
            log_lines=log_lines,
        )

        async def flush_terminal_logs():
            if not log_lines:
                return
            redis = ctx.get("redis")
            if redis:
                key = f"terminal_logs:{user_id}"
                for line in log_lines:
                    await redis.rpush(key, line)
                await redis.ltrim(key, -500, -1)
            del log_lines[:]

        # Launch portfolio engines in the background
        engine_task = asyncio.create_task(manager.scan_and_launch())

        # Push terminal logs to Redis early and often so the user's Terminal tab shows output quickly
        async def early_flushes():
            for delay in (1, 3, 10, 20):
                await asyncio.sleep(delay)
                await flush_terminal_logs()
        asyncio.create_task(early_flushes())

        # Kill-switch loop – token balance (and optional pro_expiry for paid plans).
        try:
            while True:
                now = datetime.utcnow()
                if user.pro_expiry and user.pro_expiry < now:
                    print(f"[KILL] User {user_id} subscription expired. Cancelling all activity.")
                    user.status = "expired"
                    db.commit()
                    engine_task.cancel()
                    break
                # Token balance check: bypass for now (product); log only when low
                snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
                gross = float(snap.gross_profit_usd) if snap and snap.gross_profit_usd is not None else 0.0
                tier = (user.plan_tier or "trial").lower()
                initial = PLAN_TOKEN_CREDITS.get(tier, 100)
                token_row = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
                purchased = float(token_row.purchased_tokens) if token_row and token_row.purchased_tokens is not None else 0.0
                tokens_remaining = max(0.0, float(initial) + purchased - int(gross * TOKENS_PER_USDT_GROSS))
                if tokens_remaining < 0.1:
                    # Bypass: do not stop bot for low balance for now
                    pass

                await flush_terminal_logs()
                await asyncio.sleep(user.rebalance_interval * 60)
                db.expire(user)
                user = db.query(models.User).filter(models.User.id == user_id).first()
        finally:
            await flush_terminal_logs()
            with contextlib.suppress(Exception):
                await engine_task

    except asyncio.CancelledError:
        print(f"[SHUTDOWN] Task for User {user_id} was cancelled gracefully.")
    except Exception as e:
        msg = str(e).lower()
        if "balance" in msg or "insufficient" in msg:
            print(f"[INFO] User {user_id} balance-related error (bypassing): {e}")
        else:
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
    allow_abort_jobs = True  # required for Stop Bot to cancel running task
    # Don't store job result so the same job_id can be enqueued again after the bot stops
    keep_result = 0