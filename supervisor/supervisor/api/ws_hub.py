"""WebSocket hub for broadcasting telemetry to connected clients."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING

from fastapi import WebSocket

if TYPE_CHECKING:
    from supervisor.state.datatypes import RobotState

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

    def broadcast_telemetry(self, state: RobotState) -> None:
        """Non-blocking broadcast of telemetry to all clients.

        Drops messages if clients are slow (telemetry drop is acceptable).
        """
        if not self._clients:
            return

        envelope = json.dumps(
            {
                "schema": "supervisor_ws_v1",
                "type": "telemetry",
                "ts_ms": int(time.monotonic() * 1000),
                "payload": state.to_dict(),
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
