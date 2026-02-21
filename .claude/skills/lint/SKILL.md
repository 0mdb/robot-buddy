---
name: lint
description: Run linting, formatting, and static analysis checks across Python and C/C++ code. Use when the user asks to lint, check code quality, format code, run type checking, or verify code before committing.
argument-hint: "[python|cpp|all] [--fix]"
allowed-tools: Bash(ruff:*), Bash(ruff check:*), Bash(ruff format:*), Bash(pyright:*), Bash(clang-format:*), Bash(clang-tidy:*), Read, Grep, Glob
---

Run linting and static analysis. Parse `$ARGUMENTS` to determine scope and mode.

## Argument parsing

- No arguments or `all` → run everything (Python + C++)
- `python` → Python checks only (ruff + pyright)
- `cpp` or `c++` or `firmware` → C/C++ checks only (clang-format + clang-tidy)
- `--fix` anywhere in args → auto-fix where possible
- A specific directory or file → lint only that target

## Python checks (in order)

### 1. Ruff format check
```bash
cd /home/ben/robot-buddy && ruff format --check supervisor/ server/ supervisor_v2/
```
With `--fix`:
```bash
cd /home/ben/robot-buddy && ruff format supervisor/ server/ supervisor_v2/
```

### 2. Ruff lint
```bash
cd /home/ben/robot-buddy && ruff check supervisor/ server/ supervisor_v2/
```
With `--fix`:
```bash
cd /home/ben/robot-buddy && ruff check --fix supervisor/ server/ supervisor_v2/
```

### 3. Pyright type checking
```bash
cd /home/ben/robot-buddy && pyright
```
Pyright uses `pyrightconfig.json` at the project root.

If pyright is not installed, warn the user:
> pyright is not installed. Install with: `pip install pyright`

## C/C++ checks (in order)

### 1. clang-format (style check)
```bash
cd /home/ben/robot-buddy && clang-format --dry-run -Werror esp32-reflex/main/*.cpp esp32-reflex/main/*.h esp32-face-v2/main/*.cpp esp32-face-v2/main/*.h
```
With `--fix`:
```bash
cd /home/ben/robot-buddy && clang-format -i esp32-reflex/main/*.cpp esp32-reflex/main/*.h esp32-face-v2/main/*.cpp esp32-face-v2/main/*.h
```

### 2. clang-tidy (static analysis)
Requires `compile_commands.json` from a prior `idf.py build`.

For esp32-reflex:
```bash
clang-tidy -p /home/ben/robot-buddy/esp32-reflex/build /home/ben/robot-buddy/esp32-reflex/main/*.cpp
```

For esp32-face-v2:
```bash
clang-tidy -p /home/ben/robot-buddy/esp32-face-v2/build /home/ben/robot-buddy/esp32-face-v2/main/*.cpp
```

If `build/compile_commands.json` does not exist for a firmware target, skip clang-tidy for that target and warn:
> clang-tidy skipped for esp32-reflex — no compile_commands.json. Run `idf.py build` first.

If clang-format or clang-tidy is not installed, warn the user:
> C++ tools not installed. Install with: `sudo apt install clang-format clang-tidy`

## Rules

1. Run checks in the order listed — formatting first, then lint, then type checking.
2. Report results per tool: pass/fail + issue count.
3. For failures, show the specific issues and suggest fixes.
4. If `--fix` was requested, report what was auto-fixed and what still needs manual attention.
5. Don't stop on the first failure — run all checks and report everything.
