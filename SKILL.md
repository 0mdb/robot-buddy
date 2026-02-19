# ESP32 Face V2 Firmware Flash

Repeatable operator-assisted flash workflow for `esp32-face-v2`.

## Human Checkpoints (Required)

1. **Download Mode Checkpoint**
   - Ask operator to manually put device into download mode.
   - Do not flash yet.
   - Wait for explicit confirmation (example: `ready to flash`).

2. **Post-Flash Reboot Checkpoint**
   - Ask operator to manually restart/reset device after flash completes.
   - Do not validate yet.
   - Wait for explicit confirmation (example: `device restarted`).

## Always Recheck Port After Reboot

Device path can change after reset/reenumeration. Do not assume previous `by-id` path is still valid.

```bash
ls -l /dev/serial/by-id 2>/dev/null || true
ls -l /dev/ttyACM* 2>/dev/null || true
```

Use the currently-present face device path from `/dev/serial/by-id` when possible.
If needed, fall back to `/dev/ttyACM0`.

## Standard Flash

```bash
cd /home/ben/robot-buddy/esp32-face-v2
source ~/esp/esp-idf/export.sh >/tmp/idf_export.log 2>&1
idf.py -b 460800 -p <CURRENT_FACE_PORT> flash
```

## Permissions + Environment Notes

- Serial access may fail with `Errno 13 Permission denied` on `/dev/ttyACM*` or `/dev/serial/by-id/*`.
- In sandboxed sessions, elevated permission may be required for monitor and serial probes.
- `idf.py monitor` requires a TTY/PTY; non-TTY execution can fail even when flash works.

## Monitor Caveat (Important)

This firmware uses a binary packet protocol on the face serial link. `idf.py monitor` output is often binary/gibberish and is not a reliable functional validation signal.

## Preferred Validation Path

Prefer validation via supervisor-facing telemetry and command-response behavior, not raw monitor text.

1. Connect using supervisor stack (`SerialTransport` + `FaceClient`).
2. Confirm live packet flow (`rx_face_status_packets` and heartbeat counts increasing).
3. Send active checks (`SET_STATE`, `GESTURE`, `SET_TALKING`) and verify telemetry reflects changes.
4. Restore neutral/default state after probes.

## Common Pivots (Happens Frequently)

1. `by-id` path changes after reboot; re-enumerate every flash cycle.
2. Monitor command may fail without TTY; rerun with PTY.
3. Monitor output may be binary and unreadable by design.
4. Serial permission errors require elevated execution path.
5. `supervisor --mock` may fail in restricted environments due `openpty` permission.
6. `uv run` may fail in restricted environments due cache path permissions; use local `./.venv/bin/python` fallback.
