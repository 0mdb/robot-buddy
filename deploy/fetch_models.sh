#!/usr/bin/env bash
# deploy/fetch_models.sh — download model files too big for git into supervisor/models.
# Idempotent: skips files already present with the right checksum. Called by update.sh.

set -euo pipefail
MODELS="$(cd "$(dirname "${BASH_SOURCE[0]}")/../supervisor/models" && pwd)"

fetch() {  # name url sha256
    local name=$1 url=$2 sha=$3 dest="$MODELS/$1"
    if [[ -f "$dest" ]] && echo "$sha  $dest" | sha256sum -c --quiet - 2>/dev/null; then
        return 0
    fi
    echo "[models] fetching $name"
    curl -fsSL --retry 3 -o "$dest.part" "$url"
    echo "$sha  $dest.part" | sha256sum -c --quiet - || { rm -f "$dest.part"; echo "[models] checksum mismatch: $name" >&2; return 1; }
    mv "$dest.part" "$dest"
}

# Face recognition (supervisor/inputs/face_id.py): OpenCV zoo SFace, Apache-2.0, 37 MB.
fetch face_recognition_sface_2021dec.onnx \
    https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx \
    0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79
