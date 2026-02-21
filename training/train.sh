#!/usr/bin/env bash
# Train the "Hey Buddy" OpenWakeWord model.
# Prerequisite: bash setup.sh (run once)
#
# Usage:
#   bash train.sh              # Run all 3 phases
#   bash train.sh generate     # Phase 1 only: generate synthetic clips
#   bash train.sh augment      # Phase 2 only: augment clips
#   bash train.sh train        # Phase 3 only: train model
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

source .venv/bin/activate

TRAIN_SCRIPT="openWakeWord/openwakeword/train.py"
CONFIG="config.yaml"

if [ ! -f "$TRAIN_SCRIPT" ]; then
    echo "ERROR: openWakeWord not found. Run: bash setup.sh"
    exit 1
fi

PHASE="${1:-all}"

run_phase() {
    local name="$1"
    local flag="$2"
    echo ""
    echo "════════════════════════════════════════════════════════"
    echo "  Phase: $name"
    echo "════════════════════════════════════════════════════════"
    echo ""
    python "$TRAIN_SCRIPT" --training_config "$CONFIG" "$flag"
}

case "$PHASE" in
    generate)
        run_phase "Generate synthetic clips" "--generate_clips"
        ;;
    augment)
        run_phase "Augment clips" "--augment_clips"
        ;;
    train)
        run_phase "Train model" "--train_model"
        ;;
    all)
        run_phase "Generate synthetic clips" "--generate_clips"
        run_phase "Augment clips" "--augment_clips"
        run_phase "Train model" "--train_model"
        ;;
    *)
        echo "Usage: bash train.sh [generate|augment|train|all]"
        exit 1
        ;;
esac

echo ""
echo "════════════════════════════════════════════════════════"

# Check if output model exists
MODEL="output/hey_buddy.onnx"
if [ -f "$MODEL" ]; then
    echo "  Model trained: $MODEL"
    echo "  Size: $(du -h "$MODEL" | cut -f1)"
    echo ""
    echo "  Deploy with:"
    echo "    cp $SCRIPT_DIR/$MODEL $SCRIPT_DIR/../supervisor_v2/models/hey_buddy.onnx"
else
    echo "  WARNING: Model file not found at $MODEL"
    echo "  Check output/ directory for results."
fi
echo "════════════════════════════════════════════════════════"
