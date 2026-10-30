# CAD optimisation loop

An unattended Claude Code loop that improves the chassis overnight. It makes one
measured change per tick and keeps it only if build, fit, FEA, mass, DFM and
kid-safety checks all pass. Every kept change is a commit on `cad-loop`. You
wake up to `MORNING.md`, renders, and print candidates for you to review. It
never prints.

| File | Role |
|---|---|
| `PROMPT.md` | What each tick does (the loop runs this) |
| `STATE.md` | Pass, current item, stop conditions: the loop's memory |
| `BACKLOG.md` | Workstreams + items, loop-maintained |
| `JOURNAL.md` / `metrics.csv` | One entry/row per tick |
| `QUESTIONS.md` | Calls only Ben can make. The loop skips those items and carries on |
| `MORNING.md` | One-screen summary, rewritten every tick |
| `shots/` | Per-item screenshots |

## How it runs

`/loop` with no interval = **dynamic mode**: each tick ends with a
`ScheduleWakeup` (60 s when there's work, 1800 s when SolidWorks is down or only
blocked items are left). It runs **inside this terminal session**, so:

- The Claude Code session, WSL, Windows and SolidWorks must stay up. Turn off
  Windows sleep (`powercfg /change standby-timeout-ac 0`). Leave the screen on
  or unlocked, because `SaveBMP` only writes when a SolidWorks window is visible.
- The context fills up and gets summarised over a long run. That's fine because
  all state lives in these files, and each tick re-reads them.
- A cloud `/schedule` routine can't do this: it needs your local SolidWorks.

## Preflight (once, when the current CAD work is roughed out)

1. Commit the current CAD work on `cad`. `tools/fea.py` and `tools/swsim.cs`
   are still untracked. Run `python3 tools/chassis.py rebuild` and
   `python3 tools/fea.py` once by hand: both must pass, because the loop's
   baseline is whatever passes now.
2. `git switch -c cad-loop`. Put the baseline commit and `stop_after` in STATE.md.
3. Answer `QUESTIONS.md` Q1–Q3 if you can. Unanswered ones get the stated default.
4. Start SolidWorks by hand and close every document. Don't use SolidWorks
   while the loop runs (one COM client).
5. Permissions (below), then start in a fresh session:

```
/loop Follow docs/cad/loop/PROMPT.md exactly. Repo root: /home/ben/robot-buddy.
```

## Guardrails

Auto mode will keep most tool calls from prompting. Add hard denies so nothing
outward-facing happens overnight, in `.claude/settings.local.json`:

```json
{
  "permissions": {
    "deny": [
      "Bash(git push:*)", "Bash(just flash*)", "Bash(just deploy*)",
      "Bash(ssh:*)", "Bash(scp:*)", "Bash(rsync * pi@*)",
      "Bash(git reset --hard:*)", "Bash(git rebase:*)", "Bash(git switch main*)",
      "Edit(specs/**)", "Write(specs/**)"
    ]
  }
}
```

## Steering while it runs

- Edit `BACKLOG.md` or `QUESTIONS.md`. The next tick reads them.
- Stop: type anything in the session and say "stop the loop", or set
  `stop_after` to now.
- Discard everything: `git switch cad && git branch -D cad-loop` (local only).

## Morning routine

1. Read `MORNING.md`, then `git log --oneline cad..cad-loop`.
2. Look at `shots/` and open the changed parts in SolidWorks (eyes before electrons).
3. Print the **fit coupons** first (D6), in PETG, then the real parts.
4. Cherry-pick or merge what you like into `cad`. Answer new questions, then restart the loop.
