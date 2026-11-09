---
name: dev
description: Run local supervisor + dashboard for frontend development. Builds dashboard, starts mock supervisor, and opens browser. Use when iterating on dashboard/UI changes.
---

Run a local development environment for frontend iteration. Parse `$ARGUMENTS` for the operation.

## Constants

- **Project root:** `/home/ben/robot-buddy`
- **Supervisor dir:** `/home/ben/robot-buddy/supervisor`
- **Dashboard dir:** `/home/ben/robot-buddy/dashboard`
- **Local URL:** `http://localhost:8080`

## Argument parsing

First token is the **operation** (default: `start`):

| Token | Operation |
|-------|-----------|
| `start` | Build dashboard + start mock supervisor |
| `stop` | Stop running local supervisor |
| `rebuild` | Rebuild dashboard only (supervisor stays running) |
| `restart` | Rebuild dashboard + restart supervisor |

## Operations

### start — build dashboard + start mock supervisor

1. Build the dashboard:
```bash
cd /home/ben/robot-buddy/dashboard && npm run build
```

2. Start the mock supervisor in the background. **Must run from repo root** (not `supervisor/`) because `python -m supervisor` relies on CWD to find the `supervisor` package:
```bash
cd /home/ben/robot-buddy && supervisor/.venv/bin/python -m supervisor --mock --no-face --no-vision
```
Run this in the background using `run_in_background: true`.

3. Report the local URL: `http://localhost:8080`

### stop — stop running local supervisor

Find and stop any running local supervisor process:
```bash
pkill -f "python -m supervisor --mock" || echo "No local supervisor running"
```

### rebuild — rebuild dashboard assets only

Rebuild without restarting the supervisor. The supervisor serves from `supervisor/static/` so a rebuild is instantly available on hard-refresh.

```bash
cd /home/ben/robot-buddy/dashboard && npm run build
```

Report: "Dashboard rebuilt. Hard-refresh the browser (Ctrl+Shift+R) to pick up changes."

### restart — rebuild + restart supervisor

1. Stop running supervisor:
```bash
pkill -f "python -m supervisor --mock" || true
```

2. Rebuild dashboard:
```bash
cd /home/ben/robot-buddy/dashboard && npm run build
```

3. Start supervisor in background (from repo root):
```bash
cd /home/ben/robot-buddy && supervisor/.venv/bin/python -m supervisor --mock --no-face --no-vision
```

## Rules

1. **Always build dashboard before starting** — ensures static assets are fresh.
2. **Use `--mock --no-face --no-vision`** — local dev doesn't have real hardware.
3. **Run supervisor in background** — use `run_in_background: true` so it doesn't block.
4. **Port 8080** — default supervisor port. Warn if already in use.
