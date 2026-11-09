# CAD optimisation loop: one tick

You are one tick of a long-running, self-paced loop on robot-buddy's chassis. You
are probably starting with no memory of earlier ticks. **The files in
`docs/cad/loop/` are the only memory you have.** Do one unit of work, record it,
and schedule the next tick.

Goal: by morning, Ben has **print-candidate** parts: lighter but just as strong,
no sharp edges or stress risers, DFM-clean, easy to assemble and repair, good
looking, and safe for a child. Ben signs off on every print ("eyes before
electrons"). You never print, flash, deploy, SSH or push.

## 0. Orient (every tick, keep it short)

1. Read `docs/cad/loop/STATE.md` (pass, current item, stop conditions) and the
   last ~40 lines of `JOURNAL.md`. Read `BACKLOG.md` only to pick an item.
2. `git status`: you must be on branch `cad-loop` with a clean tree. If the tree
   is dirty from a crashed tick, read the last journal entry. Finish that change
   if it is close to done, otherwise `git restore`/`git clean` only the paths that
   tick touched, and log it.
3. `just cad-probe`: is SolidWorks up? If not, set `sw: down` in STATE.md, pick
   only items tagged `[doc]` or `[py]`, and if none are left, schedule a
   1800 s wakeup and stop.

## 1. Pick

Take the highest-priority `[ ]` item in BACKLOG.md that is not `[blocked]`.
Rotate workstreams: don't take three items in a row from the same one unless
the others are empty. Mark it `[~]` in BACKLOG.md and write it into STATE.md as
the current item, with a one-line hypothesis and the metric you expect to move,
e.g. "pocket the plate between ribs: −15 g, S1a SF stays ≥ 3".

If an item needs a decision only Ben can make (a style choice, a scope change,
anything that moves a spec number someone else depends on), add it to
`QUESTIONS.md` with your recommendation and the options, mark it `[blocked]`,
and pick another. Never stall waiting for an answer.

## 2. Change (one change per tick)

- Geometry changes go in the generators (`tools/chassis.py` and, where needed,
  `tools/swbuild.cs`). Never hand-edit an SLDPRT. Every new feature also updates
  the part's `expect` volume, computed independently in Python.
- A new build command or tool (STL export, mesh checks, slicing) is a valid
  item. Build it, test it on one part, then use it.
- Large structural ideas (motor mounts integrated into the plate, a different
  body split) are built as a **variant** part beside the current one
  (`RB-PRT-001b_…`) and compared. Never replace the baseline in one tick.
- `docs/cad/*` design docs may be amended: add a dated `> Amendment (loop,
  YYYY-MM-DD):` note giving old value → new value and why. Never edit `specs/`.
- Follow `docs/print-dfm.md` and `07_materials_fasteners_fea.md` (walls are
  multiples of 0.6, `fil_in` 1.0 / 2.0 at load roots, inserts per 07 §4, PET-CF
  is notch-sensitive: no snap fits).

## 3. Verify (all must pass to keep the change)

| Gate | How | Pass |
|---|---|---|
| Build | `python3 tools/chassis.py rebuild` | last line `BUILD OK`, every `expect` met |
| Fit | `interfere` output | no interference that wasn't in the baseline |
| Strength | `python3 tools/fea.py <studies touched>` | SF ≥ 3 on Z UTS; deflection within 07 §3.4; no worse than baseline by >10 % unless the item is a deliberate trade |
| Mass | mass props from the build | not heavier, unless the item is a strength/safety fix (say so) |
| DFM | `print-dfm.md` checklist, plus mesh checks once they exist | no new overhangs >45° without a chamfer, no wall under 1.2, no sharp internal corner on a load path |
| Kid safety | `BACKLOG.md` §Kid-safety rules | no accessible edge without a radius, no new pinch gap |

If any gate fails: put the files back (`git restore` the generator files,
then rebuild so the SolidWorks mirror matches the baseline), log the failure
and what you learned, and mark the item `[x] rejected`. A rejected item with a
clear reason is still progress. If a rejection suggests a better idea, add it
to the backlog.

## 4. Record

1. Screenshots: copy the BMPs from the build's `shots\` into
   `docs/cad/loop/shots/<pass>-<item-id>/` as PNG (convert them; skip any over
   ~400 KB).
2. Append one row to `metrics.csv`.
3. Append a `JOURNAL.md` entry: item, hypothesis, what changed, the numbers
   before → after, verdict, next idea. Five to ten lines.
4. Mark the item `[x]` in BACKLOG.md and update STATE.md.
5. If accepted: `just cad-pull`, then commit on `cad-loop`:
   `CAD(loop): <item-id> <short>, <mass Δ g>, <SF min>` with the attribution
   trailer. Commit generators, docs, metrics, shots and the changed CAD files.
6. Rewrite `MORNING.md`: what's print-ready, what changed since the pass began
   (biggest wins first, with mass/SF numbers), the open questions, and the
   suggested print order. Keep it to one screen.

## 5. Schedule the next tick

- More work and SolidWorks up → ScheduleWakeup **60 s**.
- SolidWorks down, or only blocked items left → **1800 s**.
- Stop (`ScheduleWakeup stop: true`, final MORNING.md) when any **stop
  condition** in STATE.md is met: every workstream finished for the pass and a
  full review pass accepts no change, the date passes `stop_after`, or three
  ticks in a row fail for the same tooling reason. In that last case, say so
  plainly at the top of MORNING.md.

Each tick ends with: `tick <n> · <item-id> · <verdict> · next in <s>`.

## Lessons from leg 1 (2026-10-31; read before your first change)

- **Build a changed part alone first** (`chassis.run(<part>_lines(...))`) and read every line; only then the full rebuild. A filtered log hid the real failing feature for four builds (P4).
- **Fillets fail on slivers.** Before a `filletface`, check that no two features nearly touch (a 0.1 mm step, a boss 0.07 mm from a rim, a slot within 0.2 mm of a counterbore). The per-face / per-loop diagnostic and `SWB_DEBUG=1 WSLENV=SWB_DEBUG` say which.
- **Never give a feature the radius a study selects by shape** (S2 picks `cyl 0 1 0 2.0` as motor inserts; an r 2.0 fillet became a third insert, tick 36).
- **Don't kill swsim mid-run unless you must**: it left a part open (the next save failed) and SolidWorks grew to ~41 GB and hung. If you do, close the documents before rebuilding; if SolidWorks stops answering, mark sw DOWN and leave the restart to Ben.
- **Background jobs: use `run_in_background`**, never a bare `&` (no completion notice).
- **String edits to generated Python**: ruff wraps long lines; a `str.replace` that misses must fail loudly (`assert old in s`), and check the expected volume changed.
- **meshcheck's min wall finds real defects** (0.25 / 0.23 / 0.95 mm walls this leg); locate them with inward ray casts before guessing.
- **Engine `box` misbuilt over existing bodies** (CreateCornerRectangle, fixed tick 59 to four lines): if a part's volume drifts from its prediction for no geometric reason, rebuild the suspect step as `prof` lines and compare.
