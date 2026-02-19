from __future__ import annotations

import struct

from supervisor.devices.lip_sync import LipSyncTracker, compute_rms_energy


def _pcm_for_level(level: int, samples: int = 160) -> bytes:
    return struct.pack(f"<{samples}h", *([level] * samples))


def test_compute_rms_energy_is_monotonic():
    quiet = compute_rms_energy(_pcm_for_level(600))
    medium = compute_rms_energy(_pcm_for_level(3000))
    loud = compute_rms_energy(_pcm_for_level(12000))
    assert 0 <= quiet <= medium <= loud <= 255


def test_lip_sync_tracker_smooths_attack_and_release():
    tracker = LipSyncTracker()
    low = tracker.update_chunk(_pcm_for_level(300))
    high = tracker.update_chunk(_pcm_for_level(10000))
    falling = tracker.update_chunk(_pcm_for_level(600))

    assert high > low
    assert falling < high
    assert falling >= 0
