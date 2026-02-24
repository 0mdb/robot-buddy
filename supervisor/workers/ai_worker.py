"""AI worker — plan requests + conversation orchestration.

Absorbs v1 planner_client.py + conversation_manager.py.

- Plan requests: HTTP POST /plan → emits ai.plan.received
- Conversation: WebSocket /converse → mic/speaker audio via direct sockets
- Transport-level dedup of plan_id (256 entries / 60s window)
- Core does semantic validation (this worker emits raw plans)
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import socket
import struct
import time
from collections import OrderedDict
from typing import Any

from supervisor.messages.envelope import Envelope
from supervisor.messages.types import (
    AI_CMD_CANCEL,
    AI_CMD_END_CONVERSATION,
    AI_CMD_END_UTTERANCE,
    AI_CMD_REQUEST_PLAN,
    AI_CMD_SEND_AUDIO,
    AI_CMD_SEND_PROFILE,
    AI_CMD_START_CONVERSATION,
    AI_CONFIG_INIT,
    AI_CONVERSATION_DONE,
    AI_CONVERSATION_EMOTION,
    AI_CONVERSATION_GESTURE,
    AI_CONVERSATION_TRANSCRIPTION,
    AI_PLAN_RECEIVED,
    AI_STATE_CHANGED,
    SYSTEM_AUDIO_LINK_DOWN,
    SYSTEM_AUDIO_LINK_UP,
)
from supervisor.workers.base import BaseWorker, worker_main

log = logging.getLogger(__name__)

# Plan dedup (§7.3.3)
_DEDUP_WINDOW = 256
_DEDUP_TTL_S = 60.0

# WebSocket reconnect backoff (Appendix C)
_WS_BACKOFF_INITIAL_S = 1.0
_WS_BACKOFF_MAX_S = 8.0

# HTTP plan retry (Appendix C)
_HTTP_RETRY_S = 3.0


class AIWorker(BaseWorker):
    domain = "ai"

    def __init__(self) -> None:
        super().__init__()
        # Config
        self._audio_mode = "direct"
        self._mic_socket_path = ""
        self._spk_socket_path = ""
        self._server_base_url = ""
        self._robot_id = ""
        self._configured = asyncio.Event()

        # State machine
        self._state = "idle"
        self._session_id = ""
        self._turn_id = 0
        self._session_seq = 0

        # Plan dedup
        self._seen_plans: OrderedDict[str, float] = OrderedDict()
        self._plan_seq = 0

        # Sockets (Mode A — AI is server)
        self._mic_server_sock: socket.socket | None = None
        self._spk_server_sock: socket.socket | None = None
        self._mic_client: socket.socket | None = None
        self._spk_client: socket.socket | None = None

        # WebSocket
        self._ws = None
        self._ws_connected = False

        # Server connection
        self._server_connected = False

    async def on_message(self, envelope: Envelope) -> None:
        t = envelope.type
        p = envelope.payload

        if t == AI_CONFIG_INIT:
            self._audio_mode = str(p.get("audio_mode", "direct"))
            self._mic_socket_path = str(p.get("mic_socket_path", ""))
            self._spk_socket_path = str(p.get("spk_socket_path", ""))
            self._server_base_url = str(p.get("server_base_url", ""))
            self._robot_id = str(p.get("robot_id", ""))
            log.info(
                "configured: mode=%s server=%s", self._audio_mode, self._server_base_url
            )
            self._configured.set()

        elif t == AI_CMD_REQUEST_PLAN:
            world_state = p.get("world_state", {})
            asyncio.create_task(self._request_plan(world_state))

        elif t == AI_CMD_START_CONVERSATION:
            self._session_id = str(p.get("session_id", ""))
            self._turn_id = int(p.get("turn_id", 1))
            asyncio.create_task(self._start_conversation())

        elif t == AI_CMD_END_UTTERANCE:
            self._turn_id = int(p.get("turn_id", self._turn_id))
            asyncio.create_task(self._end_utterance())

        elif t == AI_CMD_END_CONVERSATION:
            asyncio.create_task(self._end_conversation())

        elif t == AI_CMD_CANCEL:
            await self._cancel()

        elif t == AI_CMD_SEND_PROFILE:
            # Forward personality profile to server (PE spec S2 §12.5)
            await self._ws_send({"type": "profile", "profile": p})

        elif t == AI_CMD_SEND_AUDIO:
            # Mode B: audio relay from Core
            if self._audio_mode == "relay" and self._ws:
                data_b64 = p.get("data_b64", "")
                if data_b64:
                    await self._ws_send({"type": "audio", "data": data_b64})

    def health_payload(self) -> dict[str, Any]:
        return {
            "connected": self._server_connected,
            "state": self._state,
            "session_id": self._session_id,
        }

    async def run(self) -> None:
        """Main loop — wait for config, bind sockets, then idle."""
        try:
            await asyncio.wait_for(self._configured.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            log.error("no config received within 10s")
            return

        # Mode A: bind audio sockets (AI is server)
        if self._audio_mode == "direct":
            asyncio.create_task(self._bind_socket("mic", self._mic_socket_path))
            asyncio.create_task(self._bind_socket("spk", self._spk_socket_path))

        # Check server health
        asyncio.create_task(self._health_check_loop())

        # Wait for shutdown
        await self.shutdown_event.wait()

    def _set_state(self, new_state: str, reason: str = "") -> None:
        if new_state == self._state:
            return
        prev = self._state
        self._state = new_state
        self.send(
            AI_STATE_CHANGED,
            {
                "state": new_state,
                "prev_state": prev,
                "session_id": self._session_id,
                "turn_id": self._turn_id,
                "reason": reason,
            },
        )

    # ── Plan requests ────────────────────────────────────────────

    async def _request_plan(self, world_state: dict) -> None:
        """HTTP POST /plan → emit ai.plan.received."""
        if not self._server_base_url:
            return

        try:
            import httpx
        except ImportError:
            return

        self._plan_seq += 1
        url = f"{self._server_base_url}/plan"
        body = dict(world_state)
        body["seq"] = self._plan_seq
        body["monotonic_ts_ms"] = int(time.monotonic() * 1000)

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(url, json=body)
                if resp.status_code != 200:
                    return

                data = resp.json()

                # Transport-level dedup
                plan_id = str(data.get("plan_id", ""))
                if self._is_duplicate_plan(plan_id):
                    return

                self._server_connected = True
                self.send(
                    AI_PLAN_RECEIVED,
                    {
                        "plan_id": plan_id,
                        "plan_seq": int(data.get("seq", 0)),
                        "t_server_ms": int(data.get("server_monotonic_ts_ms", 0)),
                        "actions": data.get("actions", []),
                        "ttl_ms": int(data.get("ttl_ms", 2000)),
                    },
                    ref_seq=self._plan_seq,
                )

        except Exception as e:
            log.warning("plan request failed: %s", e)
            self._server_connected = False

    def _is_duplicate_plan(self, plan_id: str) -> bool:
        """Transport-level dedup (§7.3.3)."""
        now = time.monotonic()
        # Prune old entries
        cutoff = now - _DEDUP_TTL_S
        while self._seen_plans:
            pid, t = next(iter(self._seen_plans.items()))
            if t > cutoff:
                break
            self._seen_plans.pop(pid)
        while len(self._seen_plans) > _DEDUP_WINDOW:
            self._seen_plans.popitem(last=False)

        if plan_id in self._seen_plans:
            return True
        self._seen_plans[plan_id] = now
        return False

    # ── Conversation ─────────────────────────────────────────────

    async def _start_conversation(self) -> None:
        """Open WebSocket to /converse and start listening."""
        self._set_state("connecting", "start_conversation")
        self._session_seq += 1

        try:
            import websockets
        except ImportError:
            self._set_state("error", "websockets not installed")
            return

        url = (
            f"{self._server_base_url.replace('http', 'ws')}/converse"
            f"?robot_id={self._robot_id}"
            f"&session_seq={self._session_seq}"
            f"&session_monotonic_ts_ms={int(time.monotonic() * 1000)}"
        )

        try:
            self._ws = await websockets.connect(url)
            self._ws_connected = True
            self._set_state("listening", "ws_connected")

            # Start reading server messages
            asyncio.create_task(self._ws_read_loop())

            # Start forwarding mic audio (Mode A)
            if self._audio_mode == "direct":
                asyncio.create_task(self._mic_to_ws_loop())

        except Exception as e:
            self._set_state("error", str(e))
            log.warning("conversation connect failed: %s", e)

    async def _end_utterance(self) -> None:
        """Signal end of user speech to server."""
        self._set_state("thinking", "end_utterance_received")
        await self._ws_send({"type": "end_utterance"})

    async def _end_conversation(self) -> None:
        """Close conversation session."""
        await self._ws_send({"type": "cancel"})
        await self._close_ws()
        self._set_state("idle", "end_conversation")
        self._session_id = ""
        self._turn_id = 0

    async def _cancel(self) -> None:
        """Cancel active request/conversation."""
        if self._ws_connected:
            await self._ws_send({"type": "cancel"})
            await self._close_ws()
        self._set_state("idle", "cancel")
        self._session_id = ""
        self._turn_id = 0

    async def _ws_read_loop(self) -> None:
        """Read messages from the converse WebSocket."""
        if not self._ws:
            return

        try:
            async for raw_msg in self._ws:
                try:
                    msg = (
                        json.loads(raw_msg)
                        if isinstance(raw_msg, str)
                        else json.loads(raw_msg.decode())
                    )
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue

                msg_type = msg.get("type", "")

                if msg_type == "transcription":
                    self.send(
                        AI_CONVERSATION_TRANSCRIPTION,
                        {
                            "session_id": self._session_id,
                            "turn_id": self._turn_id,
                            "text": msg.get("text", ""),
                        },
                    )

                elif msg_type == "emotion":
                    emotion_payload: dict[str, object] = {
                        "session_id": self._session_id,
                        "turn_id": self._turn_id,
                        "emotion": msg.get("emotion", ""),
                        "intensity": float(msg.get("intensity", 0.7)),
                    }
                    mood_reason = msg.get("mood_reason", "")
                    if mood_reason:
                        emotion_payload["mood_reason"] = str(mood_reason)
                    self.send(AI_CONVERSATION_EMOTION, emotion_payload)

                elif msg_type == "gestures":
                    self.send(
                        AI_CONVERSATION_GESTURE,
                        {
                            "session_id": self._session_id,
                            "turn_id": self._turn_id,
                            "names": msg.get("names", []),
                        },
                    )

                elif msg_type == "audio":
                    self._set_state("speaking", "audio_received")
                    # Forward audio to TTS worker via socket (Mode A) or NDJSON (Mode B)
                    data_b64 = msg.get("data", "")
                    if data_b64:
                        pcm = base64.b64decode(data_b64)
                        if self._audio_mode == "direct" and self._spk_client:
                            try:
                                frame = struct.pack("<H", len(pcm)) + pcm
                                loop = asyncio.get_running_loop()
                                await loop.sock_sendall(self._spk_client, frame)
                            except (BrokenPipeError, OSError):
                                pass
                        elif self._audio_mode == "relay":
                            self.send("ai.conversation.audio", {"data_b64": data_b64})

                elif msg_type == "done":
                    self.send(
                        AI_CONVERSATION_DONE,
                        {
                            "session_id": self._session_id,
                            "turn_id": self._turn_id,
                        },
                    )
                    self._set_state("listening", "turn_done")

                elif msg_type == "listening":
                    self._set_state("listening", "server_listening")

                elif msg_type == "error":
                    self._set_state("error", msg.get("message", "server_error"))

        except Exception as e:
            log.warning("ws read error: %s", e)
            self._set_state("error", f"ws_read: {e}")
        finally:
            self._ws_connected = False

    async def _mic_to_ws_loop(self) -> None:
        """Read mic PCM from socket and forward to server WebSocket."""
        sock = self._mic_client
        if not sock or not self._ws:
            return

        loop = asyncio.get_running_loop()
        try:
            while self._ws_connected and self._state in ("listening",):
                # Read frame: [chunk_len:u16-LE][pcm_data]
                header = await loop.sock_recv(sock, 2)
                if not header or len(header) < 2:
                    break
                chunk_len = struct.unpack("<H", header)[0]
                if chunk_len == 0 or chunk_len > 4096:
                    continue

                pcm = b""
                while len(pcm) < chunk_len:
                    data = await loop.sock_recv(sock, chunk_len - len(pcm))
                    if not data:
                        break
                    pcm += data

                if len(pcm) == chunk_len:
                    await self._ws_send(
                        {
                            "type": "audio",
                            "data": base64.b64encode(pcm).decode(),
                        }
                    )
        except (ConnectionError, OSError) as e:
            self.send(SYSTEM_AUDIO_LINK_DOWN, {"socket": "mic", "reason": str(e)})
        except asyncio.CancelledError:
            pass

    async def _ws_send(self, msg: dict) -> None:
        """Send a JSON message to the WebSocket."""
        if self._ws and self._ws_connected:
            try:
                await self._ws.send(json.dumps(msg))
            except Exception:
                pass

    async def _close_ws(self) -> None:
        """Close the WebSocket connection."""
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        self._ws = None
        self._ws_connected = False

    # ── Socket binding (Mode A — AI is server) ───────────────────

    async def _bind_socket(self, name: str, path: str) -> None:
        """Bind and listen on a unix domain socket (server role)."""
        if not path:
            return

        import os

        # Always unlink first (stale from previous crash)
        try:
            os.unlink(path)
        except OSError:
            pass

        server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_sock.bind(path)
        server_sock.listen(1)
        server_sock.setblocking(False)

        if name == "mic":
            self._mic_server_sock = server_sock
        elif name == "spk":
            self._spk_server_sock = server_sock

        log.info("listening on %s socket: %s", name, path)

        # Accept loop
        loop = asyncio.get_running_loop()
        while self.running:
            try:
                client, _ = await loop.sock_accept(server_sock)
                client.setblocking(False)
                if name == "mic":
                    self._mic_client = client
                elif name == "spk":
                    self._spk_client = client
                self.send(SYSTEM_AUDIO_LINK_UP, {"socket": name})
                log.info("accepted %s connection", name)
            except asyncio.CancelledError:
                break
            except OSError as e:
                log.warning("accept error on %s: %s", name, e)
                await asyncio.sleep(0.5)

    # ── Health check ─────────────────────────────────────────────

    async def _health_check_loop(self) -> None:
        """Periodic health check to the server."""
        while self.running:
            if self._server_base_url:
                try:
                    import httpx

                    async with httpx.AsyncClient(timeout=3.0) as client:
                        resp = await client.get(f"{self._server_base_url}/health")
                        self._server_connected = resp.status_code == 200
                except Exception:
                    self._server_connected = False
            await asyncio.sleep(5.0)


if __name__ == "__main__":
    worker_main(AIWorker)
