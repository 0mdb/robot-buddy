---
name: status
description: Quick snapshot of project state. Use at session start to understand current status, priorities, and connected hardware.
---

Quick project status snapshot for session orientation.

## Steps

### 1. Git State
```bash
git -C /home/ben/robot-buddy status --short
git -C /home/ben/robot-buddy log --oneline -5
```

### 2. Current Priority
Read the top of `docs/TODO.md` — the "Execution Order & Priority" section shows current recommended work.

### 3. Hardware Detection
```bash
ls -l /dev/serial/by-id 2>/dev/null || echo "No serial devices"
ls -l /dev/robot_* 2>/dev/null || echo "No udev symlinks"
```

### 4. Test Status (quick)
Report the last known test status. If user wants fresh results, suggest `just test-all`.

### 5. Summary
Present a concise summary:
- Current branch + uncommitted changes
- Top 3 priority items from TODO
- Connected hardware (if any)
- Any blocking issues

## Rules

1. Keep output concise — this is for quick orientation, not deep analysis.
2. Read TODO.md but only report the top priorities, not the full backlog.
3. Don't run tests automatically — just report what's known and offer to run them.
