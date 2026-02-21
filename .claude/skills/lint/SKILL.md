---
name: lint
description: Run linting, formatting, and static analysis checks across Python, C/C++, and TypeScript/React code. Use when the user asks to lint, check code quality, format code, run type checking, or verify code before committing.
argument-hint: "[python|cpp|dashboard|all] [--fix]"
allowed-tools: Bash(just:*), Bash(ruff:*), Bash(ruff check:*), Bash(ruff format:*), Bash(clang-format:*), Bash(cppcheck:*), Bash(npx:*), Read, Grep, Glob
---

Run linting and static analysis. Parse `$ARGUMENTS` to determine scope and mode.

## Argument parsing

- No arguments or `all` → run everything (Python + C++ + Dashboard)
- `python` → Python checks only
- `cpp` or `c++` or `firmware` → C/C++ checks only
- `dashboard` or `web` or `ui` or `ts` or `react` → Dashboard checks only (Biome + TypeScript)
- `--fix` anywhere in args → auto-fix where possible
- A specific directory or file → lint only that target

## Commands

### All checks (no fix)
```bash
just lint
```

### All checks with auto-fix
```bash
just lint-fix
```

### Python only
```bash
just lint-python       # check
just lint-python-fix   # fix
```

### C++ only
```bash
just lint-cpp          # check (clang-format + cppcheck)
just lint-cpp-fix      # fix (clang-format -i)
```

### Dashboard only
```bash
just lint-dashboard       # check (biome + tsc)
just lint-dashboard-fix   # fix (biome --fix)
```

### Specific file (bypass just)
For a single file, run the tool directly:
```bash
ruff check --fix path/to/file.py
clang-format -i path/to/file.cpp
npx --prefix dashboard biome check --fix path/to/file.tsx
```

## Rules

1. Run checks in order — formatting first, then lint, then static analysis.
2. Report results per tool: pass/fail + issue count.
3. For failures, show the specific issues and suggest fixes.
4. If `--fix` was requested, report what was auto-fixed and what still needs manual attention.
5. Don't stop on the first failure — run all checks and report everything.
