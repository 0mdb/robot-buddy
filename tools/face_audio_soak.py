#!/usr/bin/env python3
"""CDC audio soak tool for esp32-face-display.

Runs a full-duplex stress pass over face CDC transport:
- Downlink: sends continuous AUDIO_DATA 10 ms chunks to speaker
- Uplink: enables mic stream and counts MIC_AUDIO telemetry packets
- Talking: toggles SET_TALKING while streaming

Useful for quick production bring-up and repeatable soak checks.
"""

from __future__ import annotations

import argparse
import math
import struct
import time
from dataclasses import dataclass

try:
    import serial
except ImportError as exc:  # pragma: no cover - runtime environment dependent
    raise SystemExit(
        "pyserial is required. Install it with: pip install pyserial"
    ) from exc


# Face command IDs
CMD_SET_TALKING = 0x23
CMD_AUDIO_DATA = 0x24
CMD_SET_CONFIG = 0x25

# Face config IDs
CFG_AUDIO_MIC_STREAM_ENABLE = 0xA3

# Face telemetry IDs
TEL_HEARTBEAT = 0x93
TEL_MIC_AUDIO = 0x94

SAMPLE_RATE = 16000
CHUNK_MS = 10
SAMPLES_PER_CHUNK = SAMPLE_RATE * CHUNK_MS // 1000  # 160
BYTES_PER_CHUNK = SAMPLES_PER_CHUNK * 2  # 320
HEARTBEAT_AUDIO_FMT = struct.Struct("<IIIIIIIIIIBB")


def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def cobs_encode(src: bytes) -> bytes:
    out = bytearray()
    code_pos = 0
    out.append(0)
    code = 1
    for b in src:
        if b == 0:
            out[code_pos] = code
            code_pos = len(out)
            out.append(0)
            code = 1
        else:
            out.append(b)
            code += 1
            if code == 0xFF:
                out[code_pos] = code
                code_pos = len(out)
                out.append(0)
                code = 1
    out[code_pos] = code
    return bytes(out)


def cobs_decode(src: bytes) -> bytes:
    out = bytearray()
    i = 0
    n = len(src)
    while i < n:
        code = src[i]
        if code == 0:
            raise ValueError("invalid COBS code=0")
        i += 1
        end = i + code - 1
        if end > n:
            raise ValueError("truncated COBS frame")
        out.extend(src[i:end])
        if code != 0xFF and end < n:
            out.append(0)
        i = end
    return bytes(out)


def build_packet(pkt_type: int, seq: int, payload: bytes) -> bytes:
    raw = bytes([pkt_type & 0xFF, seq & 0xFF]) + payload
    raw += struct.pack("<H", crc16_ccitt(raw))
    return cobs_encode(raw) + b"\x00"


def build_set_talking(seq: int, talking: bool, energy: int) -> bytes:
    return build_packet(
        CMD_SET_TALKING,
        seq,
        struct.pack("<BB", 1 if talking else 0, max(0, min(255, energy))),
    )


def build_set_config_u32(seq: int, param_id: int, value: int) -> bytes:
    return build_packet(
        CMD_SET_CONFIG,
        seq,
        struct.pack("<BI", param_id & 0xFF, value & 0xFFFFFFFF),
    )


def build_audio_data(seq: int, pcm: bytes) -> bytes:
    if len(pcm) > BYTES_PER_CHUNK:
        raise ValueError(f"pcm too large: {len(pcm)} > {BYTES_PER_CHUNK}")
    if len(pcm) % 2:
        raise ValueError("pcm length must be even")
    payload = struct.pack("<H", len(pcm)) + pcm
    return build_packet(CMD_AUDIO_DATA, seq, payload)


def make_tone_chunk(hz: float, amplitude: float) -> bytes:
    amp = max(0.0, min(0.99, amplitude))
    a = int(32767 * amp)
    out = bytearray(BYTES_PER_CHUNK)
    for i in range(SAMPLES_PER_CHUNK):
        t = i / SAMPLE_RATE
        s = int(a * math.sin(2.0 * math.pi * hz * t))
        struct.pack_into("<h", out, i * 2, s)
    return bytes(out)


@dataclass
class SoakStats:
    tx_audio_chunks: int = 0
    tx_set_talking: int = 0
    tx_set_config: int = 0
    rx_mic_audio_packets: int = 0
    rx_heartbeat_packets: int = 0
    rx_bad_crc: int = 0
    rx_bad_cobs: int = 0
    rx_short: int = 0
    mic_seq_gaps: int = 0
    last_mic_seq: int = 0
    last_hb_audio: tuple[int, int, int, int, int, int, int, int, int, int, int, int] | None = None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Face CDC full-duplex audio soak")
    p.add_argument("--port", required=True, help="Serial path (/dev/serial/by-id/...)")
    p.add_argument("--baud", type=int, default=115200, help="Serial baudrate")
    p.add_argument("--seconds", type=float, default=30.0, help="Soak duration")
    p.add_argument("--tone-hz", type=float, default=440.0, help="Downlink tone frequency")
    p.add_argument("--tone-amp", type=float, default=0.15, help="Downlink tone amplitude (0-1)")
    p.add_argument("--talk-energy", type=int, default=160, help="SET_TALKING energy (0-255)")
    p.add_argument("--quiet", action="store_true", help="Suppress periodic progress output")
    return p.parse_args()


def send_packet(
    ser: serial.Serial,
    seq: int,
    pkt: bytes,
    stats: SoakStats,
    kind: str,
) -> int:
    ser.write(pkt)
    ser.flush()
    if kind == "audio":
        stats.tx_audio_chunks += 1
    elif kind == "talk":
        stats.tx_set_talking += 1
    elif kind == "cfg":
        stats.tx_set_config += 1
    return (seq + 1) & 0xFF


def drain_frames(ser: serial.Serial, buf: bytearray, stats: SoakStats) -> None:
    data = ser.read(2048)
    if not data:
        return
    buf.extend(data)
    while True:
        try:
            end = buf.index(0)
        except ValueError:
            break
        frame = bytes(buf[:end])
        del buf[: end + 1]
        if not frame:
            continue
        try:
            raw = cobs_decode(frame)
        except ValueError:
            stats.rx_bad_cobs += 1
            continue
        if len(raw) < 4:
            stats.rx_short += 1
            continue
        body = raw[:-2]
        crc_rx = struct.unpack_from("<H", raw, len(raw) - 2)[0]
        if crc16_ccitt(body) != crc_rx:
            stats.rx_bad_crc += 1
            continue
        pkt_type = body[0]
        payload = body[2:]
        if pkt_type == TEL_MIC_AUDIO:
            if len(payload) < 8:
                stats.rx_short += 1
                continue
            chunk_seq, chunk_len, _flags, _reserved = struct.unpack_from("<IHBB", payload, 0)
            if len(payload) < 8 + chunk_len:
                stats.rx_short += 1
                continue
            stats.rx_mic_audio_packets += 1
            if stats.last_mic_seq != 0 and chunk_seq > stats.last_mic_seq + 1:
                stats.mic_seq_gaps += (chunk_seq - stats.last_mic_seq - 1)
            stats.last_mic_seq = chunk_seq
        elif pkt_type == TEL_HEARTBEAT:
            stats.rx_heartbeat_packets += 1
            # Heartbeat extension starts after base+usb payload (17 + 50 = 67 bytes).
            if len(payload) >= 67 + HEARTBEAT_AUDIO_FMT.size:
                stats.last_hb_audio = HEARTBEAT_AUDIO_FMT.unpack_from(payload, 67)


def print_progress(stats: SoakStats, elapsed: float) -> None:
    line = (
        f"t={elapsed:5.1f}s tx_audio={stats.tx_audio_chunks} "
        f"rx_mic={stats.rx_mic_audio_packets} hb={stats.rx_heartbeat_packets} "
        f"mic_gaps={stats.mic_seq_gaps} bad_crc={stats.rx_bad_crc} bad_cobs={stats.rx_bad_cobs}"
    )
    print(line)


def main() -> int:
    args = parse_args()
    duration_s = max(1.0, float(args.seconds))
    tone_chunk = make_tone_chunk(args.tone_hz, args.tone_amp)
    stats = SoakStats()
    seq = 0
    rx_buf = bytearray()

    print(f"opening {args.port} @ {args.baud}")
    with serial.Serial(args.port, args.baud, timeout=0.01) as ser:
        # Give CDC a brief settle window after open to avoid dropping first config frame.
        time.sleep(0.2)
        seq = send_packet(
            ser,
            seq,
            build_set_config_u32(seq, CFG_AUDIO_MIC_STREAM_ENABLE, 1),
            stats,
            "cfg",
        )
        time.sleep(0.05)
        seq = send_packet(
            ser,
            seq,
            build_set_config_u32(seq, CFG_AUDIO_MIC_STREAM_ENABLE, 1),
            stats,
            "cfg",
        )
        seq = send_packet(ser, seq, build_set_talking(seq, True, args.talk_energy), stats, "talk")

        start = time.monotonic()
        end = start + duration_s
        next_tx = start
        next_progress = start + 1.0

        while True:
            now = time.monotonic()
            if now >= end:
                break

            drain_frames(ser, rx_buf, stats)

            while now >= next_tx:
                seq = send_packet(ser, seq, build_audio_data(seq, tone_chunk), stats, "audio")
                next_tx += CHUNK_MS / 1000.0

            if not args.quiet and now >= next_progress:
                print_progress(stats, now - start)
                next_progress += 1.0

            time.sleep(0.001)

        seq = send_packet(ser, seq, build_set_talking(seq, False, 0), stats, "talk")
        seq = send_packet(
            ser,
            seq,
            build_set_config_u32(seq, CFG_AUDIO_MIC_STREAM_ENABLE, 0),
            stats,
            "cfg",
        )

        tail_end = time.monotonic() + 0.5
        while time.monotonic() < tail_end:
            drain_frames(ser, rx_buf, stats)
            time.sleep(0.001)

    print("\nsummary:")
    print(f"  tx_audio_chunks={stats.tx_audio_chunks}")
    print(f"  tx_set_talking={stats.tx_set_talking}")
    print(f"  tx_set_config={stats.tx_set_config}")
    print(f"  rx_mic_audio_packets={stats.rx_mic_audio_packets}")
    print(f"  rx_heartbeat_packets={stats.rx_heartbeat_packets}")
    print(f"  mic_seq_gaps={stats.mic_seq_gaps}")
    print(f"  rx_bad_crc={stats.rx_bad_crc}")
    print(f"  rx_bad_cobs={stats.rx_bad_cobs}")
    print(f"  rx_short={stats.rx_short}")
    if stats.last_hb_audio is not None:
        (
            spk_rx_chunks,
            spk_rx_drops,
            spk_rx_bytes,
            spk_play_chunks,
            spk_play_errors,
            mic_capture_chunks,
            mic_tx_chunks,
            mic_tx_drops,
            mic_overruns,
            mic_queue_depth,
            mic_stream_enabled,
            _audio_reserved,
        ) = stats.last_hb_audio
        print("  heartbeat.audio:")
        print(
            "    "
            f"speaker_rx_chunks={spk_rx_chunks} "
            f"speaker_rx_drops={spk_rx_drops} "
            f"speaker_rx_bytes={spk_rx_bytes}"
        )
        print(
            "    "
            f"speaker_play_chunks={spk_play_chunks} "
            f"speaker_play_errors={spk_play_errors}"
        )
        print(
            "    "
            f"mic_capture_chunks={mic_capture_chunks} "
            f"mic_tx_chunks={mic_tx_chunks} "
            f"mic_tx_drops={mic_tx_drops} "
            f"mic_overruns={mic_overruns} "
            f"mic_queue_depth={mic_queue_depth} "
            f"mic_stream_enabled={mic_stream_enabled}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
