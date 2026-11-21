# Voice ID: who is talking, from their voice

Status 2026-11-18: built, **collecting**. Turn audio is saved and voiceprints learn from the
camera. The robot logs the server's guess but does not act on it yet: `conversation.voice_id_use`
stays off until the bake-off sets the thresholds. This is SIM-INTERACTION stage 5
(`~/vantage/docs/SIM-INTERACTION.md`) and Track E Phase 2 in `docs/TODO.md`.

## Decisions

- **On the server** (Ben, 2026-11-18; SIM-INTERACTION open question 1). Every turn's audio
  already goes there for speech-to-text. The voiceprints stay on the LAN box, which fits the
  names/privacy boundary: nothing goes to an outside service.
- **Model: SpeechBrain ECAPA-TDNN** (`speechbrain/spkrec-ecapa-voxceleb`, Apache-2.0, 192-d).
  It runs on the CPU at about 40 ms per second of speech, in a thread beside STT, so replies
  are no slower. It is trained on adult voices, so children are the open question the
  bake-off answers. WeSpeaker ResNet is the fallback candidate.
- **Learn from the camera, not an enrollment session.** A turn's voice goes into a member's
  prints only when:
  - the robot saw exactly one face, recognised at a score of `VOICE_ENROLL_FACE_SCORE` (0.5)
    or better;
  - the clip holds at least `VOICE_ENROLL_MIN_SPEECH_S` (1.5 s) of speech;
  - the clip has words.

  The risk is a child talking off camera while a parent's face is in view. So a sample is
  refused when it clearly sounds like another known member. Once a member has 5 prints, a
  sample is also refused when it sounds nothing like them (below 0.25).
- **Several samples per person, not one average.** Each member keeps up to 40 samples. A full
  set drops its most redundant sample, not its oldest. A member's score is the mean of their
  three best sample matches. A name is given only when the best member clears
  `VOICE_MATCH_SCORE` and leads the next by `VOICE_MATCH_MARGIN`, as with faces, because the
  brothers may overlap.
- **Short answers rely on the whole conversation.** Answers like "seven" (about 0.5 s) carry
  too little voice. The server also keeps a running average weighted by speech length, and
  sends both the turn's match and the conversation's. The average starts over when a turn
  clearly names someone else.

## Flow

1. **Profile (robot → server).** Each profile message carries:
   - `face_speaker` `{member_id, score, faces, bearing_deg}` when exactly one recognised face
     is in view;
   - `roster_ids`, when the roster was read and is enabled. The server drops prints of anyone
     not on that list.
2. **End of utterance** (`server/app/routers/converse.py`). The voice task starts on the
   committed turn's full audio and waits for the turn to finish. A turn dropped by a late
   resume is discarded, because its audio comes back merged into the next turn.
3. **The voice task** (`server/app/voice/service.py`) embeds, matches and maybe learns, saves
   the clip, then sends this to the robot:

   ```json
   {"type": "speaker", "turn_id": "...", "turn": {...}, "session": {...}, "learned": false, "learn_why": "..."}
   ```
4. **The robot** keeps the guess (`TickLoop._take_voice_guess`). It logs `voice.speaker ...`
   next to the faces in view, and writes a `voice` line into conversation history, which the
   dashboard shows under the turn. With `conversation.voice_id_use` on, `_speaker_member_id()`
   uses the voice in two cases:
   - nobody is in view, or the one face in view is unrecognised: the voice names the speaker;
   - several faces are in view: the voice picks the talker among the recognised faces.

   A single recognised face still wins over the voice. A guess older than 60 s is ignored.

## Storage and privacy

The data lives in `data/voice/` at the repo root on the server (git-ignored; directories
0700, files 0600).

- **Turn clips:** `turns/<YYYY-MM-DD>/<HHMMSS>_<turn_id>.wav` with a `.json` sidecar holding
  the transcript, the face label, speech length, the voice match and the learning decision.
  Clips are kept `VOICE_CAPTURE_DAYS` (30) days, and the oldest days go first above
  `VOICE_CAPTURE_MAX_MB` (2000).
- **Voiceprints:** `voiceprints.json`, keyed by roster member id. Names never reach the server.

Removing a member, or "Forget everyone", on the robot calls `DELETE /voice/prints/{id}` or
`DELETE /voice/prints`. That deletes the person's prints and every clip labelled with them.
`GET /voice/prints` lists the sample count and seconds of speech per member.

## Settings (server `.env`)

| Variable | Default | What it does |
|---|---|---|
| `VOICE_CAPTURE` | 0 | Save turn audio and sidecars |
| `VOICE_ID` | 0 | Embed, match, learn, and send `speaker` |
| `VOICE_MATCH_SCORE` / `VOICE_MATCH_MARGIN` | 0.45 / 0.08 | Placeholders until the bake-off |
| `VOICE_ENROLL_FACE_SCORE` / `VOICE_ENROLL_MIN_SPEECH_S` | 0.5 / 1.5 | When the camera's label is trusted |
| `VOICE_CAPTURE_DAYS` / `VOICE_CAPTURE_MAX_MB` | 30 / 2000 | Retention |
| `VOICE_DATA_DIR`, `VOICE_DEVICE` | `data/voice`, cpu | Where the data goes, and which device runs the model |

## Tuning (the bake-off)

After a few days of normal play:

```sh
cd server && .venv/bin/python scripts/voice_id_eval.py
```

The script uses clips with a clear face label as ground truth and prints:

- same-person and different-person scores by speech length;
- the member × member table, to check whether Owen and Clark overlap;
- leave-one-out identification (right / wrong / unsure) over a sweep of thresholds.

Then:

1. Set `VOICE_MATCH_SCORE` and `VOICE_MATCH_MARGIN` to the lowest threshold with about 0 wrong
   names. A child taken for an adult is the costly mistake.
2. Check the `voice` lines in conversation history against who was really there.
3. Turn on `conversation.voice_id_use`.

## Not built yet

- **Voice direction vs face bearing.** The XVF3800's direction of arrival
  (`ear.event.doa`) isn't consumed by the tick loop yet, and its offset and sign aren't
  calibrated against the camera. Once they are, learning can require the voice to come from
  the face, which closes the off-camera-child gap properly. `bearing_deg` is already in the
  sidecars.
- **A dashboard "record my voice" button**, for people the camera rarely sees well. Mommy
  has no face samples yet.
- **Kid vs adult from the voice alone**, as SIM-INTERACTION asks for first. It may fall out of
  enrolled matching, since every household member has a kind.
- **Owner mode** (`docs/screen-ui-and-admin.md`) needs a high-confidence voice match for Ben.
