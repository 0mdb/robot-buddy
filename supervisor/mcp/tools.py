"""Tool implementations for the MCP server.

Plain async functions, bound to supervisor runtime (tick, audit, workers)
via closure in build_mcp_server. Each call is recorded to the audit
broadcaster so the dashboard MCP Activity panel can show what tools the
consumer LLM has used.

Phase 0 scope: get_state, get_memory, recent_events, look.
"""

from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp.types import ImageContent, TextContent

from supervisor.mcp.audit import McpAuditBroadcaster, McpAuditEntry

if TYPE_CHECKING:
    from supervisor.core.tick_loop import TickLoop
    from supervisor.core.worker_manager import WorkerManager

log = logging.getLogger(__name__)

VALID_MEMORY_CATEGORIES = frozenset({"name", "topic", "ritual", "tone", "preference"})

# Frames older than this are treated as stale — don't return them even when
# consent is on. Covers the case where vision_worker crashed, the camera
# disconnected, or MJPEG got disabled after boot. 2 s is generous relative to
# the 5 Hz MJPEG rate while still catching real staleness.
LOOK_FRAME_STALE_MS = 2000.0

# Ball-detection confidence threshold at which we report ball_detected=True.
# Matches the event-bus acquire threshold in PlannerEventBus.
LOOK_BALL_ACQUIRE_CONF = 0.60


def _summarize(result: object, *, max_len: int = 120) -> str:
    """Short human-readable preview of a tool result for the audit log."""
    if isinstance(result, dict):
        keys = list(result.keys())[:5]
        preview = ", ".join(f"{k}={result.get(k)!r}" for k in keys)
    elif isinstance(result, list):
        preview = f"list(len={len(result)})"
    else:
        preview = repr(result)
    if len(preview) > max_len:
        preview = preview[: max_len - 1] + "…"
    return preview


async def get_state_impl(
    tick: TickLoop,
    audit: McpAuditBroadcaster,
    turn_id: str | None = None,
) -> dict:
    """Return a compact snapshot of the robot's current state for an LLM.

    A curated subset of /status — trims verbose telemetry a consumer model
    doesn't need mid-turn (raw speeds, clock sync state, vision config).
    """
    t0 = time.monotonic()
    try:
        robot = tick.robot.to_dict()
        world = tick.world.to_dict()
        result = {
            "mode": robot.get("mode"),
            "fault_flags": robot.get("fault_flags"),
            "face_mood": robot.get("face_mood"),
            "face_gesture": robot.get("face_gesture"),
            "reflex_connected": robot.get("reflex_connected"),
            "face_connected": robot.get("face_connected"),
            "range_mm": robot.get("range_mm"),
            "range_status": robot.get("range_status"),
            "tilt_angle_deg": robot.get("tilt_angle_deg"),
            "ball_confidence": world.get("ball_conf"),
            "ball_bearing_deg": world.get("ball_bearing"),
            "vision_age_ms": world.get("vision_age_ms"),
            "speaking": world.get("speaking"),
            "ptt_active": world.get("ptt_active"),
            "active_skill": world.get("active_skill"),
            "planner_connected": world.get("planner_connected"),
        }
        audit.record(
            McpAuditEntry(
                ts_mono=t0,
                tool="get_state",
                args={},
                ok=True,
                latency_ms=(time.monotonic() - t0) * 1000.0,
                result_summary=_summarize(result),
                turn_id=turn_id or "",
            )
        )
        return result
    except Exception as exc:
        audit.record(
            McpAuditEntry(
                ts_mono=t0,
                tool="get_state",
                args={},
                ok=False,
                latency_ms=(time.monotonic() - t0) * 1000.0,
                turn_id=turn_id or "",
                error=f"{type(exc).__name__}: {exc}",
            )
        )
        raise


async def get_memory_impl(
    memory_path: Path,
    category: str | None,
    audit: McpAuditBroadcaster,
    turn_id: str | None = None,
) -> dict:
    """Return the consumer-LLM-facing view of personality memory.

    Reads the on-disk memory file (same file the personality worker writes
    and the /api/personality/memory HTTP endpoint serves). Trims verbose
    internals — bias axes, decay constants, reinforcement counters — and
    computes current decayed strength so the model can tell strong memories
    from faded ones.
    """
    t0 = time.monotonic()
    args = {"category": category}
    try:
        if category is not None and category not in VALID_MEMORY_CATEGORIES:
            raise ValueError(
                f"unknown category {category!r}; "
                f"expected one of {sorted(VALID_MEMORY_CATEGORIES)}"
            )

        if not memory_path.exists():
            result: dict = {"entries": [], "entry_count": 0, "path": str(memory_path)}
        else:
            raw = json.loads(memory_path.read_text())
            now = time.time()
            curated: list[dict] = []
            for e in raw.get("entries", []):
                if category is not None and e.get("category") != category:
                    continue
                last = float(e.get("last_reinforced_ts", 0.0))
                initial = float(e.get("initial_strength", 1.0))
                lam = float(e.get("decay_lambda", 0.0))
                age_s = max(0.0, now - last)
                # Match MemoryEntry.current_strength: exp decay, no tier floor
                # since tier constants live in personality/memory.py and we
                # don't want to import the full module graph just to floor
                # values; raw decay is accurate enough for LLM consumption.
                strength = initial * math.exp(-lam * age_s) if lam else initial
                curated.append(
                    {
                        "tag": e.get("tag"),
                        "category": e.get("category"),
                        "strength": round(max(0.0, strength), 3),
                        "reinforcement_count": int(e.get("reinforcement_count", 0)),
                        "age_days": round(age_s / 86400.0, 2),
                    }
                )
            # Sort strongest-first so the LLM sees the most load-bearing
            # memories at the top of its context.
            curated.sort(key=lambda x: x["strength"], reverse=True)
            result = {
                "entries": curated,
                "entry_count": len(curated),
                "path": str(memory_path),
            }

        audit.record(
            McpAuditEntry(
                ts_mono=t0,
                tool="get_memory",
                args=args,
                ok=True,
                latency_ms=(time.monotonic() - t0) * 1000.0,
                result_summary=_summarize(result),
                turn_id=turn_id or "",
            )
        )
        return result
    except Exception as exc:
        audit.record(
            McpAuditEntry(
                ts_mono=t0,
                tool="get_memory",
                args=args,
                ok=False,
                latency_ms=(time.monotonic() - t0) * 1000.0,
                error=f"{type(exc).__name__}: {exc}",
                turn_id=turn_id or "",
            )
        )
        raise


async def recent_events_impl(
    tick: TickLoop,
    pattern: str | None,
    n: int,
    audit: McpAuditBroadcaster,
    turn_id: str | None = None,
) -> dict:
    """Return recent PlannerEventBus entries, optionally filtered.

    `pattern` is a case-insensitive substring match on event type (e.g.
    "button", "ball", "fault"). `n` caps results; clamped to [1, 50].
    """
    t0 = time.monotonic()
    args = {"pattern": pattern, "n": n}
    try:
        n_clamped = max(1, min(50, int(n)))
        # Pull a generous window then filter, so `pattern` doesn't produce
        # misleadingly empty results when the last few events are unrelated.
        events = tick._event_bus.latest(50)
        if pattern:
            needle = pattern.lower()
            events = [e for e in events if needle in e.type.lower()]
        events = events[-n_clamped:]
        payload = {
            "events": [
                {
                    "type": e.type,
                    "payload": e.payload,
                    "t_mono_ms": round(e.t_mono_ms, 1),
                    "seq": e.seq,
                }
                for e in events
            ],
            "count": len(events),
        }
        audit.record(
            McpAuditEntry(
                ts_mono=t0,
                tool="recent_events",
                args=args,
                ok=True,
                latency_ms=(time.monotonic() - t0) * 1000.0,
                result_summary=_summarize(payload),
                turn_id=turn_id or "",
            )
        )
        return payload
    except Exception as exc:
        audit.record(
            McpAuditEntry(
                ts_mono=t0,
                tool="recent_events",
                args=args,
                ok=False,
                latency_ms=(time.monotonic() - t0) * 1000.0,
                error=f"{type(exc).__name__}: {exc}",
                turn_id=turn_id or "",
            )
        )
        raise


def _memory_consent_from_workers(workers: WorkerManager) -> bool:
    """Read the parental memory-consent flag from the personality worker.

    Mirrors the /api/personality/memory HTTP endpoint's consent lookup so the
    MCP tool gate matches the dashboard's view.
    """
    try:
        snap = workers.worker_snapshot() or {}
        health = (snap.get("personality") or {}).get("health") or {}
        return bool(health.get("memory_consent", False))
    except Exception:
        # Fail closed — if we can't read the consent flag, don't return images.
        return False


async def look_impl(
    tick: TickLoop,
    workers: WorkerManager,
    hint: str | None,
    audit: McpAuditBroadcaster,
    turn_id: str | None = None,
) -> list[Any]:
    """Return the most recent camera frame + ball-detection metadata.

    Returns a list of MCP content blocks:
      - ImageContent (JPEG) if consent is on and a fresh frame is available.
      - TextContent (JSON metadata) always, explaining what the consumer is
        seeing (or why no image came back: consent-off, stale, no-frame).

    The JPEG is the same 320x240 downsized frame the /video MJPEG endpoint
    serves; no new frame capture or encoding happens here. `hint` is
    free-form text the caller can echo for its own reasoning ("what colors
    do you see?") — we log it but don't interpret it.

    Privacy: when memory_consent is off, no image bytes ever leave this
    tool. The audit log still records a thumbnail (same JPEG) for the
    dashboard — it's already visible via /video; the boundary is whether
    it reaches the consumer LLM, not whether it's visible to a parent.

    `turn_id` correlates this call with a /converse turn on the planner so
    the dashboard can cross-reference ConversationStudio cards with MCP
    Activity rows.
    """
    t0 = time.monotonic()
    args = {"hint": hint}
    try:
        consent = _memory_consent_from_workers(workers)
        world = tick.world
        age_ms = world.vision_age_ms
        frame_seq = int(world.vision_frame_seq)
        ball_conf = float(world.ball_confidence)
        ball_bearing = float(world.ball_bearing_deg)
        jpeg_b64 = world.latest_jpeg_b64 or ""

        metadata: dict[str, Any] = {
            "ball_detected": ball_conf >= LOOK_BALL_ACQUIRE_CONF,
            "ball_confidence": round(ball_conf, 2),
            "ball_bearing_deg": round(ball_bearing, 1),
            "vision_age_ms": round(age_ms, 1),
            "vision_frame_seq": frame_seq,
            "consent": "on" if consent else "off",
            "hint": hint,
        }

        include_image = True
        if not consent:
            include_image = False
            metadata["reason"] = "consent_off"
        elif not jpeg_b64:
            include_image = False
            metadata["reason"] = "no_frame"
        elif age_ms < 0 or age_ms > LOOK_FRAME_STALE_MS:
            include_image = False
            metadata["reason"] = "stale"

        content: list[Any] = []
        if include_image:
            content.append(
                ImageContent(type="image", data=jpeg_b64, mimeType="image/jpeg")
            )
        content.append(
            TextContent(type="text", text=json.dumps(metadata, separators=(",", ":")))
        )

        # Audit summary: compact human-readable line, NEVER the JPEG bytes.
        summary_parts = [
            f"consent={metadata['consent']}",
            f"image={'y' if include_image else 'n'}",
            f"ball={'y' if metadata['ball_detected'] else 'n'}",
            f"age_ms={metadata['vision_age_ms']}",
            f"seq={frame_seq}",
        ]
        if not include_image and "reason" in metadata:
            summary_parts.append(f"reason={metadata['reason']}")
        # Include a thumbnail in the audit entry when a fresh frame exists
        # AND consent is on. Already-captured JPEG; no re-encode needed.
        audit_image = jpeg_b64 if (include_image and consent) else ""
        audit.record(
            McpAuditEntry(
                ts_mono=t0,
                tool="look",
                args=args,
                ok=True,
                latency_ms=(time.monotonic() - t0) * 1000.0,
                result_summary=" ".join(summary_parts),
                turn_id=turn_id or "",
                image_b64=audit_image,
            )
        )
        return content
    except Exception as exc:
        audit.record(
            McpAuditEntry(
                ts_mono=t0,
                tool="look",
                args=args,
                ok=False,
                latency_ms=(time.monotonic() - t0) * 1000.0,
                error=f"{type(exc).__name__}: {exc}",
                turn_id=turn_id or "",
            )
        )
        raise
