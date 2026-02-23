#!/usr/bin/env python3
"""Generate a clang-compatible compile_commands.json for ESP-IDF firmware.

Usage: python3 tools/gen_clang_db.py <input.json> <output.json>

ESP-IDF generates compile commands using xtensa-esp32s3-elf-gcc, which includes
flags that are unknown to clang/clang-tidy.  This script strips those flags so
esp-clang (Espressif's Xtensa-capable clang) can process the files.

esp-clang ships with ESP-IDF and is installed via:
  python3 ~/esp/esp-idf/tools/idf_tools.py install esp-clang

Flags removed (GCC-specific, not understood by clang):
  -mlongcalls              Xtensa call-range extension (clang uses -mlong-calls)
  -fno-tree-switch-conversion  GCC optimizer pass
  -fstrict-volatile-bitfields  GCC extension
  -fno-shrink-wrap         GCC optimizer pass
"""

from __future__ import annotations

import json
import shlex
import sys

_REMOVE_FLAGS = frozenset(
    {
        "-mlongcalls",
        "-fno-tree-switch-conversion",
        "-fstrict-volatile-bitfields",
        "-fno-shrink-wrap",
    }
)


def filter_command(command: str) -> str:
    args = shlex.split(command)
    return shlex.join(a for a in args if a not in _REMOVE_FLAGS)


def main() -> None:
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input.json> <output.json>", file=sys.stderr)
        sys.exit(1)

    input_path, output_path = sys.argv[1], sys.argv[2]

    with open(input_path) as f:
        commands = json.load(f)

    for entry in commands:
        if "command" in entry:
            entry["command"] = filter_command(entry["command"])
        elif "arguments" in entry:
            entry["arguments"] = [
                a for a in entry["arguments"] if a not in _REMOVE_FLAGS
            ]

    with open(output_path, "w") as f:
        json.dump(commands, f, indent=2)

    print(f"gen_clang_db: wrote {len(commands)} entries → {output_path}")


if __name__ == "__main__":
    main()
