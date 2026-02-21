---
name: preflight
description: Pre-commit quality checklist. Run lint + tests + git status to verify everything is clean before committing.
disable-model-invocation: true
allowed-tools: Bash(just:*), Bash(git:*), Read, Grep, Glob
---

Run all quality checks before committing. No arguments needed.

## Steps

### 1. Git status
```bash
git -C /home/ben/robot-buddy status --short
```
Report uncommitted changes. Informational — don't block on it.

### 2. Full lint + test suite
```bash
just preflight
```

This runs `just lint` then `just test-all` in sequence.

## Output

Summarize results as a checklist:
```
Preflight results:
  [pass/fail] ruff format
  [pass/fail] ruff check
  [pass/fail] clang-format
  [pass/fail] cppcheck
  [pass/fail] biome (dashboard)
  [pass/fail] tsc (dashboard)
  [pass/fail] supervisor tests (X passed, Y failed)
  [pass/fail] server tests (X passed, Y failed)
  [pass/fail] supervisor_v2 tests (X passed, Y failed)
  [pass/fail] dashboard tests (X passed, Y failed)
```

## Rules

1. Run ALL checks — don't stop on first failure.
2. If any check fails, clearly report what failed and suggest fixes.
3. If all pass, say so clearly — the user can commit with confidence.
