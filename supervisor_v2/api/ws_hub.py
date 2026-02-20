"""WebSocket hub for broadcasting telemetry to connected clients."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import WebSocket

log = logging.getLogger(__name__)


class WsHub:
    """Manages WebSocket clients and broadcasts telemetry."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    def add(self, ws: WebSocket) -> None:
        self._clients.add(ws)
        log.info("ws: client connected (%d total)", len(self._clients))

    def remove(self, ws: WebSocket) -> None:
        self._clients.discard(ws)
        log.info("ws: client disconnected (%d total)", len(self._clients))

    def broadcast_telemetry(self, state_dict: dict[str, Any]) -> None:
        """Non-blocking broadcast of telemetry to all clients.

        Drops messages if clients are slow (telemetry drop is acceptable).
        """
        if not self._clients:
            return

        envelope = json.dumps(
            {
                "schema": "supervisor_ws_v2",
                "type": "telemetry",
                "ts_ms": int(time.monotonic() * 1000),
                "payload": state_dict,
            }
        )

        stale: list[WebSocket] = []
        for ws in self._clients:
            try:
                asyncio.ensure_future(ws.send_text(envelope))
            except Exception:
                stale.append(ws)

        for ws in stale:
            self._clients.discard(ws)
