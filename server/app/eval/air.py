"""Over-the-air rig: talk to the real robot through a speaker, read what it did.

Layers L2 / L4 of ``~/vantage/docs/SIM-INTERACTION.md``: the L1 harness runs text against the
prompt; this plays synthetic speech from a speaker near the robot (so the real mic, XVF DSP,
wake word, VAD, Whisper, LLM, TTS, and speaker are all in the loop) and scores what the
supervisor reports on ``/ws/conversation``.

Commands (``python -m app.eval.air --help``):

- ``wake``  -- wake-word sweep. Positives ("alexa" in several voices, pitches, levels) and
  near-miss negatives; records each clip's peak score with sessions suppressed, then reports
  recall / false wakes per threshold and recommends one (``--apply`` sets it).
- ``eou``   -- end-of-speech + STT. Sentences with mid-sentence pauses at each
  ``ear.vad_silence_ms`` value: cut-offs, transcript word error rate, utterance-end latency.
- ``talk``  -- conversations: a scripted game or an L1 persona, the kid's lines either scripted
  or written live by Claude (``--kid claude``). Per turn: what Buddy heard, what it said,
  whether the follow-up opened without the wake word, and heard latency (end of the kid's
  speech -> Buddy's first sound), plus the L1 hard checks; ``--judge`` adds the Claude judge.

Timing uses only the Pi's clock: end of speech = end-of-utterance event - its reported silence;
Buddy's first sound = ``tts.event.started``. Nothing crosses machines.

Privacy (SIM-INTERACTION): every voice here is synthetic and every persona invented. Nothing
recorded leaves this machine; the run directory holds events and transcripts only.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import re
import statistics
import subprocess
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx
import numpy as np

SR = 16000
CLIP_DIR = Path(__file__).resolve().parents[2] / "eval_out" / "air" / "clips"
RUN_DIR = Path(__file__).resolve().parents[2] / "eval_out" / "air"

# ── Audio ───────────────────────────────────────────────────────────


def _pcm(x: np.ndarray) -> bytes:
    return np.clip(x, -32768, 32767).astype(np.int16).tobytes()


def _arr(pcm: bytes) -> np.ndarray:
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32)


def silence(ms: int) -> bytes:
    return b"\x00\x00" * int(SR * ms / 1000)


def shape(pcm: bytes, *, gain_db: float = 0.0, pitch: float = 1.0) -> bytes:
    """Level and pitch a clip. Pitch is a plain resample (tempo moves with it): crude, but
    enough to push an adult TTS voice toward a child's register."""
    x = _arr(pcm)
    if pitch != 1.0 and len(x) > 1:
        n = int(len(x) / pitch)
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
    return _pcm(x * 10 ** (gain_db / 20))


def trim(pcm: bytes, floor: float = 300.0) -> bytes:
    """Strip leading/trailing near-silence so 'end of clip' means end of speech."""
    x = _arr(pcm)
    idx = np.flatnonzero(np.abs(x) > floor)
    if len(idx) == 0:
        return pcm
    pad = int(0.03 * SR)
    return _pcm(x[max(0, idx[0] - pad) : idx[-1] + pad])


CALIBRATION = RUN_DIR / "calibration.json"


class Speaker:
    """The test speaker: an ALSA device on this machine (the dev box's line out), placed
    near the robot. Buddy itself still answers through the Pi's own speaker.

    ``gain_db`` is the calibrated level (``calibrate``): at 0 dB relative, a clip reaches the
    robot as loud as the reference voice did."""

    def __init__(self, device: str, gain_db: float = 0.0) -> None:
        self.device = device
        self.gain_db = gain_db

    async def play(self, pcm: bytes) -> None:
        if self.gain_db:
            pcm = shape(pcm, gain_db=self.gain_db)
        proc = await asyncio.create_subprocess_exec(
            "aplay", "-q", "-D", self.device, "-f", "S16_LE", "-r", str(SR), "-c", "1",
            stdin=subprocess.PIPE,
        )  # fmt: skip
        assert proc.stdin is not None
        proc.stdin.write(pcm)
        await proc.stdin.drain()
        proc.stdin.close()
        await proc.wait()


class Voices:
    """Synthetic speech from the server's Orpheus ``/tts`` (test voices), cached on disk."""

    def __init__(self, server: str) -> None:
        self.server = server.rstrip("/")
        CLIP_DIR.mkdir(parents=True, exist_ok=True)

    async def say(
        self, text: str, voice: str = "tara", *, tries: int = 4, max_wer: float = 0.2
    ) -> bytes:
        key = re.sub(r"[^a-z0-9]+", "_", f"{voice}_{text.lower()}")[:80]
        digest = hashlib.sha1(f"{voice}\n{text}".encode()).hexdigest()[:8]
        path = CLIP_DIR / f"{key}_{digest}.pcm"
        if path.exists():
            return path.read_bytes()
        # Orpheus is stochastic and sometimes garbles short lines (a lone "alexa" came
        # back spelled out, "L. X. A."): keep a take only if Whisper hears the words.
        best, best_wer = b"", 2.0
        async with httpx.AsyncClient(timeout=60) as c:
            for _ in range(tries):
                r = await c.post(
                    f"{self.server}/tts",
                    json={
                        "text": text,
                        "voice": voice,
                        "emotion": "neutral",
                        "intensity": 0,
                    },
                )
                r.raise_for_status()
                pcm = trim(r.content)
                s = await c.post(f"{self.server}/eval/stt", content=pcm)
                s.raise_for_status()
                err = wer(text, s.json().get("text", ""))
                if err < best_wer:
                    best, best_wer = pcm, err
                if err <= max_wer:
                    break
        if best_wer > max_wer:
            print(
                f"  warning: {voice} {text!r} never transcribed cleanly ({best_wer:.2f})"
            )
        path.write_bytes(best)
        return best


# ── The robot ───────────────────────────────────────────────────────


class Robot:
    """The supervisor seen from outside: params over HTTP, commands on /ws, and every
    conversation event from /ws/conversation, each stamped with the Pi's monotonic ms."""

    def __init__(self, host: str) -> None:
        self.http = f"http://{host}:8080"
        self.ws_base = f"ws://{host}:8080"
        self.events: list[dict[str, Any]] = []
        self._new = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []
        self._cmd_ws: Any = None
        self.log_path: Path | None = None

    async def __aenter__(self) -> Robot:
        import websockets

        self._conv_ws = await websockets.connect(f"{self.ws_base}/ws/conversation")
        self._cmd_ws = await websockets.connect(f"{self.ws_base}/ws", max_size=None)
        self._tasks.append(asyncio.create_task(self._read_conv()))
        self._tasks.append(asyncio.create_task(self._drain_cmd()))
        return self

    async def __aexit__(self, *_: object) -> None:
        for t in self._tasks:
            t.cancel()
        await self._conv_ws.close()
        await self._cmd_ws.close()

    async def _read_conv(self) -> None:
        async for raw in self._conv_ws:
            try:
                ev = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "personality.state.snapshot":
                continue
            self.events.append(ev)
            if self.log_path is not None:
                with self.log_path.open("a") as f:
                    f.write(raw + "\n")
            self._new.set()

    async def _drain_cmd(self) -> None:
        async for _ in self._cmd_ws:  # telemetry we don't need
            pass

    async def command(self, msg: dict[str, Any]) -> None:
        await self._cmd_ws.send(json.dumps(msg))

    async def get_params(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{self.http}/params")
            r.raise_for_status()
            return {p["name"]: p.get("value") for p in r.json()}

    async def set_params(self, items: dict[str, Any]) -> None:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"{self.http}/params", json={"items": items})
            r.raise_for_status()
            bad = {k: v for k, v in r.json().items() if not v.get("ok")}
            if bad:
                raise RuntimeError(f"params rejected: {bad}")

    async def mic_level(self) -> float | None:
        """The ear's last 1 s input RMS (dBFS) on its selected channel."""
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{self.http}/debug/workers")
            r.raise_for_status()
            return (r.json().get("ear", {}).get("health") or {}).get("input_rms_dbfs")

    async def levels(self, seconds: float) -> list[float]:
        """Sample the mic level for `seconds` (one new reading per second)."""
        out: list[float] = []
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            v = await self.mic_level()
            if v is not None and (not out or v != out[-1]):
                out.append(float(v))
            await asyncio.sleep(0.5)
        return out

    async def memory_tags(self) -> set[str]:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{self.http}/api/personality/memory")
            r.raise_for_status()
            return {e["tag"] for e in r.json().get("entries", [])}

    async def forget_memories(self, tags: list[str]) -> None:
        if not tags:
            return
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"{self.http}/api/personality/memory/forget", json={"tags": tags}
            )
            r.raise_for_status()

    async def status(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{self.http}/status")
            r.raise_for_status()
            return r.json()

    def mark(self) -> int:
        return len(self.events)

    def since(self, mark: int, type_: str | None = None) -> list[dict[str, Any]]:
        return [e for e in self.events[mark:] if type_ is None or e["type"] == type_]

    async def wait(
        self,
        mark: int,
        type_: str,
        timeout: float,
        where: Callable[[dict[str, Any]], bool] = lambda e: True,
    ) -> dict[str, Any] | None:
        """First event of `type_` after `mark` (matching `where`), or None on timeout."""
        deadline = time.monotonic() + timeout
        while True:
            for e in self.since(mark, type_):
                if where(e):
                    return e
            left = deadline - time.monotonic()
            if left <= 0:
                return None
            self._new.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._new.wait(), left)

    async def idle(self, timeout: float = 30.0) -> bool:
        """Wait until no session is open and nothing is speaking."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            st = await self.status()
            if not st.get("session_id") and not st.get("speaking"):
                return True
            await asyncio.sleep(0.3)
        return False

    async def cancel(self) -> None:
        await self.command({"type": "conversation.cancel"})
        await self.idle()


# ── Scoring helpers ─────────────────────────────────────────────────

_WORD = re.compile(r"[a-z0-9']+")


# Whisper writes US spelling and digits; the scripts don't. Not errors.
_SAME = {
    "favourite": "favorite", "colour": "color", "colours": "colors", "grey": "gray",
    "mum": "mom", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10", "twenty": "20",
}  # fmt: skip


_FILLERS = frozenset({"hmm", "hm", "um", "umm", "uh", "oh", "ooh", "ah", "er"})


def _words(text: str) -> list[str]:
    return [_SAME.get(w, w) for w in _WORD.findall(text.lower()) if w not in _FILLERS]


def wer(ref: str, hyp: str) -> float:
    r, h = _words(ref), _words(hyp)
    if not r:
        return 0.0 if not h else 1.0
    d = list(range(len(h) + 1))
    for i, rw in enumerate(r, 1):
        prev, d[0] = d[0], i
        for j, hw in enumerate(h, 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (rw != hw))
            prev, d[j] = d[j], cur
    return d[len(h)] / len(r)


def pct(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return s[min(len(s) - 1, int(q * (len(s) - 1) + 0.5))]


def fmt(x: float | None, unit: str = "") -> str:
    return "-" if x is None else f"{x:.0f}{unit}"


# ── wake: threshold sweep ───────────────────────────────────────────

WAKE = "alexa"
NEGATIVES = [
    "Alexander, come here please.",
    "I found a lexicon in the library.",
    "We went to Alaska last summer.",
    "Alex said hello.",
    "Hey buddy, what are you doing?",
    "Can you pass me the electric drill?",
    "I like pizza with extra cheese.",
    "Let's read a story before bed.",
    "My sister has a red bicycle.",
    "Is it time for lunch yet?",
]


@dataclass
class WakeClip:
    text: str
    voice: str
    pitch: float
    gain_db: float
    positive: bool
    peak: float = 0.0
    fired: bool = False


async def run_wake(
    robot: Robot,
    voices: Voices,
    speaker: Speaker,
    *,
    voice_list: list[str],
    pitches: list[float],
    gains: list[float],
    reps: int,
) -> list[WakeClip]:
    clips: list[WakeClip] = []
    for v in voice_list:
        for p in pitches:
            for g in gains:
                clips += [WakeClip(WAKE, v, p, g, True) for _ in range(reps)]
    for text in NEGATIVES:
        for v in voice_list[:2]:
            clips.append(WakeClip(text, v, 1.0, gains[0], False))

    # Record raw scores without starting conversations: a threshold above any score.
    await robot.command({"type": "ear.set_threshold", "threshold": 1.0})
    await robot.command({"type": "ear.stream_scores", "enabled": True})
    try:
        for i, c in enumerate(clips, 1):
            pcm = shape(
                await voices.say(c.text, c.voice), gain_db=c.gain_db, pitch=c.pitch
            )
            mark = robot.mark()
            await speaker.play(silence(200) + pcm)
            await asyncio.sleep(1.0)  # the model's window trails the audio
            scores = [
                max(e.get("scores", {}).values() or [0.0])
                for e in robot.since(mark, "ear.event.oww_score")
            ]
            c.peak = max(scores or [0.0])
            c.fired = bool(robot.since(mark, "ear.event.wake_word"))
            if robot.since(mark, "conv.session.started"):
                await robot.cancel()
            tag = "+" if c.positive else "-"
            print(f"  [{i}/{len(clips)}] {tag} {c.voice} x{c.pitch} {c.gain_db:+.0f}dB "
                  f"peak={c.peak:.2f}  {c.text[:40]}", flush=True)  # fmt: skip
    finally:
        await robot.command({"type": "ear.stream_scores", "enabled": False})
        params = await robot.get_params()
        await robot.command(
            {"type": "ear.set_threshold", "threshold": params["ear.wakeword_threshold"]}
        )
    return clips


def wake_report(clips: list[WakeClip]) -> tuple[str, float | None]:
    pos = [c for c in clips if c.positive]
    neg = [c for c in clips if not c.positive]
    max_neg = max((c.peak for c in neg), default=0.0)
    lines = ["| threshold | recall | false wakes |", "|---|---|---|"]
    best: float | None = None
    for t in [x / 100 for x in range(20, 96, 5)]:
        rec = sum(c.peak >= t for c in pos) / max(1, len(pos))
        fa = sum(c.peak >= t for c in neg)
        lines.append(f"| {t:.2f} | {rec:.0%} | {fa}/{len(neg)} |")
    # Highest recall with a margin above every near-miss; among ties, the higher threshold.
    candidates = [x / 100 for x in range(20, 96)]
    safe = [t for t in candidates if t >= max_neg + 0.1]
    if safe:
        best = max(safe, key=lambda t: (sum(c.peak >= t for c in pos), -t))
    by_voice: dict[str, list[float]] = {}
    for c in pos:
        by_voice.setdefault(f"{c.voice} x{c.pitch} {c.gain_db:+.0f}dB", []).append(
            c.peak
        )
    lines += ["", "| positive set | peak scores (min / median) |", "|---|---|"]
    for k, v in sorted(by_voice.items()):
        lines.append(f"| {k} | {min(v):.2f} / {statistics.median(v):.2f} |")
    lines += ["", f"Highest near-miss score: {max_neg:.2f} "
              f"({max(neg, key=lambda c: c.peak).text if neg else '-'})"]  # fmt: skip
    return "\n".join(lines), best


# ── eou: end-of-speech + STT ────────────────────────────────────────

# "|" marks a mid-sentence pause (a child stopping to think).
EOU_SENTENCES = [
    "What's your favourite colour?",
    "Can we play a game | where you guess the animal?",
    "I think the moon is | really really far away | right?",
    "My dog is called Biscuit and | he likes to chase his tail.",
    "Why do | why do fish live in water?",
]


@dataclass
class EouResult:
    silence_ms: int
    pause_ms: int
    sentence: str
    heard: str = ""
    wer: float = 1.0
    eou_count: int = 0
    cut_off: bool = False
    end_wait_ms: float | None = None  # end of speech -> end-of-utterance event


async def play_utterance(
    voices: Voices,
    speaker: Speaker,
    sentence: str,
    voice: str,
    pitch: float,
    pause_ms: int,
) -> None:
    parts = [p.strip() for p in sentence.split("|")]
    pcm = b""
    for i, part in enumerate(parts):
        if i:
            pcm += silence(pause_ms)
        pcm += shape(await voices.say(part, voice), pitch=pitch)
    await speaker.play(pcm)


async def wake_up(
    robot: Robot,
    voices: Voices,
    speaker: Speaker,
    voice: str,
    *,
    reuse_open: bool = True,
) -> bool:
    """Start a conversation: just talk if Buddy is already listening (a follow-up window
    is open), as a child would; otherwise say the wake word and wait for the session."""
    st = await robot.status()
    if reuse_open and st.get("session_id") and not st.get("speaking"):
        return True
    await robot.idle()
    mark = robot.mark()
    await speaker.play(silence(150) + await voices.say(WAKE, voice))
    ok = await robot.wait(mark, "conv.session.started", 3.0)
    await asyncio.sleep(0.35)  # the listening chime / attention face
    return ok is not None


async def run_eou(
    robot: Robot,
    voices: Voices,
    speaker: Speaker,
    *,
    silences: list[int],
    pauses: list[int],
    voice: str,
    pitch: float,
) -> list[EouResult]:
    params = await robot.get_params()
    keep = {
        "ear.vad_silence_ms": params["ear.vad_silence_ms"],
        "conversation.follow_up_window_s": params["conversation.follow_up_window_s"],
    }
    out: list[EouResult] = []
    try:
        await robot.set_params({"conversation.follow_up_window_s": 0})
        for s_ms in silences:
            await robot.set_params({"ear.vad_silence_ms": s_ms})
            for pause in pauses:
                for sent in EOU_SENTENCES:
                    r = EouResult(s_ms, pause, sent.replace(" | ", " "))
                    if not await wake_up(robot, voices, speaker, voice):
                        print(f"  wake failed: {sent}")
                        out.append(r)
                        continue
                    mark = robot.mark()
                    await play_utterance(voices, speaker, sent, voice, pitch, pause)
                    tr = await robot.wait(mark, "ai.conversation.transcription", 15)
                    eous = robot.since(mark, "ear.event.end_of_utterance")
                    r.eou_count = len(eous)
                    r.heard = (tr or {}).get("text", "")
                    r.wer = wer(r.sentence, r.heard)
                    r.cut_off = r.wer > 0.3 and len(_WORD.findall(r.heard)) < len(
                        _WORD.findall(r.sentence)
                    )
                    if eous:
                        r.end_wait_ms = float(eous[0].get("silence_ms", 0))
                    await robot.cancel()
                    out.append(r)
                    print(f"  silence={s_ms} pause={pause} wer={r.wer:.2f} "
                          f"{'CUT ' if r.cut_off else ''}heard={r.heard!r}", flush=True)  # fmt: skip
    finally:
        await robot.set_params(keep)
    return out


def eou_report(rs: list[EouResult]) -> str:
    lines = [
        "| vad_silence_ms | pause | cut off | mean WER | end-of-speech wait |",
        "|---|---|---|---|---|",
    ]
    keys = sorted({(r.silence_ms, r.pause_ms) for r in rs})
    for s_ms, pause in keys:
        g = [r for r in rs if r.silence_ms == s_ms and r.pause_ms == pause]
        lines.append(
            f"| {s_ms} | {pause} ms | {sum(r.cut_off for r in g)}/{len(g)} | "
            f"{statistics.mean(r.wer for r in g):.2f} | "
            f"{fmt(pct([r.end_wait_ms for r in g if r.end_wait_ms], 0.5), ' ms')} |"
        )
    return "\n".join(lines)


# ── calibrate: level the test speaker to a real voice ──────────────

PASSAGE = (
    "One, two, three, four, five, six, seven, eight, nine, ten. "
    "My robot is called Buddy, and he likes to play games with me. "
    "The quick brown fox jumps over the lazy dog."
)
RAW_CHANNEL = 2  # a raw Flex mic: no AGC to flatten the difference being measured


def speech_level(levels: list[float]) -> float | None:
    """Loudness while talking: the mean of the loudest 40 % of 1 s windows."""
    if not levels:
        return None
    top = sorted(levels, reverse=True)[: max(1, int(len(levels) * 0.4))]
    return statistics.mean(top)


@contextlib.asynccontextmanager
async def raw_mic(robot: Robot):  # type: ignore[no-untyped-def]
    params = await robot.get_params()
    await robot.set_params({"ear.mic_channel": RAW_CHANNEL})
    await asyncio.sleep(1.5)
    try:
        yield
    finally:
        # -1 ("use --usb-mic-channel") is not pushed to the ear, so switch to 0 first.
        await robot.set_params({"ear.mic_channel": 0})
        await robot.set_params({"ear.mic_channel": params.get("ear.mic_channel", -1)})


async def calibrate_reference(robot: Robot, seconds: float) -> dict[str, Any]:
    async with raw_mic(robot):
        quiet = await robot.levels(3)
        floor = min(quiet) if quiet else -90.0
        print(
            "\n>>> When ready, read this in a normal voice from where the speaker is:\n"
        )
        print(
            f"    {PASSAGE}\n    (keep going, or count, for {seconds:.0f} s)\n",
            flush=True,
        )
        # Wait (up to 3 min) for the talking to start, then measure.
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            v = await robot.mic_level()
            if v is not None and v > floor + 10:
                break
            await asyncio.sleep(0.3)
        else:
            raise RuntimeError(f"heard nobody talking (room {floor:.1f} dBFS)")
        print("    heard you, measuring...", flush=True)
        talk = await robot.levels(seconds)
    cal = {
        "reference_dbfs": speech_level(talk),
        "noise_dbfs": min(quiet) if quiet else None,
        "channel": RAW_CHANNEL,
        "samples": talk,
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if cal["reference_dbfs"] is None or (
        cal["noise_dbfs"] is not None and cal["reference_dbfs"] < cal["noise_dbfs"] + 6
    ):
        raise RuntimeError(f"no speech heard over the noise floor: {cal}")
    return cal


async def calibrate_speaker(
    robot: Robot, voices: Voices, device: str, ref: dict[str, Any]
) -> dict[str, Any]:
    pcm = await voices.say(PASSAGE, "tara")
    target = float(ref["reference_dbfs"])
    gain, tries, delta = -10.0, [], 99.0
    async with raw_mic(robot):
        for _ in range(6):
            sp = Speaker(device, gain)
            dur = len(pcm) / (2 * SR)
            play = asyncio.create_task(sp.play(pcm + pcm))
            await asyncio.sleep(0.8)
            got = speech_level(await robot.levels(2 * dur - 1.5))
            await play
            if got is None:
                raise RuntimeError("robot reported no level")
            tries.append({"gain_db": gain, "heard_dbfs": round(got, 1)})
            print(
                f"  gain {gain:+.1f} dB -> robot hears {got:.1f} dBFS (target {target:.1f})"
            )
            delta = target - got
            if abs(delta) <= 1.5:
                break
            gain = min(6.0, gain + delta)
            await asyncio.sleep(1.0)
    if gain >= 6.0 and abs(delta) > 1.5:
        print(
            "  !! still too quiet at +6 dB: turn the line-out amp or `amixer -c 1 sset PCM` up"
        )
    return {**ref, "device": device, "gain_db": round(gain, 1), "tries": tries}


# ── talk: conversations ─────────────────────────────────────────────

# Air-only scripts for a fluid conversation (not L1 personas, which lean to safety cases).
# Each line is what the kid says; "expect" words must appear in the reply to that line.
SCRIPTS: dict[str, dict[str, Any]] = {
    "twenty_questions": {
        "age": 7,
        "style": "A 7-year-old playing 20 questions with Buddy, thinking of a giraffe.",
        "lines": [
            ("Can we play twenty questions? I'm thinking of an animal.", ()),
            ("Yes it is!", ()),
            ("No, it doesn't.", ()),
            ("Yes, it's really tall!", ()),
            ("Yes! You got it! It's a giraffe!", ("giraffe",)),
        ],
    },
    "buddy_thinks": {
        "age": 7,
        "style": "A 7-year-old who asks Buddy to think of an animal, then guesses it with "
        "yes/no questions, and insists on a clear yes or no each time.",
        "lines": [("Buddy, you think of an animal and I'll guess it!", ())],
    },
    "memory_callback": {
        "age": 6,
        "style": "A 6-year-old telling Buddy about their pet, then checking it remembers.",
        "lines": [
            ("I have a cat called Pepper.", ()),
            ("She likes to sleep on my bed.", ()),
            ("What's my cat's name?", ("pepper",)),
        ],
    },
    "storyteller": {
        "age": 5,
        "style": "A chatty 5-year-old telling a long, wandering story about a dragon.",
        "lines": [
            ("Do you want to hear a story about a dragon?", ()),
            ("Once there was a dragon and | he was really really big and | green.", ()),
            ("And he ate all the cookies!", ()),
        ],
    },
}


@dataclass
class TurnResult:
    said: str
    heard: str = ""
    reply: str = ""
    wer: float = 1.0
    follow_up: bool | None = (
        None  # opened without the wake word (None on the first turn)
    )
    heard_latency_ms: float | None = None  # end of kid speech -> Buddy's first sound
    first_audio_ms: float | None = None  # supervisor's server round trip
    reply_s: float | None = None
    failures: list[str] = field(default_factory=list)


KidFn = Callable[[list[TurnResult]], Awaitable[str | None]]


async def run_talk(
    robot: Robot,
    voices: Voices,
    speaker: Speaker,
    next_line: KidFn,
    *,
    voice: str,
    pitch: float,
    pause_ms: int = 600,
    expect: Callable[[int], tuple[str, ...]] = lambda i: (),
    end_session: bool = True,
) -> list[TurnResult]:
    """One conversation: wake once, then each kid line goes into the follow-up window
    (falling back to the wake word, and recording the miss, when the window never opens)."""
    turns: list[TurnResult] = []
    line = await next_line(turns)
    if not line or not await wake_up(robot, voices, speaker, voice):
        return turns
    follow_up: bool | None = None
    while line:
        t = TurnResult(
            said=line.replace("|", " ").replace("  ", " "), follow_up=follow_up
        )
        mark = robot.mark()
        await play_utterance(voices, speaker, line, voice, pitch, pause_ms)
        eou = await robot.wait(mark, "ear.event.end_of_utterance", 20)
        # Transcription follows the end of utterance within a second; don't sit through
        # every later timeout when nothing was heard (cost 3 min in one memory run).
        tr = await robot.wait(mark, "ai.conversation.transcription", 10 if eou else 1)
        t.heard = (tr or {}).get("text", "")
        t.wer = wer(t.said, t.heard)
        if not tr:
            err = robot.since(mark, "ai.conversation.error")
            t.failures.append(
                "nothing transcribed"
                + (
                    f" ({err[-1].get('error') or err[-1].get('message')})"
                    if err
                    else ""
                )
                + ("" if eou else "; no end of utterance")
            )
            turns.append(t)
            print(f"  KID  : {t.said}\n  HEARD: (nothing)  {t.failures}", flush=True)
            break
        txt = await robot.wait(mark, "ai.conversation.assistant_text", 40)
        t.reply = (txt or {}).get("text", "")
        start = await robot.wait(mark, "tts.event.started", 40)
        fa = await robot.wait(mark, "ai.conversation.first_audio", 1)
        if eou and start:
            speech_end = eou["ts_mono_ms"] - float(eou.get("silence_ms", 0))
            t.heard_latency_ms = start["ts_mono_ms"] - speech_end
        if fa:
            t.first_audio_ms = fa.get("roundtrip_ms") or fa.get("first_audio_ms")

        # Ask for the kid's next line while Buddy is still talking: Claude has the
        # reply text already, and the follow-up window is short.
        turns.append(t)

        async def prepare(mark: int = mark) -> str | None:
            # Write and render the next line while Buddy talks: a live line synthesised
            # after the window opened missed the 6 s follow-up window (2026-11-15).
            nxt = await next_line(turns)
            if nxt:
                # After Buddy's own audio is generated, so the two don't share the GPU.
                await robot.wait(mark, "ai.conversation.done", 30)
                for part in nxt.split("|"):
                    if part.strip():  # a live line can't wait for many retakes
                        await voices.say(part.strip(), voice, tries=2, max_wer=0.35)
            return nxt

        line_task = asyncio.create_task(prepare())

        end = await robot.wait(
            mark,
            "tts.event.finished",
            90,
        ) or await robot.wait(mark, "tts.event.cancelled", 1)
        if start and end:
            t.reply_s = (end["ts_mono_ms"] - start["ts_mono_ms"]) / 1000
        if end and end["type"] == "tts.event.cancelled":
            t.failures.append("reply cut off (tts cancelled)")
        if not t.reply:
            t.failures.append("no reply")
        if not tr:
            t.failures.append("nothing transcribed")
        words = expect(len(turns) - 1)
        if words and not any(w in t.reply.lower() for w in words):
            t.failures.append(f"reply lacks {'/'.join(words)}")
        print(f"  KID  : {t.said}\n  HEARD: {t.heard}\n  BUDDY: {t.reply}\n"
              f"  heard latency {fmt(t.heard_latency_ms, ' ms')}  "
              f"follow-up {t.follow_up}  {t.failures or ''}", flush=True)  # fmt: skip

        line = await line_task
        if not line:
            break
        if end is None:
            t.failures.append("reply never finished")
            break
        # The follow-up window opens ~0.4 s after the reply ends; speak into it.
        fu = await robot.wait(
            mark,
            "conv.session.started",
            3.0,
            where=lambda e: e["ts_mono_ms"] >= end["ts_mono_ms"],
        )
        if fu is not None and any(
            e["ts_mono_ms"] > fu["ts_mono_ms"]
            for e in robot.since(mark, "conv.session.ended")
        ):  # the window closed before the line was ready: the rig was slow, not Buddy
            t.failures.append("rig: next line missed the follow-up window")
            fu = None
        if fu is not None:
            follow_up = True
            await asyncio.sleep(0.3)
        else:
            follow_up = False
            if not await wake_up(robot, voices, speaker, voice):
                t.failures.append("could not re-wake")
                break
    if end_session:
        await robot.cancel()
    return turns


def scripted_kid(lines: list[str]) -> KidFn:
    async def nxt(turns: list[TurnResult]) -> str | None:
        return lines[len(turns)] if len(turns) < len(lines) else None

    return nxt


def claude_kid(
    style: str, age: int | None, opener: str | None, max_turns: int
) -> KidFn:
    """The kid's side written live by Claude (a model other than the one under test)."""
    from app.eval.converse_sim import _SIM_USER_PROMPT, anthropic_chat

    chat = anthropic_chat()
    system = _SIM_USER_PROMPT.format(style=style, age=f" Age {age}." if age else "")
    system += (
        " Speak the way a child that age talks out loud: short, simple, sometimes trailing"
        " off. Plain words only: no emoji, no asterisks, no brackets. Answer Buddy's"
        " questions; if a game is going, keep playing it."
    )

    async def nxt(turns: list[TurnResult]) -> str | None:
        if len(turns) >= max_turns:
            return None
        if not turns and opener:
            return opener
        msgs: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for t in turns:
            msgs.append({"role": "assistant", "content": t.said})
            msgs.append({"role": "user", "content": t.reply or "..."})
        out = (await chat(msgs, None, 0.9)).strip().strip('"')
        return re.sub(r"[*\[\]()]", "", out)[:200] or None

    return nxt


def agenda_kid(
    style: str,
    age: int | None,
    goals: list[str],
    *,
    rules: str = "",
    max_turns: int = 10,
) -> KidFn:
    """A Claude-played child with goals for this conversation, who answers whatever Buddy
    just asked before moving on: a scripted kid ignored Buddy's questions."""
    from app.eval.converse_sim import _SIM_USER_PROMPT, anthropic_chat

    chat = anthropic_chat()
    plan = "\n".join(f"{i}. {g}" for i, g in enumerate(goals, 1))
    system = _SIM_USER_PROMPT.format(style=style, age=f" Age {age}." if age else "") + (
        " Speak the way a child that age talks out loud: short and simple. Plain words: no"
        " emoji, asterisks, or brackets.\n\nYour goals for this conversation, in order:\n"
        f"{plan}\n\nOne goal per turn. If Buddy just asked you something, answer it in a few"
        " words first, then do your next goal. When every goal is done, answer Buddy once"
        " more if it asked something, then say goodbye. After Buddy answers your goodbye,"
        " reply with exactly DONE." + (f"\n\n{rules}" if rules else "")
    )

    async def nxt(turns: list[TurnResult]) -> str | None:
        if len(turns) >= max_turns:
            return None
        msgs: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for t in turns:
            msgs.append({"role": "assistant", "content": t.said})
            msgs.append({"role": "user", "content": t.reply or "..."})
        out = (await chat(msgs, None, 0.9)).strip().strip('"')
        if not out or out.upper().startswith("DONE"):
            return None
        return re.sub(r"[*\[\]()]", "", out)[:200] or None

    return nxt


def talk_report(
    name: str, turns: list[TurnResult], judge: dict[str, Any] | None
) -> str:
    lat = [t.heard_latency_ms for t in turns if t.heard_latency_ms is not None]
    fus = [t.follow_up for t in turns if t.follow_up is not None]
    lines = [
        f"### {name}",
        "",
        f"Heard latency (end of kid speech -> Buddy's first sound): p50 "
        f"{fmt(pct(lat, 0.5), ' ms')}, p90 {fmt(pct(lat, 0.9), ' ms')}, max "
        f"{fmt(max(lat) if lat else None, ' ms')}. Follow-up opened without the wake word: "
        f"{sum(fus)}/{len(fus)}. Mean WER {statistics.mean(t.wer for t in turns or [TurnResult('')]):.2f}.",
        "",
        "| # | kid said | Buddy heard | Buddy said | latency | follow-up | issues |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, t in enumerate(turns, 1):
        lines.append(
            f"| {i} | {t.said} | {t.heard} | {t.reply} | {fmt(t.heard_latency_ms, ' ms')} | "
            f"{'-' if t.follow_up is None else ('yes' if t.follow_up else 'NO')} | "
            f"{'; '.join(t.failures)} |"
        )
    if judge:
        lines += ["", f"Judge: {json.dumps(judge)}"]
    return "\n".join(lines)


async def judge_talk(
    style: str, age: int | None, turns: list[TurnResult]
) -> dict[str, Any]:
    from app.eval.converse_sim import Dialogue, Exchange, anthropic_chat, judge_dialogue

    dlg = Dialogue(persona=style, kind="kid", age=age, seed=0)
    dlg.exchanges = [Exchange(user=t.heard or t.said, reply=t.reply) for t in turns]
    return await judge_dialogue(dlg, anthropic_chat(effort="medium"))


def hard_checks(turns: list[TurnResult]) -> None:
    from app.eval.converse_sim import Exchange, check_exchange

    for t in turns:
        t.failures += check_exchange(None, Exchange(user=t.heard, reply=t.reply))


# ── memory: facts across conversations, and across people ──────────

# Invented children with invented facts (SIM-INTERACTION privacy rule: no real names).
USERS: dict[str, dict[str, Any]] = {
    "kid5": {
        "voice": "zoe",
        "pitch": 1.15,
        "age": 5,
        "style": "A cheerful 5-year-old.",
        "tell_goals": [
            "Say hi to Buddy.",
            "Tell Buddy you have a cat called Pepper.",
            "Tell Buddy you love strawberry ice cream.",
        ],
        "ask_goals": [
            "Ask Buddy if it remembers your cat's name.",
            "Ask Buddy what ice cream you like.",
            "Ask Buddy what your pet is called.",
        ],
        "facts": [
            ("cat Pepper", ("pepper",)),
            ("strawberry ice cream", ("strawberr",)),
        ],
        "tell": [
            "Hi Buddy!",
            "I have a cat called Pepper.",
            "I love strawberry ice cream.",
        ],
        "probes": [
            ("Do you remember my cat's name?", ("pepper",)),
            ("What ice cream do I like?", ("strawberr",)),
            # Ambiguous on purpose: one shared memory and no speaker ID mixes the kids up.
            ("What's my pet called?", ("pepper",)),
        ],
    },
    "kid7": {
        "voice": "jess",
        "pitch": 1.08,
        "age": 7,
        "style": "A chatty 7-year-old.",
        "tell_goals": [
            "Say hi to Buddy.",
            "Tell Buddy you got a new dog and his name is Rocket.",
            "Tell Buddy your favourite sport is soccer.",
        ],
        "ask_goals": [
            "Ask Buddy what your dog is called.",
            "Ask Buddy which sport you like best.",
            "Ask Buddy what your pet is called.",
        ],
        "facts": [("dog Rocket", ("rocket",)), ("soccer", ("soccer",))],
        "tell": [
            "Hi Buddy, it's me.",
            "I got a new dog and his name is Rocket.",
            "My favourite sport is soccer.",
        ],
        "probes": [
            ("What's my dog called?", ("rocket",)),
            ("Which sport do I like best?", ("soccer",)),
            ("What's my pet called?", ("rocket",)),
        ],
    },
}


@dataclass
class ProbeResult:
    user: str
    question: str
    heard: str
    reply: str
    recalled: bool
    mixed_up: list[str]


async def run_memory(
    robot: Robot,
    voices: Voices,
    speaker: Speaker,
    *,
    users: list[str],
    gap: str,
    server: str,
    robot_id: str,
    kid: str = "scripted",
) -> list[ProbeResult]:
    if kid == "claude":
        return await _run_memory_claude(
            robot,
            voices,
            speaker,
            users=users,
            gap=gap,
            server=server,
            robot_id=robot_id,
        )
    await forget_history(robot, server, robot_id, require=False)  # a clean slate
    for u in users:  # conversation 1: each child tells Buddy about themselves
        cfg = USERS[u]
        print(f"-- {u}: telling", flush=True)
        await run_talk(
            robot, voices, speaker, scripted_kid(cfg["tell"]),
            voice=cfg["voice"], pitch=cfg["pitch"],
        )  # fmt: skip
    await asyncio.sleep(3)  # let the personality worker store the memory tags
    if gap == "long":
        await forget_history(robot, server, robot_id)
    else:
        print("-- short gap: conversation history kept", flush=True)
    out: list[ProbeResult] = []
    for u in users:  # conversation 2: each child checks what Buddy remembers
        cfg = USERS[u]
        others = sorted(
            {w for o in users if o != u for _, ws in USERS[o]["probes"] for w in ws}
        )
        print(f"-- {u}: asking", flush=True)
        turns = await run_talk(
            robot, voices, speaker, scripted_kid([q for q, _ in cfg["probes"]]),
            voice=cfg["voice"], pitch=cfg["pitch"],
        )  # fmt: skip
        for t, (q, expect) in zip(turns, cfg["probes"], strict=False):
            low = t.reply.lower()
            out.append(
                ProbeResult(
                    user=u,
                    question=q,
                    heard=t.heard,
                    reply=t.reply,
                    recalled=any(w in low for w in expect),
                    mixed_up=[w for w in others if w in low],
                )
            )
    return out


async def forget_history(
    robot: Robot, server: str, robot_id: str, *, require: bool = True
) -> None:
    """Drop the server's stashed history, once no session holds it live.

    A follow-up window can reopen a session after the rig's last line, pulling the stash
    back into a live connection that re-stashes it when it closes; forgetting in that
    window did nothing (2026-11-15). Wait for the robot and the server to be idle first.
    """
    async with httpx.AsyncClient(timeout=10) as c:
        for _ in range(60):
            await robot.idle()
            h = (await c.get(f"{server}/health")).json().get("converse_sessions", {})
            if robot_id not in (h.get("robots") or []):
                r = await c.post(
                    f"{server}/eval/forget_history", json={"robot_id": robot_id}
                )
                if r.json().get("dropped") or not require:
                    print("-- conversation history dropped", flush=True)
                    return
            await asyncio.sleep(1.0)
    raise RuntimeError(
        "could not drop the conversation history (session kept reopening)"
    )


async def _run_memory_claude(
    robot: Robot,
    voices: Voices,
    speaker: Speaker,
    *,
    users: list[str],
    gap: str,
    server: str,
    robot_id: str,
) -> list[ProbeResult]:
    """Memory test with Claude-played children who answer Buddy's questions as they go.

    Conversation 1: each child tells their facts. Conversation 2 (after the gap): each asks
    what Buddy remembers, without saying the answers. A fact counts as recalled when its
    word shows up in Buddy's replies; if the child said it anyway, it isn't scored.
    """
    await forget_history(robot, server, robot_id, require=False)  # a clean slate
    for i, u in enumerate(
        users
    ):  # one conversation; the next child talks into the window
        cfg = USERS[u]
        print(f"-- {u}: telling", flush=True)
        kid = agenda_kid(cfg["style"], cfg["age"], cfg["tell_goals"], max_turns=6)
        await run_talk(
            robot, voices, speaker, kid, voice=cfg["voice"], pitch=cfg["pitch"],
            end_session=i == len(users) - 1,
        )  # fmt: skip
    await asyncio.sleep(3)  # let the personality worker store the memory tags
    if gap == "long":
        await forget_history(robot, server, robot_id)
    else:
        await robot.idle()  # a new conversation later on: the wake word again
        print("-- short gap: conversation history kept", flush=True)
    out: list[ProbeResult] = []
    for i, u in enumerate(users):
        cfg = USERS[u]
        mine = [w for _, ws in cfg["facts"] for w in ws]
        others = sorted(
            {w for o in users if o != u for _, ws in USERS[o]["facts"] for w in ws}
        )
        rules = (
            "You are checking what Buddy remembers from last time. Never say the answers "
            f"yourself (not even if Buddy asks): don't say {', '.join(mine)}. If Buddy gets "
            "it wrong, say no and let it try once more."
        )
        print(f"-- {u}: asking", flush=True)
        kid = agenda_kid(
            cfg["style"], cfg["age"], cfg["ask_goals"], rules=rules, max_turns=8
        )
        turns = await run_talk(
            robot, voices, speaker, kid, voice=cfg["voice"], pitch=cfg["pitch"],
            end_session=i == len(users) - 1,
        )  # fmt: skip
        said = " ".join(t.said for t in turns).lower()
        replies = [t.reply for t in turns]
        mixed = [w for w in others if any(w in r.lower() for r in replies)]
        for j, (label, words) in enumerate(cfg["facts"]):
            hit = next((r for r in replies if any(w in r.lower() for w in words)), "")
            leaked = any(w in said for w in words)
            out.append(
                ProbeResult(
                    user=u,
                    question=label
                    + (" (the child said it: not scored)" if leaked else ""),
                    heard=" / ".join(t.heard for t in turns),
                    reply=hit or (replies[-1] if replies else ""),
                    recalled=bool(hit) and not leaked,
                    mixed_up=mixed if j == 0 else [],
                )
            )
    return out


def memory_report(gap: str, rs: list[ProbeResult]) -> str:
    lines = [
        f"## Memory across conversations ({gap} gap)",
        "",
        f"Recalled {sum(r.recalled for r in rs)}/{len(rs)}; "
        f"mixed up with another child {sum(bool(r.mixed_up) for r in rs)}/{len(rs)}.",
        "",
        "| child | asked | Buddy heard | Buddy said | recalled | mixed up |",
        "|---|---|---|---|---|---|",
    ]
    for r in rs:
        lines.append(
            f"| {r.user} | {r.question} | {r.heard} | {r.reply} | "
            f"{'yes' if r.recalled else 'NO'} | {', '.join(r.mixed_up)} |"
        )
    return "\n".join(lines)


# ── textlab: the same conversations typed, for fast prompt iteration ──


async def run_textlab(
    server: str, next_line: KidFn, *, robot_id: str
) -> list[TurnResult]:
    """Kid lines go to /converse as text (no audio, no robot): ~1 min a game instead of 5.
    Use it to iterate on prompts and profiles, then confirm over the air."""
    import websockets

    ws_url = server.replace("http", "ws", 1) + f"/converse?robot_id={robot_id}"
    turns: list[TurnResult] = []
    async with websockets.connect(ws_url, max_size=None) as ws:
        await ws.recv()  # listening
        while (line := await next_line(turns)) is not None:
            t = TurnResult(said=line, heard=line, wer=0.0)
            t0 = time.monotonic()
            await ws.send(json.dumps({"type": "text", "text": line}))
            while True:
                m = json.loads(await ws.recv())
                if m["type"] == "first_audio" and t.first_audio_ms is None:
                    t.first_audio_ms = (time.monotonic() - t0) * 1000
                elif m["type"] == "assistant_text":
                    t.reply = m.get("text", "")
                elif m["type"] in ("error", "turn_error"):
                    t.failures.append(f"server: {m.get('message') or m.get('reason')}")
                elif m["type"] == "done" or (m["type"] == "listening" and t.failures):
                    break
            if not t.reply:
                t.failures.append("no reply")
            turns.append(t)
            print(f"  KID  : {t.said}\n  BUDDY: {t.reply}", flush=True)
    return turns


# ── CLI ─────────────────────────────────────────────────────────────


def _csv(s: str, cast: Callable[[str], Any] = str) -> list[Any]:
    return [cast(x) for x in s.split(",") if x.strip()]


async def _main(a: argparse.Namespace) -> int:
    run = RUN_DIR / time.strftime("%Y%m%d-%H%M%S")
    run.mkdir(parents=True, exist_ok=True)
    voices = Voices(a.server)
    cal = json.loads(CALIBRATION.read_text()) if CALIBRATION.exists() else {}
    if a.cmd != "calibrate" and cal.get("device") != a.device:
        print(f"note: no calibration for {a.device}; playing at 0 dB (run `calibrate`)")
        cal = {}
    speaker = Speaker(a.device, float(cal.get("gain_db", 0.0)))
    report: list[str] = [
        f"# Over-the-air run {run.name}",
        "",
        f"`{' '.join(a.argv)}`",
        "",
    ]
    async with Robot(a.robot) as robot:
        robot.log_path = run / "events.jsonl"
        params = await robot.get_params()
        report.append(
            "Params: "
            + ", ".join(
                f"{k}={params.get(k)}"
                for k in sorted(params)
                if k.startswith(("ear.", "conversation.", "tts.speaker"))
            )
        )
        report.append("")
        if a.cmd == "calibrate":
            if a.reference:
                ref = await calibrate_reference(robot, a.seconds)
                CALIBRATION.write_text(json.dumps(ref, indent=1))
                report += [f"Reference voice: {ref['reference_dbfs']:.1f} dBFS speaking, "
                           f"{ref['noise_dbfs']:.1f} dBFS room ({ref['samples']})"]  # fmt: skip
            else:
                if "reference_dbfs" not in cal:
                    raise SystemExit("run `calibrate --reference` first")
                out = await calibrate_speaker(robot, voices, a.device, cal)
                CALIBRATION.write_text(json.dumps(out, indent=1))
                report += [f"Speaker {a.device}: gain {out['gain_db']:+.1f} dB matches the "
                           f"reference {cal['reference_dbfs']:.1f} dBFS ({out['tries']})"]  # fmt: skip
        elif a.cmd == "wake":
            clips = await run_wake(
                robot, voices, speaker,
                voice_list=_csv(a.voices), pitches=_csv(a.pitches, float),
                gains=_csv(a.gains, float), reps=a.reps,
            )  # fmt: skip
            text, best = wake_report(clips)
            report += ["## Wake word", "", text, "", f"Recommended threshold: {best}"]
            (run / "wake.json").write_text(
                json.dumps([asdict(c) for c in clips], indent=1)
            )
            if a.apply and best is not None:
                await robot.set_params({"ear.wakeword_threshold": best})
                report.append(f"Applied ear.wakeword_threshold = {best}")
        elif a.cmd == "eou":
            rs = await run_eou(
                robot, voices, speaker,
                silences=_csv(a.silences, int), pauses=_csv(a.pauses, int),
                voice=a.voice, pitch=a.pitch,
            )  # fmt: skip
            report += ["## End of speech + STT", "", eou_report(rs)]
            (run / "eou.json").write_text(json.dumps([asdict(r) for r in rs], indent=1))
        elif a.cmd == "memory":
            before = await robot.memory_tags()
            try:
                rs = await run_memory(
                    robot, voices, speaker, users=_csv(a.users), gap=a.gap,
                    server=a.server, robot_id=a.robot_id, kid=a.kid,
                )  # fmt: skip
            finally:
                await asyncio.sleep(3)
                added = sorted(await robot.memory_tags() - before)
                if not a.keep_memory:
                    await robot.forget_memories(added)
                print(f"-- memory tags this run added: {added} "
                      f"({'kept' if a.keep_memory else 'forgotten'})")  # fmt: skip
            report += [memory_report(a.gap, rs)]
            (run / "memory.json").write_text(
                json.dumps([asdict(r) for r in rs], indent=1)
            )
        elif a.cmd == "textlab":
            sc = SCRIPTS.get(a.script)
            style = sc["style"] if sc else a.script
            age = sc["age"] if sc else 7
            opener = sc["lines"][0][0] if sc else None
            for n in range(a.runs):
                kid = claude_kid(style, age, opener, a.turns)
                turns = await run_textlab(
                    a.server, kid, robot_id=f"textlab-{run.name}-{n}"
                )
                hard_checks(turns)
                (run / f"text{n + 1}.json").write_text(
                    json.dumps([asdict(t) for t in turns], indent=1)
                )
                judge = None
                if a.judge and turns:
                    try:
                        judge = await judge_talk(style, age, turns)
                    except Exception as exc:  # noqa: BLE001
                        judge = {"error": f"judge failed: {exc}"[:300]}
                report += [
                    talk_report(f"{a.script} (text) run {n + 1}", turns, judge),
                    "",
                ]
                (run / "report.md").write_text("\n".join(report) + "\n")
        elif a.cmd == "talk":
            if a.script in SCRIPTS:
                sc = SCRIPTS[a.script]
                style, age = sc["style"], sc["age"]
                lines = [ln for ln, _ in sc["lines"]]
                expects = [e for _, e in sc["lines"]]
                expect = lambda i: expects[i] if i < len(expects) else ()  # noqa: E731
                kid = (
                    claude_kid(style, age, lines[0], a.turns)
                    if a.kid == "claude"
                    else scripted_kid(lines)
                )
            else:
                from app.eval.personas import PERSONAS

                per = {p.id: p for p in PERSONAS}[a.script]
                style, age = per.style, per.age
                lines = [t.text for t in per.turns]
                expect = lambda i: ()  # noqa: E731
                kid = (
                    claude_kid(style, age, lines[0] if lines else None, a.turns)
                    if a.kid == "claude"
                    else scripted_kid(lines)
                )
            for n in range(a.runs):
                turns = await run_talk(
                    robot, voices, speaker, kid,
                    voice=a.voice, pitch=a.pitch, pause_ms=a.pause, expect=expect,
                )  # fmt: skip
                hard_checks(turns)
                # Save the conversation before judging: a judge failure must not lose it.
                (run / f"talk{n + 1}.json").write_text(
                    json.dumps([asdict(t) for t in turns], indent=1)
                )
                judge = None
                if a.judge and turns:
                    try:
                        judge = await judge_talk(style, age, turns)
                    except Exception as exc:  # noqa: BLE001 -- report it, keep the run
                        judge = {"error": f"judge failed: {exc}"[:300]}
                report += [
                    talk_report(f"{a.script} ({a.kid}) run {n + 1}", turns, judge),
                    "",
                ]
                (run / "report.md").write_text("\n".join(report) + "\n")
    (run / "report.md").write_text("\n".join(report) + "\n")
    print("\n".join(report))
    print(f"\nRun directory: {run}")
    return 0


def main() -> int:
    import sys

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--robot", default="192.168.55.180", help="supervisor host (port 8080)"
    )
    ap.add_argument(
        "--server", default="http://localhost:8100", help="planner server (/tts)"
    )
    ap.add_argument(
        "--device",
        default="plughw:CARD=Audio,DEV=0",
        help="ALSA device of the test speaker on this machine (default: the line out)",
    )
    ap.add_argument("--robot-id", default="robot-1", help="the supervisor's --robot-id")
    ap.add_argument("--voice", default="zoe", help="Orpheus voice for the kid")
    ap.add_argument(
        "--pitch", type=float, default=1.15, help="resample factor toward a child"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("calibrate", help="level the test speaker to a real voice")
    c.add_argument("--reference", action="store_true", help="measure a person talking")
    c.add_argument("--seconds", type=float, default=15)
    w = sub.add_parser("wake", help="wake-word threshold sweep")
    w.add_argument("--voices", default="zoe,mia,tara,leo,dan,jess")
    w.add_argument("--pitches", default="1.0,1.2")
    w.add_argument("--gains", default="0,-10")
    w.add_argument("--reps", type=int, default=2)
    w.add_argument("--apply", action="store_true", help="set the recommended threshold")
    e = sub.add_parser("eou", help="end-of-speech + STT sweep")
    e.add_argument("--silences", default="500,650,800")
    e.add_argument("--pauses", default="400,800")
    m = sub.add_parser("memory", help="facts across conversations and children")
    m.add_argument("--users", default="kid5,kid7", help=f"from {', '.join(USERS)}")
    m.add_argument("--kid", choices=["claude", "scripted"], default="claude",
                   help="claude: children who answer Buddy's questions; scripted: fixed lines")  # fmt: skip
    m.add_argument("--keep-memory", action="store_true",
                   help="keep the long-term memory tags the test children created")  # fmt: skip
    m.add_argument("--gap", choices=["short", "long"], default="short",
                   help="short: history kept (<30 min); long: dropped, long-term memory only")  # fmt: skip
    x = sub.add_parser(
        "textlab", help="Claude-kid conversation typed to /converse (fast)"
    )
    x.add_argument("--script", default="twenty_questions",
                   help="a script name, or free text describing the kid")  # fmt: skip
    x.add_argument("--turns", type=int, default=16)
    x.add_argument("--runs", type=int, default=1)
    x.add_argument("--judge", action="store_true")
    t = sub.add_parser("talk", help="conversation over the air")
    t.add_argument("--script", default="twenty_questions",
                   help=f"one of {', '.join(SCRIPTS)} or an L1 persona id")  # fmt: skip
    t.add_argument("--kid", choices=["claude", "scripted"], default="claude")
    t.add_argument("--turns", type=int, default=8, help="max turns with --kid claude")
    t.add_argument("--runs", type=int, default=1)
    t.add_argument(
        "--pause", type=int, default=600, help="ms for a '|' pause in a line"
    )
    t.add_argument(
        "--judge", action="store_true", help="Claude judge on each transcript"
    )
    a = ap.parse_args()
    a.argv = sys.argv[1:]
    return asyncio.run(_main(a))


if __name__ == "__main__":
    raise SystemExit(main())
