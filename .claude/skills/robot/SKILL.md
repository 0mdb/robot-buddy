---
name: robot
description: Manage the robot remotely via SSH — deploy, test, logs, status, restart, stop. Use when the user wants to interact with the Raspberry Pi.
---

Manage the robot (Raspberry Pi at 192.168.55.201) remotely via SSH. Parse `$ARGUMENTS` for the operation.

## Constants

- **SSH target:** `192.168.55.201`
- **Remote repo:** `~/robot-buddy`
- **Service:** `robot-buddy-supervisor`
- **Supervisor dir:** `~/robot-buddy/supervisor`

## Argument parsing

First token is the **operation** (required):

| Token | Operation |
|-------|-----------|
| `deploy` | Push + pull + restart |
| `test` | Run pytest on the Pi |
| `logs` | View recent journalctl logs |
| `status` | Show systemctl status |
| `restart` | Restart the systemd service |
| `stop` | Stop the systemd service |
| `start` | Start the systemd service |

Any remaining tokens are passed as extra options (e.g., test filter, log line count).

If no operation is given, ask the user what they want to do.

## Operations

### deploy — push, pull, restart

**Pre-flight (run locally on dev machine):**

1. Check for uncommitted changes:
```bash
git -C /home/ben/robot-buddy status --porcelain
```
If there are uncommitted changes, warn the user and stop. Do NOT deploy with dirty working tree.

2. Check current branch:
```bash
git -C /home/ben/robot-buddy branch --show-current
```

3. Push to origin:
```bash
git -C /home/ben/robot-buddy push origin "$(git -C /home/ben/robot-buddy branch --show-current)"
```

**Remote (SSH to Pi):**

4. Run update script:
```bash
ssh 192.168.55.201 'cd ~/robot-buddy && bash deploy/update.sh'
```

5. Verify service status:
```bash
ssh 192.168.55.201 'sudo systemctl status robot-buddy-supervisor --no-pager -l'
```

6. Show recent logs to confirm healthy startup:
```bash
ssh 192.168.55.201 'sudo journalctl -u robot-buddy-supervisor -n 20 --no-pager'
```

### test — run pytest on the Pi

```bash
ssh 192.168.55.201 'cd ~/robot-buddy/supervisor && .venv/bin/python -m pytest tests/ -v'
```

With a test filter (extra args):
```bash
ssh 192.168.55.201 'cd ~/robot-buddy/supervisor && .venv/bin/python -m pytest tests/ -v -k "test_something"'
```

### logs — view recent service logs

Default (last 50 lines):
```bash
ssh 192.168.55.201 'sudo journalctl -u robot-buddy-supervisor -n 50 --no-pager'
```

With custom line count (if user specifies a number):
```bash
ssh 192.168.55.201 'sudo journalctl -u robot-buddy-supervisor -n 100 --no-pager'
```

IMPORTANT: Never use `-f` (follow) — it streams indefinitely and will hang. Always use `-n` with `--no-pager`.

### status — check service status

```bash
ssh 192.168.55.201 'sudo systemctl status robot-buddy-supervisor --no-pager -l'
```

### restart — restart the service

Confirm with the user before restarting, then:
```bash
ssh 192.168.55.201 'sudo systemctl restart robot-buddy-supervisor'
```

Wait briefly, then show status:
```bash
ssh 192.168.55.201 'sleep 2 && sudo systemctl status robot-buddy-supervisor --no-pager -l'
```

### stop — stop the service

Confirm with the user before stopping, then:
```bash
ssh 192.168.55.201 'sudo systemctl stop robot-buddy-supervisor'
```

Show status to confirm:
```bash
ssh 192.168.55.201 'sudo systemctl status robot-buddy-supervisor --no-pager -l || true'
```

### start — start the service

```bash
ssh 192.168.55.201 'sudo systemctl start robot-buddy-supervisor'
```

Wait briefly, then show status:
```bash
ssh 192.168.55.201 'sleep 2 && sudo systemctl status robot-buddy-supervisor --no-pager -l'
```

## SSH connectivity check

If any SSH command fails with a connection error, report:
1. The Pi may be powered off or not on the network.
2. Suggest: `ssh 192.168.55.201 'echo ok'` to test connectivity.
3. Check that the Pi is connected via USB Ethernet (192.168.55.x subnet).

## Rules

1. **Confirm before destructive operations** — restart, stop, and deploy require user confirmation before proceeding.
2. **Never use journalctl -f** — it streams forever. Always use `-n <count> --no-pager`.
3. **Deploy must push first** — always push local commits before SSH-ing in to pull.
4. **Deploy must have clean working tree** — do not deploy with uncommitted changes.
5. **Report results clearly** — show service status and relevant log lines after any state-changing operation.
6. **If an operation is ambiguous**, ask the user to clarify rather than guessing.
