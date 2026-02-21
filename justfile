# Robot Buddy — Task Runner
# Usage: just <recipe>        List all: just --list

set dotenv-load := false
project := justfile_directory()

# ── Testing ──────────────────────────────────────────────

# Run all tests
test-all: test-supervisor test-server test-sv2 test-dashboard

# Run supervisor tests (with optional filter)
test-supervisor *filter:
    cd {{project}}/supervisor && python -m pytest tests/ -v {{filter}}

# Run server tests (with optional filter)
test-server *filter:
    cd {{project}}/server && uv run pytest tests/ -v {{filter}}

# Run supervisor_v2 tests (with optional filter)
test-sv2 *filter:
    cd {{project}}/supervisor_v2 && python -m pytest tests/ -v {{filter}}

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
    ruff format --check {{project}}/supervisor/ {{project}}/server/ {{project}}/supervisor_v2/
    ruff check {{project}}/supervisor/ {{project}}/server/ {{project}}/supervisor_v2/

# Auto-fix Python formatting + lint
lint-python-fix:
    ruff format {{project}}/supervisor/ {{project}}/server/ {{project}}/supervisor_v2/
    ruff check --fix {{project}}/supervisor/ {{project}}/server/ {{project}}/supervisor_v2/

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
    cd {{project}}/supervisor && python -m supervisor --mock --no-face --no-vision

# Run supervisor (default ports)
run:
    cd {{project}}/supervisor && python -m supervisor

# Run supervisor v2 with mock hardware
run-v2-mock:
    cd {{project}}/supervisor_v2 && python -m supervisor_v2 --mock --no-face --no-vision

# Run planner server
run-server:
    cd {{project}}/server && uv run python -m app.main

# Run dashboard dev server
run-dashboard:
    cd {{project}}/dashboard && npx vite

# Build dashboard (outputs to supervisor_v2/static/)
build-dashboard:
    cd {{project}}/dashboard && npm run build

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

# Deploy supervisor v1 (update)
deploy:
    cd {{project}} && bash deploy/update.sh

# Deploy supervisor v2 (update)
deploy-v2:
    cd {{project}} && bash deploy/update.sh --v2

# First-time install on Pi
install:
    cd {{project}} && bash deploy/install.sh

# First-time install v2 on Pi
install-v2:
    cd {{project}} && bash deploy/install.sh --v2

# ── Preflight ────────────────────────────────────────────

# Full pre-commit quality check
preflight: lint test-all
    @echo ""
    @echo "✓ All checks passed — ready to commit."
