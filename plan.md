# Robot Buddy Emotion Protocol & Conversation Pipeline

## Context

Robot Buddy needs a full emotional pipeline — from LLM response generation through TTS
with prosody to face animation — to make the robot charming, expressive, and capable of
real conversations with kids aged 5–12. The robot should introduce the potential of AI
to young kids with guardrails to make it safe but exciting.

### Hardware Status & Known Gaps

| Component | Status | Notes |
|-----------|--------|-------|
| ESP32 face display (TX/telemetry) | **Working** | FACE_STATUS, TOUCH_EVENT, HEARTBEAT, MIC_AUDIO telemetry active |
| ESP32 face USB RX (commands in) | **Working** | SET_STATE, GESTURE, SET_SYSTEM, SET_TALKING, AUDIO_DATA, SET_CONFIG parsed and applied |
| ESP32 mic (ES8311) | **Working (CDC uplink)** | 10 ms PCM uplink (`MIC_AUDIO`) gated by `AUDIO_MIC_STREAM_ENABLE` |
| ESP32 speaker (ES8311) | **Working (stream path)** | 10 ms PCM downlink queue + playback worker, drop-oldest on overflow |
| ESP32 face rendering (LVGL) | **Working** | Eyes + mouth render + talking-energy linkage active |

**Current focus**: close remaining server-side TTS latency/stability issues on warm/cold `/converse` paths while preserving stable CDC audio transport on the face MCU.

---

## 1. Emotion Taxonomy (12 Emotions)

Each with intensity 0.0–1.0. Designed for clear, exaggerated kid-readable expressions:

| ID | Name | Eye Expression | Voice Prosody |
|----|------|----------------|---------------|
| 0 | `neutral` | Calm, attentive | Even pace, warm tone |
| 1 | `happy` | Upturned crescents | Bright, melodic |
| 2 | `excited` | Wide open, sparkly | Fast, high pitch, energetic |
| 3 | `curious` | One brow raised, tilted | Rising intonation, thoughtful pauses |
| 4 | `sad` | Droopy, glistening | Slow, lower pitch, soft |
| 5 | `scared` | Wide, shrunk pupils | Breathy, trembling, quick |
| 6 | `angry` | Narrowed, intense | Firm, clipped (kept mild for kids) |
| 7 | `surprised` | Wide open, raised brows | Sharp intake, rising pitch |
| 8 | `sleepy` | Half-closed, slow blinks | Slow, mumbling, yawning |
| 9 | `love` | Heart-shaped / warm glow | Warm, gentle, adoring |
| 10 | `silly` | Cross-eyed or asymmetric | Goofy pitch wobble, giggly |
| 11 | `thinking` | Looking up/aside | Measured pace, "hmm" fillers |

### Gestures (13 One-Shot Animations)

| ID | Name | Trigger |
|----|------|---------|
| 0–9 | blink, wink_l, wink_r, confused, laugh, surprise, heart, x_eyes, sleepy, rage | (existing) |
| 10 | `nod` | Agreement/acknowledgment |
| 11 | `headshake` | Disagreement/no |
| 12 | `wiggle` | Playful shimmy |

---

## 2. TTS: Orpheus TTS

**Primary: Orpheus TTS** (3B param, ~6GB VRAM) — built-in emotion tags (`<happy>`,
`<sad>`, etc.), expressive prosody, streaming output, Llama-based architecture.

**Fallback: Kokoro TTS** (82M params, <1GB VRAM) — extremely fast, good for
real-time if Orpheus is too slow.

**Emotion → Prosody Tag Mapping:**

```python
EMOTION_TO_PROSODY_TAG = {
    "neutral": "",  "happy": "<happy>",  "excited": "<excited>",
    "curious": "",  "sad": "<sad>",      "scared": "<scared>",
    "angry": "<angry>",  "surprised": "<surprised>",  "sleepy": "<yawn>",
    "love": "<happy>",   "silly": "<laughing>",       "thinking": "",
}
```

---

## 3. Conversation Pipeline

```
Kid speaks → ESP32 mic → Pi supervisor → 3090 Ti server
  → Whisper STT → Qwen3 14B LLM → Orpheus TTS
  → emotion + audio stream back to Pi → ESP32 face + speaker
```

**Key design**: Emotion is sent before audio so the face changes expression before
the robot starts speaking — this feels more natural.

### Latency Budget (Target: <2s end-to-end)

| Stage | Target |
|-------|--------|
| VAD + utterance detection | ~300ms |
| STT (Whisper) | ~500ms |
| LLM first token | ~300ms |
| Emotion event sent | ~50ms |
| TTS first chunk | ~200ms |
| **Total to first audio** | **~1.4s** |

**VRAM budget**: Whisper ~3GB + Qwen3 ~9GB + Orpheus ~6GB = ~18GB (3090 Ti has 24GB)

### Two Emotion Modes (coexisting)

- **Reactive** (existing `/plan`): world-state-driven (obstacles, battery, ball)
- **Conversational** (new `WS /converse`): speech-driven, takes priority while speaking

---

## 4. Wire Protocol (v2)

### Commands (supervisor → MCU)

| ID | Name | Payload |
|----|------|---------|
| 0x20 | SET_STATE | mood(u8) intensity(u8) gaze_x(i8) gaze_y(i8) brightness(u8) |
| 0x21 | GESTURE | gesture_id(u8) duration_ms(u16-LE) |
| 0x22 | SET_SYSTEM | mode(u8) phase(u8) param(u8) |
| 0x23 | **SET_TALKING** | talking(u8) energy(u8) |
| 0x24 | **AUDIO_DATA** | chunk_len(u16-LE) pcm_data(N) |
| 0x25 | SET_CONFIG | param_id(u8) value(4 bytes) |

### Server WebSocket: `WS /converse`

Client → Server: `audio` chunks, `end_utterance`, `cancel`
Server → Client: `emotion` (immediate), `audio` (streaming), `transcription`, `done`

---

## 5. Implementation Status

### Phase 1: Protocol Definition — DONE
- [x] `esp32-face-display/main/protocol.h` — expanded enums, new command IDs
- [x] `esp32-face-display/main/face_state.h` — 12 moods, 13 gestures, talking state
- [x] `esp32-face-display/main/face_state.cpp` — eyelid/mouth/color mappings for all moods
- [x] `supervisor/supervisor/devices/protocol.py` — matching Python enums + builders
- [x] `supervisor/supervisor/devices/face_client.py` — send_talking, send_audio_data
- [x] `supervisor/supervisor/runtime.py` — 1:1 emotion mapping (no more lossy collapse)
- [x] `supervisor/supervisor/state/datatypes.py` — face_talking state
- [x] `server/app/llm/prompts.py` — expanded personality + emotion taxonomy
- [x] `server/app/llm/schemas.py` — VALID_EMOTIONS set
- [x] `docs/protocols.md` — v2 protocol spec
- [x] Tests pass, linter clean

### Phase 2: Server Conversation Endpoint — DONE
- [x] `server/app/stt/whisper.py` — Whisper STT (faster-whisper, lazy-loaded)
- [x] `server/app/tts/orpheus.py` — Orpheus TTS with prosody tags, streaming chunks
- [x] `server/app/routers/converse.py` — WS /converse (audio+text input, emotion+audio output)
- [x] `server/app/llm/conversation.py` — history, structured JSON prompt, Ollama integration
- [x] `server/app/main.py` — converse router wired up
- [x] `server/pyproject.toml` — optional deps for stt/tts
- [x] Tests pass, linter clean

### Phase 3: Supervisor Pipeline — DONE
- [x] `supervisor/supervisor/devices/conversation_manager.py` — WebSocket client,
      emotion→face, audio→speaker with RMS energy, talking animation, gesture dispatch
- [x] Tests pass, linter clean

### Phase 4: ESP32 Hardware Bring-Up (CDC conversation path) — DONE
- [x] USB RX command path stable in app mode
- [x] `SET_TALKING (0x23)` and `AUDIO_DATA (0x24)` handlers
- [x] RX frame capacity raised (`MAX_FRAME=768`)
- [x] Speaker stream queue + dedicated playback worker
- [x] Talking animation linkage with timeout clear
- [x] Mic stream worker + telemetry (`MIC_AUDIO=0x94`)
- [x] `AUDIO_MIC_STREAM_ENABLE (0xA3)` config control
- [x] Heartbeat audio diagnostics tail appended (optional/append-only)

### Phase 5: Supervisor + Server Full-Duplex Wiring — DONE
- [x] `ConversationManager` wired into supervisor runtime lifecycle
- [x] Face mic stream (`MIC_AUDIO`) forwarded to `/converse` as `audio` events
- [x] Supervisor VAD-style utterance segmentation + `end_utterance` on silence/gap
- [x] Orpheus stream chunking aligned to 10 ms (`320` bytes at 16 kHz s16 mono)
- [x] `send_talking(True, energy)` per outbound subchunk + clear on end/cancel
- [x] Mic stream enable on face connect, disable on shutdown

### Phase 6: Validation + Soak (in progress)
- [x] Protocol parser/unit coverage added for MIC_AUDIO + heartbeat extension
- [x] Firmware builds clean
- [x] USB unplug/replug recovery during active streaming
- [x] 10-minute full-duplex CDC soak completed (speaker stable; mic uplink active)
- [ ] 15-minute speaker downlink soak
- [ ] 15-minute mic uplink soak
- [ ] End-to-end latency validation (`emotion` before first audio chunk, `<2s` target)
- [ ] Cold `/converse` reliability (occasional LLM timeout observed)
- [ ] Warm `/converse` stability and first-audio latency reduction (Orpheus init path still high)

Current measured `/converse` behavior (latest):
- `emotion` is delivered before audio as designed.
- Warm path can produce audio, but first audio has been in the ~23–31s range.
- Cold path can still hit `LLM timeout` in some runs.
