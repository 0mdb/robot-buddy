---
name: deploy
description: Deploy or update the supervisor on the Raspberry Pi. Only invoke manually.
argument-hint: "[v1|v2] [install|update]"
disable-model-invocation: true
allowed-tools: Bash(bash:*), Bash(git:*), Bash(pytest:*), Bash(python -m pytest:*), Bash(systemctl:*), Bash(ssh:*), Read, Grep, Glob
---

Deploy or update the robot-buddy supervisor. Parse `$ARGUMENTS` for version and action.

## Argument parsing

- `v1` or `supervisor` → original supervisor (`deploy/install.sh` / `deploy/update.sh`)
- `v2` or `supervisor_v2` → v2 supervisor (`deploy/install.sh --v2` / `deploy/update.sh --v2`)
- `install` → first-time setup
- `update` → pull and restart (default if not specified)
- No version → ask which one

## Pre-flight checks (always run first)

1. Check for uncommitted changes:
```bash
git -C /home/ben/robot-buddy status --porcelain
```
2. Check current branch:
```bash
git -C /home/ben/robot-buddy branch --show-current
```
3. Run tests for the target package:
```bash
cd /home/ben/robot-buddy/supervisor && python -m pytest tests/ -v
```
or for v2:
```bash
cd /home/ben/robot-buddy/supervisor_v2 && python -m pytest tests/ -v
```

If pre-flight fails, stop and report. Do NOT deploy with failing tests or uncommitted changes.

## Deploy scripts

### First-time install
```bash
cd /home/ben/robot-buddy && bash deploy/install.sh        # v1
cd /home/ben/robot-buddy && bash deploy/install.sh --v2   # v2
```

### Update (pull + restart)
```bash
cd /home/ben/robot-buddy && bash deploy/update.sh        # v1
cd /home/ben/robot-buddy && bash deploy/update.sh --v2   # v2
```

## Service management

```bash
# v1
sudo systemctl status robot-buddy-supervisor
sudo systemctl restart robot-buddy-supervisor
sudo journalctl -u robot-buddy-supervisor -f

# v2
sudo systemctl status robot-buddy-supervisor-v2
sudo systemctl restart robot-buddy-supervisor-v2
sudo journalctl -u robot-buddy-supervisor-v2 -f
```

## Runtime configuration

- v1: `/etc/robot-buddy/supervisor.env` — sets `SUPERVISOR_ARGS`
- v2: `/etc/robot-buddy/supervisor-v2.env` — sets `SUPERVISOR_ARGS`

Common flags: `--mock`, `--no-face`, `--no-vision`, `--http-port 8080`, `--planner-api http://...`

## Rules

1. ALWAYS run pre-flight checks first.
2. ALWAYS confirm with the user before deploying.
3. Report the service status after deployment.
4. If deployment fails, check `journalctl` for the service logs.
