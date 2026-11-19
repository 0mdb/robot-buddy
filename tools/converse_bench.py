#!/usr/bin/env python3
"""Conversation latency bench: speak recorded questions into /converse, time the reply.

Runs from any host, so the same questions can be timed on the server itself
(localhost, no network) and on the Pi (over Wi-Fi or ethernet); the difference
is what the link costs.

Each question is 16 kHz 16-bit mono PCM, streamed in 20 ms chunks at real-time
pace like the robot's mic, followed by end_utterance. Measured from
end_utterance (client clock):
  transcription  first "transcription" message
  first_audio    first "audio" chunk (what the listener waits for)
  done           "done"
plus the reply's audio stream: largest gap between chunks, and whether audio
arrived faster than real time (an underrun would be heard as a stutter).

Uses its own robot_id (default "bench") so it never replaces the robot's live
session. Needs only `websockets`.

Make the questions once (on the server):
    python tools/converse_bench.py --make-questions DIR --http http://127.0.0.1:8100
Run:
    python tools/converse_bench.py --server ws://192.168.55.64:8100 --questions DIR --runs 3
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import statistics
import time
import urllib.request
from pathlib import Path

SAMPLE_RATE = 16000
CHUNK_BYTES = 640  # 20 ms
QUESTIONS = [
    "What is your favourite colour?",
    "Can you tell me a fun fact about octopuses?",
    "How far away is the moon?",
    "What should we play today?",
    "Why is the sky blue?",
]


def make_questions(out_dir: Path, http_base: str, voice: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, text in enumerate(QUESTIONS):
        body = json.dumps({"text": text, "voice": voice, "stream": False}).encode()
        req = urllib.request.Request(
            f"{http_base}/tts", data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            pcm = r.read()
        # Trailing silence as the mic would capture before VAD ends the turn.
        pcm += b"\x00" * (SAMPLE_RATE * 2 // 5)
        path = out_dir / f"q{i}.pcm"
        path.write_bytes(pcm)
        print(f"{path}  {len(pcm) / (SAMPLE_RATE * 2):.1f} s  {text}")


async def one_turn(
    server: str, robot_id: str, seq: int, pcm: bytes
) -> dict[str, float]:
    import websockets

    url = (
        f"{server}/converse?robot_id={robot_id}&session_seq={seq}"
        f"&session_monotonic_ts_ms={int(time.monotonic() * 1000)}&resume=0"
    )
    async with websockets.connect(
        url, ping_interval=20, ping_timeout=60, max_size=None
    ) as ws:
        while json.loads(await ws.recv()).get("type") != "listening":
            pass
        t0 = time.monotonic()
        for i in range(0, len(pcm), CHUNK_BYTES):
            await ws.send(
                json.dumps(
                    {
                        "type": "audio",
                        "data": base64.b64encode(pcm[i : i + CHUNK_BYTES]).decode(),
                    }
                )
            )
            await asyncio.sleep(
                max(0.0, t0 + (i + CHUNK_BYTES) / (SAMPLE_RATE * 2) - time.monotonic())
            )
        await ws.send(json.dumps({"type": "end_utterance"}))
        t_end = time.monotonic()

        res: dict[str, float] = {}
        audio_bytes = 0
        last_chunk: float | None = None
        max_gap = 0.0
        min_slack = float("inf")  # audio buffered ahead of playback, worst case
        first_audio_t: float | None = None
        async for raw in ws:
            now = time.monotonic()
            msg = json.loads(raw)
            t = msg.get("type")
            if t == "transcription" and "transcription" not in res:
                res["transcription"] = now - t_end
            elif t == "first_audio":
                res["server_first_audio"] = msg.get("first_audio_ms", 0) / 1000
            elif t == "audio":
                if first_audio_t is None:
                    first_audio_t = now
                    res["first_audio"] = now - t_end
                else:
                    max_gap = max(max_gap, now - (last_chunk or now))
                    # Playback started at first_audio_t; this chunk is needed at
                    # first_audio_t + audio already received.
                    min_slack = min(
                        min_slack, first_audio_t + audio_bytes / (SAMPLE_RATE * 2) - now
                    )
                last_chunk = now
                audio_bytes += len(base64.b64decode(msg.get("data", "")))
            elif t in ("error", "turn_error"):
                res["error"] = 1.0
                print(f"    server error: {msg}")
            elif t == "done":
                res["done"] = now - t_end
                break
        res["audio_s"] = audio_bytes / (SAMPLE_RATE * 2)
        res["max_gap"] = max_gap
        res["min_slack"] = min_slack if min_slack != float("inf") else 0.0
        return res


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))]


async def bench(
    server: str, qdir: Path, runs: int, robot_id: str, pause: float
) -> None:
    files = sorted(qdir.glob("q*.pcm"))
    rows: list[dict[str, float]] = []
    seq = int(time.time())
    for r in range(runs):
        for f in files:
            seq += 1
            res = await one_turn(server, robot_id, seq, f.read_bytes())
            rows.append(res)
            print(
                f"run {r} {f.stem}: stt {res.get('transcription', -1):.2f}  "
                f"first_audio {res.get('first_audio', -1):.2f} (server {res.get('server_first_audio', -1):.2f})  "
                f"done {res.get('done', -1):.2f}  audio {res['audio_s']:.1f}s  "
                f"max_gap {res['max_gap'] * 1000:.0f}ms  min_slack {res['min_slack']:.2f}s"
            )
            await asyncio.sleep(pause)
    ok = [x for x in rows if "first_audio" in x and "error" not in x]
    print(f"\n{len(ok)}/{len(rows)} turns ok")
    for key in (
        "transcription",
        "first_audio",
        "server_first_audio",
        "max_gap",
        "min_slack",
    ):
        xs = [x[key] for x in ok if key in x]
        if xs:
            print(
                f"{key:20s} p50 {statistics.median(xs):.3f}  p90 {pct(xs, 0.9):.3f}  "
                f"min {min(xs):.3f}  max {max(xs):.3f}"
            )


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--server",
        default="ws://127.0.0.1:8100",
        help="ws base URL of the planner server",
    )
    ap.add_argument("--questions", type=Path, help="directory of q*.pcm files")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--robot-id", default="bench")
    ap.add_argument("--pause", type=float, default=1.0, help="seconds between turns")
    ap.add_argument(
        "--make-questions",
        type=Path,
        metavar="DIR",
        help="synthesize questions via /tts and exit",
    )
    ap.add_argument(
        "--http",
        default="http://127.0.0.1:8100",
        help="server http base for --make-questions",
    )
    ap.add_argument(
        "--voice", default="leo", help="Orpheus test voice for --make-questions"
    )
    a = ap.parse_args()
    if a.make_questions:
        make_questions(a.make_questions, a.http, a.voice)
        return
    if not a.questions:
        ap.error("--questions is required")
    asyncio.run(bench(a.server, a.questions, a.runs, a.robot_id, a.pause))


if __name__ == "__main__":
    main()
