#!/usr/bin/env bash
# Setup script for OpenWakeWord "Hey Buddy" model training.
# Run once before training: bash setup.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== OpenWakeWord Training Setup ==="

# ── 1. Python venv ──────────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "[1/5] Creating Python venv..."
    python3 -m venv .venv
else
    echo "[1/5] Venv already exists, skipping."
fi
source .venv/bin/activate

# ── 2. Clone repos ──────────────────────────────────────────
echo "[2/5] Cloning repos..."

OPENWAKEWORD_COMMIT="368c037"   # 2025-12-30 — tflite conversion behind flag
PIPER_SAMPLER_COMMIT="f1988a4"  # 2023-09-11

if [ ! -d "openWakeWord" ]; then
    git clone https://github.com/dscripka/openWakeWord.git
    git -C openWakeWord checkout "$OPENWAKEWORD_COMMIT"
else
    echo "  openWakeWord already cloned."
fi

if [ ! -d "piper-sample-generator" ]; then
    git clone https://github.com/dscripka/piper-sample-generator.git
    git -C piper-sample-generator checkout "$PIPER_SAMPLER_COMMIT"
else
    echo "  piper-sample-generator already cloned."
fi

# Patch: PyTorch 2.6+ requires weights_only=False for Piper model loading
sed -i 's/model = torch.load(model_path)/model = torch.load(model_path, weights_only=False)/' \
    piper-sample-generator/generate_samples.py 2>/dev/null || true

# ── 3. Install Python packages ─────────────────────────────
echo "[3/5] Installing Python packages..."

pip install --upgrade pip

# Install openwakeword in dev mode
pip install -e ./openWakeWord

# PyTorch with CUDA 11.8 support (needed for Piper TTS generation + training)
pip install \
    torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# piper-sample-generator dependencies
pip install piper-phonemize-fix webrtcvad audiomentations espeak-phonemizer

# Training dependencies (from the automatic_model_training.ipynb notebook)
pip install \
    mutagen \
    torchinfo \
    torchmetrics \
    speechbrain==0.5.14 \
    torch-audiomentations \
    acoustics \
    pronouncing \
    'datasets==2.14.6' \
    'pyarrow>=12,<16' \
    deep-phonemizer \
    onnxruntime \
    'scipy<1.15' \
    'setuptools<70'

# NOTE: TFLite conversion is not used (ONNX-only). Skipping tensorflow-cpu,
# tensorflow_probability, and onnx_tf (~1.5 GB saved).

# ── 4. Download Piper TTS model ─────────────────────────────
echo "[4/5] Downloading Piper TTS model..."

PIPER_MODEL_DIR="piper-sample-generator/models"
mkdir -p "$PIPER_MODEL_DIR"

if [ ! -f "$PIPER_MODEL_DIR/en_US-libritts_r-medium.pt" ]; then
    wget -q --show-progress -O "$PIPER_MODEL_DIR/en_US-libritts_r-medium.pt" \
        "https://github.com/rhasspy/piper-sample-generator/releases/download/v2.0.0/en_US-libritts_r-medium.pt"
else
    echo "  Piper model already downloaded."
fi

# Symlink expected by generate_samples.py (defaults to en-us-libritts-high.pt)
ln -sf en_US-libritts_r-medium.pt "$PIPER_MODEL_DIR/en-us-libritts-high.pt"

# Download OpenWakeWord feature extraction models (melspectrogram.onnx, embedding_model.onnx)
echo "  Downloading OpenWakeWord feature models..."
python3 -c "from openwakeword.utils import download_models; download_models(model_names=[])"

# ── 5. Download training datasets ────────────────────────────
echo "[5/5] Downloading training datasets..."

DATA_DIR="data"
mkdir -p "$DATA_DIR"

# ACAV100M negative features (~1.7 GB)
if [ ! -f "$DATA_DIR/openwakeword_features_ACAV100M_2000_hrs_16bit.npy" ]; then
    echo "  Downloading ACAV100M features (~1.7 GB, this may take a while)..."
    wget -q --show-progress -O "$DATA_DIR/openwakeword_features_ACAV100M_2000_hrs_16bit.npy" \
        "https://huggingface.co/datasets/davidscripka/openwakeword_features/resolve/main/openwakeword_features_ACAV100M_2000_hrs_16bit.npy"
else
    echo "  ACAV100M features already downloaded."
fi

# Validation set features (~100 MB)
if [ ! -f "$DATA_DIR/validation_set_features.npy" ]; then
    echo "  Downloading validation set features..."
    wget -q --show-progress -O "$DATA_DIR/validation_set_features.npy" \
        "https://huggingface.co/datasets/davidscripka/openwakeword_features/resolve/main/validation_set_features.npy"
else
    echo "  Validation features already downloaded."
fi

# MIT Room Impulse Responses (270 WAV files)
if [ ! -d "$DATA_DIR/mit_rirs" ]; then
    echo "  Downloading MIT RIRs..."
    python3 -c "
import datasets, scipy.io.wavfile, os, numpy as np
from tqdm import tqdm
os.makedirs('$DATA_DIR/mit_rirs', exist_ok=True)
ds = datasets.load_dataset('davidscripka/MIT_environmental_impulse_responses', split='train', streaming=True)
i = 0
for row in tqdm(ds, desc='RIRs'):
    name = row['audio']['path'].split('/')[-1]
    scipy.io.wavfile.write(
        os.path.join('$DATA_DIR/mit_rirs', name),
        16000,
        (np.array(row['audio']['array']) * 32767).astype(np.int16)
    )
    i += 1
print(f'Saved {i} RIR files')
"
else
    echo "  MIT RIRs already downloaded."
fi

# FMA background music (1 hour of 30-second clips)
if [ ! -d "$DATA_DIR/fma" ]; then
    echo "  Downloading FMA background clips (1 hour)..."
    python3 -c "
import datasets, scipy.io.wavfile, os, numpy as np
from tqdm import tqdm
os.makedirs('$DATA_DIR/fma', exist_ok=True)
ds = datasets.load_dataset('rudraml/fma', name='small', split='train', streaming=True)
ds = iter(ds.cast_column('audio', datasets.Audio(sampling_rate=16000)))
n_clips = 3600 // 30  # 1 hour of 30-second clips
for i in tqdm(range(n_clips), desc='FMA'):
    row = next(ds)
    name = row['audio']['path'].split('/')[-1].replace('.mp3', '.wav')
    scipy.io.wavfile.write(
        os.path.join('$DATA_DIR/fma', name),
        16000,
        (np.array(row['audio']['array']) * 32767).astype(np.int16)
    )
print(f'Saved {n_clips} FMA clips')
"
else
    echo "  FMA already downloaded."
fi

echo ""
echo "=== Setup complete ==="
echo "Datasets in: $SCRIPT_DIR/data/"
echo ""
echo "Next: bash train.sh"
