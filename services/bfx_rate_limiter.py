"""
Global IP-level rate limiter for Bitfinex REST API **and** WebSocket connections.

REST:  Bitfinex enforces 10-90 requests/min per endpoint per IP.
WS:    Bitfinex allows max 5 new WS connections per 15 seconds per IP.

When all bots + scheduler run on the same server, every outgoing request
shares the same IP. This module provides token-bucket limiters that all
Bitfinex callers must acquire before making a request or opening a connection.

Designed for a single-process deployment (uvicorn + ARQ worker in same
event loop or separate processes sharing nothing). Each process gets its
own bucket — for a 2-process setup (main + worker), set BFX_RATE_LIMIT
to half the target (e.g. 40 for a 80/min total).

Usage:
    from services.bfx_rate_limiter import bfx_acquire, bfx_acquire_sync, ws_conn_acquire

    # async REST (bot_engine, main.py scheduler)
    await bfx_acquire()
    result = await do_bitfinex_request(...)

    # sync REST (bitfinex_service._post_sync)
    bfx_acquire_sync()
    result = requests.post(...)

    # async WS connection (worker.py before opening auth WS)
    await ws_conn_acquire()
    ws = await websockets.connect(...)
"""
import asyncio
import os
import threading
import time

# ---------------------------------------------------------------------------
# REST rate limiter
# ---------------------------------------------------------------------------

_MAX_TOKENS = int(os.getenv("BFX_RATE_LIMIT", "45"))
_REFILL_INTERVAL = 1.0  # refill 1 token per this many seconds
_REFILL_RATE = _MAX_TOKENS / 60.0  # tokens per second to reach MAX in 60s

# --- Async limiter (for bot_engine, main.py schedulers) ---
_async_tokens: float = float(_MAX_TOKENS)
_async_last_refill: float = time.monotonic()
_async_lock = asyncio.Lock()


async def bfx_acquire(tokens: int = 1) -> None:
    """Wait until a rate-limit token is available, then consume it."""
    global _async_tokens, _async_last_refill
    while True:
        async with _async_lock:
            now = time.monotonic()
            elapsed = now - _async_last_refill
            _async_tokens = min(_MAX_TOKENS, _async_tokens + elapsed * _REFILL_RATE)
            _async_last_refill = now
            if _async_tokens >= tokens:
                _async_tokens -= tokens
                return
        await asyncio.sleep(0.1)


# --- Sync limiter (for bitfinex_service._post_sync via run_in_executor) ---
_sync_tokens: float = float(_MAX_TOKENS)
_sync_last_refill: float = time.monotonic()
_sync_lock = threading.Lock()


def bfx_acquire_sync(tokens: int = 1) -> None:
    """Blocking wait until a rate-limit token is available (thread-safe)."""
    global _sync_tokens, _sync_last_refill
    while True:
        with _sync_lock:
            now = time.monotonic()
            elapsed = now - _sync_last_refill
            _sync_tokens = min(_MAX_TOKENS, _sync_tokens + elapsed * _REFILL_RATE)
            _sync_last_refill = now
            if _sync_tokens >= tokens:
                _sync_tokens -= tokens
                return
        time.sleep(0.1)


# ---------------------------------------------------------------------------
# WebSocket connection rate limiter  (4 new connections per 15 seconds)
# ---------------------------------------------------------------------------
# Bitfinex allows 5 per 15s per IP; we use 4 to leave 1 slot headroom for
# reconnections or other tools.

_WS_MAX_TOKENS = int(os.getenv("BFX_WS_CONN_LIMIT", "4"))
_WS_WINDOW_SEC = 15.0
_WS_REFILL_RATE = _WS_MAX_TOKENS / _WS_WINDOW_SEC  # tokens per second

_ws_tokens: float = float(_WS_MAX_TOKENS)
_ws_last_refill: float = time.monotonic()
_ws_lock = asyncio.Lock()


async def ws_conn_acquire(tokens: int = 1) -> None:
    """Wait until a WS-connection rate-limit slot is available."""
    global _ws_tokens, _ws_last_refill
    while True:
        async with _ws_lock:
            now = time.monotonic()
            elapsed = now - _ws_last_refill
            _ws_tokens = min(_WS_MAX_TOKENS, _ws_tokens + elapsed * _WS_REFILL_RATE)
            _ws_last_refill = now
            if _ws_tokens >= tokens:
                _ws_tokens -= tokens
                return
        await asyncio.sleep(0.5)
