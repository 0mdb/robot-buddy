# server

Optional AI personality stack running on a 3090 Ti on the local network.

## Architecture

```
Supervisor (Pi 5) ──POST /plan──► FastAPI server ──/api/chat──► Ollama (qwen3:14b)
                  ◄── PlanResponse ──┘                           GPU: 3090 Ti
```

- **Model:** Qwen 3 14B (Q4_K_M) via Ollama (~9 GB VRAM)
- **Server:** FastAPI + uvicorn on port 8100
- **LLM client:** async httpx calling Ollama's `/api/chat` with structured output (JSON schema)

## Current Conversational Audio Status (2026-02-18)

- End-to-end conversation transport is working:
  - face mic uplink (`MIC_AUDIO`) reaches supervisor and server
  - server `/converse` emits emotion + TTS audio chunks
  - supervisor forwards TTS chunks to face speaker over `AUDIO_DATA`
- Face speaker playback is confirmed by on-device heartbeat counters:
  - `speaker_rx_chunks` and `speaker_play_chunks` both increase during turns
  - `speaker_play_errors` remains `0` in recent probes
- Current quality blocker:
  - audio on the face speaker is often unintelligible despite correct transport
  - this is now a quality-tuning problem (not a pipeline/connectivity problem)

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

## Configuration

All settings are overridable via environment variables:

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API base URL |
| `MODEL_NAME` | `qwen3:14b` | Ollama model name |
| `PLAN_TIMEOUT_S` | `5.0` | Max seconds to wait for LLM response |
| `WARMUP_LLM` | `1` | Warm Ollama model at startup (`0` to disable) |
| `MAX_ACTIONS` | `5` | Max actions per plan |
| `TEMPERATURE` | `0.7` | LLM sampling temperature |
| `NUM_CTX` | `4096` | Context window size (tokens) |
| `CONVERSE_KEEP_ALIVE` | `0s` | Ollama keep-alive for `/converse` calls |
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
{"status": "ok", "model": "qwen3:14b", "ollama": true}
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
        {"action": "move", "v_mm_s": 150, "w_mrad_s": 50, "duration_ms": 1500}
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
| `move` | `v_mm_s`, `w_mrad_s`, `duration_ms` | speed -300..300, turn -500..500, duration 0..3000 ms |

## Testing

```bash
cd server/
uv run pytest tests/ -v
```

## TODO

- [ ] Implement `/tts` endpoint (optional voice pipeline)
- [ ] Add caching for instant responses to common triggers
- [ ] Interaction history / conversation memory
- [ ] Supervisor-side `PersonalityClient` integration
