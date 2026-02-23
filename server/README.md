# server

Optional AI planner stack running on a 3090 Ti on the local network.

## Architecture

```
Supervisor (Pi 5) ──POST /plan / WS /converse──► FastAPI server
                  ◄────────────── PlanResponse ──┘
                                      │
                                      ├─ LLM backend: Ollama (legacy) or vLLM (target)
                                      └─ TTS backend: Orpheus (vLLM) with espeak shedding
```

- **Planner model:** default `Qwen/Qwen3-8B-AWQ` when `LLM_BACKEND=vllm`
- **Rollout backend switch:** `LLM_BACKEND=ollama|vllm` (default `vllm`)
- **Server:** FastAPI + uvicorn on port 8100
- **STT:** faster-whisper, CPU-first (`STT_DEVICE=cpu`)

## Current Conversational Audio Status (2026-02-18)

- Active architecture is supervisor-owned USB audio on the Pi:
  - USB mic capture on supervisor -> server `/converse`
  - server emits emotion + TTS audio stream
  - supervisor plays TTS on USB speaker
- Face MCU (`esp32-face`) is visual/interaction only:
  - receives `SET_STATE` / `GESTURE` / `SET_SYSTEM` / `SET_TALKING`
  - sends touch/button/status telemetry
  - does not carry PCM speaker/mic audio over its CDC protocol

## Setup

### 1. Install the server

```bash
cd server/
uv sync --extra dev --extra llm --extra stt --extra tts
```

### 2. Optional: install Ollama (legacy backend only)

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:8b
```

### 3. Run (testing profile, vLLM planner + CPU STT + espeak)

```bash
cd server/
LLM_BACKEND=vllm \
VLLM_MODEL_NAME=Qwen/Qwen3-8B-AWQ \
PERFORMANCE_MODE=0 \
STT_DEVICE=cpu \
STT_COMPUTE_TYPE=int8 \
TTS_BACKEND=espeak \
uv run --extra llm --extra stt --extra tts python -m app.main
```

### 4. Run (performance profile, vLLM planner + Orpheus TTS)

```bash
cd server/
LLM_BACKEND=vllm \
VLLM_MODEL_NAME=Qwen/Qwen3-8B-AWQ \
PERFORMANCE_MODE=1 \
STT_DEVICE=cpu \
VLLM_GPU_MEMORY_UTILIZATION=0.35 \
ORPHEUS_GPU_MEMORY_UTILIZATION=0.35 \
uv run --extra llm --extra stt --extra tts python -m app.main
```

The server starts on `http://0.0.0.0:8100`.

The server now auto-loads a local `.env` file (if present), and by default will
use backend-appropriate model loading:
- `LLM_BACKEND=vllm`: model download handled by Hugging Face/vLLM (`HF_TOKEN` required for gated repos).
- `LLM_BACKEND=ollama`: optional auto-pull with `AUTO_PULL_OLLAMA_MODEL=1`.

Example `.env`:

```bash
LLM_BACKEND=vllm
VLLM_MODEL_NAME=Qwen/Qwen3-8B-AWQ
STT_DEVICE=cpu
HF_TOKEN=hf_xxx

# Legacy Ollama compatibility path:
MODEL_NAME=qwen3:8b
AUTO_PULL_OLLAMA_MODEL=1
OLLAMA_PULL_TIMEOUT_S=1800
```

Notes:
- `STT_DEVICE=cpu` avoids STT contention with Qwen/Orpheus GPU inference.
- Keep `CONVERSE_KEEP_ALIVE=0s` and `PLAN_KEEP_ALIVE=0s` when using Ollama compatibility mode.
- `PERFORMANCE_MODE=0` keeps Orpheus disabled (espeak/off fallback only).

## Configuration

All settings are overridable via environment variables:

| Variable | Default | Description |
|---|---|---|
| `LLM_BACKEND` | `vllm` | `vllm` (default) or `ollama` compatibility backend |
| `LLM_MAX_INFLIGHT` | `1` | Shared generation concurrency across `/plan` and `/converse` |
| `VLLM_MODEL_NAME` | `Qwen/Qwen3-8B-AWQ` | Planner/conversation model for vLLM backend |
| `VLLM_DTYPE` | `bfloat16` | vLLM dtype |
| `VLLM_GPU_MEMORY_UTILIZATION` | `0.35` | GPU memory target for Qwen vLLM engine |
| `VLLM_MAX_MODEL_LEN` | `4096` | vLLM max sequence length |
| `VLLM_MAX_NUM_SEQS` | `2` | vLLM max concurrent sequences |
| `VLLM_MAX_NUM_BATCHED_TOKENS` | `256` | vLLM batch cap |
| `VLLM_TEMPERATURE` | `0.7` | vLLM sampling temperature |
| `VLLM_TIMEOUT_S` | `20.0` | vLLM generation timeout |
| `VLLM_MAX_OUTPUT_TOKENS` | `512` | vLLM max output tokens |
| `GPU_UTILIZATION_CAP` | `0.80` | Enforced cap for `Qwen + Orpheus` utilization sum |
| `PLAN_TIMEOUT_S` | `5.0` | Ollama mode timeout |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API base URL |
| `MODEL_NAME` | `qwen3:14b` | Ollama model name |
| `AUTO_PULL_OLLAMA_MODEL` | `1` | Auto-pull `MODEL_NAME` from Ollama if missing |
| `OLLAMA_PULL_TIMEOUT_S` | `1800.0` | Timeout for model pull at startup / retry |
| `PLAN_MAX_INFLIGHT` | `1` | Max concurrent `/plan` requests before fast 429 shedding |
| `PLAN_KEEP_ALIVE` | `0s` | Ollama keep-alive for `/plan` calls |
| `WARMUP_LLM` | `1` | Warm selected LLM backend at startup |
| `MAX_ACTIONS` | `5` | Max actions per plan |
| `TEMPERATURE` | `0.7` | Ollama sampling temperature |
| `NUM_CTX` | `4096` | Ollama context window size |
| `CONVERSE_KEEP_ALIVE` | `0s` | Ollama keep-alive for `/converse` calls |
| `PERFORMANCE_MODE` | `0` | Enables Orpheus path only when true |
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
| `ORPHEUS_MIN_FREE_VRAM_GB` | `10.0` | Minimum free VRAM to allow Orpheus startup in performance mode |
| `TTS_BUSY_QUEUE_THRESHOLD` | `0` | Any active Orpheus request beyond this sheds immediately to `espeak` |
| `SERVER_HOST` | `0.0.0.0` | Bind address |
| `SERVER_PORT` | `8100` | Bind port |

## API

### `GET /health`

Returns server and LLM backend status.

```json
{
  "status": "ok",
  "model": "Qwen/Qwen3-8B-AWQ",
  "llm_backend": "vllm",
  "llm_engine_loaded": true,
  "ollama": false,
  "resource_profile": "conservative",
  "performance_mode": false,
  "orpheus_enabled": false,
  "gpu_budget": {
    "qwen_backend": "vllm",
    "qwen_utilization": 0.35,
    "orpheus_utilization": 0.35,
    "combined_utilization": 0.7,
    "cap": 0.8
  },
  "ai": {
    "stt": {"model_size": "base.en", "device": "cpu", "compute_type": "int8", "loaded": false},
    "tts": {"backend_pref": "auto", "backend_active": "espeak", "loaded": true}
  }
}
```

Returns `503` when the selected LLM backend is not reachable.

## TTS Notes

- Orpheus model repos are gated on Hugging Face. Account access + auth are required.
- First TTS request can be significantly slower than warm-path requests because model load/compile happens lazily.
- The Orpheus backend uses a persistent event loop thread to keep the vLLM engine alive between requests. On failure, the engine is explicitly shut down and GPU memory is freed before retrying.
- If logs show `CUDA out of memory`, lower:
  - `ORPHEUS_GPU_MEMORY_UTILIZATION`
  - `ORPHEUS_MAX_NUM_SEQS`
  - `ORPHEUS_MAX_NUM_BATCHED_TOKENS`
- If logs show `orpheus stream idle ...` timeouts, raise:
  - `ORPHEUS_IDLE_TIMEOUT_S`
  - `ORPHEUS_TOTAL_TIMEOUT_S`

### `POST /plan`

Accepts a world-state snapshot, returns a bounded performance plan.

**Request:**

```json
{
    "robot_id": "robot-1",
    "seq": 42,
    "monotonic_ts_ms": 123456789,
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
    "plan_id": "f6a4d07e9abf49ce88381d0b0b6a93ab",
    "robot_id": "robot-1",
    "seq": 42,
    "monotonic_ts_ms": 123456789,
    "server_monotonic_ts_ms": 987654321,
    "actions": [
        {"action": "emote", "name": "excited", "intensity": 0.9},
        {"action": "say", "text": "Oh! A ball!"},
        {"action": "gesture", "name": "look_at", "params": {"bearing": 15.2}},
        {"action": "skill", "name": "investigate_ball"}
    ],
    "ttl_ms": 2000
}
```

**Error codes:** 429 (planner busy), 504 (LLM timeout), 502 (LLM unreachable or backend error), 422 (invalid request).

### `WebSocket /converse`

- Requires `robot_id` query parameter.
- Optional diagnostics: `session_seq`, `session_monotonic_ts_ms`.
- Only one active stream per `robot_id`; newer sessions preempt older sessions with close code `4001`.

### `POST /tts`

- Optional metadata fields: `robot_id`, `seq`, `monotonic_ts_ms`.
- If Orpheus is busy and `espeak` fallback is unavailable, returns `503` with `detail=tts_busy_no_fallback` immediately (no long timeout).

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

See [docs/TODO.md](../docs/TODO.md) for the full backlog. Key remaining items for server:
- Interaction history / conversation memory
- Personality engine: system prompt v2 with affect state embedding
- Personality engine: LLM response → affect impulse parsing
- Response caching for common triggers
