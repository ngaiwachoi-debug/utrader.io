"""
IQM multi-tenant runner: single process that runs the Shared Market Oracle and
PortfolioOrchestrator tasks for all users with bot_desired_state=running and tokens > 0.
Uses semaphore(20) and 0.1s stagger. Requires REDIS_URL in .env.
"""
import asyncio
import os
import signal
from pathlib import Path

from sqlalchemy.orm import joinedload
from database import SessionLocal
import models
from services import token_ledger_service as token_ledger_svc
from services.shared_oracle import GlobalMarketOracle, get_oracle_snapshot
from bot_engine import PortfolioOrchestrator

# Load .env from project root
_path = Path(__file__).resolve().parent / ".env"
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_path)
except ImportError:
    pass

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
RECONCILE_INTERVAL_SEC = 60
ORCHESTRATOR_SEMAPHORE = 20
STAGGER_SEC = 0.1


def get_active_bot_users():
    """
    Return list of user records (dicts) with id, api_key, api_secret, gemini_key, plan_tier
    for users where bot_desired_state == 'running', vault present, and tokens_remaining > 0.
    """
    db = SessionLocal()
    try:
        users = (
            db.query(models.User)
            .filter(models.User.bot_desired_state == "running")
            .join(models.APIVault, models.User.id == models.APIVault.user_id)
            .options(joinedload(models.User.vault))
            .all()
        )
        out = []
        for user in users:
            if not user.vault or not getattr(user.vault, "encrypted_key", None):
                continue
            tokens = token_ledger_svc.get_tokens_remaining(db, user.id)
            if tokens <= 0:
                continue
            keys = user.vault.get_keys()
            out.append({
                "id": user.id,
                "api_key": keys.get("bfx_key") or "",
                "api_secret": keys.get("bfx_secret") or "",
                "gemini_key": (keys.get("gemini_key") or "").strip(),
                "plan_tier": getattr(user, "plan_tier", None) or "trial",
            })
        return out
    finally:
        db.close()


async def _run_with_sem(sem, user_record, redis_pool):
    """Run one orchestrator under the semaphore; on cancel set bot_status=stopped."""
    async with sem:
        orch = PortfolioOrchestrator(user_record, redis_pool)
        try:
            await orch.scan_and_launch()
        except asyncio.CancelledError:
            db = SessionLocal()
            try:
                u = db.query(models.User).filter(models.User.id == orch.user_id).first()
                if u and hasattr(u, "bot_status"):
                    u.bot_status = "stopped"
                    db.commit()
            except Exception:
                if db:
                    db.rollback()
            finally:
                if db:
                    db.close()
            raise


async def main():
    try:
        from redis.asyncio import Redis
        redis = Redis.from_url(REDIS_URL, decode_responses=True)
        await redis.ping()
    except Exception as e:
        print(f"[FATAL] Redis connection failed: {e}. Set REDIS_URL in .env.")
        return

    oracle = GlobalMarketOracle(redis)
    oracle_task = asyncio.create_task(oracle.run_forever())
    sem = asyncio.Semaphore(ORCHESTRATOR_SEMAPHORE)
    running: dict[int, asyncio.Task] = {}
    shutdown_requested = False

    def shutdown():
        nonlocal shutdown_requested
        shutdown_requested = True
        for t in list(running.values()):
            t.cancel()
        oracle_task.cancel()

    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, shutdown)
    except NotImplementedError:
        # Windows: add_signal_handler not supported; Ctrl+C will raise KeyboardInterrupt in main()
        pass

    print("[IQM] Oracle started. Reconciling active users every", RECONCILE_INTERVAL_SEC, "s.")
    while not shutdown_requested:
        try:
            active = get_active_bot_users()
            active_ids = {r["id"] for r in active}
            # Cancel tasks for users no longer active
            for uid in list(running.keys()):
                if uid not in active_ids:
                    running[uid].cancel()
                    del running[uid]
            # Start new orchestrators with stagger
            for i, rec in enumerate(active):
                if rec["id"] in running:
                    continue
                await asyncio.sleep(STAGGER_SEC)
                task = asyncio.create_task(_run_with_sem(sem, rec, redis))
                running[rec["id"]] = task
            # Clean finished/cancelled from running
            for uid in list(running.keys()):
                if running[uid].done():
                    try:
                        running[uid].result()
                    except (asyncio.CancelledError, Exception):
                        pass
                    del running[uid]
        except asyncio.CancelledError:
            break
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[IQM] Reconcile error: {e}")
        if shutdown_requested:
            break
        await asyncio.sleep(RECONCILE_INTERVAL_SEC)

    if not oracle_task.done():
        oracle_task.cancel()
    try:
        await oracle_task
    except asyncio.CancelledError:
        pass
    for t in running.values():
        t.cancel()
    await asyncio.gather(*running.values(), return_exceptions=True)
    await redis.aclose()
    print("[IQM] Shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[IQM] Interrupted.")
