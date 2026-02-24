# Robot Buddy — Task Runner
# Usage: just <recipe>        List all: just --list

set dotenv-load := false
project := justfile_directory()

# ── Testing ──────────────────────────────────────────────

# Run all tests
test-all: test-supervisor test-server test-dashboard

# Run supervisor tests (with optional filter)
test-supervisor *filter:
    cd {{project}}/supervisor && uv run pytest tests/ -v {{filter}}

# Run server tests (with optional filter)
test-server *filter:
    cd {{project}}/server && uv run pytest tests/ -v {{filter}}

# Run dashboard tests
test-dashboard *filter:
    cd {{project}}/dashboard && npx vitest run --passWithNoTests {{filter}}

# ── Linting ──────────────────────────────────────────────

# Run all lint checks (no auto-fix)
lint: lint-python lint-cpp lint-dashboard

# Run all lint checks and auto-fix
lint-fix: lint-python-fix lint-cpp-fix lint-dashboard-fix

# Check Python formatting + lint
lint-python:
    cd {{project}}/supervisor && uv run ruff format --check {{project}}/server/ {{project}}/supervisor/
    cd {{project}}/supervisor && uv run ruff check {{project}}/server/ {{project}}/supervisor/

# Auto-fix Python formatting + lint
lint-python-fix:
    cd {{project}}/supervisor && uv run ruff format {{project}}/server/ {{project}}/supervisor/
    cd {{project}}/supervisor && uv run ruff check --fix {{project}}/server/ {{project}}/supervisor/

# Check C++ formatting + static analysis
lint-cpp:
    clang-format --dry-run -Werror {{project}}/esp32-reflex/main/*.cpp {{project}}/esp32-reflex/main/*.h {{project}}/esp32-face/main/*.cpp {{project}}/esp32-face/main/*.h
    cppcheck --language=c++ --enable=warning,performance,portability --suppress=missingIncludeSystem --error-exitcode=1 -I {{project}}/esp32-reflex/main {{project}}/esp32-reflex/main/*.cpp {{project}}/esp32-reflex/main/*.h
    cppcheck --language=c++ --enable=warning,performance,portability --suppress=missingIncludeSystem --error-exitcode=1 -I {{project}}/esp32-face/main {{project}}/esp32-face/main/*.cpp {{project}}/esp32-face/main/*.h

# Auto-fix C++ formatting
lint-cpp-fix:
    clang-format -i {{project}}/esp32-reflex/main/*.cpp {{project}}/esp32-reflex/main/*.h {{project}}/esp32-face/main/*.cpp {{project}}/esp32-face/main/*.h

# Run clang-tidy deep static analysis on firmware (requires: just build-reflex, just build-face)
# Uses esp-clang (Xtensa-capable clang) — install: python3 ~/esp/esp-idf/tools/idf_tools.py install esp-clang
_ESP_CLANG_TIDY := "/home/ben/.espressif/tools/esp-clang/esp-18.1.2_20240912/esp-clang/bin/clang-tidy"
lint-cpp-tidy:
    {{_ESP_CLANG_TIDY}} -p {{project}}/esp32-reflex/build \
        {{project}}/esp32-reflex/main/*.cpp
    {{_ESP_CLANG_TIDY}} -p {{project}}/esp32-face/build \
        {{project}}/esp32-face/main/*.cpp

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
    cd {{project}}/supervisor && uv run python -m supervisor --mock --no-face --no-vision

# Run supervisor (default ports)
run:
    cd {{project}}/supervisor && uv run python -m supervisor

# Run planner server
run-server:
    bash -lc 'set -a; [ -f "{{project}}/.env" ] && source "{{project}}/.env"; set +a; cd "{{project}}/server" && uv run python -m app.main'

# Run dashboard dev server
run-dashboard:
    cd {{project}}/dashboard && npx vite

# Build dashboard (outputs to supervisor/static/)
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

# ESP-IDF export script (used if `idf.py` isn't already on PATH)
# Override if your ESP-IDF lives elsewhere: `ESP_IDF_EXPORT=/path/to/esp-idf/export.sh just build-reflex`
ESP_IDF_EXPORT := env_var_or_default("ESP_IDF_EXPORT", "$HOME/esp/esp-idf/export.sh")
ESP_IDF_EXPORT_LOG := env_var_or_default("ESP_IDF_EXPORT_LOG", "/tmp/idf_export.log")

# Build reflex firmware (also filters GCC-specific flags from compile_commands.json for clang/clang-tidy)
build-reflex:
    @expected="{{project}}/esp32-reflex"; \
        cache="{{project}}/esp32-reflex/build/CMakeCache.txt"; \
        if [ -f "$cache" ]; then \
            configured=$(grep -m1 '^CMAKE_HOME_DIRECTORY:INTERNAL=' "$cache" | cut -d= -f2-); \
            if [ -n "$configured" ] && [ "$configured" != "$expected" ]; then \
                echo "Build dir mismatch (configured for $configured, expected $expected). Running idf.py fullclean..."; \
                if command -v idf.py >/dev/null 2>&1; then \
                    cd "$expected" && idf.py fullclean; \
                else \
                    if [ ! -f "{{ESP_IDF_EXPORT}}" ]; then \
                        echo "ESP-IDF export script not found: {{ESP_IDF_EXPORT}}"; \
                        echo "Install ESP-IDF or set ESP_IDF_EXPORT=/path/to/export.sh"; \
                        exit 1; \
                    fi; \
                    bash -lc 'source "{{ESP_IDF_EXPORT}}" >"{{ESP_IDF_EXPORT_LOG}}" 2>&1 && cd "{{project}}/esp32-reflex" && idf.py fullclean'; \
                fi; \
            fi; \
        fi
    @if command -v idf.py >/dev/null 2>&1; then \
        cd {{project}}/esp32-reflex && idf.py build; \
    else \
        if [ ! -f "{{ESP_IDF_EXPORT}}" ]; then \
            echo "ESP-IDF export script not found: {{ESP_IDF_EXPORT}}"; \
            echo "Install ESP-IDF or set ESP_IDF_EXPORT=/path/to/export.sh"; \
            exit 1; \
        fi; \
        bash -lc 'source "{{ESP_IDF_EXPORT}}" >"{{ESP_IDF_EXPORT_LOG}}" 2>&1 && cd "{{project}}/esp32-reflex" && idf.py build'; \
    fi
    python3 {{project}}/tools/gen_clang_db.py \
        {{project}}/esp32-reflex/build/compile_commands.json \
        {{project}}/esp32-reflex/build/compile_commands.json

# Build face firmware (also filters GCC-specific flags from compile_commands.json for clang/clang-tidy)
build-face:
    @expected="{{project}}/esp32-face"; \
        cache="{{project}}/esp32-face/build/CMakeCache.txt"; \
        if [ -f "$cache" ]; then \
            configured=$(grep -m1 '^CMAKE_HOME_DIRECTORY:INTERNAL=' "$cache" | cut -d= -f2-); \
            if [ -n "$configured" ] && [ "$configured" != "$expected" ]; then \
                echo "Build dir mismatch (configured for $configured, expected $expected). Running idf.py fullclean..."; \
                if command -v idf.py >/dev/null 2>&1; then \
                    cd "$expected" && idf.py fullclean; \
                else \
                    if [ ! -f "{{ESP_IDF_EXPORT}}" ]; then \
                        echo "ESP-IDF export script not found: {{ESP_IDF_EXPORT}}"; \
                        echo "Install ESP-IDF or set ESP_IDF_EXPORT=/path/to/export.sh"; \
                        exit 1; \
                    fi; \
                    bash -lc 'source "{{ESP_IDF_EXPORT}}" >"{{ESP_IDF_EXPORT_LOG}}" 2>&1 && cd "{{project}}/esp32-face" && idf.py fullclean'; \
                fi; \
            fi; \
        fi
    @if command -v idf.py >/dev/null 2>&1; then \
        cd {{project}}/esp32-face && idf.py build; \
    else \
        if [ ! -f "{{ESP_IDF_EXPORT}}" ]; then \
            echo "ESP-IDF export script not found: {{ESP_IDF_EXPORT}}"; \
            echo "Install ESP-IDF or set ESP_IDF_EXPORT=/path/to/export.sh"; \
            exit 1; \
        fi; \
        bash -lc 'source "{{ESP_IDF_EXPORT}}" >"{{ESP_IDF_EXPORT_LOG}}" 2>&1 && cd "{{project}}/esp32-face" && idf.py build'; \
    fi
    python3 {{project}}/tools/gen_clang_db.py \
        {{project}}/esp32-face/build/compile_commands.json \
        {{project}}/esp32-face/build/compile_commands.json

# Flash reflex firmware
flash-reflex: build-reflex
    @if command -v idf.py >/dev/null 2>&1; then \
        cd {{project}}/esp32-reflex && idf.py flash; \
    else \
        if [ ! -f "{{ESP_IDF_EXPORT}}" ]; then \
            echo "ESP-IDF export script not found: {{ESP_IDF_EXPORT}}"; \
            echo "Install ESP-IDF or set ESP_IDF_EXPORT=/path/to/export.sh"; \
            exit 1; \
        fi; \
        bash -lc 'source "{{ESP_IDF_EXPORT}}" >"{{ESP_IDF_EXPORT_LOG}}" 2>&1 && cd "{{project}}/esp32-reflex" && idf.py flash'; \
    fi

# Flash face firmware
flash-face: build-face
    @if command -v idf.py >/dev/null 2>&1; then \
        cd {{project}}/esp32-face && idf.py flash; \
    else \
        if [ ! -f "{{ESP_IDF_EXPORT}}" ]; then \
            echo "ESP-IDF export script not found: {{ESP_IDF_EXPORT}}"; \
            echo "Install ESP-IDF or set ESP_IDF_EXPORT=/path/to/export.sh"; \
            exit 1; \
        fi; \
        bash -lc 'source "{{ESP_IDF_EXPORT}}" >"{{ESP_IDF_EXPORT_LOG}}" 2>&1 && cd "{{project}}/esp32-face" && idf.py flash'; \
    fi

# Monitor reflex serial output
monitor-reflex:
    @if command -v idf.py >/dev/null 2>&1; then \
        cd {{project}}/esp32-reflex && idf.py monitor; \
    else \
        if [ ! -f "{{ESP_IDF_EXPORT}}" ]; then \
            echo "ESP-IDF export script not found: {{ESP_IDF_EXPORT}}"; \
            echo "Install ESP-IDF or set ESP_IDF_EXPORT=/path/to/export.sh"; \
            exit 1; \
        fi; \
        bash -lc 'source "{{ESP_IDF_EXPORT}}" >"{{ESP_IDF_EXPORT_LOG}}" 2>&1 && cd "{{project}}/esp32-reflex" && idf.py monitor'; \
    fi

# Monitor face serial output
monitor-face:
    @if command -v idf.py >/dev/null 2>&1; then \
        cd {{project}}/esp32-face && idf.py monitor; \
    else \
        if [ ! -f "{{ESP_IDF_EXPORT}}" ]; then \
            echo "ESP-IDF export script not found: {{ESP_IDF_EXPORT}}"; \
            echo "Install ESP-IDF or set ESP_IDF_EXPORT=/path/to/export.sh"; \
            exit 1; \
        fi; \
        bash -lc 'source "{{ESP_IDF_EXPORT}}" >"{{ESP_IDF_EXPORT_LOG}}" 2>&1 && cd "{{project}}/esp32-face" && idf.py monitor'; \
    fi

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

# Retrain wake word model (augment + train only, skip clip generation)
retrain-wakeword:
    cd {{project}}/training && bash train.sh augment && bash train.sh train

# Deploy trained model to supervisor
deploy-wakeword:
    cp {{project}}/training/output/hey_buddy.onnx {{project}}/supervisor/models/hey_buddy.onnx
    @echo "Deployed hey_buddy.onnx to supervisor/models/"

# ── Parity ──────────────────────────────────────────────

# Check V3 sim / MCU face parity
check-parity:
    cd {{project}} && uv run --project tools python tools/check_face_parity.py

# ── Preflight ────────────────────────────────────────────

# Full pre-commit quality check
preflight: lint test-all check-parity
    @echo ""
    @echo "✓ All checks passed — ready to commit."
