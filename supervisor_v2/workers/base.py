"""Base worker process — NDJSON stdin/stdout loop with heartbeat.

Every worker inherits from BaseWorker and implements:

- ``domain``   — e.g. ``"tts"``, ``"vision"``, ``"ai"``
- ``on_message(envelope)`` — handle inbound messages from Core
- ``run()`` — the worker's main async entry point (called after startup handshake)

BaseWorker provides:

- NDJSON reading from stdin (async line reader)
- ``send(msg_type, payload)`` — write one NDJSON line to stdout
- Automatic ``<domain>.status.health`` heartbeat at 1 Hz
- Lifecycle events (started / stopped)
- Graceful shutdown on ``system.lifecycle.shutdown``
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

from supervisor_v2.messages.envelope import Envelope, SeqCounter, make_envelope
from supervisor_v2.messages.types import SYSTEM_LIFECYCLE_SHUTDOWN

log = logging.getLogger(__name__)


class BaseWorker:
    """Abstract base for all worker processes."""

    domain: str = ""  # Override in subclass: "tts", "vision", "ai"

    def __init__(self) -> None:
        self._seq = SeqCounter()
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._stdin_reader: asyncio.StreamReader | None = None
        self._stdout_writer: asyncio.StreamWriter | None = None

    # ── Public API for subclasses ────────────────────────────────

    def send(
        self, msg_type: str, payload: dict[str, Any] | None = None, **kwargs: Any
    ) -> None:
        """Write one NDJSON message to stdout (synchronous, atomic)."""
        env = make_envelope(
            msg_type=msg_type,
            src=self.domain,
            seq=self._seq.next(),
            payload=payload,
            **kwargs,
        )
        line = env.to_line()
        # Atomic write to stdout — prevents interleaving (§6.1)
        sys.stdout.buffer.write(line)
        sys.stdout.buffer.flush()

    async def on_message(self, envelope: Envelope) -> None:
        """Handle an inbound message from Core.  Override in subclass."""

    async def run(self) -> None:
        """Worker main logic.  Override in subclass."""

    def health_payload(self) -> dict[str, Any]:
        """Return worker-specific health fields.  Override in subclass."""
        return {}

    # ── Lifecycle ────────────────────────────────────────────────

    async def start(self) -> None:
        """Entry point — called by ``worker_main()``.  Do not override."""
        self._running = True

        # Emit lifecycle.started
        self.send(f"{self.domain}.lifecycle.started")
        log.info("%s worker started", self.domain)

        # Launch background tasks
        reader_task = asyncio.create_task(
            self._stdin_loop(), name=f"{self.domain}-stdin"
        )
        heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(), name=f"{self.domain}-hb"
        )

        try:
            await self.run()
        except Exception:
            log.exception("%s worker run() failed", self.domain)
        finally:
            self._running = False
            self._shutdown_event.set()
            reader_task.cancel()
            heartbeat_task.cancel()
            # Suppress CancelledError from background tasks
            for t in (reader_task, heartbeat_task):
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
            self.send(f"{self.domain}.lifecycle.stopped")
            log.info("%s worker stopped", self.domain)

    # ── Internal loops ───────────────────────────────────────────

    async def _stdin_loop(self) -> None:
        """Read NDJSON lines from stdin and dispatch to on_message."""
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        transport, _ = await loop.connect_read_pipe(
            lambda: asyncio.StreamReaderProtocol(reader),
            sys.stdin.buffer,
        )
        try:
            while self._running:
                line = await reader.readline()
                if not line:
                    # EOF — Core closed our stdin (or died)
                    log.warning("%s stdin EOF", self.domain)
                    self._shutdown_event.set()
                    self._running = False
                    return
                try:
                    env = Envelope.from_line(line)
                except (ValueError, Exception) as e:
                    log.warning("%s bad NDJSON: %s", self.domain, e)
                    continue

                if env.type == SYSTEM_LIFECYCLE_SHUTDOWN:
                    log.info("%s received shutdown", self.domain)
                    self._shutdown_event.set()
                    self._running = False
                    return

                try:
                    await self.on_message(env)
                except Exception:
                    log.exception("%s on_message error for %s", self.domain, env.type)
        finally:
            transport.close()

    async def _heartbeat_loop(self) -> None:
        """Emit health status at 1 Hz (Appendix C: worker heartbeat interval)."""
        while self._running:
            try:
                payload = self.health_payload()
                self.send(f"{self.domain}.status.health", payload)
            except Exception:
                log.exception("%s heartbeat error", self.domain)
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=1.0)
                return  # shutdown signalled
            except asyncio.TimeoutError:
                pass  # 1s elapsed — emit next heartbeat

    @property
    def running(self) -> bool:
        return self._running

    @property
    def shutdown_event(self) -> asyncio.Event:
        return self._shutdown_event


def worker_main(worker_cls: type[BaseWorker]) -> None:
    """Convenience entry point for worker __main__.py modules.

    Usage::

        if __name__ == "__main__":
            worker_main(MyWorker)
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,  # stderr reserved for logs (§6.1)
    )
    worker = worker_cls()
    try:
        asyncio.run(worker.start())
    except KeyboardInterrupt:
        pass
