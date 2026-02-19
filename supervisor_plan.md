# Consolidated supervisor_plan.md — Planner-Centric Supervisor V2 + Future Skills Backlog

## Summary
- Planner proposes intent; supervisor executes deterministically.
- Keep 50 Hz control loop and layered safety policy.
- Add EventBus, SkillExecutor, AudioOrchestrator, PlannerValidator, PlannerScheduler.
- Hard-cut rename from personality to planner.
- Reserve future-skill contracts for people recognition, recognized-person greeting, eye tracking, and wake word.

## Locked Decisions
1. Planner speech uses `POST /tts` + local playback.
2. Motion authority is skill-intent-only.
3. Naming is planner-first, no compatibility aliases.
4. PTT/listening preempts planner speech.
5. Event ingestion uses callback fanout + transition polling.
6. `/plan` supports `skill` and removes `move`.
7. Unified audio orchestration owns `/converse` + `/tts` arbitration.
8. WANDER idle default is slow patrol drift.

## Implemented V2 Scope
- `supervisor/supervisor/planner/event_bus.py`
- `supervisor/supervisor/planner/skill_executor.py`
- `supervisor/supervisor/planner/validator.py`
- `supervisor/supervisor/planner/scheduler.py`
- `supervisor/supervisor/devices/audio_orchestrator.py`
- `supervisor/supervisor/devices/planner_client.py` (renamed from personality client)
- `supervisor/supervisor/runtime.py` updated to planner pipeline + deterministic skill execution
- Face client callback fanout: `subscribe_button(cb)`, `subscribe_touch(cb)`
- Debug endpoint: `GET /debug/planner`
- `/plan` contract migrated to `skill` actions in server schemas/prompts/tests

## Future Skills Backlog (TODO)
| Epic | Target Outcome | Reserved Event/Interface | First Acceptance Target |
|---|---|---|---|
| People recognition (known household profiles, local-only) | Identify opted-in known users with unknown fallback | `person.detected`, `person.recognized`, `person.lost` | recognized vs unknown emitted with confidence and cooldowned UI output |
| Greet recognized people | Personalized greeting behavior when known person appears | skill `greet_known_person` | one greeting per person per cooldown window, no spam |
| Eye tracking / face following | Robot eyes track face in frame without body motion initially | skill `track_face_gaze`; gaze target `(x_norm, y_norm)` | smooth gaze tracking with deadband and no jitter |
| Wake word “hey robot” (on-device) | Hands-free transition into listening mode | `audio.wake_word_detected` | wake word enters listening state with timeout/cancel |

## Reserved Contracts for Backlog
1. Event namespace reservation: `person.*`, `audio.wake_word_detected`.
2. Scheduler supports future per-skill cooldown buckets.
3. AudioOrchestrator remains sole listen/talk arbiter.
4. SkillExecutor interface remains generic for `greet_known_person` and `track_face_gaze`.
