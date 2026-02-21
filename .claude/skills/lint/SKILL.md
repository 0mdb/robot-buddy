---
name: lint
description: Run linting, formatting, and static analysis checks across Python and C/C++ code. Use when the user asks to lint, check code quality, format code, run type checking, or verify code before committing.
argument-hint: "[python|cpp|all] [--fix]"
allowed-tools: Bash(ruff:*), Bash(ruff check:*), Bash(ruff format:*), Bash(pyright:*), Bash(clang-format:*), Bash(cppcheck:*), Read, Grep, Glob
---

Run linting and static analysis. Parse `$ARGUMENTS` to determine scope and mode.

## Argument parsing

- No arguments or `all` → run everything (Python + C++)
- `python` → Python checks only (ruff + pyright)
- `cpp` or `c++` or `firmware` → C/C++ checks only (clang-format + cppcheck)
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

### 3. Pyright type checking (optional)
```bash
cd /home/ben/robot-buddy && pyright
```
Pyright uses `pyrightconfig.json` at the project root. Pylance in VSCode provides the same checks in-editor.

If pyright is not installed, skip and note:
> Pyright CLI not installed (Pylance handles this in VSCode). Install with: `pip install pyright`

## C/C++ checks (in order)

### 1. clang-format (style check)
```bash
cd /home/ben/robot-buddy && clang-format --dry-run -Werror esp32-reflex/main/*.cpp esp32-reflex/main/*.h esp32-face-v2/main/*.cpp esp32-face-v2/main/*.h
```
With `--fix`:
```bash
cd /home/ben/robot-buddy && clang-format -i esp32-reflex/main/*.cpp esp32-reflex/main/*.h esp32-face-v2/main/*.cpp esp32-face-v2/main/*.h
```

### 2. cppcheck (static analysis)
No compilation database needed — works directly on source files.

```bash
cd /home/ben/robot-buddy && cppcheck --language=c++ --enable=warning,performance,portability --suppress=missingIncludeSystem --inline-suppr --error-exitcode=1 -I esp32-reflex/main esp32-reflex/main/*.cpp esp32-reflex/main/*.h
```

```bash
cd /home/ben/robot-buddy && cppcheck --language=c++ --enable=warning,performance,portability --suppress=missingIncludeSystem --inline-suppr --error-exitcode=1 -I esp32-face-v2/main esp32-face-v2/main/*.cpp esp32-face-v2/main/*.h
```

Key flags:
- `--language=c++` — .h files are C++, not C
- `--enable=warning,performance,portability` — useful checks without excessive noise
- `--suppress=missingIncludeSystem` — suppress ESP-IDF system header warnings
- `--error-exitcode=1` — fail on warnings for CI

If cppcheck is not installed, warn the user:
> cppcheck not installed. Install with: `sudo apt install cppcheck`

## Rules

1. Run checks in the order listed — formatting first, then lint, then static analysis.
2. Report results per tool: pass/fail + issue count.
3. For failures, show the specific issues and suggest fixes.
4. If `--fix` was requested, report what was auto-fixed and what still needs manual attention.
5. Don't stop on the first failure — run all checks and report everything.
