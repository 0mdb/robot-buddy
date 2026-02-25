"""Worker process lifecycle manager.

Launches workers as child processes, reads their NDJSON stdout,
monitors heartbeats, and restarts on failure.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from supervisor.messages.envelope import Envelope, SeqCounter, make_envelope
from supervisor.messages.types import (
    SRC_CORE,
    SYSTEM_LIFECYCLE_SHUTDOWN,
)

log = logging.getLogger(__name__)

_WORKER_STDERR_LEVEL_RE = re.compile(
    r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)\b(?:\s+|$)(.*)"
)


def _parse_worker_stderr_level(line: str) -> tuple[int, str]:
    """Extract Python log level from worker stderr formatter prefix."""
    match = _WORKER_STDERR_LEVEL_RE.match(line)
    if not match:
        return logging.INFO, line
    level_name, message = match.groups()
    level = getattr(logging, level_name, logging.INFO)
    return level, message.lstrip() if message else ""


def _log_worker_stderr_line(worker_name: str, line: str) -> None:
    """Forward one worker stderr line using parsed severity."""
    level, message = _parse_worker_stderr_level(line)
    if message:
        log.log(level, "[%s] %s", worker_name, message)
    else:
        log.log(level, "[%s]", worker_name)


# Type for the event callback: async fn(worker_name, envelope)
EventCallback = Callable[[str, Envelope], Coroutine[Any, Any, None]]


@dataclass(slots=True)
class WorkerInfo:
    """Runtime state for one managed worker."""

    name: str
    module: str
    process: asyncio.subprocess.Process | None = None
    reader_task: asyncio.Task | None = None
    restart_count: int = 0
    last_heartbeat_ns: int = 0
    last_seq: int = 0
    alive: bool = False
    starting: bool = False
    last_health: dict = field(default_factory=dict)


class WorkerManager:
    """Launch, monitor, and restart worker processes."""

    def __init__(
        self,
        *,
        on_event: EventCallback,
        heartbeat_timeout_s: float = 5.0,
        max_restarts: int = 5,
        restart_backoff_min_s: float = 1.0,
        restart_backoff_max_s: float = 5.0,
    ) -> None:
        self._on_event = on_event
        self._heartbeat_timeout_s = heartbeat_timeout_s
        self._max_restarts = max_restarts
        self._restart_backoff_min_s = restart_backoff_min_s
        self._restart_backoff_max_s = restart_backoff_max_s

        self._workers: dict[str, WorkerInfo] = {}
        self._seq = SeqCounter()
        self._monitor_task: asyncio.Task | None = None
        self._running = False

        # Audio socket paths (created once, passed to TTS + AI workers)
        self._pid = os.getpid()
        self._mic_socket_path = f"/tmp/rb-mic-{self._pid}.sock"
        self._spk_socket_path = f"/tmp/rb-spk-{self._pid}.sock"

    @property
    def mic_socket_path(self) -> str:
        return self._mic_socket_path

    @property
    def spk_socket_path(self) -> str:
        return self._spk_socket_path

    def register(self, name: str, module: str) -> None:
        """Register a worker to be managed.  Call before start()."""
        self._workers[name] = WorkerInfo(name=name, module=module)

    async def start(self) -> None:
        """Launch all registered workers and start heartbeat monitor."""
        self._running = True
        self._cleanup_stale_sockets()

        for info in self._workers.values():
            await self._launch(info)

        self._monitor_task = asyncio.create_task(
            self._heartbeat_monitor(), name="worker-monitor"
        )

    async def stop(self) -> None:
        """Gracefully shut down all workers."""
        self._running = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except (asyncio.CancelledError, Exception):
                pass

        # Send shutdown to all workers
        for info in self._workers.values():
            await self._send_shutdown(info)

        # Wait for processes to exit
        for info in self._workers.values():
            if info.process and info.process.returncode is None:
                try:
                    await asyncio.wait_for(info.process.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    log.warning("killing %s (did not exit in 3s)", info.name)
                    info.process.kill()

            if info.reader_task:
                info.reader_task.cancel()
                try:
                    await info.reader_task
                except (asyncio.CancelledError, Exception):
                    pass

            info.alive = False

        self._cleanup_sockets()

    async def send_to(
        self,
        worker_name: str,
        msg_type: str,
        payload: dict | None = None,
        **kwargs: Any,
    ) -> bool:
        """Send one NDJSON message to a worker's stdin."""
        info = self._workers.get(worker_name)
        if not info or not info.process or not info.process.stdin:
            return False

        env = make_envelope(
            msg_type=msg_type,
            src=SRC_CORE,
            seq=self._seq.next(),
            payload=payload,
            **kwargs,
        )
        try:
            info.process.stdin.write(env.to_line())
            await info.process.stdin.drain()
            return True
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            log.warning("send_to %s failed: %s", worker_name, e)
            return False

    def worker_alive(self, name: str) -> bool:
        info = self._workers.get(name)
        return info.alive if info else False

    def worker_snapshot(self) -> dict[str, dict]:
        """Debug snapshot of all workers."""
        result = {}
        for name, info in self._workers.items():
            result[name] = {
                "alive": info.alive,
                "restart_count": info.restart_count,
                "last_seq": info.last_seq,
                "pid": info.process.pid if info.process else None,
                "health": dict(info.last_health),
            }
        return result

    # ── Internal ─────────────────────────────────────────────────

    async def _launch(self, info: WorkerInfo) -> None:
        """Spawn a worker subprocess."""
        info.starting = True
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                info.module,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            info.process = proc
            info.alive = True
            info.last_heartbeat_ns = time.monotonic_ns()
            info.reader_task = asyncio.create_task(
                self._read_loop(info), name=f"reader-{info.name}"
            )
            # Also forward stderr to our log
            asyncio.create_task(self._stderr_loop(info), name=f"stderr-{info.name}")
            log.info(
                "launched %s (pid=%d, module=%s)", info.name, proc.pid, info.module
            )
        except Exception:
            log.exception("failed to launch %s", info.name)
            info.alive = False
        finally:
            info.starting = False

    async def _read_loop(self, info: WorkerInfo) -> None:
        """Read NDJSON lines from worker stdout and dispatch events."""
        proc = info.process
        if not proc or not proc.stdout:
            return

        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    # EOF — process exited
                    break

                try:
                    env = Envelope.from_line(line)
                except (ValueError, json.JSONDecodeError) as e:
                    log.warning("%s bad NDJSON: %s", info.name, e)
                    continue

                info.last_seq = env.seq

                # Health messages update heartbeat + store payload
                if env.type.endswith(".status.health"):
                    info.last_heartbeat_ns = time.monotonic_ns()
                    if env.payload:
                        info.last_health = dict(env.payload)

                # Lifecycle started also counts as heartbeat
                if env.type.endswith(".lifecycle.started"):
                    info.last_heartbeat_ns = time.monotonic_ns()

                try:
                    await self._on_event(info.name, env)
                except Exception:
                    log.exception("event handler error for %s %s", info.name, env.type)

        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("%s reader error", info.name)
        finally:
            info.alive = False
            log.info("%s stdout closed (pid=%s)", info.name, proc.pid if proc else "?")

    async def _stderr_loop(self, info: WorkerInfo) -> None:
        """Forward worker stderr to Core's log."""
        proc = info.process
        if not proc or not proc.stderr:
            return
        try:
            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                decoded = line.decode(errors="replace").rstrip()
                _log_worker_stderr_line(info.name, decoded)
        except (asyncio.CancelledError, Exception):
            pass

    async def _heartbeat_monitor(self) -> None:
        """Check worker heartbeats every second, restart stale workers."""
        while self._running:
            await asyncio.sleep(1.0)
            now = time.monotonic_ns()
            timeout_ns = int(self._heartbeat_timeout_s * 1_000_000_000)

            for info in self._workers.values():
                if not info.alive or info.starting:
                    continue

                age_ns = now - info.last_heartbeat_ns
                if age_ns > timeout_ns:
                    log.warning(
                        "%s heartbeat stale (%d ms), restarting",
                        info.name,
                        age_ns // 1_000_000,
                    )
                    await self._restart(info)

    async def _restart(self, info: WorkerInfo) -> None:
        """Kill and relaunch a worker with backoff."""
        if info.restart_count >= self._max_restarts:
            log.error(
                "%s exceeded max restarts (%d), giving up",
                info.name,
                self._max_restarts,
            )
            info.alive = False
            return

        # Kill current process
        if info.process and info.process.returncode is None:
            try:
                info.process.kill()
                await info.process.wait()
            except Exception:
                pass

        if info.reader_task:
            info.reader_task.cancel()
            try:
                await info.reader_task
            except (asyncio.CancelledError, Exception):
                pass

        info.restart_count += 1
        info.alive = False

        # Backoff
        backoff = min(
            self._restart_backoff_min_s * info.restart_count,
            self._restart_backoff_max_s,
        )
        log.info(
            "restarting %s in %.1fs (attempt %d/%d)",
            info.name,
            backoff,
            info.restart_count,
            self._max_restarts,
        )
        await asyncio.sleep(backoff)

        if self._running:
            await self._launch(info)

    async def _send_shutdown(self, info: WorkerInfo) -> None:
        """Send graceful shutdown to a worker."""
        if not info.process or not info.process.stdin:
            return
        env = make_envelope(
            msg_type=SYSTEM_LIFECYCLE_SHUTDOWN,
            src=SRC_CORE,
            seq=self._seq.next(),
        )
        try:
            info.process.stdin.write(env.to_line())
            await info.process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _cleanup_stale_sockets(self) -> None:
        """Remove any leftover socket files from previous crashes."""
        import glob

        for pattern in ("/tmp/rb-mic-*.sock", "/tmp/rb-spk-*.sock"):
            for path in glob.glob(pattern):
                try:
                    os.unlink(path)
                    log.info("cleaned up stale socket: %s", path)
                except OSError:
                    pass

    def _cleanup_sockets(self) -> None:
        """Remove our socket files."""
        for path in (self._mic_socket_path, self._spk_socket_path):
            try:
                os.unlink(path)
            except OSError:
                pass
