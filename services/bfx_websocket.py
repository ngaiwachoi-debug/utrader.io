"""
Authenticated Bitfinex WebSocket state manager for the bot engine.

Maintains real-time in-memory mirrors of wallets, funding credits, and
funding offers.  Exposes write helpers (submit_offer, cancel_offer) that
send input messages over the WS and wait for the notification response.

One instance per user / API-key.  All currency engines for that user share
the same connection and read from the shared state dicts.

Connection lifecycle:
    Connecting → Authenticating → Ready ⇄ Reconnecting → Closed
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Callable

import websockets

from services.bitfinex_nonce import get_next_nonce
from services.bfx_rate_limiter import ws_conn_acquire

logger = logging.getLogger(__name__)

WS_URL = "wss://api.bitfinex.com/ws/2"

_BACKOFF_INITIAL = 5.0
_BACKOFF_MAX = 60.0
_AUTH_TIMEOUT = 15.0
_SNAPSHOT_TIMEOUT = 20.0
_WRITE_ACK_TIMEOUT = 10.0
_PING_INTERVAL = 25.0
_PING_TIMEOUT = 10.0


class BfxWebSocketState:
    """Per-user authenticated WebSocket connection that mirrors Bitfinex state."""

    def __init__(
        self,
        user_id: int,
        api_key: str,
        api_secret: str,
        redis_pool=None,
        log_fn: Callable[[str], None] | None = None,
    ):
        self.user_id = user_id
        self._api_key = api_key
        self._api_secret = api_secret
        self._redis_pool = redis_pool
        self._log_fn = log_fn or (lambda m: logger.info(m))

        # In-memory mirrors  — all keyed/structured exactly as Bitfinex sends them
        # wallets: list of [WALLET_TYPE, CURRENCY, BALANCE, UNSETTLED, BALANCE_AVAILABLE, ...]
        self._wallets: list[list] = []
        # funding_credits: {symbol: [row, ...]}  row = Bitfinex fcs array
        self._funding_credits: dict[str, list[list]] = {}
        # funding_offers:   {symbol: [row, ...]}  row = Bitfinex fos array
        self._funding_offers: dict[str, list[list]] = {}

        # Channel mapping:  chan_id → channel_type ("wallet" | "trades" | ...)
        self._chan_map: dict[int, str] = {}

        # Write-acknowledgement: single pending future (offers are submitted sequentially)
        self._pending_write: asyncio.Future | None = None
        self._write_lock = asyncio.Lock()

        # Connection state
        self._ws: Any = None
        self._ready = asyncio.Event()
        self._closed = False
        self._recv_task: asyncio.Task | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._auth_ok = asyncio.Event()
        self._snapshots_received = asyncio.Event()
        self._expected_snapshots: set[str] = set()
        self._received_snapshots: set[str] = set()

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def is_ready(self) -> bool:
        return self._ready.is_set() and not self._closed

    # ------------------------------------------------------------------
    # Public read helpers — zero-copy from in-memory state
    # ------------------------------------------------------------------

    def get_wallets(self) -> list[list]:
        """Return current wallet snapshot (list of wallet rows)."""
        return list(self._wallets)

    def get_funding_credits(self, symbol: str) -> list[list]:
        """Return active funding credits for *symbol* (e.g. ``fUSD``)."""
        return list(self._funding_credits.get(symbol, []))

    def get_funding_offers(self, symbol: str) -> list[list]:
        """Return open funding offers for *symbol*."""
        return list(self._funding_offers.get(symbol, []))

    # ------------------------------------------------------------------
    # Public write helpers — send WS input, wait for notification
    # ------------------------------------------------------------------

    async def submit_offer(self, params: dict) -> dict | None:
        """Submit a funding offer via WS input message ``fon``.

        *params* should contain keys like ``type``, ``symbol``, ``amount``,
        ``rate``, ``period``, and optionally ``flags``.

        Returns the notification payload on success, or ``None`` on timeout /
        error.
        """
        if not self.is_ready:
            return None
        async with self._write_lock:
            msg = [
                0,
                "fon",
                None,
                {
                    "type": params.get("type", "LIMIT"),
                    "symbol": params["symbol"],
                    "amount": str(params["amount"]),
                    "rate": str(params["rate"]),
                    "period": int(params.get("period", 2)),
                    "flags": int(params.get("flags", 0)),
                },
            ]
            loop = asyncio.get_event_loop()
            fut: asyncio.Future = loop.create_future()
            self._pending_write = fut
            try:
                await self._ws.send(json.dumps(msg))
                result = await asyncio.wait_for(fut, timeout=_WRITE_ACK_TIMEOUT)
                return result
            except (asyncio.TimeoutError, Exception) as exc:
                self._log(f"[WS] submit_offer failed: {exc}")
                return None
            finally:
                self._pending_write = None

    async def cancel_offer(self, offer_id: int) -> dict | None:
        """Cancel a single funding offer by *offer_id* via WS ``foc``."""
        if not self.is_ready:
            return None
        async with self._write_lock:
            msg = [0, "foc", None, {"id": offer_id}]
            loop = asyncio.get_event_loop()
            fut: asyncio.Future = loop.create_future()
            self._pending_write = fut
            try:
                await self._ws.send(json.dumps(msg))
                result = await asyncio.wait_for(fut, timeout=_WRITE_ACK_TIMEOUT)
                return result
            except (asyncio.TimeoutError, Exception) as exc:
                self._log(f"[WS] cancel_offer id={offer_id} failed: {exc}")
                return None
            finally:
                self._pending_write = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Establish the authenticated WS connection and wait until ready."""
        if self._closed:
            raise RuntimeError("BfxWebSocketState already closed")
        await self._do_connect()

    async def close(self) -> None:
        """Gracefully tear down the connection."""
        self._closed = True
        self._ready.clear()
        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        if self._pending_write and not self._pending_write.done():
            self._pending_write.cancel()
        self._pending_write = None
        self._log("[WS] Connection closed.")

    async def wait_ready(self, timeout: float = 30.0) -> bool:
        """Block until the WS state is ready or *timeout* expires."""
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    # ------------------------------------------------------------------
    # Internal connection plumbing
    # ------------------------------------------------------------------

    async def _do_connect(self) -> None:
        """Open WS, authenticate, wait for snapshots, then mark ready."""
        self._auth_ok.clear()
        self._snapshots_received.clear()
        self._expected_snapshots = {"ws", "fcs", "fos"}
        self._received_snapshots = set()
        self._ready.clear()

        try:
            self._ws = await websockets.connect(
                WS_URL,
                ping_interval=_PING_INTERVAL,
                ping_timeout=_PING_TIMEOUT,
                close_timeout=5,
            )
        except Exception as exc:
            self._log(f"[WS] Connection failed: {exc}")
            self._schedule_reconnect()
            return

        self._recv_task = asyncio.create_task(self._recv_loop())

        # Send auth
        try:
            await self._send_auth()
        except Exception as exc:
            self._log(f"[WS] Auth send failed: {exc}")
            self._schedule_reconnect()
            return

        # Wait for auth confirmation
        try:
            await asyncio.wait_for(self._auth_ok.wait(), timeout=_AUTH_TIMEOUT)
        except asyncio.TimeoutError:
            self._log("[WS] Auth timeout — reconnecting")
            self._schedule_reconnect()
            return

        # Wait for initial snapshots
        try:
            await asyncio.wait_for(self._snapshots_received.wait(), timeout=_SNAPSHOT_TIMEOUT)
        except asyncio.TimeoutError:
            self._log("[WS] Snapshot timeout — marking ready with partial data")

        self._ready.set()
        self._log("[WS] Connection ready — real-time state active.")

    async def _send_auth(self) -> None:
        """Send authentication payload using HMAC-SHA384."""
        if self._redis_pool:
            nonce = await get_next_nonce(self._redis_pool, self._api_key)
        else:
            nonce = str(int(time.time() * 1000000))

        auth_payload = f"AUTH{nonce}"
        sig = hmac.new(
            self._api_secret.encode("utf-8"),
            auth_payload.encode("utf-8"),
            hashlib.sha384,
        ).hexdigest()

        auth_msg = {
            "event": "auth",
            "apiKey": self._api_key,
            "authSig": sig,
            "authNonce": nonce,
            "authPayload": auth_payload,
            "filter": ["funding", "wallet", "notify"],
        }
        await self._ws.send(json.dumps(auth_msg))

    # ------------------------------------------------------------------
    # Receive loop & message dispatch
    # ------------------------------------------------------------------

    async def _recv_loop(self) -> None:
        """Read messages from the WS and dispatch to handlers."""
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                if isinstance(msg, dict):
                    self._handle_event(msg)
                elif isinstance(msg, list):
                    self._handle_data(msg)
        except websockets.ConnectionClosed:
            self._log("[WS] Connection closed by server.")
        except asyncio.CancelledError:
            return
        except Exception as exc:
            self._log(f"[WS] recv_loop error: {exc}")
        finally:
            if not self._closed:
                self._ready.clear()
                self._schedule_reconnect()

    def _handle_event(self, msg: dict) -> None:
        """Handle top-level event messages (auth, info, subscribed, error)."""
        event = msg.get("event")
        if event == "auth":
            if msg.get("status") == "OK":
                self._log("[WS] Auth OK.")
                self._chan_map[0] = "auth"
                self._auth_ok.set()
            else:
                self._log(f"[WS] Auth FAILED: {msg}")
        elif event == "info":
            pass
        elif event == "error":
            self._log(f"[WS] Server error: {msg}")

    def _handle_data(self, msg: list) -> None:
        """Route channel data to the appropriate handler."""
        if len(msg) < 2:
            return
        chan_id = msg[0]
        payload = msg[1]

        # Heartbeat
        if payload == "hb":
            return

        # Channel 0 = account info (auth channel)
        if chan_id == 0:
            self._handle_account_message(msg)

    def _handle_account_message(self, msg: list) -> None:
        """Process authenticated account channel messages.

        msg format: [0, TYPE, payload]  or  [0, TYPE, [snapshot_rows...]]
        """
        if len(msg) < 3:
            return
        msg_type = msg[1]
        data = msg[2]

        # --- Wallet ---
        if msg_type == "ws":
            self._on_wallet_snapshot(data)
        elif msg_type == "wu":
            self._on_wallet_update(data)

        # --- Funding Credits ---
        elif msg_type == "fcs":
            self._on_funding_credits_snapshot(data)
        elif msg_type in ("fcn", "fcu"):
            self._on_funding_credit_update(data)
        elif msg_type == "fcc":
            self._on_funding_credit_close(data)

        # --- Funding Offers ---
        elif msg_type == "fos":
            self._on_funding_offers_snapshot(data)
        elif msg_type in ("fon", "fou"):
            self._on_funding_offer_update(data)
        elif msg_type == "foc":
            self._on_funding_offer_close(data)

        # --- Notifications (write ack) ---
        elif msg_type == "n":
            self._on_notification(data)

    # ------------------------------------------------------------------
    # Wallet handlers
    # ------------------------------------------------------------------

    def _on_wallet_snapshot(self, rows: list) -> None:
        self._wallets = list(rows) if isinstance(rows, list) else []
        self._mark_snapshot("ws")

    def _on_wallet_update(self, row: list) -> None:
        if not isinstance(row, list) or len(row) < 3:
            return
        w_type, w_curr = row[0], row[1]
        for i, w in enumerate(self._wallets):
            if isinstance(w, list) and len(w) >= 2 and w[0] == w_type and w[1] == w_curr:
                self._wallets[i] = row
                return
        self._wallets.append(row)

    # ------------------------------------------------------------------
    # Funding credit handlers
    # ------------------------------------------------------------------

    def _on_funding_credits_snapshot(self, rows: list) -> None:
        self._funding_credits.clear()
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, list) and len(row) > 1:
                    sym = row[1] if isinstance(row[1], str) else ""
                    self._funding_credits.setdefault(sym, []).append(row)
        self._mark_snapshot("fcs")

    def _on_funding_credit_update(self, row: list) -> None:
        if not isinstance(row, list) or len(row) < 2:
            return
        credit_id = row[0]
        sym = row[1] if isinstance(row[1], str) else ""
        credits = self._funding_credits.setdefault(sym, [])
        for i, c in enumerate(credits):
            if isinstance(c, list) and c[0] == credit_id:
                credits[i] = row
                return
        credits.append(row)

    def _on_funding_credit_close(self, row: list) -> None:
        if not isinstance(row, list) or len(row) < 2:
            return
        credit_id = row[0]
        sym = row[1] if isinstance(row[1], str) else ""
        credits = self._funding_credits.get(sym, [])
        self._funding_credits[sym] = [c for c in credits if not (isinstance(c, list) and c[0] == credit_id)]

    # ------------------------------------------------------------------
    # Funding offer handlers
    # ------------------------------------------------------------------

    def _on_funding_offers_snapshot(self, rows: list) -> None:
        self._funding_offers.clear()
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, list) and len(row) > 1:
                    sym = row[1] if isinstance(row[1], str) else ""
                    self._funding_offers.setdefault(sym, []).append(row)
        self._mark_snapshot("fos")

    def _on_funding_offer_update(self, row: list) -> None:
        if not isinstance(row, list) or len(row) < 2:
            return
        offer_id = row[0]
        sym = row[1] if isinstance(row[1], str) else ""
        offers = self._funding_offers.setdefault(sym, [])
        for i, o in enumerate(offers):
            if isinstance(o, list) and o[0] == offer_id:
                offers[i] = row
                return
        offers.append(row)

    def _on_funding_offer_close(self, row: list) -> None:
        if not isinstance(row, list) or len(row) < 2:
            return
        offer_id = row[0]
        sym = row[1] if isinstance(row[1], str) else ""
        offers = self._funding_offers.get(sym, [])
        self._funding_offers[sym] = [o for o in offers if not (isinstance(o, list) and o[0] == offer_id)]

    # ------------------------------------------------------------------
    # Notification handler (write acknowledgements)
    # ------------------------------------------------------------------

    def _on_notification(self, data: list) -> None:
        """Handle ``n`` messages — resolve the pending write future.

        Notification format: [MTS, TYPE, MSG_ID, null, [OFFER_DATA], CODE, STATUS, TEXT]
        Bitfinex funding offers do not carry a client-side cid, so we resolve
        the single pending future (writes are serialized by _write_lock).
        """
        if not isinstance(data, list) or len(data) < 5:
            return

        n_type = data[1]
        offer_data = data[4] if len(data) > 4 else None
        status = data[6] if len(data) > 6 else ""
        text_msg = data[7] if len(data) > 7 else ""

        result = {
            "type": n_type,
            "status": status,
            "text": text_msg,
            "data": offer_data,
        }

        # Resolve pending write future for fon-req / foc-req notifications
        if n_type in ("fon-req", "foc-req") and self._pending_write is not None:
            fut = self._pending_write
            if not fut.done():
                fut.set_result(result)
        elif status == "ERROR" and self._pending_write is not None:
            fut = self._pending_write
            if not fut.done():
                fut.set_result(result)
        elif status == "ERROR":
            self._log(f"[WS] Notification error: {text_msg} (type={n_type})")

        # Update local state mirrors from the notification
        if n_type in ("fon-req", "fon-new") and isinstance(offer_data, list):
            self._on_funding_offer_update(offer_data)
        elif n_type in ("foc-req",) and isinstance(offer_data, list):
            self._on_funding_offer_close(offer_data)

    # ------------------------------------------------------------------
    # Snapshot tracking
    # ------------------------------------------------------------------

    def _mark_snapshot(self, kind: str) -> None:
        self._received_snapshots.add(kind)
        if self._expected_snapshots.issubset(self._received_snapshots):
            self._snapshots_received.set()

    # ------------------------------------------------------------------
    # Reconnection
    # ------------------------------------------------------------------

    def _schedule_reconnect(self) -> None:
        if self._closed:
            return
        if self._reconnect_task and not self._reconnect_task.done():
            return
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        backoff = _BACKOFF_INITIAL
        while not self._closed:
            self._log(f"[WS] Reconnecting in {backoff:.0f}s ...")
            await asyncio.sleep(backoff)
            if self._closed:
                return
            try:
                await ws_conn_acquire()
                await self._do_connect()
                if self._ready.is_set():
                    return
            except Exception as exc:
                self._log(f"[WS] Reconnect attempt failed: {exc}")
            backoff = min(backoff * 2, _BACKOFF_MAX)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log(self, msg: str) -> None:
        full = f"[User {self.user_id}] {msg}"
        self._log_fn(full)
