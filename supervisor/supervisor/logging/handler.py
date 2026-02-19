"""Logging handler for WebSocket streaming."""

from __future__ import annotations

import asyncio
import logging

log_queue: asyncio.Queue[str] = asyncio.Queue()


class WebSocketLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        log_entry = self.format(record)
        try:
            log_queue.put_nowait(log_entry)
        except asyncio.QueueFull:
            # This can happen if the queue is full.
            # We can either block, or drop the message.
            # For now, we'll just drop it.
            pass
