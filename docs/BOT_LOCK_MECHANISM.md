# Bot Lock Mechanism

## Overview

The bot uses a **Redis lock** (`bot_run_lock:{user_id}`) to prevent multiple concurrent bot runs for the same user. This is intentional and prevents:
- Race conditions
- Duplicate orders
- Resource conflicts
- API rate limit issues

## Lock Details

- **Key format**: `bot_run_lock:{user_id}`
- **TTL**: 90 seconds
- **Renewal interval**: Every 30 seconds while bot is running
- **Implementation**: Redis `SET` with `NX` (only set if not exists) and `EX` (expiration)

## Lock Lifecycle

1. **Acquisition**: When a bot task starts, it tries to acquire the lock
   - If lock exists → Task exits with: "Another run for this user is active; exiting."
   - If lock doesn't exist → Task acquires lock and starts bot

2. **Renewal**: While bot is running, the lock is renewed every 30 seconds
   - Ensures lock doesn't expire during long-running bot sessions
   - If renewal fails, bot continues but lock may expire

3. **Release**: Lock is released when:
   - Bot task completes normally
   - Bot task is cancelled
   - Lock TTL expires (90 seconds after last renewal)

## Stale Locks

If the bot crashes or the worker is killed unexpectedly, the lock may become stale:
- Lock will expire automatically after 90 seconds (if not renewed)
- Or restart the worker/backend services to clear stale locks
- Or manually clear using: `python scripts/clear_bot_lock.py {user_id} --force`

## Clearing Locks

### Option 1: Wait for TTL (Recommended)
- Lock expires automatically after 90 seconds
- No action needed

### Option 2: Restart Worker/Backend
- Restarting the worker or backend services will clear stale locks
- Use: `cd scripts; .\restart_all_servers.ps1`

### Option 3: Manual Clear (Use with caution)
```bash
python scripts/clear_bot_lock.py 2 --force
```
**Warning**: Only clear if you're certain the bot is not running!

## Related Files

- `worker.py`: Lock implementation (lines 37-39, 133-176)
- `scripts/clear_bot_lock.py`: Script to manually clear locks
- `scripts/restart_all_servers.ps1`: Restart services to clear stale locks

## Notes

- **The lock will NOT expire while bot is running** - it's renewed every 30 seconds
- **The lock WILL expire** if bot crashes (90 seconds after last renewal)
- **Restarting services** is the safest way to clear stale locks
- **Manual clearing** should only be done if you're sure the bot is stopped
