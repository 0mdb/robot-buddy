# Robot Buddy — Task Runner
# Usage: just <recipe>        List all: just --list

set dotenv-load := false
project := justfile_directory()

# ── Testing ──────────────────────────────────────────────

# Run all tests
test-all: test-supervisor test-server test-dashboard

# Run supervisor tests (with optional filter)
test-supervisor *filter:
    cd {{project}}/supervisor_v2 && python -m pytest tests/ -v {{filter}}

# Run server tests (with optional filter)
test-server *filter:
    cd {{project}}/server && uv run pytest tests/ -v {{filter}}

# Run dashboard tests
test-dashboard *filter:
    cd {{project}}/dashboard && npx vitest run {{filter}}

# ── Linting ──────────────────────────────────────────────

# Run all lint checks (no auto-fix)
lint: lint-python lint-cpp lint-dashboard

# Run all lint checks and auto-fix
lint-fix: lint-python-fix lint-cpp-fix lint-dashboard-fix

# Check Python formatting + lint
lint-python:
    ruff format --check {{project}}/server/ {{project}}/supervisor_v2/
    ruff check {{project}}/server/ {{project}}/supervisor_v2/

# Auto-fix Python formatting + lint
lint-python-fix:
    ruff format {{project}}/server/ {{project}}/supervisor_v2/
    ruff check --fix {{project}}/server/ {{project}}/supervisor_v2/

# Check C++ formatting + static analysis
lint-cpp:
    clang-format --dry-run -Werror {{project}}/esp32-reflex/main/*.cpp {{project}}/esp32-reflex/main/*.h {{project}}/esp32-face-v2/main/*.cpp {{project}}/esp32-face-v2/main/*.h
    cppcheck --language=c++ --enable=warning,performance,portability --suppress=missingIncludeSystem --error-exitcode=1 -I {{project}}/esp32-reflex/main {{project}}/esp32-reflex/main/*.cpp {{project}}/esp32-reflex/main/*.h
    cppcheck --language=c++ --enable=warning,performance,portability --suppress=missingIncludeSystem --error-exitcode=1 -I {{project}}/esp32-face-v2/main {{project}}/esp32-face-v2/main/*.cpp {{project}}/esp32-face-v2/main/*.h

# Auto-fix C++ formatting
lint-cpp-fix:
    clang-format -i {{project}}/esp32-reflex/main/*.cpp {{project}}/esp32-reflex/main/*.h {{project}}/esp32-face-v2/main/*.cpp {{project}}/esp32-face-v2/main/*.h

# Check dashboard formatting + lint
lint-dashboard:
    cd {{project}}/dashboard && npx biome check src/
    cd {{project}}/dashboard && npx tsc -b --noEmit

# Auto-fix dashboard formatting + lint
lint-dashboard-fix:
    cd {{project}}/dashboard && npx biome check --fix src/

# ── Running ──────────────────────────────────────────────

# Run supervisor with mock hardware (no robot needed)
run-mock:
    cd {{project}}/supervisor_v2 && python -m supervisor_v2 --mock --no-face --no-vision

# Run supervisor (default ports)
run:
    cd {{project}}/supervisor_v2 && python -m supervisor_v2

# Run planner server
run-server:
    cd {{project}}/server && uv run python -m app.main

# Run dashboard dev server
run-dashboard:
    cd {{project}}/dashboard && npx vite

# Build dashboard (outputs to supervisor_v2/static/)
build-dashboard:
    cd {{project}}/dashboard && npm run build

# Run face simulator V3
sim:
    cd {{project}} && uv run --project tools --extra sim python -m tools.face_sim_v3

# Run a tool script (e.g. just tool serial_diag --all)
tool script *args:
    uv run --project {{project}}/tools python {{project}}/tools/{{script}}.py {{args}}

# Run serial diagnostics on connected MCUs
serial-diag *args:
    uv run --project {{project}}/tools python {{project}}/tools/serial_diag.py {{args}}

# ── ESP32 Firmware ───────────────────────────────────────

# Build reflex firmware
build-reflex:
    cd {{project}}/esp32-reflex && idf.py build

# Build face firmware
build-face:
    cd {{project}}/esp32-face-v2 && idf.py build

# Flash reflex firmware
flash-reflex: build-reflex
    cd {{project}}/esp32-reflex && idf.py flash

# Flash face firmware
flash-face: build-face
    cd {{project}}/esp32-face-v2 && idf.py flash

# Monitor reflex serial output
monitor-reflex:
    cd {{project}}/esp32-reflex && idf.py monitor

# Monitor face serial output
monitor-face:
    cd {{project}}/esp32-face-v2 && idf.py monitor

# ── Deployment ───────────────────────────────────────────

# Deploy supervisor (update)
deploy:
    cd {{project}} && bash deploy/update.sh

# First-time install on Pi
install:
    cd {{project}} && bash deploy/install.sh

# ── Wake Word Training ─────────────────────────────────────

# Setup training environment (run once)
setup-training:
    cd {{project}}/training && bash setup.sh

# Train "Hey Buddy" wake word model
train-wakeword *phase:
    cd {{project}}/training && bash train.sh {{phase}}

# Deploy trained model to supervisor
deploy-wakeword:
    cp {{project}}/training/output/hey_buddy.onnx {{project}}/supervisor_v2/models/hey_buddy.onnx
    @echo "Deployed hey_buddy.onnx to supervisor_v2/models/"

# ── Parity ──────────────────────────────────────────────

# Check V3 sim / MCU face parity
check-parity:
    cd {{project}} && python tools/check_face_parity.py

# ── Preflight ────────────────────────────────────────────

# Full pre-commit quality check
preflight: lint test-all check-parity
    @echo ""
    @echo "✓ All checks passed — ready to commit."
