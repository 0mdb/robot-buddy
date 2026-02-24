"""Vision mask persistence + validation utilities.

Stores exclusion polygons (normalized coordinates) for vision detectors.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

MASK_VERSION = 1
MAX_POLYS_PER_MASK = 32
MAX_POINTS_PER_POLY = 64


def default_mask() -> dict[str, Any]:
    return {
        "version": MASK_VERSION,
        "floor": {"enabled": False, "exclude_polys": []},
        "ball": {"enabled": False, "exclude_polys": []},
    }


def _clamp01(v: float) -> float:
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def validate_and_normalize_mask(body: Any) -> dict[str, Any]:
    """Validate/clamp a VisionMask.v1 payload and return normalized dict.

    - Drops invalid polygons (<3 valid points)
    - Truncates to sane limits (max polys + max points)
    - Clamps coordinates to [0..1]
    """
    if not isinstance(body, dict):
        raise ValueError("mask body must be an object")

    version = body.get("version", MASK_VERSION)
    try:
        version_int = int(version)
    except Exception as e:
        raise ValueError("mask.version must be an int") from e
    if version_int != MASK_VERSION:
        raise ValueError(f"unsupported mask version: {version_int}")

    out: dict[str, Any] = {"version": MASK_VERSION}

    for key in ("floor", "ball"):
        raw = body.get(key, {})
        if not isinstance(raw, dict):
            raw = {}

        enabled = raw.get("enabled", False)
        enabled_bool = (
            bool(int(enabled)) if isinstance(enabled, (int, float)) else bool(enabled)
        )

        raw_polys = raw.get("exclude_polys", [])
        polys: list[list[list[float]]] = []
        if isinstance(raw_polys, list):
            for poly in raw_polys[:MAX_POLYS_PER_MASK]:
                if not isinstance(poly, list):
                    continue
                points: list[list[float]] = []
                for pt in poly[:MAX_POINTS_PER_POLY]:
                    if not isinstance(pt, (list, tuple)) or len(pt) != 2:
                        continue
                    x, y = pt[0], pt[1]
                    if not isinstance(x, (int, float)) or not isinstance(
                        y, (int, float)
                    ):
                        continue
                    points.append([_clamp01(float(x)), _clamp01(float(y))])
                if len(points) >= 3:
                    polys.append(points)

        out[key] = {"enabled": enabled_bool, "exclude_polys": polys}

    return out


def load_mask(path: Path) -> dict[str, Any]:
    """Load mask JSON from disk; return defaults if missing/invalid."""
    if not path.exists():
        return default_mask()
    try:
        raw = json.loads(path.read_text())
        return validate_and_normalize_mask(raw)
    except Exception as e:
        log.warning("failed to load mask file %s: %s", path, e)
        return default_mask()


def save_mask_atomic(path: Path, mask: dict[str, Any]) -> None:
    """Write mask JSON to disk atomically (temp + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(mask, indent=2) + "\n")
    tmp.replace(path)
