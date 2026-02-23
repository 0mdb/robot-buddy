#!/usr/bin/env python3
"""Generate a clang-compatible compile_commands.json for ESP-IDF firmware.

Usage: python3 tools/gen_clang_db.py <input.json> <output.json>

ESP-IDF generates compile commands using xtensa-esp32s3-elf-gcc, which includes
flags unknown to clang-tidy and uses a compiler binary whose name implies an
Xtensa target that the system clang doesn't support.

This script:
  1. Removes GCC-specific flags unknown to clang.
  2. Replaces the Xtensa GCC compiler binary with esp-clang's clang/clang++.
  3. Adds --target=xtensa-esp-unknown-elf and -mcpu=<chip> so esp-clang finds
     its bundled Xtensa runtime headers.

Prerequisites:
  esp-clang must be installed via:
    python3 ~/esp/esp-idf/tools/idf_tools.py install esp-clang

Flags removed (GCC-specific, not understood by clang):
  -mlongcalls              Xtensa call-range extension (clang uses -mlong-calls)
  -fno-tree-switch-conversion  GCC optimizer pass
  -fstrict-volatile-bitfields  GCC extension
  -fno-shrink-wrap         GCC optimizer pass
"""

from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path

_REMOVE_FLAGS = frozenset(
    {
        "-mlongcalls",
        "-fno-tree-switch-conversion",
        "-fstrict-volatile-bitfields",
        "-fno-shrink-wrap",
    }
)

# Regex to extract the chip name from the Xtensa GCC compiler binary name.
# e.g. "xtensa-esp32s3-elf-g++" → "esp32s3"
_CHIP_RE = re.compile(r"xtensa-(esp\w+)-elf")

_ESP_CLANG_BIN = Path(
    "/home/ben/.espressif/tools/esp-clang/esp-18.1.2_20240912/esp-clang/bin"
)


def _replace_compiler(binary: str) -> tuple[str, list[str]]:
    """Return (new_compiler, extra_flags) for a given GCC compiler binary path.

    For Xtensa GCC binaries, swaps in esp-clang and adds the target/cpu flags
    needed to point it at the correct Xtensa runtime headers.
    For any other compiler, returns it unchanged with no extra flags.
    """
    name = Path(binary).name
    m = _CHIP_RE.search(name)
    if not m:
        return binary, []

    chip = m.group(1)  # e.g. "esp32s3"
    is_cxx = "++" in name
    new_binary = str(_ESP_CLANG_BIN / ("clang++" if is_cxx else "clang"))
    extra = ["--target=xtensa-esp-unknown-elf", f"-mcpu={chip}"]
    return new_binary, extra


def filter_command(command: str) -> str:
    args = shlex.split(command)
    new_compiler, extra_flags = _replace_compiler(args[0])
    filtered = [a for a in args[1:] if a not in _REMOVE_FLAGS]
    return shlex.join([new_compiler] + extra_flags + filtered)


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
            args = entry["arguments"]
            new_compiler, extra_flags = _replace_compiler(args[0])
            filtered = [a for a in args[1:] if a not in _REMOVE_FLAGS]
            entry["arguments"] = [new_compiler] + extra_flags + filtered

    with open(output_path, "w") as f:
        json.dump(commands, f, indent=2)

    print(f"gen_clang_db: wrote {len(commands)} entries → {output_path}")


if __name__ == "__main__":
    main()
