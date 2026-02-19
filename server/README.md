# server

Optional AI planner stack running on a 3090 Ti on the local network.

## Architecture

```
Supervisor (Pi 5) ──POST /plan──► FastAPI server ──/api/chat──► Ollama (qwen3:14b)
                  ◄── PlanResponse ──┘                           GPU: 3090 Ti
```

- **Model:** Qwen 3 14B (Q4_K_M) via Ollama (~9 GB VRAM)
- **Server:** FastAPI + uvicorn on port 8100
- **LLM client:** async httpx calling Ollama's `/api/chat` with structured output (JSON schema)

## Current Conversational Audio Status (2026-02-18)

- Active architecture is supervisor-owned USB audio on the Pi:
  - USB mic capture on supervisor -> server `/converse`
  - server emits emotion + TTS audio stream
  - supervisor plays TTS on USB speaker
- Face MCU (`esp32-face-v2`) is visual/interaction only:
  - receives `SET_STATE` / `GESTURE` / `SET_SYSTEM` / `SET_TALKING`
  - sends touch/button/status telemetry
  - does not carry PCM speaker/mic audio over its CDC protocol

## Setup

### 1. Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### 2. Pull the model

```bash
ollama pull qwen3:14b
```

Or create a custom model with pinned parameters:

```bash
cd server/
ollama create robot-buddy -f Modelfile
```

### 3. Install the server

```bash
cd server/
uv sync --extra dev --extra stt --extra tts
```

### 4. Run

```bash
# Make sure Ollama is running (ollama serve)
cd server/
uv run --extra stt --extra tts python -m app.main
```

The server starts on `http://0.0.0.0:8100`.

Note: `uv run` does not include optional extras unless passed explicitly.

The server now auto-loads a local `.env` file (if present), and by default will
auto-pull the configured Ollama model when missing.

Example `.env`:

```bash
MODEL_NAME=qwen2.5:3b
AUTO_PULL_OLLAMA_MODEL=1
OLLAMA_PULL_TIMEOUT_S=1800
HF_TOKEN=hf_xxx
```

### Recommended single-GPU run (Qwen + Orpheus on one 3090)

```bash
cd server/
WARMUP_LLM=0 \
PLAN_TIMEOUT_S=25 \
CONVERSE_KEEP_ALIVE=0s \
ORPHEUS_GPU_MEMORY_UTILIZATION=0.35 \
ORPHEUS_MAX_MODEL_LEN=4096 \
ORPHEUS_MAX_NUM_SEQS=4 \
ORPHEUS_MAX_NUM_BATCHED_TOKENS=256 \
uv run --extra stt --extra tts python -m app.main
```

This reduces vLLM startup pressure and avoids sampler warmup OOM when Orpheus and Ollama share one GPU.

### Low-memory conversational test profile (recommended for bring-up)

```bash
cd server/
MODEL_NAME=qwen2.5:3b \
PLAN_TIMEOUT_S=35 \
WARMUP_LLM=0 \
CONVERSE_KEEP_ALIVE=0s \
STT_MODEL_SIZE=base.en \
STT_DEVICE=cpu \
STT_COMPUTE_TYPE=int8 \
TTS_BACKEND=espeak \
uv run --extra stt --extra tts python -m app.main
```

Notes:
- `TTS_BACKEND=espeak` avoids vLLM/Orpheus GPU churn during testing.
- `STT_DEVICE=cpu` removes Whisper from GPU memory contention.
- You can switch back to `TTS_BACKEND=orpheus` once memory is stable.

## Configuration

All settings are overridable via environment variables:

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API base URL |
| `MODEL_NAME` | `qwen3:14b` | Ollama model name |
| `AUTO_PULL_OLLAMA_MODEL` | `1` | Auto-pull `MODEL_NAME` from Ollama if missing |
| `OLLAMA_PULL_TIMEOUT_S` | `1800.0` | Timeout for model pull at startup / retry |
| `PLAN_TIMEOUT_S` | `5.0` | Max seconds to wait for LLM response |
| `WARMUP_LLM` | `1` | Warm Ollama model at startup (`0` to disable) |
| `MAX_ACTIONS` | `5` | Max actions per plan |
| `TEMPERATURE` | `0.7` | LLM sampling temperature |
| `NUM_CTX` | `4096` | Context window size (tokens) |
| `CONVERSE_KEEP_ALIVE` | `0s` | Ollama keep-alive for `/converse` calls |
| `STT_MODEL_SIZE` | `base.en` | faster-whisper model size for `/converse` |
| `STT_DEVICE` | `cpu` | faster-whisper device (`cpu` or `cuda`) |
| `STT_COMPUTE_TYPE` | `int8` | faster-whisper compute type |
| `TTS_BACKEND` | `auto` | `auto`, `orpheus`, `espeak`, or `off` |
| `TTS_MODEL_NAME` | `canopylabs/orpheus-3b-0.1-ft` | Orpheus model repo when using Orpheus |
| `TTS_VOICE` | `en-us` | Voice for `espeak` fallback backend |
| `TTS_RATE_WPM` | `165` | Speech rate for `espeak` fallback backend |
| `ORPHEUS_GPU_MEMORY_UTILIZATION` | `0.45` | vLLM GPU memory target for Orpheus |
| `ORPHEUS_MAX_MODEL_LEN` | `8192` | vLLM max sequence length for Orpheus |
| `ORPHEUS_MAX_NUM_SEQS` | `8` | vLLM max concurrent sequences for Orpheus |
| `ORPHEUS_MAX_NUM_BATCHED_TOKENS` | `512` | vLLM max batched tokens for Orpheus |
| `ORPHEUS_IDLE_TIMEOUT_S` | `8.0` | Max idle wait for next Orpheus chunk before reset/retry |
| `ORPHEUS_TOTAL_TIMEOUT_S` | `60.0` | Max total synthesis wait for one Orpheus request |
| `SERVER_HOST` | `0.0.0.0` | Bind address |
| `SERVER_PORT` | `8100` | Bind port |

## API

### `GET /health`

Returns server and Ollama status.

```json
{
  "status": "ok",
  "model": "qwen3:14b",
  "ollama": true,
  "ai": {
    "stt": {"model_size": "base.en", "device": "cpu", "compute_type": "int8", "loaded": false},
    "tts": {"backend_pref": "auto", "backend_active": "espeak", "loaded": true}
  }
}
```

Returns 503 if Ollama is unreachable.

## TTS Notes

- Orpheus model repos are gated on Hugging Face. Account access + auth are required.
- First TTS request can be significantly slower than warm-path requests because model load/compile happens lazily.
- Current behavior: conversational TTS can work end-to-end but has high first-audio latency and occasional `EngineDeadError`/timeout events on some warm turns.
- If logs show `CUDA out of memory ... warming up sampler with 128 dummy requests`, lower:
  - `ORPHEUS_GPU_MEMORY_UTILIZATION`
  - `ORPHEUS_MAX_NUM_SEQS`
  - `ORPHEUS_MAX_NUM_BATCHED_TOKENS`
- If logs show `orpheus stream idle ...` or `EngineDeadError`, raise:
  - `ORPHEUS_IDLE_TIMEOUT_S`
  - `ORPHEUS_TOTAL_TIMEOUT_S`

### `POST /plan`

Accepts a world-state snapshot, returns a bounded performance plan.

**Request:**

```json
{
    "mode": "WANDER",
    "battery_mv": 7800,
    "range_mm": 600,
    "faults": [],
    "clear_confidence": 0.92,
    "ball_detected": true,
    "ball_bearing_deg": 15.2,
    "speed_l_mm_s": 100,
    "speed_r_mm_s": 95,
    "v_capped": 80,
    "w_capped": 0,
    "trigger": "ball_seen"
}
```

**Response (200):**

```json
{
    "actions": [
        {"action": "emote", "name": "excited", "intensity": 0.9},
        {"action": "say", "text": "Oh! A ball!"},
        {"action": "gesture", "name": "look_at", "params": {"bearing": 15.2}},
        {"action": "skill", "name": "investigate_ball"}
    ],
    "ttl_ms": 2000
}
```

**Error codes:** 504 (LLM timeout), 502 (Ollama unreachable or LLM error), 422 (invalid request).

## Plan Actions

| Action | Fields | Constraints |
|---|---|---|
| `say` | `text` | max 200 chars, kid-friendly |
| `emote` | `name`, `intensity` | intensity 0.0–1.0 |
| `gesture` | `name`, `params` | params dict varies by gesture |
| `skill` | `name` | one of `patrol_drift`, `investigate_ball`, `avoid_obstacle`, `greet_on_button` |

## Testing

```bash
cd server/
uv run pytest tests/ -v
```

## TODO

- [x] Implement `/tts` endpoint
- [ ] Add caching for instant responses to common triggers
- [ ] Interaction history / conversation memory
- [x] Supervisor-side `PlannerClient` integration
