# Jarvis

The owner's assistant: a **separate service** from buddy-server, with its own persona,
memory, logs, tools and credentials. Design: `docs/screen-ui-and-admin.md` §6 and the
Owner mode plan in `docs/TODO.md`. It lives here until it has a second client, then moves
to its own repo.

**Status: text-only skeleton.** No voice, no Buddy client, no scene drawing yet.

## What it does now

- `POST /v1/turn {text}` → `{text, speak, scene, tools_used, latency_ms}`: one turn on a
  local Ollama model with a tool loop (up to `JARVIS_MAX_TOOL_ROUNDS`).
- Tools, **read tier only**: `home_list`, `home_state` over Home Assistant's REST API. The
  HA client only has GET methods, so nothing in the house can change whatever the model
  asks. Entity domains are allow-listed; `person`, `device_tracker` and `camera` are left out.
- `speak: false` when a reply used a tool marked `personal` (none yet; finance will be).
  `scene` is always null until the scene protocol exists.
- `GET /v1/history`: the caller's own turns. `GET /v1/tools`: tools with tiers.
  `GET /health`: no auth, nothing personal.

## Auth

Every call except `/health` needs both:

- `Authorization: Bearer <device token>`, one token per client (`JARVIS_DEVICE_TOKENS`)
- `X-Jarvis-User: <identity>`, which must be in `JARVIS_OWNERS`

Missing or wrong → 401/403, logged as `refused`. With no tokens or owners configured,
everything is refused. The identity is asserted by the client; Buddy's supervisor will
send it only after PIN + face ID or voice ID.

## Data (`~/.local/share/jarvis`, mode 0700)

- `audit.jsonl`: refusals, turns, every tool call with its arguments and result status
- `history/<identity>.jsonl`: that owner's turns, fed back as context (last 6 within 30 min)

Nothing goes to Buddy's history, memory or capture.

## Run

```sh
cp jarvis/env.example ~/.config/jarvis/jarvis.env && chmod 600 ~/.config/jarvis/jarvis.env
# fill JARVIS_OWNERS, a cli token (openssl rand -hex 24), JARVIS_CLI_*, optionally HA
just jarvis-run                # foreground on :8200
just jarvis "is the garage open?"   # or `just jarvis` for a prompt
just jarvis-test
just jarvis-service            # systemd user unit, reads the main checkout
```

The default model is the gemma4 26B that Buddy already has loaded on :11435, so Jarvis
costs no extra VRAM. Turns share Ollama's single slot (`OLLAMA_NUM_PARALLEL=1`) with Buddy,
so a Jarvis turn can delay a Buddy reply by about a second.

## Next

1. A HA user + token, then try real questions; widen `_KEEP_ATTRS` as needed.
2. Tool-use eval on gemma4 26B (the BFCL-style eval in `server/app/eval`).
3. Reversible tier via HA's MCP server, with an entity allow-list and a confirm step.
4. Buddy as a client: supervisor routes turns in Jarvis mode, separate TTS voice, `J` badge.
