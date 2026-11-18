# Screen UI, grown-up settings and the Jarvis boundary

**Status:** design, 2026-11-18. Nothing built yet. Builds on the touch-scene protocol proposed
in `docs/learning-games.md` §9 (`SET_SCENE` / `SET_TILE` / `SCENE_TAP`).

The face screen is getting touch scenes for learning games. The same machinery can carry a
small kid menu, a grown-up settings screen, and an admin ("Daddy") mode that talks to Home
Assistant and personal data. The admin side is R&D for a future house assistant ("Jarvis"),
so it is built as a **separate service from day one**, with Buddy's screen and speaker only as
one of its clients. Jarvis is the "Owner mode" plan in `docs/TODO.md` (2026-11-15: same speech
stack, `owner` profile, separate memory, local tools over MCP); this doc adds the screen side,
the unlock rules and the service boundary.

## 0. Settled decisions (Ben, 2026-11-18)

| # | Decision |
|---|---|
| S1 | **Jarvis is a separate service**, not a mode inside Buddy's server. Its own persona, memory, logs, tools and credentials. |
| S2 | **Buddy gets a settings screen**: a kid menu (no PIN) and grown-up settings (PIN). |

## 1. Goals and non-goals

**Goals**
- Kids can change the harmless things themselves (volume, quiet, sleep).
- Ben can do the everyday grown-up things at the robot without opening the dashboard.
- Ben can use Buddy's screen and voice as a front end to Jarvis: Home Assistant control,
  home status, stocks, later more.
- Nothing from the grown-up or Jarvis side can leak into a child's conversation.

**Non-goals**
- Buddy is not a tablet. The face is the default screen; menus are a swipe away.
- No guardrail toggles on the screen. HC-1..HC-10 and RS-1..RS-10 stay dashboard-only
  (personality spec stage 1, "Guardrail rules are mandatory but toggleable").
- No door locks, garage, alarm or anything irreversible from the robot (§6.4).

## 2. Three trust levels

| Level | Who | Unlock | What |
|---|---|---|---|
| **Kid menu** | anyone | swipe down from the top edge | volume, brightness, "quiet please", "go to sleep", battery, "who am I?", feelings check-in |
| **Grown-up settings** | registered adults | PIN + face ID (§3) | quiet mode, bedtime, session limits, grade ceilings, today's summary, camera/mic privacy, status, restart |
| **Jarvis (Daddy mode)** | Ben only, at first | PIN + face ID, per-person PIN | Home Assistant beyond the kid whitelist, home status, stocks; later calendar etc. Served by the Jarvis service (§6) |

Each level is a superset of the one above it for the same person. Leaving grown-up or Jarvis
mode always returns to the face.

## 3. Unlocking: PIN plus face ID

A 4-digit PIN tapped on a 2.8" screen next to watching kids is weak: it can be read over a
shoulder, the smudges show which digits were used, and kids have endless patience for guessing.
So the PIN is never enough on its own.

1. **Two factors.** Unlock needs a correct PIN **and** that adult recognised at the moment of
   entry: face ID now, high-confidence voice ID (SIM-INTERACTION stage 5, as the Owner mode plan
   requires for voice-only use) once it exists. Neither available (camera off, server down) →
   grown-up mode is dashboard-only.
2. **Per-person PINs**, 4-6 digits, set and changed only from the dashboard. Stored on the Pi
   as a salted slow hash (scrypt or argon2), never in the repo, never sent to the server.
3. **Shuffled keypad.** The supervisor sends the digit layout in `SET_SCENE` and reshuffles it
   every time the keypad opens. The face only reports tile ids; the Pi maps them to digits.
   Watching the pattern or the smudges does not reveal the PIN.
4. **No echo.** Dots only, no digits shown, no tap sounds that differ per key, nothing spoken.
5. **Lockout.** 5 wrong tries → keypad locked for 10 minutes and a parent alert (existing
   ParentAlertsPanel). Doubling lock time after each further lockout.
6. **Locks itself.** Back to the face after 60 s with no touch, when the unlocked adult has not
   been seen for 10 s, or immediately when a child's face is recognised in view while a Jarvis
   screen shows personal data (§6.3).
7. **Audit.** Every unlock, failed try, and setting changed is logged on the Pi with who and
   when, visible in the dashboard.

## 4. Prerequisite: dashboard login

Today `supervisor/api/http_server.py` has no auth. Anyone on the LAN, including a kid on a
tablet, can open the dashboard and change the household, quiet mode, personality and guardrail
settings. A PIN on the robot's screen protects nothing while that is open.

- One admin identity per adult, shared by the screen, the dashboard and Jarvis clients.
- Dashboard: login with the adult's password (not the screen PIN), session cookie, HTTPS on the
  LAN (self-signed or a local CA). Websocket and MCP endpoints check the same session.
- Read-only kiosk view without login is fine (face mirror, battery), nothing that changes state.
- Build this **before** the grown-up screen.

## 5. Screens

All use the scene protocol from `learning-games.md` §9; the extra layouts are listed in §7.

### 5.1 Kid menu (swipe down from the top)

- Volume and brightness (sliders or 3-step tiles).
- "Quiet please" (existing quiet mode, kid-settable on, grown-up-settable off if configured)
  and "go to sleep".
- Battery level as a picture.
- "Who am I?": tap your picture when face ID isn't sure. Feeds the speaker identity for this
  conversation only; it never enrols or retrains anything.
- Feelings check-in: tap a face. Stored as a semantic tag only (HC-3), shown to parents (RS-4).
- A small lock tile in a corner opens the grown-up keypad.

### 5.2 Grown-up settings

- Quiet mode, bedtime / sleep hours, session and daily limits (RS-1, RS-2 values within the
  ranges the dashboard allows).
- Per-child grade ceilings and progress at a glance (`learning-games.md` §2).
- Today's summary: time played per child, games played, parent alerts.
- Camera and mic privacy toggle (shown on the face as a persistent small icon while off).
- Server, Wi-Fi and battery status; restart supervisor; shut down.
- Face calibration screen (existing).

### 5.3 Kid screens worth adding (not settings, listed here for the screen budget)

- **Picture cards** while she talks: the animal in a guessing game, story pictures, weather.
- **Visual timer**: "5 more minutes", bedtime countdown, draining visibly.
- **Morning routine checklist**: teeth, clothes, breakfast; tap to tick, she cheers.
- **Read-along**: words highlight as she reads a story (literacy practice, fits the curriculum).
- **Drawing pad**: the child draws, she guesses using the vision model on the drawing.

## 6. Jarvis: a separate service

### 6.1 Shape

```
            ┌──────────────── 3090Ti box ────────────────┐
Pi          │  buddy-server (8100)      jarvis (own port) │
supervisor ─┼─> kid conversations       admin conversations│
   │        │   game cards, TTS         HA MCP, finance,   │
   │        │   Buddy memory            own memory & logs  │
   │        └────────────────────────────────▲─────────────┘
   └── in Jarvis mode only: transcript/taps ─┘  <- text + scene back
```

- Runs as its own systemd user service (e.g. `jarvis-server`) on the 3090Ti, with its own
  env file, its own data directory and its own logs. Starts life in this repo under
  `jarvis/` and moves to its own repo once it has a second client (wall tablet, phone).
- Local LLM only (Ollama on the same box). No household names or personal data to external
  APIs, the same boundary as Buddy. Tool use likely needs a larger local model than Buddy's
  gemma-4-E4B, loaded on demand (VRAM is shared with Orpheus); see the Owner mode plan.
- Tools via MCP: the Home Assistant MCP server for house control and status; a quotes source
  for stocks; later calendar etc. Its tool list is its own; Buddy's HA whitelist
  (`docs/home-assistant-integration.md`) is unchanged.
- Auth: the supervisor calls Jarvis with a per-device token plus the unlocked adult's
  identity. Jarvis refuses calls without both.

### 6.2 What crosses the boundary

| From Buddy to Jarvis | From Jarvis to Buddy |
|---|---|
| the adult's transcript (in Jarvis mode only), screen taps, who is unlocked | reply text, a scene to draw, a `speak` flag per reply |

- Nothing from Jarvis enters Buddy's LLM context, conversation history, per-person memory or
  conversation capture. In Jarvis mode the supervisor routes turns to Jarvis and does not
  record them on Buddy's side.
- Jarvis keeps its own history, readable only by its owner.
- Buddy's time limits (RS-1, RS-2) don't count Jarvis time.

### 6.3 Showing it on Buddy

- Jarvis mode looks different: a distinct border colour and a small "J" badge, and a different
  TTS voice, so kids can tell Buddy isn't the one talking.
- Replies flagged `speak: false` (anything personal, e.g. balances later) appear on the screen
  only, never through the speaker.
- Personal screens blank and lock the moment a child is recognised in view (§3.6).

### 6.4 What Jarvis may do from the robot

| Tier | Examples | From Buddy's screen/voice |
|---|---|---|
| Read | lights on?, garage open?, temperature, stock quotes | yes |
| Reversible changes | lights, thermostat, media, start the dishwasher | yes, with a confirm tap for anything outside lights |
| Security / irreversible | door locks, garage door, alarm, purchases | **no**; phone or wall tablet only |

### 6.5 Finances

- **Data:** local only, as in the Owner mode plan: statements exported from the bank (OFX/CSV)
  and imported into a local database Jarvis queries. No bank credentials anywhere in the house
  system, no cloud aggregators. Stock quotes are public and fine.
- **On Buddy:** finance replies are always `speak: false` (screen only, §6.3) and blank the
  moment a child is recognised in view. Buddy speaks out loud in a family room and its
  conversations are near the kids, so spoken finance answers belong on other Jarvis clients
  (phone, office mic/speaker), not the robot.

## 7. Protocol and firmware needs

Uses `SET_SCENE` / `SET_TILE` / `SCENE_TAP` from `learning-games.md` §9 (protocols.md
amendment needed before build). Extra layouts:

| Layout | Used by |
|---|---|
| keypad 3×4, digits supplied per open (shuffled) + dot row | PIN entry |
| menu list (up to 5 rows, icon + label, scroll) | kid menu, grown-up settings |
| toggle / slider rows | volume, brightness, quiet, privacy |
| text card (title + up to ~6 lines) | status, summary, Jarvis replies |
| picture card (icon atlas or small image) | picture cards, timer, routine checklist |

- Corner face and persistent icons (privacy off, Jarvis badge) are face-side overlays.
- Opening the menu needs a new gesture. Long-press already toggles PTT, tap is boop/cancel
  and a long drag is a pet (protocols.md, SCREEN button 2), so none of those can be reused.
  Proposed: **swipe down from the top edge** (touch starts within ~20 px of the top, moves down
  ≥ 80 px) as a new `BUTTON_EVENT` type, e.g. `6` MENU. During a conversation it is ignored.
- **Swipe vs pet.** A stroke of 160 px or more is already a PET with a local pet reaction
  (`touch_gesture.cpp`, visual-language §1.6), and kids stroke the face a lot, so the classifier
  in `touch_gesture.cpp` must tell them apart: **edge start** (first touch at y < ~20 px) **plus a
  mostly vertical** (|dy| ≥ 2·|dx|) **and fast** (≥ 80 px within ~250 ms) motion = MENU; anything
  else stays a pet or a plain drag. A MENU swipe never also fires PET. Test with kids stroking
  from the top of the screen before shipping; if menus open by accident, require a two-step open
  (swipe shows a small tab, tap the tab).
- Small images (picture cards, drawings back from the vision model) may need a chunked image
  command; 768-byte frames limit one frame to tiles and short text.

## 8. Spec impact

- **Personality spec S2**: no change to HC-x. Note in RS-4 that parental visibility includes
  the unlock audit log; add the "who am I?" tap as a weak, per-conversation identity hint that
  never enrols (HC-2).
- **protocols.md**: the scene commands (shared with learning games) and the MENU gesture.
- **Face comm spec** §9.5 (touch gestures): add the swipe-down MENU gesture and the swipe-vs-pet
  rule (§7).
- **home-assistant-integration.md**: unchanged for kids; add a pointer that broader HA control
  lives in Jarvis.

## 9. Build order

1. **Dashboard login** (§4). Standalone, worth doing now.
2. **Scene protocol + face layouts** (shared with learning games §9.6 step 1).
3. **Kid menu** (§5.1).
4. **PIN + face ID unlock and grown-up settings** (§3, §5.2), with lockout, audit, auto-lock.
5. **Jarvis skeleton**: service, auth token, HA MCP read-only tier, text card replies,
   separate voice. Then the reversible tier with confirm.
6. **Kid screens** from §5.3 as the games work allows.

## 10. Open questions

1. Who besides Ben gets grown-up settings, and does anyone else get Jarvis?
2. Should "quiet please" from the kid menu be undoable by kids, or only by a grown-up?
3. Wall tablet or phone as Jarvis's first non-Buddy client?
