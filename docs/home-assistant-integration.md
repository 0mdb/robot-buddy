# Home Assistant Light Control via Conversation

## Context

Kids should be able to say "Hey Buddy, turn off my bedroom light" or "change my lamp to blue" and have it happen. The planner server is on the same network as Home Assistant. We extend the existing conversation structured JSON schema with a `home_actions` field and add a server-side HA client.

Scope: lights only, manual YAML device whitelist, act immediately (no confirmation).

## Implementation

### 1. Device registry — new `server/config/home_devices.yaml`

Static whitelist of allowed light entities with kid-friendly names:

```yaml
ha_url: "http://homeassistant.local:8123"
# HA_TOKEN comes from env var, not this file

devices:
  bedroom_light:
    friendly_name: "bedroom light"
    entity_id: "light.kids_bedroom"
    allowed_actions: [turn_on, turn_off]

  bedroom_lamp:
    friendly_name: "bedroom lamp"
    entity_id: "light.kids_lamp"
    allowed_actions: [turn_on, turn_off, set_color, set_brightness]
```

### 2. HA client module — new `server/app/home.py` (~100 lines)

- `DeviceEntry` dataclass: `name`, `friendly_name`, `entity_id`, `allowed_actions`
- `HomeDeviceRegistry`: loads YAML on init, provides `get_device(name)` and `list_devices_for_prompt()` (returns a string for the system prompt)
- `HomeClient`: wraps httpx calls to HA REST API
  - `async execute_action(device: DeviceEntry, action: str, params: dict) -> bool`
  - Maps our action names to HA service calls:
    - `turn_on` → `POST /api/services/light/turn_on` `{"entity_id": "..."}`
    - `turn_off` → `POST /api/services/light/turn_off` `{"entity_id": "..."}`
    - `set_color` → `POST /api/services/light/turn_on` `{"entity_id": "...", "rgb_color": [r, g, b]}`
    - `set_brightness` → `POST /api/services/light/turn_on` `{"entity_id": "...", "brightness_pct": N}`
  - Color name → RGB mapping for common colors (red, blue, green, purple, pink, orange, yellow, white, warm white)
  - 3-second timeout, logs errors, returns `bool` success
- Validation: reject any action not in the device's `allowed_actions` list
- If `HA_TOKEN` env var is not set or YAML doesn't exist, the registry is empty and the feature is silently disabled

### 3. Config — edit `server/app/config.py`

Add to `Settings`:
- `ha_token: str` — from `HA_TOKEN` env var, default `""` (disabled)
- `ha_devices_path: str` — from `HA_DEVICES_PATH` env var, default `"config/home_devices.yaml"` (relative to server root)

### 4. Conversation schema — edit `server/app/llm/conversation.py`

Extend `CONVERSATION_SYSTEM_PROMPT` with a conditional block (only if devices are configured):
```
You can control smart home lights. Available devices:
- "bedroom_light": bedroom light (can: turn_on, turn_off)
- "bedroom_lamp": bedroom lamp (can: turn_on, turn_off, set_color, set_brightness)

To control a device, include "home_actions" in your response:
  "home_actions": [{"device": "bedroom_lamp", "action": "set_color", "color": "blue"}]

Only use devices and actions from the list above. If the kid asks to control
something not on the list, say you can't do that one yet.
```

Extend `CONVERSATION_RESPONSE_SCHEMA` with:
```python
"home_actions": {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "device": {"type": "string"},
            "action": {"type": "string", "enum": ["turn_on", "turn_off", "set_color", "set_brightness"]},
            "color": {"type": "string"},
            "brightness": {"type": "integer", "minimum": 0, "maximum": 100},
        },
        "required": ["device", "action"],
    },
}
```

Add `home_actions` field to `ConversationResponse` dataclass:
```python
home_actions: list[dict] = field(default_factory=list)
```

Parse it in `parse_conversation_response_content()` — validate device names and actions against the registry, drop any that don't match.

### 5. Execute actions — edit `server/app/routers/converse.py`

In `_generate_and_stream()`, after getting the LLM response and before streaming TTS:
```python
# Execute home actions (fire-and-forget with logging)
if response.home_actions:
    home_client = ws.app.state.home_client  # may be None
    if home_client:
        for ha in response.home_actions:
            ok = await home_client.execute_action(ha["device"], ha["action"], ha)
            if not ok:
                log.warning("Home action failed: %s", ha)
```

Actions execute before TTS starts, so by the time the kid hears "turning off your light," it's already done.

### 6. Server startup — edit `server/app/main.py`

In the lifespan function, initialize the device registry and home client:
```python
if settings.ha_token:
    registry = HomeDeviceRegistry(settings.ha_devices_path)
    app.state.home_client = HomeClient(settings.ha_url, settings.ha_token, registry)
    # Inject device list into conversation prompt
else:
    app.state.home_client = None
```

### Files Summary

| File | Change |
|------|--------|
| `server/app/config.py` | Add `ha_token`, `ha_devices_path` settings |
| `server/app/home.py` | **New** — device registry + HA REST client |
| `server/config/home_devices.yaml` | **New** — device whitelist (example config) |
| `server/app/llm/conversation.py` | Extend schema, system prompt, response parsing |
| `server/app/routers/converse.py` | Execute home actions after LLM response |
| `server/app/main.py` | Initialize home client on startup |

## Verification

1. **Unit test**: mock httpx calls, verify device registry loading, action validation, color mapping
2. **Integration test**: start server with test YAML + mock HA, send text message via `/converse` WebSocket asking to "turn off bedroom light", verify HA API was called with correct entity_id and service
3. **Manual test**: configure real HA token + devices, use dashboard text input or wake word → ask Buddy to change lamp color → verify light changes and Buddy responds naturally
4. **Negative tests**: ask to control a device not in the whitelist → Buddy says it can't; HA unreachable → Buddy still responds verbally, logs warning
