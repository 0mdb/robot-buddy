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

## What This Plan Does NOT Include (Future Enhancements)



This section details potential future enhancements and how they could be implemented.



### Interaction History / Memory



To give the robot a sense of conversational context and prevent it from repeating itself, a short-term memory could be implemented.



-   **Goal:** Allow the LLM to see the last few turns of a conversation.

-   **Implementation Sketch:**

    -   **Server-Side:** The `PersonalityServer` would manage a rolling window of the last N interactions (e.g., a `collections.deque` of user inputs and robot plans). This history would be passed to the LLM as part of the prompt.

    -   **Prompt Engineering:** The system prompt would be updated to instruct the LLM on how to use the conversation history. The user prompt would include a formatted summary of the recent turns.

    -   **Supervisor-Side:** The `PersonalityClient` would need to be updated to manage a `session_id` and pass the conversation history back and forth.



### Caching Layer



To reduce latency for common world states, a caching layer could be introduced in front of the LLM.



-   **Goal:** Reuse previously generated plans for identical world states.

-   **Implementation Sketch:**

    -   **Server-Side:** In the `/plan` endpoint, a cache (e.g., an in-memory LRU cache via `functools.lru_cache` or a Redis cache) would be used.

    -   **Cache Key:** The key would be a hash of the incoming `WorldState` object.

    -   **Cache Value:** The value would be the corresponding `PlanResponse`.

    -   **TTL:** A Time-To-Live (TTL) would be applied to each cache entry (potentially using the `ttl_ms` from the plan itself) to ensure the robot doesn't get stuck in repetitive loops.



### Supervisor PersonalityClient



This is a note that the client-side implementation is a separate but coupled task.



-   **Location:** `supervisor/supervisor/devices/personality_client.py`

-   **Responsibilities:**

    -   Constructing the `world_state` dictionary from the supervisor's `RobotState`.

    -   Making async HTTP requests to the `PersonalityServer`.

    -   Handling network errors, timeouts, and retry logic.

    -   Parsing the server's JSON response into a validated `PersonalityPlan` dataclass.



### Multiple Model Support



The ability to switch between different models (e.g., a large, powerful model and a smaller, faster one) could optimize for cost, latency, or capability depending on the context.



-   **Goal:** Dynamically select an LLM based on the situation.

-   **Implementation Sketch:**

    -   **Configuration:** The current approach of using environment variables (`MODEL_NAME`) for the model is the first step.

    -   **Dynamic Selection:** A "model router" could be implemented in the `PersonalityServer`. This router could select a model based on the `trigger` in the `WorldState`. For example, simple `heartbeat` triggers could use a small, fast model, while more complex conversational triggers use a larger model.

    -   **API:** The `/plan` endpoint could be updated to accept an optional `model` parameter to allow the supervisor to request a specific model.





## Implementation Status & Next Steps (as of 2026-02-18)



### Current Implementation Status



The initial implementation of the AI Personality Server and key supervisor components is complete.



**Server-Side:**

- **Complete:** All foundational steps (scaffolding, schemas, prompts, endpoints) are implemented.

- **Implemented:** The `/plan` endpoint is functional.

- **Implemented:** The `/health` endpoint is functional.

- **Implemented:** The `/tts` endpoint, originally deferred, has been implemented. It allows for direct text-to-speech generation, bypassing the LLM for deterministic phrases.



**Supervisor-Side:**

- **Implemented:** An `AudioService` has been created to handle audio playback on the Raspberry Pi.

- **Implemented:** Lip-sync is integrated into the `AudioService`, calculating RMS amplitude of audio chunks to animate the face.

- **Implemented:** Webserver observability has been significantly enhanced:

    - A `/ws/logs` WebSocket endpoint provides real-time log streaming.

    - The `/status` endpoint has been updated to include `face.mood`, `face.talking`, and `last_decision` (the last plan from the personality server).



### Next Steps



1.  **PTT (Push-to-Talk) Integration:**

    - Implement the logic in the supervisor to listen for button events from the face MCU.

    - On PTT press: stop any current TTS, play a "listening" chime, and start recording from the USB microphone.

    - On PTT release: stop recording and send the audio to the `/converse` endpoint on the server.



2.  **Refine Lip-Sync:**

    - The current energy scaling for lip-sync (`rms * 10`) is a placeholder. It needs to be tuned by observing the robot's face to find a value that looks natural and responsive.



### Testing Plan



- **Server-Side:**

    - **`/tts` endpoint:** Use `curl` to send text and verify that PCM audio is streamed back correctly.

- **Supervisor-Side:**

    - **`AudioService`:** Trigger the `play_stream` method with audio from the `/tts` endpoint and confirm playback on the USB speaker.

    - **Lip-Sync:** Observe the face animation during TTS playback to assess the quality of the lip-sync.

    - **Observability:** Connect to the `/ws/logs` WebSocket and verify that logs are streaming. Poll the `/status` endpoint and confirm the new fields are present and updated correctly.

- **End-to-End:**

    - Perform a full conversation loop: press PTT, speak a phrase, release PTT, and verify that the robot responds with speech and facial expressions as determined by the personality server's plan.



### Potential Future Enhancements



- **Advanced Lip-Sync:** Move from simple energy-based lip flap to a more sophisticated phoneme-to-viseme mapping for more realistic mouth movements.

- **Conversation History:** Implement context/memory so the robot can remember previous turns in a conversation.

- **Sound Effects:** Add a library of sound effects that can be triggered by the personality plan for more expressive, non-verbal communication.

- **Dynamic Face Expressions:** Allow the face to show more nuanced expressions by combining base emotions with modifiers (e.g., a "slightly curious" look).
