---
name: test
description: Run tests for supervisor, server, or supervisor_v2. Use when the user asks to run tests, verify changes, check for regressions, or wants to make sure things still work.
argument-hint: "[supervisor|server|sv2|all] [test filter]"
allowed-tools: Bash(pytest:*), Bash(python -m pytest:*), Bash(uv run pytest:*), Read, Grep, Glob
---

Run the project test suite. Parse `$ARGUMENTS` to determine scope and filter.

## Argument parsing

- No arguments or `all` → run all three test suites
- `supervisor` → supervisor tests only
- `server` → server tests only
- `sv2` or `supervisor_v2` → supervisor_v2 tests only
- Any additional text after the component name is a pytest filter (passed as `-k`)

## Commands

### Supervisor
```bash
cd /home/ben/robot-buddy/supervisor && python -m pytest tests/ -v
```

### Server
```bash
cd /home/ben/robot-buddy/server && uv run pytest tests/ -v
```

### Supervisor V2
```bash
cd /home/ben/robot-buddy/supervisor_v2 && python -m pytest tests/ -v
```

### With keyword filter
Append `-k "<filter>"` to the pytest command.

## Rules

1. Always use `-v` for verbose output.
2. If tests fail, read the failing test file and the source it tests to understand the failure — don't just report the error.
3. Summarize results: total passed, failed, skipped per component.
4. If a specific test file is mentioned (e.g., `test_state_machine`), run only that file.
