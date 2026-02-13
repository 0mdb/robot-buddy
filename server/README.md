# server

Optional personality stack running on a 3090 Ti on the local network.

## Responsibilities
- LLM: generate short performance plans (emotions + gestures + lines)
- TTS/STT: optional voice pipeline

## Contract
Input: world state + recent interaction history
Output: performance plan (bounded length):
- say(text)
- emote(name, intensity)
- gesture(name, params)
- move(mode or twist target)

## TODO
- [ ] Decide serving framework (FastAPI recommended)
- [ ] Implement `/plan` endpoint
- [ ] Implement `/tts` endpoint (optional)
- [ ] Add caching for instant responses
