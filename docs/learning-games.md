# Learning games

**Status:** design, 2026-11-18. Nothing built yet. Curriculum notes:
`docs/research/alberta-curriculum-g2-g3.md` (Alberta K-6, what CBE teaches).

The point of Alexa is to encourage learning. She already plays guessing games well (the kids
played one end to end on 2026-11-17 and again today). This doc adds math, phonics and word
games pitched at each child's grade, which move up as the child shows they know a skill.
Grade 3 material is available as stretch, behind two locks.

## 0. Settled decisions (Ben, 2026-11-18)

| # | Decision |
|---|---|
| L1 | **Ceilings:** Owen up to **Grade 3**; the five-year-old up to **Grade 1**. Grade 3 only once progress is measured (§2.1). |
| L2 | **Offering:** at most **once a day per child**, and only when she **sees** that child (face ID), not in the middle of something else. |
| L3 | **Telling kids about progress:** yes, but only for a skill where the measurement is solid (§2.1, "confident"). |

## 1. Principles

1. **A game first, a lesson second.** Short turns, her own personality, silly stakes ("if you
   get five, I'll do my rocket face"). Never a worksheet read aloud.
2. **The child chooses.** She offers a learning game at most once a day per child, when she
   sees them ("want to try a number riddle?"), and only when nothing else is going on. Any "no", "stop"
   or "something else" ends it straight away, cheerfully.
3. **Honest and kind.** The existing HONESTY rule applies: a wrong answer is named kindly
   before helping ("not quite, 7 + 8 is 15; want a trick for that one?"). Praise is specific,
   not stock.
4. **Stretch, but not past frustration.** Aim for mostly right answers (about 4 in 5). Two
   misses in a row means an easier step for the rest of this game, without saying so. A miss
   is never stored as a failure.
5. **Same rules as everything else:** session time limits, safety, quiet mode.

## 2. Levels and the two locks

Each child has a **base level** from their roster age: 5 → Kindergarten, 6 → Grade 1,
7 → Grade 2, 8 → Grade 3. Each **skill** (§4) has its own steps (K, G1, G2, G3) and its own
current step per child, starting at the base level.

A skill moves up one step only when **both locks** open:

1. **Parent ceiling (lock 1):** a per-child setting in the dashboard (Household panel), the
   highest grade Alexa may use. Set: Owen up to Grade 3, the five-year-old up to Grade 1 (L1);
   default for a new child is base level + 1.
2. **Mastery (lock 2):** at least 80% correct in each of **3 games on 3 different days** at the
   current step. Shown in the dashboard per child and skill.

A skill can step down one level if a child misses most of 2 games in a row. That isn't shown
to the child; it only keeps games fun.

### 2.1 Measuring progress

Progress is only worth anything if the scoring is right, so the model's own "correct" is not
trusted where the robot can check it.

**Each attempt is recorded** (per member, robot-local `data/learning_progress.json`):
skill, step, the item ("7 + 8", "swap c→h in cat", "un + happy"), the expected answer, what
the child said (as transcribed), correct or not, **who decided** (`checked` by code or
`model`), and the game and date.

**Who decides "correct":**
- **Math is checked by code.** The card asks the model to put each question in a fixed form in
  the `practice` field (e.g. `{"item": "7+8", "answer": "15"}`); the server computes the
  expected result and compares it with the number in the child's transcript (words or digits,
  "fifteen" / "15"). The model can't mark a wrong sum right, and a garbled number ("fifty"
  for "fifteen") is recorded as *unclear*, not wrong.
- **Words and sounds are checked by code where a list exists:** rhyme pairs (CMU
  pronouncing dictionary, already in the training venv), prefix/suffix and opposite pairs
  from a small table per card. Anything else falls back to the model's judgement, marked
  `model`.

**What counts:**
- **Accuracy per game** at the current step (unclear items left out).
- **Mastery** (lock 2): ≥80% in 3 games on 3 different days, with at least 5 scored items in
  each game.
- **Confident** (when she may tell the child, L3): mastery reached on items that were mostly
  `checked` by code (≥80% of them). A skill judged mainly by the model is never announced.
- **Trend:** accuracy over the last 5 games, shown to parents.

**What she says** when a skill is confident: something specific and true ("you got every
5s question today, and last week those were tricky!"), at most once per game, never a
comparison with a sibling, never about a skill that isn't confident.

**Parents see** in the dashboard, per child and skill: current step, ceiling, accuracy per
game, trend, items missed most, and how much was code-checked. Progress can be reset per
child.

**Checking the checker:** before scoring goes live, replay 50 recorded attempts from the
conversation history (opt-in) and compare the code's verdict with a hand label; fix the
number parser on any mismatch.

## 3. How it works (progressive disclosure)

The system prompt stays small and cached (~2,300 tokens; prefill ~100 ms cached vs ~520 ms
cold, measured 2026-11-18). Game detail only enters the prompt while a game is on.

```
system prompt (cached)        GAMES: one line listing the games she can offer, plus
                              "when a game starts, the first thing in notes is Game: <id>"
...conversation history...
CURRENT STATE (per turn)      mood, audience, memory, game picks
GAME CARD (per turn, only     rules for that game + this child's step for its skill,
  while a game is on)         with the content for that step
child's message
```

- **Which card:** the server reads `Game: <id>` from the last reply's notes. On the turn a
  game is asked for (before any notes exist), a keyword cue (like `safety_cues.py`) matches
  the child's words to a game ("number riddle", "rhyme", "times tables"). An unknown game
  gets no card and she plays it from general knowledge, as she does now.
- **Cards are data:** `server/app/llm/games/<id>.toml` with rules, keywords, the skill they
  practise, and content per step. They are added to the prompt as a system message right
  before the child's message, so they never break the cached prefix.
- **Learner info comes from the robot:** with per-person memory (PE spec S2 §8, amended
  2026-11-18) the robot knows who is talking. It adds `learner` to the profile for the
  recognised speaker: base level, ceiling, and current step per skill. Nobody recognised →
  no learner info → the card's base-level content for the audience profile's age.
- **Scoring (as built, 2026-11-18):** no reply field. For the drill games the server already
  knows each verdict (`drill.py`), so when a turn completes it sends the robot a `practice`
  record: game, skill, step, the item, the expected answer, the child's answer *as parsed* (a
  number or the right word, never their raw words), the verdict, `decided: code` and
  `source: voice|touch`. Records are keyed `<seed>:<game>:<Q#>` and replaced if re-answered,
  never counted twice; a dropped speculative turn sends nothing. The robot files it under the
  recognised child (only face in view; nobody recognised → not recorded) in
  `data/household_learning/progress.json` (mode 600, removed with the member or "Forget
  everyone"). A model-filled field (and its spec amendment) waits until a model-judged game
  needs scoring.

## 4. Skills and their steps (from the curriculum)

| Skill | K | Grade 1 | Grade 2 | Grade 3 (stretch) |
|---|---|---|---|---|
| **Counting** | count to 20, one more / one less | to 100, skip by 2s, 5s, 10s | to 1000 from any number; by 2s, 10s anywhere; by 20s, 25s, 50s from 0 | rows of the times tables (3s, 4s, 6s...) |
| **Place value** | bigger / smaller to 10 | tens and ones to 100 | hundreds, tens, ones; compare with < > | to 100 000; rounding |
| **Add/subtract facts** | within 5, then 10 | within 20 | facts to 10 + 10 fluently; within 100 with make-ten, doubles; missing numbers | within 1000 (column), estimation |
| **Times tables** | — | — | equal groups by 2s, 5s, 10s | facts to 10 × 10 and division; remainders |
| **Money** | coin names | coin values | same coins by skip counting | mixed coins in cents; dollars |
| **Fractions** | halves | halves, quarters | unit fractions to tenths, compare | fractions to twelfths, compare |
| **Shapes** | circle, square, triangle | sides, corners | sort by two attributes; 3-D faces | right angles, polygons to octagon |
| **Time** | morning / night, days | days of the week, months | longer / shorter, calendar | clock: minutes past / to, a.m./p.m. |
| **Sounds** (phonological) | first sound, rhymes, syllable claps, c-at blending | blend/segment to 5 sounds, swap a sound | blends (str, fl), 6 sounds, swap inside a blend | (ends in Grade 2) |
| **Phonics patterns** | letter sounds | the first 60 letter-sound patterns (sh, ch, th, long vowels, ar/er/or...) | patterns 61-120 (ai/ay, igh, oo, ow, ph, wr, -tion...) | clusters, silent letters, chunking long words |
| **Word parts** | compound words | -s, -ing, -ed | -er/-est, compound words, synonyms/antonyms | prefixes re, un, dis, mis, sub, super; -ly, -er/-or/-ist; homophones |

## 5. First games (8)

| # | Game | Skill | How it goes |
|---|---|---|---|
| 1 | **Number Detective** | Place value | "I'm thinking of a number between 1 and 1000. Ask if it's bigger or smaller", or clue mode: "it has 4 hundreds, no tens, and 7 ones". Uses the game picks idea for her secret number. |
| 2 | **Rocket Math** | Add/subtract, times tables | Countdown to "blast off": 5 quick facts at the child's step; a miss gets a trick (make ten, doubles) and an easier one. Rocket face on blast-off. |
| 3 | **Skip-Count Relay** | Counting | Take turns: "25, 50..." "75!". She makes the odd silly mistake for the child to catch. |
| 4 | **Alexa's Shop** | Money | "A cookie costs 35 cents. Which coins could you pay with?" Grade 3: change from a dollar. |
| 5 | **Sound Swap** | Sounds | "Say cat. Now change the c to h." "What's left if you take the s off spin?" K: "What sound does sun start with?" |
| 6 | **Rhyme Time** | Sounds (K/G1) | Take turns finding rhymes; nonsense rhymes count and get a giggle. |
| 7 | **Word Builder** | Word parts | "Un plus happy?" "Someone who paints is a...?" "What's the opposite of tiny?" |
| 8 | **Clock Riddles** | Time | "It's 3:45. How many minutes until 4?" Grade 2: "Which is longer, a minute or an hour?" |

Earlier ideas stay in the plan as non-scored games (cards without a skill): 20 Questions with
food and things, Would You Rather, Word Chain, Story Builder, Riddles, I Spy with `look()`,
Guess My Face (feelings on the screen), Memory List, and the movement games once Buddy drives
(Red Light Green Light, Simon Says, Hot and Cold).

## 6. Risks to test before building

- **Isolated sounds through Orpheus.** Blending games need her to say "/sh/ /i/ /p/". TTS may
  read slashes or letter names. Test spellings like "shh... ih... puh" first; if they don't
  sound right, keep sound games to whole words and swaps (Sound Swap still works).
- **Spelling out loud through Whisper.** A child spelling "c-a-t" may transcribe badly. Test
  before any spelling game.
- **Numbers in transcripts.** "Fifteen" vs "15" vs "50": the card tells her to accept both
  and to ask again if a number is unclear rather than mark it wrong. Test teen/ty numbers.
- **Over-quizzing.** Watch the conversation history: if games start feeling like tests, lower
  the offer rate.

## 7. Build order

1. **Cards + menu, no scoring.** _(built 2026-11-18, not yet on the robot.)_ Card loader
   (`server/app/llm/games/`), keyword cue, injection, `Game:` in notes; Guessing Game, Number
   Detective, Rocket Math, Sound Swap, Rhyme Time at base level from the speaker's age. The
   guessing-game rules stay in the core prompt for now (short, proven in play).
   **Playtest lessons (2026-11-18, real model, scripted child):**
   - Left to judge, the model called wrong answers right (5 + 4 = 13 "You got it!"; "hat"
     for a ball-to-tall swap). So **Rocket Math and Sound Swap are run by code**
     (`games/drill.py`): the server picks each item per grade (sums; Sound Swap from word
     tables, with cue words instead of letter names for K/G1), checks the answer, keeps the
     score, and hands the model the verdict and the exact next item. Number Detective's
     higher/lower is checked by code too.
   - The model writes its words before its notes, so items it chose in the notes went
     unsaid. The server now gives the item before the words are written, and if a reply
     still skips it, speaks the item itself after the reply.
   - Game questions are exempt from the profiles' "don't tack on a question" speech rule.
   - Result: Rocket Math rounds honest end to end (verdicts, score, every question spoken);
     Sound Swap the same with an occasional repeated puzzle; Number Detective's
     higher/lower always right (praise for a poor guess can still be generous).
2. **Scoring and progress.** _(built 2026-11-18, with robot-buddy-86's first draft.)_
   Server `practice` records for drill items (above), robot `LearningStore`
   (`supervisor/personality/learning.py`): rounds of 5, mastery (≥80% in 3 games on 3 days)
   moves a skill up within the ceiling, two poor games step it down, confident when ≥80%
   code-checked; `learner` (base, ceiling, step per skill, confident skills) in the profile
   for the recognised child; the server pitches each round at that step (a round keeps its
   grade) and adds a PROGRESS line for confident skills. Saying goodbye mid-round is not a
   miss and gets no question. Still open: the checker check (§2.1 replay of 50 labelled
   attempts) needs opt-in conversation history and some real games.
3. **Dashboard.** _(built 2026-11-18.)_ Monitor tab → Learning: per child, the ceiling
   (default one grade above start), each skill's step, mastered grades, last games, trend,
   code-checked share, items missed most, and reset. API: `GET /api/learning`,
   `PUT /api/learning/{id}/ceiling`, `DELETE /api/learning/{id}`. No login yet (see
   `screen-ui-and-admin.md` §4): anyone on the home network can change the ceilings.
4. **The rest of the games**, and Grade 3 content behind the locks.

## 8. Open questions

None open; L1-L3 settled 2026-11-18.

## 9. Touch-screen games (proposal, 2026-11-18)

**Status:** idea, not settled. Builds on §1-§7; nothing here changes them.

### 9.1 Why

Answering by tap removes three of the §6 risks at once: spoken spelling through Whisper,
teen/ty numbers, and isolated sounds (she says a whole word, the child taps the picture that
starts with /sh/). A tap is an exact answer, so the mastery and confident rules in §2 can
trust it. Voice stays the main way to play; the screen is a prop, and every touch question can
also be answered out loud.

### 9.2 What the hardware already does

- Face MCU: 320×240 2.8" ILI9341, FT6336 capacitive touch, LVGL running, 8 MB PSRAM.
- Raw `TOUCH_EVENT` (x, y) and SCREEN gestures (tap, long-press, pet) already reach the
  supervisor (`docs/protocols.md`).
- Missing: the face protocol only carries small fixed commands (mood, gesture, border). There
  is no way to say "draw these tiles", and only Montserrat 14 is compiled in.
- Face link frames are capped at 768 bytes (`esp32-face/main/usb_rx.cpp`, `MAX_FRAME`). A
  scene of 4-12 short tiles fits easily; a full frame (~150 KB) does not, so no streaming.

### 9.3 Design: the face draws the scene, the supervisor runs the game

```
LLM server ── talk, personality, game card with state (§3) ──┐
                                                             v
supervisor ── game engine (Python, deterministic) ── SET_SCENE ──> face MCU (LVGL draws,
     ^                                                                hit-tests, highlights
     └──────────────────────── SCENE_TAP(tile_id) <──────────────────  the tap instantly)
```

- **Protocol (amendment needed in `docs/protocols.md` before building):**
  - `SET_SCENE` (new command, variable length): scene id, layout id, then tiles
    (id, text up to ~8 chars or icon id, colour, state). Layout 0 = no scene, full face.
  - `SET_TILE` (new command): change one tile's text/colour/state (mark right, wrong, taken)
    without resending the scene.
  - `SCENE_TAP` (new telemetry): scene id, tile id, event (tap, drag-end with value for the
    clock hands). Stale scene ids are dropped by the supervisor.
- **Layouts (firmware templates, about five cover §4):**
  1. 2×2 choice (answers, pictures)
  2. N×M grid (boards, memory cards, ten-frames, pizza slices); up to 4×3 at 320×240
  3. letter-tile row + answer slots (spelling, word parts)
  4. number pad 0-9 + entry
  5. clock face with draggable hands
- **Face stays present.** During a scene the face shrinks to a corner (about 80 px); on
  Buddy's turn it grows back with thinking eyes and gaze toward the tile it is about to pick
  (`face_gaze.py`). The conversation border keeps working.
- **Rules in code, not in the LLM** (the lesson of server-picked guessing secrets, 81321fd):
  the board, score, right/wrong check and Buddy's moves are plain Python on the supervisor, so
  games run with the server down. The LLM gets the state as the game card and adds her voice.
  A tap gets an instant local highlight and, if needed, a canned line; it never waits on the LLM.
- **Scoring:** a tap answer writes the same `practice` record as §3 (with `source: touch`) to the robot's progress
  store, marked `source: touch`. It counts for mastery: a tap is an exact answer, so in §2.1
  terms it is `checked` (decided by code). Touch-heavy skills will reach "confident" sooner.
- **Where each engine lives:** voice games keep cards and answer checking on the server (§3,
  §7 step 1), where the transcript is; touch games run on the supervisor. Both write the same
  record. For touch games the server's game card (`server/app/llm/games/<id>.toml`) also
  carries the current scene state, so she can talk about the board.
- **Drills reuse `drill.py`.** Rocket Math and Sound Swap are already run by code on the server
  (`server/app/llm/games/drill.py`: item, `Q#<n>`, verdict, score). For those, a tap is just
  another way to answer item n: the supervisor sends it to the server as the answer to `Q#<n>`
  and the existing verdict flow checks it. Only games with no server engine (board games
  against Buddy, §9.4) get a supervisor engine.
- **Firmware extras:** Montserrat 28 and 48, a small icon atlas in flash (coins, shapes,
  animals, simple pictures for phonics), tap targets at least 60 px.
- **Prototype in `tools/face_sim_v3` first**, then flash.

### 9.4 Games

**Practice (§4 skills, scored):**

| Skill | Touch version |
|---|---|
| Add/subtract, times tables | Rocket Math with 4 answer tiles; tap or say it |
| Phonics, sounds | She says "ship"; tap the picture or word that starts with /sh/ |
| Spelling, word parts | She says a word; build it from letter tiles; "un + happy" from parts |
| Place value | Tap tens rods and ones cubes to make 47 |
| Money | Tap coins onto a pile to make 35¢; Grade 3: change from a dollar |
| Time | "Show me quarter to four": drag the clock hands |
| Fractions, shapes | Shade 3/8 of a pizza; tap every triangle |

**Buddy plays against the kids (not scored, or scored where the game uses a skill):**
tic-tac-toe, small Connect Four (7×5), Nim / race to 21 (adding plus strategy), Memory with
math pairs (3+4 ↔ 7). A minimax engine picks her moves, tuned so she loses about 40% of the
time; she thinks out loud, brags a little and loses well.

**Playing together:**
- **Teach Buddy:** she confidently gets one wrong; the child taps the right answer and
  explains. Extends the Skip-Count Relay mistakes in §5.
- **Team vs the clock:** child and Buddy beat a timer together.
- **Two kids:** pass-and-play with her as host, or a quiz buzzer with half the screen each
  (who answered from the half tapped, confirmed by voice ID).

**Beyond the screen:** camera games with `look()` ("draw a triangle and show me", "hold up 7
fingers", "find something red"); movement answers once Track F lands (drive to the answer
card, one spin per right answer).

### 9.5 Limits

- Small screen: 4-6 targets for the five-year-old, up to 12 for Grade 2-3; two kids crowd it.
- Not a tablet: same session limits (§1.5), short games, the face always comes back.
- Firmware flash and RAM for fonts and icons need checking against the current build.

### 9.6 Build order (after §7 step 1)

1. Protocol amendment in `docs/protocols.md`; `SET_SCENE`/`SET_TILE`/`SCENE_TAP`; layout 1
   (2×2) in the face sim and firmware (face flash is manual, Ben only); supervisor scene
   manager; Rocket Math playable by tap or voice, using the §7 step 1 card for her talk.
2. Layout 3 (letter tiles): spelling and phonics pictures.
3. Layout 2 (grid): tic-tac-toe and Memory against Buddy.
4. Layouts 4-5: number pad, clock; coins.

### 9.7 Open questions

1. Does a game scene replace the face fully on the child's turn, or always keep the corner face?
2. Touch engine on the supervisor (offline, fast) as proposed, or on the server beside the cards?

Settled: touch answers count for mastery (`checked`, §2.1).
