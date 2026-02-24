---
name: deploy
description: Deploy or update the supervisor on the Raspberry Pi. Only invoke manually.
---

Deploy or update the robot-buddy supervisor. Parse `$ARGUMENTS` for the action.

## Argument parsing

- `install` → first-time setup
- `update` → pull and restart (default if not specified)

## Pre-flight checks (always run first)

1. Check for uncommitted changes:
```bash
git -C /home/ben/robot-buddy status --porcelain
```
2. Check current branch:
```bash
git -C /home/ben/robot-buddy branch --show-current
```
3. Run tests:
```bash
cd /home/ben/robot-buddy/supervisor && uv run pytest tests/ -v
```

If pre-flight fails, stop and report. Do NOT deploy with failing tests or uncommitted changes.

## Deploy scripts

### First-time install
```bash
cd /home/ben/robot-buddy && bash deploy/install.sh
```

### Update (pull + restart)
```bash
cd /home/ben/robot-buddy && bash deploy/update.sh
```

## Service management

```bash
sudo systemctl status robot-buddy-supervisor
sudo systemctl restart robot-buddy-supervisor
sudo journalctl -u robot-buddy-supervisor -f
```

## Runtime configuration

- Config: `/etc/robot-buddy/supervisor.env` — sets `SUPERVISOR_ARGS`

Common flags: `--mock`, `--no-face`, `--no-vision`, `--http-port 8080`, `--planner-api http://...`

## Rules

1. ALWAYS run pre-flight checks first.
2. ALWAYS confirm with the user before deploying.
3. Report the service status after deployment.
4. If deployment fails, check `journalctl` for the service logs.
