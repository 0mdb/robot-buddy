# CLAUDE.md — robot-buddy

Kid-safe expressive tracked robot: Pi 5 supervisor, ESP32-S3 reflex MCU
(motors/IMU/safety), ESP32-S3 face MCU (2.8" TFT), USB mic + speaker, optional
LAN AI server. Overview: `README.md`. Agent notes: `AGENTS.md`.

## Ground rules

- `docs/TODO.md` is the single source of implementation truth.
- `specs/` is immutable reference; amend a spec before diverging from it.
- Prefer `just` recipes (`just --list`). Hardware/deploy actions (`flash-*`,
  `deploy`, SSH) are manual-only unless explicitly requested.
- Python: type hints, ruff (`ruff.toml`). C++: clang-format/clang-tidy.

## Mechanical / CAD

- **Repo `CAD/` is the master**, in Git LFS. SolidWorks 2024 runs on Windows and
  is driven from WSL over COM. Sync with `just cad-push` / `just cad-pull`
  (`tools/sw.py`). Skill: `/solidworks`. API reference: `docs/cad/solidworks-api.md`.
  These were ported from `~/fpv250/fpv250`; buddy's copies are the source of truth here.
- Index of parts and specs: `docs/cad/00_robot_buddy_index.md`. FDM rules:
  `docs/print-dfm.md`. Materials: `docs/print-bom.md`.
- Chassis frame: origin at the base-plate top centre, +X forward, +Y left, +Z up.
- One SolidWorks client at a time. Start SolidWorks by hand. Close documents before `cad-pull`.
- Eyes before electrons: Ben reviews a render or the open model before anything is printed.
