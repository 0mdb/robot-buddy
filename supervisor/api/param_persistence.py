"""Param persistence — save/load param values to/from disk.

Only supervisor-owned, runtime-mutable params are persisted.
File location: ~/.config/robot-buddy/params.json
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from supervisor.api.param_registry import ParamRegistry

log = logging.getLogger(__name__)

_PARAMS_FILE = Path("~/.config/robot-buddy/params.json").expanduser()


def load_params(reg: ParamRegistry, path: Path = _PARAMS_FILE) -> None:
    """Apply saved values from disk to registry.

    Unknown or boot_only params are silently skipped.
    """
    if not path.exists():
        return
    try:
        saved: dict[str, Any] = json.loads(path.read_text())
    except Exception as e:
        log.warning("param_persistence: failed to load %s: %s", path, e)
        return

    applied = 0
    for name, value in saved.items():
        p = reg.get(name)
        if p is None or p.mutable == "boot_only":
            continue
        ok, reason = reg.set(name, value)
        if ok:
            applied += 1
        else:
            log.warning("param_persistence: skipped %s=%s: %s", name, value, reason)

    log.info("param_persistence: loaded %d params from %s", applied, path)


def on_param_changed(name: str, value: Any, path: Path = _PARAMS_FILE) -> None:
    """Upsert one param value in the JSON file (atomic write)."""
    try:
        existing: dict[str, Any] = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text())
            except Exception:
                pass  # overwrite corrupt file

        existing[name] = value

        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".params_")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(existing, f, indent=2)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise
    except Exception as e:
        log.warning("param_persistence: failed to save %s=%s: %s", name, value, e)
