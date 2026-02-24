# Robot Buddy — TODO Archive

Completed items moved from `docs/TODO.md` during periodic compaction.
This file is not loaded into Claude Code context. See `docs/TODO.md` for active work.

---

## Archived 2026-02-24

### Personality Engine — B6 Evaluation (tests)
- [x] Add/extend tests: clamping behavior, worker intensity caps, planner-emote impulse routing, conv-ended teardown coverage, `confused` server vocab, schema-v2 parsing, guided decoding compliance
- [x] Add tests for RS-1/RS-2 time limits, `/converse` overflow/timeouts/disconnects, and "no transcript logs by default" privacy policy

### Conversation & Voice
- [x] `[opus]` LLM conversation history/memory — server-side session context (stash/restore with 30 min TTL)
- [x] `[sonnet]` TTS perf hardening: replace Python-loop resampling in `server/app/tts/orpheus.py` with an efficient resampler; add max utterance duration safeguards

### Dashboard
- [x] `[sonnet]` Camera settings panel
