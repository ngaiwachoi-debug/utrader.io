import asyncio
import contextlib
import os
from datetime import datetime
from pathlib import Path

from arq.connections import RedisSettings
from sqlalchemy import text

from database import SessionLocal
import models
from bot_engine import PortfolioManager
from dotenv import load_dotenv

# Load .env from project root (same as database.py) so worker always uses same DB/Redis
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_env_path)


def _tokens_remaining_for_user(db, user_id: int) -> float:
    """Token balance for bot gate: user_token_balance.tokens_remaining from DB (direct check)."""
    try:
        from services import token_ledger_service as token_ledger_svc
        return token_ledger_svc.get_tokens_remaining(db, user_id)
    except Exception as e:
        print(f"[WARN] Worker token read for user {user_id} failed: {e}")
    return 0.0


# Terminal logs: keep last N lines per user, key expires after TTL (cost-effective for many users)
TERMINAL_MAX_LINES = 100
TERMINAL_KEY_TTL_SEC = 3600  # 1 hour

async def _term(redis, user_id: int, msg: str) -> None:
    """Push one timestamped line to terminal_logs for the user (so Terminal tab shows it)."""
    if not redis:
        return
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    try:
        key = f"terminal_logs:{user_id}"
        await redis.rpush(key, line)
        await redis.ltrim(key, -TERMINAL_MAX_LINES, -1)
        await redis.expire(key, TERMINAL_KEY_TTL_SEC)
    except Exception:
        pass


# Tier rebalance intervals (minutes): Trial/Free 40m, Pro 20m, AI Ultra 10m, Whales 3m.
PLAN_CONFIG = {
    "trial": {"sleep_minutes": 40},
    "free": {"sleep_minutes": 40},
    "pro": {"sleep_minutes": 20},
    "ai_ultra": {"sleep_minutes": 10},
    "whales": {"sleep_minutes": 3},
}
TOKENS_PER_USDT_GROSS = 10
PLAN_TOKEN_CREDITS = {"trial": 100, "free": 100, "pro": 1500, "ai_ultra": 9000, "whales": 40000}


async def run_bot_task(ctx, user_id: int):
    """
    ARQ Background Task for a single user.

    Enforces:
    - Subscription tiers (limits + rebalance interval)
    - Kill switch based on token balance only
    """
    print(f"[{ctx['job_id']}] Booting Lending Engine for User {user_id}...")

    redis = ctx.get("redis")
    key = f"terminal_logs:{user_id}"

    await _term(redis, user_id, "Job picked up from queue. Loading...")

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user or not user.vault:
            print(f"[ERROR] No API keys found for User {user_id}")
            await _term(redis, user_id, "Failure: No API keys found. Bot not started.")
            if user and hasattr(user, "bot_status"):
                try:
                    user.bot_status = "stopped"
                    db.commit()
                except Exception:
                    db.rollback()
            return

        # Initialize plan config on each start (in case plan changed); normalize tier (e.g. "ai ultra" -> ai_ultra)
        raw_tier = (user.plan_tier or "trial").strip().lower()
        tier = "ai_ultra" if raw_tier in ("ai ultra", "ai_ultra") else raw_tier.replace(" ", "_")
        cfg = PLAN_CONFIG.get(tier, PLAN_CONFIG["trial"])
        user.rebalance_interval = cfg["sleep_minutes"]
        db.commit()

        await _term(redis, user_id, "API keys found. Checking token balance...")

        # Token gate at start: run only when tokens_remaining > 0 (same as POST /start-bot)
        tokens_remaining = _tokens_remaining_for_user(db, user_id)
        print(f"[INFO] User {user_id} tokens_remaining={tokens_remaining} (from user_token_balance)")
        if tokens_remaining <= 0:
            await _term(redis, user_id, f"Failure: No tokens remaining (balance={tokens_remaining:.0f}). Bot not started.")
            user.bot_status = "stopped"
            db.commit()
            print(f"[INFO] User {user_id} tokens_remaining={tokens_remaining} (<=0). Bot not started.")
            return

        await _term(redis, user_id, f"Token balance OK ({tokens_remaining:.0f} tokens). Starting trading engine...")

        vault = user.vault
        keys = vault.get_keys()

        # State sync: DB bot_status so /bot-stats and UI show Running immediately
        try:
            user.bot_status = "running"
            db.commit()
        except Exception:
            db.rollback()

        await _term(redis, user_id, "Bot status: running. Launching portfolio manager...")

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
                await redis.ltrim(key, -TERMINAL_MAX_LINES, -1)
                await redis.expire(key, TERMINAL_KEY_TTL_SEC)
            del log_lines[:]

        # Launch portfolio engines in the background
        engine_task = asyncio.create_task(manager.scan_and_launch())

        await _term(redis, user_id, f"Trading terminal active. Rebalance every {user.rebalance_interval} min. Scanner starting...")

        # Flush after 2s so "[SCANNER] Initializing..." appears in terminal
        async def flush_after_2s():
            await asyncio.sleep(2)
            await flush_terminal_logs()
        asyncio.create_task(flush_after_2s())
        # Second flush at 5s to catch any further scanner output
        async def one_early_flush():
            await asyncio.sleep(5)
            await flush_terminal_logs()
        asyncio.create_task(one_early_flush())

        # Batch flush every 90s to limit Redis writes
        TERMINAL_FLUSH_INTERVAL_SEC = 90
        async def periodic_flush():
            while True:
                await asyncio.sleep(TERMINAL_FLUSH_INTERVAL_SEC)
                await flush_terminal_logs()
        asyncio.create_task(periodic_flush())

        # Kill-switch loop – token balance only.
        loop_count = 0
        try:
            while True:
                tokens_remaining = _tokens_remaining_for_user(db, user_id)
                if tokens_remaining <= 0:
                    await _term(redis, user_id, f"Failure: No tokens remaining (balance={tokens_remaining:.0f}). Stopping bot.")
                    print(f"[KILL] User {user_id} tokens_remaining={tokens_remaining} (<=0). Stopping bot.")
                    user.bot_status = "stopped"
                    db.commit()
                    engine_task.cancel()
                    break

                await flush_terminal_logs()
                loop_count += 1
                if loop_count == 1:
                    await _term(redis, user_id, f"Heartbeat: Bot running. Next rebalance in {user.rebalance_interval} min.")
                await asyncio.sleep(user.rebalance_interval * 60)
                db.expire(user)
                user = db.query(models.User).filter(models.User.id == user_id).first()
        finally:
            await flush_terminal_logs()
            with contextlib.suppress(Exception):
                await engine_task

    except asyncio.CancelledError:
        # Normal stop (user clicked Stop): set both so desired state stays in sync
        print(f"[SHUTDOWN] Task for User {user_id} was cancelled gracefully.")
        try:
            await _term(ctx.get("redis"), user_id, "Shutdown: task cancelled.")
        except Exception:
            pass
        try:
            if db is not None:
                u = db.query(models.User).filter(models.User.id == user_id).first()
                if u:
                    if hasattr(u, "bot_status"):
                        u.bot_status = "stopped"
                    if hasattr(u, "bot_desired_state"):
                        u.bot_desired_state = "stopped"
                    db.commit()
        except Exception:
            try:
                if db is not None:
                    db.rollback()
            except Exception:
                pass
    except Exception as e:
        print(f"[CRITICAL] Worker failed for User {user_id}: {e}")
        try:
            await _term(ctx.get("redis"), user_id, f"Failure: {type(e).__name__}: {e}")
        except Exception:
            pass
    finally:
        # Only set bot_status here (token exhaustion / crash). Normal stop sets both in CancelledError handler.
        try:
            if db is not None:
                u = db.query(models.User).filter(models.User.id == user_id).first()
                if u and hasattr(u, "bot_status"):
                    u.bot_status = "stopped"
                    db.commit()
        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
            print(f"[WARN] Worker finally: could not set bot_status=stopped for user {user_id}: {e}")
        try:
            if db is not None:
                db.close()
        except Exception:
            pass
        print(f"[INFO] Cleanup complete for User {user_id}")


# Migrated to NEW Upstash Redis; REDIS_URL from .env (rediss:// only, no old account references)
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