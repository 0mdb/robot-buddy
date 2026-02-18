#!/usr/bin/env python3
"""Standalone TTS playback test — connects to /converse WebSocket and plays audio.

Sends a text message (bypassing STT), receives LLM response with TTS audio,
and plays it on a local USB speaker via aplay. No supervisor or MCU needed.

Usage:
    python audio_conversation_test.py --server ws://10.0.0.20:8100/converse
    python audio_conversation_test.py --server ws://10.0.0.20:8100/converse --speaker plughw:2,0
    python audio_conversation_test.py --server ws://10.0.0.20:8100/converse --text "Tell me a joke"
    python audio_conversation_test.py --server ws://10.0.0.20:8100/converse --mic plughw:3,0
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import math
import shutil
import struct
import subprocess
import sys


SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_BYTES = 320  # 10ms at 16kHz 16-bit mono


def compute_rms(pcm: bytes) -> float:
    n = len(pcm) // 2
    if n == 0:
        return 0.0
    samples = struct.unpack(f"<{n}h", pcm[: n * 2])
    return math.sqrt(sum(s * s for s in samples) / n)


async def run_text_test(server_url: str, speaker_device: str, text: str) -> None:
    """Send text, receive and play TTS audio."""
    import websockets

    print(f"Connecting to {server_url} ...")
    async with websockets.connect(server_url, ping_interval=20, ping_timeout=10) as ws:
        print("Connected. Sending text ...")
        await ws.send(json.dumps({"type": "text", "text": text}))

        # Start aplay subprocess for streaming playback
        aplay_cmd = [
            "aplay", "-q",
            "-D", speaker_device,
            "-c", str(CHANNELS),
            "-r", str(SAMPLE_RATE),
            "-f", "S16_LE",
            "-t", "raw",
        ]
        print(f"Starting speaker: {' '.join(aplay_cmd)}")
        speaker = await asyncio.create_subprocess_exec(
            *aplay_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )

        chunk_count = 0
        total_bytes = 0
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type", "")

                if msg_type == "listening":
                    print("  [server] listening")

                elif msg_type == "emotion":
                    emotion = msg.get("emotion", "?")
                    intensity = msg.get("intensity", 0)
                    print(f"  [emotion] {emotion} (intensity={intensity:.2f})")

                elif msg_type == "gestures":
                    names = msg.get("names", [])
                    print(f"  [gestures] {names}")

                elif msg_type == "transcription":
                    print(f"  [transcription] {msg.get('text', '')}")

                elif msg_type == "audio":
                    data = msg.get("data", "")
                    if data:
                        pcm = base64.b64decode(data)
                        chunk_count += 1
                        total_bytes += len(pcm)
                        rms = compute_rms(pcm)
                        if chunk_count <= 3 or chunk_count % 50 == 0:
                            print(f"  [audio] chunk {chunk_count}: {len(pcm)} bytes, rms={rms:.0f}")
                        if speaker.stdin:
                            speaker.stdin.write(pcm)
                            await speaker.stdin.drain()

                elif msg_type == "done":
                    duration_s = total_bytes / (SAMPLE_RATE * 2)
                    print(f"  [done] {chunk_count} chunks, {total_bytes} bytes, ~{duration_s:.1f}s audio")
                    break

                elif msg_type == "error":
                    print(f"  [ERROR] {msg.get('message', '?')}")
                    break

        finally:
            if speaker.stdin:
                try:
                    speaker.stdin.close()
                    await speaker.stdin.wait_closed()
                except Exception:
                    pass
            # Wait for aplay to finish playing buffered audio
            try:
                await asyncio.wait_for(speaker.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                speaker.terminate()
                await speaker.wait()

            stderr_out = await speaker.stderr.read() if speaker.stderr else b""
            if speaker.returncode and speaker.returncode != 0:
                print(f"  aplay exited with code {speaker.returncode}")
                if stderr_out:
                    print(f"  aplay stderr: {stderr_out.decode(errors='replace')}")

    print("Done.")


async def run_mic_test(
    server_url: str, speaker_device: str, mic_device: str, duration: float
) -> None:
    """Record from mic, send to server for STT + LLM + TTS, play response."""
    import websockets

    print(f"Connecting to {server_url} ...")
    async with websockets.connect(server_url, ping_interval=20, ping_timeout=10) as ws:
        # Wait for listening signal
        raw = await ws.recv()
        msg = json.loads(raw)
        if msg.get("type") == "listening":
            print("Server is listening.")

        # Start mic capture
        arecord_cmd = [
            "arecord", "-q",
            "-D", mic_device,
            "-c", str(CHANNELS),
            "-r", str(SAMPLE_RATE),
            "-f", "S16_LE",
            "-t", "raw",
        ]
        print(f"Recording {duration}s from mic: {' '.join(arecord_cmd)}")
        print("  Speak now!")
        mic = await asyncio.create_subprocess_exec(
            *arecord_cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        # Stream mic audio to server for `duration` seconds
        chunks_sent = 0
        try:
            end_time = asyncio.get_event_loop().time() + duration
            while asyncio.get_event_loop().time() < end_time:
                chunk = await asyncio.wait_for(
                    mic.stdout.read(CHUNK_BYTES), timeout=0.5
                )
                if not chunk:
                    break
                encoded = base64.b64encode(chunk).decode("ascii")
                await ws.send(json.dumps({"type": "audio", "data": encoded}))
                chunks_sent += 1
        except asyncio.TimeoutError:
            pass
        finally:
            mic.terminate()
            await mic.wait()

        print(f"  Sent {chunks_sent} audio chunks ({chunks_sent * 10}ms)")
        print("  Sending end_utterance ...")
        await ws.send(json.dumps({"type": "end_utterance"}))

        # Now receive response (transcription + emotion + TTS audio)
        aplay_cmd = [
            "aplay", "-q",
            "-D", speaker_device,
            "-c", str(CHANNELS),
            "-r", str(SAMPLE_RATE),
            "-f", "S16_LE",
            "-t", "raw",
        ]
        speaker = await asyncio.create_subprocess_exec(
            *aplay_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )

        chunk_count = 0
        total_bytes = 0
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type", "")

                if msg_type == "transcription":
                    print(f"  [STT] You said: \"{msg.get('text', '')}\"")

                elif msg_type == "emotion":
                    print(f"  [emotion] {msg.get('emotion')} ({msg.get('intensity', 0):.2f})")

                elif msg_type == "gestures":
                    print(f"  [gestures] {msg.get('names', [])}")

                elif msg_type == "audio":
                    data = msg.get("data", "")
                    if data:
                        pcm = base64.b64decode(data)
                        chunk_count += 1
                        total_bytes += len(pcm)
                        if chunk_count <= 3 or chunk_count % 50 == 0:
                            print(f"  [audio] chunk {chunk_count}: {len(pcm)} bytes")
                        if speaker.stdin:
                            speaker.stdin.write(pcm)
                            await speaker.stdin.drain()

                elif msg_type == "done":
                    duration_s = total_bytes / (SAMPLE_RATE * 2)
                    print(f"  [done] {chunk_count} chunks, ~{duration_s:.1f}s audio")
                    break

                elif msg_type == "error":
                    print(f"  [ERROR] {msg.get('message', '?')}")
                    break
        finally:
            if speaker.stdin:
                try:
                    speaker.stdin.close()
                    await speaker.stdin.wait_closed()
                except Exception:
                    pass
            try:
                await asyncio.wait_for(speaker.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                speaker.terminate()
                await speaker.wait()

    print("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test TTS/STT pipeline against personality server"
    )
    parser.add_argument(
        "--server",
        default="ws://10.0.0.20:8100/converse",
        help="WebSocket URL for /converse endpoint",
    )
    parser.add_argument(
        "--speaker",
        default="plughw:2,0",
        help="ALSA playback device (default: plughw:2,0)",
    )
    parser.add_argument(
        "--mic",
        default=None,
        help="ALSA capture device for mic test (e.g., plughw:3,0). "
        "If provided, records audio and tests full STT+LLM+TTS pipeline.",
    )
    parser.add_argument(
        "--mic-duration",
        type=float,
        default=5.0,
        help="Seconds to record from mic (default: 5)",
    )
    parser.add_argument(
        "--text",
        default="Hello! Tell me a fun fact about robots.",
        help="Text to send (text mode only, bypasses STT)",
    )
    args = parser.parse_args()

    # Check aplay is available
    if shutil.which("aplay") is None:
        print("ERROR: aplay not found. Install alsa-utils.", file=sys.stderr)
        sys.exit(1)

    if args.mic:
        if shutil.which("arecord") is None:
            print("ERROR: arecord not found. Install alsa-utils.", file=sys.stderr)
            sys.exit(1)
        asyncio.run(run_mic_test(args.server, args.speaker, args.mic, args.mic_duration))
    else:
        asyncio.run(run_text_test(args.server, args.speaker, args.text))


if __name__ == "__main__":
    main()
