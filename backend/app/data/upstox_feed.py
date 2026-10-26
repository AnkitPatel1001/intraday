"""Upstox Market Data Feed V3 client (WebSocket + protobuf, LTPC mode).

One WebSocket connection streams last-traded prices for subscribed
instruments, so quote reads never hit the REST API (50 req/s cap -> no 429s).

Wire format (matches official Upstox SDK behavior):
- subscribe: JSON utf-8 sent as a *binary* frame
  {"guid": ..., "method": "sub", "data": {"instrumentKeys": [...], "mode": "ltpc"}}
- responses: protobuf-encoded FeedResponse
  (schema: assets.upstox.com/feed/market-data-feed/v1.1/MarketDataFeed.proto)

PAPER ONLY: this module subscribes to market data. It has no order,
portfolio, or account endpoints of any kind.
"""

from __future__ import annotations

import asyncio
import json
import logging
import struct
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

WS_URL = "wss://api.upstox.com/v3/feed/market-data-feed"
SUBSCRIBE_MODE = "ltpc"


# ---------------------------------------------------------------- protobuf

def _read_varint(buf: bytes, i: int) -> tuple[int, int]:
    shift = 0
    val = 0
    while True:
        if i >= len(buf):
            raise ValueError("truncated varint")
        b = buf[i]
        i += 1
        val |= (b & 0x7F) << shift
        if not b & 0x80:
            return val, i
        shift += 7
        if shift > 63:
            raise ValueError("varint too long")


def iter_fields(buf: bytes):
    """Yield (field_number, wire_type, payload_bytes_or_int)."""
    i = 0
    n = len(buf)
    while i < n:
        key, i = _read_varint(buf, i)
        field, wire = key >> 3, key & 7
        if wire == 0:  # varint
            val, i = _read_varint(buf, i)
            yield field, wire, val
        elif wire == 1:  # fixed64
            if i + 8 > n:
                raise ValueError("truncated fixed64")
            yield field, wire, buf[i:i + 8]
            i += 8
        elif wire == 2:  # length-delimited
            ln, i = _read_varint(buf, i)
            if i + ln > n:
                raise ValueError("truncated bytes")
            yield field, wire, buf[i:i + ln]
            i += ln
        elif wire == 5:  # fixed32
            if i + 4 > n:
                raise ValueError("truncated fixed32")
            yield field, wire, buf[i:i + 4]
            i += 4
        else:
            raise ValueError(f"unsupported wire type {wire}")


def _decode_ltpc(buf: bytes) -> dict:
    out: dict = {}
    for field, wire, val in iter_fields(buf):
        if field == 1 and wire == 1:
            out["ltp"] = struct.unpack("<d", val)[0]
        elif field == 2 and wire == 0:
            out["ltt"] = val
        elif field == 3 and wire == 0:
            out["ltq"] = val
        elif field == 4 and wire == 1:
            out["cp"] = struct.unpack("<d", val)[0]
    return out


def _decode_feed(buf: bytes) -> dict:
    """Decode the `Feed` oneof: prefer ltpc (field 1)."""
    for field, wire, val in iter_fields(buf):
        if field == 1 and wire == 2:
            return _decode_ltpc(val)
        # ff (full feed) and oc (option chain) ignored: we subscribe ltpc only
    return {}


def decode_feed_response(buf: bytes) -> dict:
    """Decode FeedResponse -> {"type": int, "feeds": {key: ltpc_dict}, "currentTs": int}."""
    feeds: dict[str, dict] = {}
    msg_type = 0
    current_ts = 0
    for field, wire, val in iter_fields(buf):
        if field == 1 and wire == 0:
            msg_type = val
        elif field == 2 and wire == 2:
            key = ""
            feed: dict = {}
            for f2, w2, v2 in iter_fields(val):
                if f2 == 1 and w2 == 2:
                    key = v2.decode("utf-8", "replace")
                elif f2 == 2 and w2 == 2:
                    feed = _decode_feed(v2)
            if key and feed:
                feeds[key] = feed
        elif field == 3 and wire == 0:
            current_ts = val
    return {"type": msg_type, "feeds": feeds, "currentTs": current_ts}


def build_subscribe_payload(instrument_keys: list[str],
                            mode: str = SUBSCRIBE_MODE,
                            guid: Optional[str] = None) -> bytes:
    """JSON subscribe request, utf-8 encoded (sent as binary frame)."""
    body = {
        "guid": guid or str(uuid.uuid4()),
        "method": "sub",
        "data": {"instrumentKeys": list(instrument_keys), "mode": mode},
    }
    return json.dumps(body).encode("utf-8")


# ---------------------------------------------------------------- feed

class UpstoxQuoteFeed:
    """Lazy, self-reconnecting LTPC feed with an in-memory price cache.

    get_cached() is synchronous and safe from any coroutine; the background
    task keeps the connection alive and re-subscribes after reconnects.
    """

    def __init__(self, token_getter, ws_url: str = WS_URL):
        self._token_getter = token_getter
        self.ws_url = ws_url
        self._cache: dict[str, tuple[float, float, int]] = {}  # key -> (ltp, cp, ts_ms)
        self._wanted: set[str] = set()
        self._subscribed: set[str] = set()
        self._task: Optional[asyncio.Task] = None
        self._stopping = False
        self.connected = False

    # -- public API -----------------------------------------------------

    def get_cached(self, instrument_key: str) -> Optional[tuple[float, float, int]]:
        return self._cache.get(instrument_key)

    async def ensure_started(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stopping = False
        self._task = asyncio.create_task(self._run(), name="upstox-quote-feed")

    async def subscribe(self, instrument_keys: list[str]) -> None:
        new = [k for k in instrument_keys if k not in self._wanted]
        self._wanted.update(instrument_keys)
        if new and self._conn is not None and self.connected:
            try:
                await self._conn.send(build_subscribe_payload(new))
                self._subscribed.update(new)
            except Exception:  # pragma: no cover - reconnect path handles it
                logger.debug("upstox ws subscribe failed; will resubscribe", exc_info=True)

    async def stop(self) -> None:
        self._stopping = True
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self.connected = False

    # -- internals ------------------------------------------------------

    _conn = None

    async def _run(self) -> None:
        import websockets

        backoff = 1.0
        while not self._stopping:
            try:
                token = self._token_getter()
                if not token:
                    raise RuntimeError("no upstox token configured")
                # websockets renamed extra_headers -> additional_headers in v14
                try:
                    conn = websockets.connect(
                        self.ws_url,
                        additional_headers={"Authorization": f"Bearer {token}"},
                        max_size=2**20,
                    )
                except TypeError:
                    conn = websockets.connect(
                        self.ws_url,
                        extra_headers={"Authorization": f"Bearer {token}"},
                        max_size=2**20,
                    )
                async with conn as ws:
                    self._conn = ws
                    self.connected = True
                    backoff = 1.0
                    self._subscribed.clear()
                    pending = sorted(self._wanted - self._subscribed)
                    if pending:
                        await ws.send(build_subscribe_payload(pending))
                        self._subscribed.update(pending)
                    async for message in ws:
                        if self._stopping:
                            break
                        if isinstance(message, (bytes, bytearray)):
                            try:
                                self._handle_message(bytes(message))
                            except ValueError:
                                logger.debug("upstox ws: undecodable frame skipped")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.connected = False
                self._conn = None
                if self._stopping:
                    break
                logger.info("upstox ws disconnected (%s); retry in %.0fs", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 15.0)
        self.connected = False

    def _handle_message(self, buf: bytes) -> None:
        msg = decode_feed_response(buf)
        for key, ltpc in msg["feeds"].items():
            if "ltp" in ltpc:
                self._cache[key] = (
                    float(ltpc["ltp"]),
                    float(ltpc.get("cp") or ltpc["ltp"]),
                    int(ltpc.get("ltt") or msg.get("currentTs") or 0),
                )


_feed: Optional[UpstoxQuoteFeed] = None


def get_feed(token_getter=None) -> UpstoxQuoteFeed:
    """Process-wide singleton feed (token read lazily at connect time)."""
    global _feed
    if _feed is None:
        from app.core.config import get_settings
        getter = token_getter or (
            lambda: get_settings().upstox_analytics_token
            or get_settings().upstox_access_token
        )
        _feed = UpstoxQuoteFeed(getter)
    return _feed


def reset_feed() -> None:
    """Tests only: drop the singleton."""
    global _feed
    _feed = None
