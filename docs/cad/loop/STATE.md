# CAD loop state

pass: 1
tick: 37
sw: DOWN (SLDWORKS exited after hanging at ~41 GB, 06:25; needs Ben to start it. Rebuild the baseline first when it's back)
current: D1 pending (patch patches/D1-endstop-fillet-r2.2-pending.patch; reapply + rebuild + S2 pair when SW is back)
hypothesis: —
baseline_commit: d8179d2 (cad)
stop_after: 2026-10-31 12:00   (Ben, 2026-10-31 ~06:20: extended from 07:00)

## Stop conditions
- every workstream finished for this pass, and a full review pass after it accepts no change
- the clock passes `stop_after`
- three ticks in a row fail for the same tooling reason

## Pass plan
Pass 1: P → T → M → S → W → D → A → R → E (first cut of each; P = every missing part, Ben 2026-10-30).
Pass 2+: re-review every part against all workstreams with the new tools; only measured improvements are kept.
