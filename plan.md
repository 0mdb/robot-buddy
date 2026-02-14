# AI Personality Server — Implementation Plan

## Model Selection

**Primary: Qwen 3 14B (Q4_K_M)** — ~9 GB VRAM, best-in-class tool-calling accuracy, leaves ~15 GB headroom for context + TTS later.

**Fallback: Qwen 3 8B (Q4_K_M)** — ~5 GB VRAM, faster inference (~50 tok/s), nearly identical tool-calling accuracy. Good if we need room for a TTS model simultaneously.

**Serving framework: Ollama** — simplest path to an OpenAI-compatible API with structured output support. Handles model management, quantization, and GPU allocation. If we outgrow it, we can swap to vLLM later (same OpenAI-compatible API surface).

Why not vLLM: vLLM is more powerful but heavier to set up and has had structured output bugs across releases. Ollama is rock-solid for single-model serving and trivial to install.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│ 3090 Ti Box                                          │
│                                                      │
│  ┌──────────┐     ┌──────────────────────────────┐  │
│  │ Ollama   │     │ Personality Server (FastAPI)  │  │
│  │ qwen3:14b│◄────┤                              │  │
│  │ :11434   │     │  POST /plan                  │  │
│  └──────────┘     │  POST /tts  (future)         │  │
│                   │  GET  /health                 │  │
│                   │  :8100                        │  │
│                   └──────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
        ▲
        │ HTTP (LAN)
        │
┌───────┴─────────┐
│ Supervisor (Pi5) │
│ PersonalityClient│
└─────────────────┘
```

The personality server is a thin FastAPI layer between the supervisor and Ollama. It owns the system prompt, formats the world state into the LLM prompt, validates the structured response, and returns a clean plan. The supervisor never talks to Ollama directly.

## File Structure

```
server/
├── app/
│   ├── main.py              # FastAPI app, lifespan, /health
│   ├── routers/
│   │   └── plan.py          # POST /plan endpoint
│   ├── llm/
│   │   ├── client.py        # Ollama HTTP client (async httpx)
│   │   ├── prompts.py       # System prompt, user prompt template
│   │   └── schemas.py       # Pydantic models for plan actions
│   └── config.py            # Settings (model name, Ollama URL, timeouts)
├── tests/
│   ├── test_plan.py         # Endpoint integration tests
│   ├── test_prompts.py      # Prompt formatting tests
│   └── test_schemas.py      # Schema validation tests
├── pyproject.toml           # Dependencies, metadata
├── Modelfile                # Ollama Modelfile for custom params
└── README.md                # Updated docs
```

## Step-by-Step Implementation

### Step 1: Project scaffolding & dependencies

Create `pyproject.toml` with:
- `fastapi`, `uvicorn[standard]` — HTTP server
- `httpx` — async HTTP client for Ollama
- `pydantic` >= 2.0 — request/response schemas + structured output schema
- `ruff` — linting (match supervisor conventions)

Create `app/config.py`:
- `Settings` dataclass with env-var overrides
- `OLLAMA_URL` (default `http://localhost:11434`)
- `MODEL_NAME` (default `qwen3:14b`)
- `PLAN_TIMEOUT_S` (default `5.0`)
- `MAX_ACTIONS` (default `5`)
- `TEMPERATURE` (default `0.7`)

### Step 2: Pydantic schemas for plan actions

`app/llm/schemas.py` — define the structured output contract:

```python
class SayAction(BaseModel):
    action: Literal["say"]
    text: str = Field(max_length=200)

class EmoteAction(BaseModel):
    action: Literal["emote"]
    name: str           # "happy", "surprised", "curious", ...
    intensity: float = Field(ge=0.0, le=1.0)

class GestureAction(BaseModel):
    action: Literal["gesture"]
    name: str           # "nod", "shake", "look_at", "wiggle"
    params: dict = {}   # gesture-specific (e.g. {"bearing": 15.2})

class MoveAction(BaseModel):
    action: Literal["move"]
    v_mm_s: int = Field(ge=-300, le=300)
    w_mrad_s: int = Field(ge=-500, le=500)
    duration_ms: int = Field(ge=0, le=3000)  # bounded!

PlanAction = SayAction | EmoteAction | GestureAction | MoveAction

class PlanResponse(BaseModel):
    actions: list[PlanAction] = Field(max_length=5)
    ttl_ms: int = Field(default=2000, ge=500, le=5000)

class WorldState(BaseModel):
    """Incoming world state from supervisor."""
    mode: str
    battery_mv: int
    range_mm: int
    faults: list[str]
    clear_confidence: float
    ball_detected: bool
    ball_bearing_deg: float
    speed_l_mm_s: int
    speed_r_mm_s: int
    v_capped: int
    w_capped: int
    trigger: str            # "heartbeat", "ball_seen", "obstacle", "mode_change"
```

### Step 3: System prompt & user prompt template

`app/llm/prompts.py`:

**System prompt** — defines the robot's personality and output format:

```
You are the personality of Robot Buddy, a small wheeled robot for kids.
You are curious, playful, and friendly. You express yourself through
emotions, gestures, short spoken phrases, and movement.

You receive the robot's current world state and respond with a short
performance plan — a list of 1-5 actions the robot should take right now.

Available actions:
- say(text): Speak a short phrase (max 200 chars, kid-friendly language)
- emote(name, intensity): Show an emotion on the LED face
  Names: happy, sad, surprised, curious, excited, sleepy, scared, angry, love, neutral
  Intensity: 0.0 to 1.0
- gesture(name, params): Physical gesture
  Names: nod, shake, look_at, wiggle, spin, back_up
  Params vary by gesture (e.g. look_at takes {"bearing": degrees})
- move(v_mm_s, w_mrad_s, duration_ms): Move for a bounded duration
  v_mm_s: -300 to 300 (forward/backward speed)
  w_mrad_s: -500 to 500 (turning rate)
  duration_ms: 0 to 3000 (max 3 seconds per action)

Rules:
- Keep spoken phrases short, fun, and age-appropriate (ages 4-10)
- Never say anything scary, mean, or inappropriate
- Match emotions to the situation
- If the robot sees a ball, act excited
- If an obstacle is close (range < 500mm), prefer backing up or turning
- If battery is low (< 6800mV), mention being sleepy
- Do not repeat the same phrase twice in a row
- Respond ONLY with valid JSON matching the schema. No other text.
```

**User prompt template** — formats world state into a concise prompt:

```
World state:
- Mode: {mode}
- Battery: {battery_mv}mV
- Range sensor: {range_mm}mm
- Faults: {faults}
- Path clear confidence: {clear_confidence:.0%}
- Ball detected: {ball_detected} (bearing: {ball_bearing_deg}°)
- Current speed: L={speed_l_mm_s} R={speed_r_mm_s} mm/s
- Speed after safety caps: v={v_capped} w={w_capped}
- Trigger: {trigger}

What should Robot Buddy do right now?
```

### Step 4: Ollama async client

`app/llm/client.py`:
- Async `httpx.AsyncClient` calling `POST /api/chat` on Ollama
- Pass the `format` parameter with the JSON schema from `PlanResponse.model_json_schema()` — Ollama uses this for structured output (grammar-constrained generation)
- Timeout via `httpx.Timeout(PLAN_TIMEOUT_S)`
- Parse response, validate against `PlanResponse`
- Return validated plan or raise on timeout/parse error

Key implementation detail: Ollama's `/api/chat` accepts a `format` field with a JSON schema. This constrains token generation so the output always matches our Pydantic schema. No post-hoc parsing failures.

### Step 5: `/plan` endpoint

`app/routers/plan.py`:
- `POST /plan` accepts `WorldState` body
- Calls the LLM client with formatted prompts
- Returns `PlanResponse` on success
- Returns 504 on LLM timeout
- Returns 502 on Ollama connection error
- Returns 422 on validation failure (shouldn't happen with structured output, but defense in depth)

### Step 6: `/health` endpoint & lifespan

`app/main.py`:
- FastAPI app with lifespan handler
- On startup: verify Ollama is reachable, model is loaded (warm the model with a dummy request)
- `GET /health` returns `{"status": "ok", "model": "qwen3:14b", "ollama": true/false}`

### Step 7: Ollama Modelfile

`server/Modelfile` — custom parameters for serving:

```
FROM qwen3:14b
PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER num_ctx 4096
PARAMETER stop </s>
```

This keeps context window small (4096 tokens is plenty — our prompts are short) which maximizes throughput and minimizes latency.

### Step 8: Tests

- `test_schemas.py`: Validate that example plans parse correctly, invalid plans are rejected, field bounds are enforced
- `test_prompts.py`: Verify prompt formatting produces expected strings for various world states
- `test_plan.py`: Integration test with a mock Ollama response (patch httpx), verify the endpoint returns valid plans, handles timeouts, handles connection errors

### Step 9: Update README.md

Document:
- How to install Ollama and pull the model
- How to start the server
- Environment variables
- API contract
- Example curl commands

## What This Plan Does NOT Include (deferred)

- **TTS endpoint** — add later when we wire up audio playback on the Pi
- **Interaction history / memory** — start stateless, add conversation context later
- **Caching** — premature until we see real latency numbers
- **Supervisor PersonalityClient** — separate task, lives in the supervisor codebase
- **Multiple model support** — start with one model, swap via config if needed
