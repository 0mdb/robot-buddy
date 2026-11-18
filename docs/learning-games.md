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
- **Scoring:** during a learning game the reply gets one short trailing field after `text`,
  e.g. `"practice": {"skill": "add_sub_facts", "correct": true}`, or empty. The robot stores
  it per member (`data/learning_progress.json`, beside the memory file; local only, parent
  can view and reset). It costs a few tokens, and only during learning games. Spec
  amendment needed (response schema) before building.

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

1. **Cards + menu, no scoring.** Card loader, keyword cue, injection, `Game:` in notes; games
   1, 2, 5, 6 at base level from the roster age. Trim the GAMES AND STORIES section of the
   system prompt into the menu line (guessing-game rules move into its own card).
2. **Scoring and progress.** `practice` field (spec amendment), robot progress store per
   member, code checking for math (and rhyme/word tables), `learner` in the profile, steps
   per skill, mastery and confident rules, the checker check (§2.1).
3. **Dashboard.** Per-child ceiling setting; progress per skill; reset.
4. **The rest of the games**, and Grade 3 content behind the locks.

## 8. Open questions

None open; L1-L3 settled 2026-11-18.
