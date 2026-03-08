import asyncio
import contextlib
import os
import traceback
from datetime import datetime
from pathlib import Path

from arq.connections import RedisSettings
from sqlalchemy import text
from sqlalchemy.orm import joinedload

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

# One job per user at run time: Redis lock so a second run for same user exits without starting.
# Keep TTL short so stale locks clear quickly after crash/restart; renew periodically while owner is alive.
BOT_RUN_LOCK_PREFIX = "bot_run_lock:"
BOT_RUN_LOCK_TTL_SEC = 90
BOT_RUN_LOCK_RENEW_SEC = 30

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
    lock_acquired = False
    lock_key = None
    lock_val = None
    lock_renew_task = None
    try:
        user = db.query(models.User).options(joinedload(models.User.vault)).filter(models.User.id == user_id).first()
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

        # If user already clicked Stop (e.g. duplicate/queued job picked up after stop), exit without running
        if getattr(user, "bot_desired_state", None) == "stopped":
            await _term(redis, user_id, "Shutdown: bot already stopped (skipping).")
            try:
                user.bot_status = "stopped"
                db.commit()
            except Exception:
                db.rollback()
            return

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

        # One job per user: acquire Redis run lock before any Bitfinex/engine work; if another run holds it, exit
        job_id = ctx.get("job_id") or f"bot_user_{user_id}"
        lock_key = f"{BOT_RUN_LOCK_PREFIX}{user_id}"
        lock_val = job_id
        try:
            acquired = await redis.set(lock_key, lock_val, ex=BOT_RUN_LOCK_TTL_SEC, nx=True)
            if not acquired:
                msg = "Another run for this user is active; exiting. (Only one job per user.)"
                print(f"[{job_id}] User {user_id}: {msg}")
                await _term(redis, user_id, msg)
                return
            lock_acquired = True
            # Refresh TTL while this task owns the lock so long-running bots keep ownership.
            async def _renew_run_lock():
                while True:
                    await asyncio.sleep(BOT_RUN_LOCK_RENEW_SEC)
                    try:
                        current = await redis.get(lock_key)
                        cur_val = current.decode() if isinstance(current, bytes) else current
                        if current is None or cur_val != lock_val:
                            return
                        await redis.expire(lock_key, BOT_RUN_LOCK_TTL_SEC)
                    except Exception:
                        # Best-effort renewal; lock still has TTL and fail-safe checks on every start.
                        pass

            lock_renew_task = asyncio.create_task(_renew_run_lock())
        except Exception as e:
            # If SET failed (e.g. Redis error), check if lock exists = another run active; do not run
            print(f"[WARN] User {user_id} lock acquire failed: {e}; checking if another run holds lock.")
            try:
                existing = await redis.get(lock_key)
                if existing is not None:
                    msg = "Another run for this user is active; exiting. (Only one job per user.)"
                    print(f"[{job_id}] User {user_id}: {msg}")
                    await _term(redis, user_id, msg)
                    return
            except Exception:
                pass
            # Lock key missing and we couldn't set; skip this run to avoid 10114 from multiple runners
            msg = "Could not acquire run lock; skipping to avoid duplicate run. (Only one job per user.)"
            print(f"[{job_id}] User {user_id}: {msg}")
            await _term(redis, user_id, msg)
            return

        # State sync: DB bot_status so /bot-stats and UI show Running (we hold the lock now)
        try:
            user.bot_status = "running"
            db.commit()
        except Exception:
            db.rollback()

        await _term(redis, user_id, "Bot status: running. Launching portfolio manager...")

        vault = user.vault
        keys = vault.get_keys()

        log_lines: list[str] = []
        
        # Resolve nonce Redis URL to ensure worker and API use same stream
        nonce_url = (os.getenv("NONCE_REDIS_URL") or os.getenv("REDIS_URL") or "").strip()
        if ".upstash.io" in nonce_url and nonce_url.startswith("redis://"):
            nonce_url = nonce_url.replace("redis://", "rediss://", 1)
        queue_url = (os.getenv("REDIS_URL") or "").strip()
        if ".upstash.io" in queue_url and queue_url.startswith("redis://"):
            queue_url = queue_url.replace("redis://", "rediss://", 1)
        if not nonce_url or nonce_url == queue_url:
            nonce_pool = ctx.get("redis")
        else:
            try:
                from arq.connections import create_pool
                nonce_settings = RedisSettings.from_dsn(nonce_url)
                nonce_pool = await create_pool(nonce_settings)
            except Exception as e:
                print(f"[WARN] Failed to create dedicated nonce pool: {e}. Falling back to queue redis.")
                nonce_pool = ctx.get("redis")

        manager = PortfolioManager(
            user_id=user_id,
            api_key=keys["bfx_key"],
            api_secret=keys["bfx_secret"],
            gemini_key=keys.get("gemini_key", ""),
            redis_pool=nonce_pool,
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

        # Aggressive early flushes so dashboard shows progress quickly
        for delay in (2, 5, 10, 20):
            async def _flush_at(d=delay):
                await asyncio.sleep(d)
                await flush_terminal_logs()
            asyncio.create_task(_flush_at())

        # Periodic flush every 30s (balances Redis writes vs dashboard freshness)
        async def periodic_flush():
            while True:
                await asyncio.sleep(30)
                await flush_terminal_logs()
        asyncio.create_task(periodic_flush())

        # Kill-switch loop – token balance only.
        MAX_ENGINE_RESTARTS = 3
        engine_restart_count = 0
        loop_count = 0
        shutdown_requested_logged = [False]  # Only log "stop requested" once per task
        try:
            while True:
                # If scanner/engine task exited, attempt auto-restart unless user requested stop
                if engine_task.done():
                    try:
                        exc = engine_task.exception()
                    except asyncio.CancelledError:
                        exc = None

                    # Check if user requested stop before restarting
                    db.expire(user)
                    user = db.query(models.User).filter(models.User.id == user_id).first()
                    user_wants_stop = user and getattr(user, "bot_desired_state", None) == "stopped"

                    if user_wants_stop:
                        await _term(redis, user_id, "Shutdown: scanner exited and stop was requested.")
                        try:
                            user.bot_status = "stopped"
                            db.commit()
                        except Exception:
                            db.rollback()
                        break

                    if engine_restart_count >= MAX_ENGINE_RESTARTS:
                        err_msg = f"Shutdown: engine crashed {engine_restart_count} times. Stopping to prevent loop."
                        await _term(redis, user_id, err_msg)
                        print(f"[CRITICAL] User {user_id}: {err_msg}")
                        try:
                            user.bot_status = "stopped"
                            if hasattr(user, "bot_desired_state"):
                                user.bot_desired_state = "stopped"
                            db.commit()
                        except Exception:
                            db.rollback()
                        break

                    engine_restart_count += 1
                    reason = f"{type(exc).__name__}: {exc}" if exc else "exited cleanly"
                    restart_msg = f"Engine exited ({reason}). Auto-restarting ({engine_restart_count}/{MAX_ENGINE_RESTARTS})..."
                    await _term(redis, user_id, restart_msg)
                    print(f"[RESTART] User {user_id}: {restart_msg}")

                    await asyncio.sleep(5 * engine_restart_count)  # back-off: 5s, 10s, 15s

                    try:
                        manager = PortfolioManager(
                            user_id=user_id,
                            api_key=keys["bfx_key"],
                            api_secret=keys["bfx_secret"],
                            gemini_key=keys.get("gemini_key", ""),
                            redis_pool=nonce_pool,
                            log_lines=log_lines,
                        )
                        engine_task = asyncio.create_task(manager.scan_and_launch())
                        await _term(redis, user_id, f"Engine restarted successfully (attempt {engine_restart_count}).")
                    except Exception as re_err:
                        await _term(redis, user_id, f"Engine restart failed: {type(re_err).__name__}: {re_err}")
                        try:
                            user.bot_status = "stopped"
                            if hasattr(user, "bot_desired_state"):
                                user.bot_desired_state = "stopped"
                            db.commit()
                        except Exception:
                            db.rollback()
                        break
                    continue

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
                # Sleep in 5s chunks so Stop Bot (job.abort) can cancel within ~5s instead of after up to 40 min.
                # Also check DB each chunk: if user clicked Stop, bot_desired_state is set and we exit even if abort didn't reach us.
                sleep_sec = user.rebalance_interval * 60
                for _ in range(max(1, sleep_sec // 5)):
                    await asyncio.sleep(5)
                    db.expire(user)
                    user = db.query(models.User).filter(models.User.id == user_id).first()
                    if user and getattr(user, "bot_desired_state", None) == "stopped":
                        if not shutdown_requested_logged[0]:
                            shutdown_requested_logged[0] = True
                            await _term(redis, user_id, "Shutdown: stop requested from dashboard.")
                        print(f"[SHUTDOWN] User {user_id} bot_desired_state=stopped. Exiting.")
                        user.bot_status = "stopped"
                        db.commit()
                        engine_task.cancel()
                        raise asyncio.CancelledError()
                db.expire(user)
                user = db.query(models.User).filter(models.User.id == user_id).first()
        finally:
            await flush_terminal_logs()
            with contextlib.suppress(Exception):
                await engine_task

    except asyncio.CancelledError:
        # Normal stop (user clicked Stop or job aborted): set both so desired state stays in sync
        print(f"[SHUTDOWN] User {user_id} job cancelled or aborted (CancelledError). Exiting normally.")
        print(f"[SHUTDOWN] Task for User {user_id} was cancelled gracefully.")
        try:
            redis_term = ctx.get("redis")
            if redis_term:
                await _term(redis_term, user_id, "Shutdown: task cancelled.")
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
        traceback.print_exc()
        try:
            await _term(ctx.get("redis"), user_id, f"Failure: {type(e).__name__}: {e}")
        except Exception:
            pass
        # Auto re-enqueue if user still wants bot running (desired_state != stopped).
        # Release lock first so the new job can acquire it.
        try:
            r = ctx.get("redis")
            if lock_acquired and r and lock_key and lock_val:
                current = await r.get(lock_key)
                cur_val = current.decode() if isinstance(current, bytes) else current
                if current is not None and cur_val == lock_val:
                    await r.delete(lock_key)
                lock_acquired = False  # prevent double-release in finally
        except Exception:
            pass
        try:
            if db is not None:
                u = db.query(models.User).filter(models.User.id == user_id).first()
                if u and getattr(u, "bot_desired_state", None) != "stopped":
                    r = ctx.get("redis")
                    if r:
                        await asyncio.sleep(10)
                        job_id = f"bot_user_{user_id}"
                        await r.enqueue_job("run_bot_task", user_id, _job_id=job_id)
                        await _term(r, user_id, "Auto re-enqueued after crash. Restarting in ~10s...")
                        print(f"[AUTO-RESTART] User {user_id} bot re-enqueued after crash.")
        except Exception as re_err:
            print(f"[WARN] User {user_id} auto re-enqueue failed: {re_err}")
    finally:
        # Stop lock renewer first so it can't race with lock release.
        try:
            if lock_renew_task is not None:
                lock_renew_task.cancel()
                with contextlib.suppress(Exception):
                    await lock_renew_task
        except Exception:
            pass
        # Release per-user run lock and clean stale ARQ metadata so the same job_id can be re-enqueued
        try:
            r = ctx.get("redis")
            if lock_acquired and r and lock_key and lock_val:
                current = await r.get(lock_key)
                cur_val = current.decode() if isinstance(current, bytes) else current
                if current is not None and cur_val == lock_val:
                    await r.delete(lock_key)
            if r:
                job_id = ctx.get("job_id") or f"bot_user_{user_id}"
                await r.delete(
                    f"arq:retry:{job_id}",
                    f"arq:in-progress:{job_id}",
                )
        except Exception as e:
            print(f"[WARN] User {user_id} lock/arq cleanup failed: {e}")
        # Only lock owner may force final stopped state; non-owner duplicate jobs must not overwrite DB state.
        try:
            if lock_acquired and db is not None:
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
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")
if ".upstash.io" in REDIS_URL and REDIS_URL.startswith("redis://"):
    REDIS_URL = REDIS_URL.replace("redis://", "rediss://", 1)


class WorkerSettings:
    functions = [run_bot_task]

    if REDIS_URL:
        redis_settings = RedisSettings.from_dsn(REDIS_URL)
    else:
        redis_settings = RedisSettings()

    job_timeout = 3600 * 24 * 7  # 7 days – bot runs indefinitely; ARQ must not kill it
    queue_name = "arq:queue"
    health_check_interval = 30
    allow_abort_jobs = True  # required for Stop Bot to cancel running task
    # Don't store job result so the same job_id can be enqueued again after the bot stops
    keep_result = 0
    max_tries = 1  # avoid retries so only one nonce stream per start (prevents 10114 on retry)