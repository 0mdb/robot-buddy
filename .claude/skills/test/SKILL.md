---
name: test
description: Run tests for supervisor, server, supervisor_v2, or dashboard. Use when the user asks to run tests, verify changes, check for regressions, or wants to make sure things still work.
argument-hint: "[supervisor|server|sv2|dashboard|all] [test filter]"
allowed-tools: Bash(just:*), Bash(pytest:*), Bash(python -m pytest:*), Bash(uv run pytest:*), Bash(npx:*), Read, Grep, Glob
---

Run the project test suite. Parse `$ARGUMENTS` to determine scope and filter.

## Argument parsing

- No arguments or `all` → run all test suites
- `supervisor` → supervisor tests only
- `server` → server tests only
- `sv2` or `supervisor_v2` → supervisor_v2 tests only
- `dashboard` or `web` or `ui` → dashboard tests only (Vitest)
- Any additional text after the component name is a test filter (passed as `-k` for pytest, or as positional for vitest)

## Commands

### All tests
```bash
just test-all
```

### Supervisor
```bash
just test-supervisor
```
With filter: `just test-supervisor -k "test_boot"`

### Server
```bash
just test-server
```

### Supervisor V2
```bash
just test-sv2
```

### Dashboard
```bash
just test-dashboard
```
With filter: `just test-dashboard src/lib/ringBuffer.test.ts`

### Specific test file (Python)
```bash
just test-supervisor tests/test_state_machine.py
```

## Rules

1. Always use `-v` for verbose output (built into just recipes).
2. If tests fail, read the failing test file and the source it tests to understand the failure — don't just report the error.
3. Summarize results: total passed, failed, skipped per component.
4. If a specific test file is mentioned (e.g., `test_state_machine`), run only that file.
