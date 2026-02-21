#!/bin/bash
set -e

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

[[ -z "$FILE_PATH" ]] && exit 0
[[ ! -f "$FILE_PATH" ]] && exit 0

# Python files — ruff format + lint fix
if [[ "$FILE_PATH" == *.py ]]; then
    ruff format "$FILE_PATH" 2>/dev/null || true
    ruff check --fix "$FILE_PATH" 2>/dev/null || true
fi

# C/C++ files — clang-format
if [[ "$FILE_PATH" == *.cpp || "$FILE_PATH" == *.h || "$FILE_PATH" == *.c ]]; then
    if command -v clang-format &>/dev/null; then
        clang-format -i "$FILE_PATH" 2>/dev/null || true
    fi
fi

# TypeScript/React files — biome format
if [[ "$FILE_PATH" == *.ts || "$FILE_PATH" == *.tsx || "$FILE_PATH" == *.js || "$FILE_PATH" == *.jsx ]]; then
    DASHBOARD_DIR="/home/ben/robot-buddy/dashboard"
    if [[ "$FILE_PATH" == "$DASHBOARD_DIR"/* ]]; then
        npx --prefix "$DASHBOARD_DIR" biome format --write "$FILE_PATH" 2>/dev/null || true
    fi
fi

exit 0
