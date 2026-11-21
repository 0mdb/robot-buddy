"""Voice ID bake-off on saved turns (docs/voice-id.md §Tuning).

Uses clips the camera labelled (one face, recognised at --face-score or better) as ground
truth, embeds them with the model, and reports what the thresholds should be:

- same-person vs different-person scores, by speech length (does "seven" carry a voice?);
- the member x member score table (do the brothers overlap?);
- leave-one-out identification: each clip matched against everyone's other clips, as the
  server would, at a sweep of thresholds: right / wrong / unsure;
- the session view: a conversation's clips averaged, as for short answers.

    cd server && .venv/bin/python scripts/voice_id_eval.py [--data ../data/voice]
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.voice.capture import TurnAudioStore, read_wav  # noqa: E402
from app.voice.config import VoiceConfig  # noqa: E402
from app.voice.embed import Embedder  # noqa: E402
from app.voice.prints import member_score  # noqa: E402

BUCKETS = [(0.0, 1.0), (1.0, 2.0), (2.0, 4.0), (4.0, 99.0)]


def bucket(s: float) -> str:
    for lo, hi in BUCKETS:
        if lo <= s < hi:
            return f"{lo:g}-{hi:g}s" if hi < 99 else f">{lo:g}s"
    return "?"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=VoiceConfig().data_dir)
    ap.add_argument("--face-score", type=float, default=0.5)
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()

    store = TurnAudioStore(args.data)
    clips = store.clips()
    labelled = []
    for wav, m in clips:
        f = m.get("face") or {}
        if (
            f.get("member_id")
            and int(f.get("faces", 1)) == 1
            and float(f.get("score") or 0) >= args.face_score
        ):
            labelled.append((wav, m, str(f["member_id"])))
    print(f"{len(clips)} clips, {len(labelled)} labelled by a clear face")
    if len(labelled) < 4:
        print("Not enough labelled clips yet: play with Buddy a while longer.")
        return

    emb = Embedder(args.device)
    rows = []
    for wav, m, mid in labelled:
        e, speech_s = emb.embed(read_wav(wav))
        if e is not None:
            rows.append((mid, speech_s, e, m))
    members = sorted({r[0] for r in rows})
    per = defaultdict(int)
    for r in rows:
        per[r[0]] += 1
    print("clips per member:", dict(per))

    # Pairwise, by the shorter clip's length.
    same, diff = defaultdict(list), defaultdict(list)
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a, b = rows[i], rows[j]
            s = float(a[2] @ b[2])
            key = bucket(min(a[1], b[1]))
            (same if a[0] == b[0] else diff)[key].append(s)
    print("\npairwise cosine, by the shorter clip's speech length")
    print(
        f"{'length':>8} {'same mean':>10} {'same p10':>9} {'diff mean':>10} {'diff p90':>9}"
    )
    for lo, hi in BUCKETS:
        k = bucket((lo + hi) / 2 if hi < 99 else lo + 1)
        if same[k] or diff[k]:
            sm = np.array(same[k]) if same[k] else np.array([np.nan])
            dm = np.array(diff[k]) if diff[k] else np.array([np.nan])
            print(
                f"{k:>8} {np.nanmean(sm):10.2f} {np.nanpercentile(sm, 10):9.2f}"
                f" {np.nanmean(dm):10.2f} {np.nanpercentile(dm, 90):9.2f}"
            )

    # Member x member: mean of each clip's score against the other member's clips.
    print("\nmember x member (mean top-3 score, clip vs member's other clips)")
    print(" " * 14 + "".join(f"{m[:10]:>11}" for m in members))
    for a in members:
        line = f"{a[:12]:>12}  "
        for b in members:
            vals = []
            for i, r in enumerate(rows):
                if r[0] != a:
                    continue
                others = np.array(
                    [x[2] for j, x in enumerate(rows) if x[0] == b and j != i]
                )
                if len(others):
                    vals.append(member_score(others, r[2]))
            line += f"{np.mean(vals):11.2f}" if vals else f"{'-':>11}"
        print(line)

    # Leave-one-out identification at a sweep of thresholds.
    print("\nleave-one-out: right / wrong / unsure (margin 0.08)")
    for thr in (0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6):
        res = defaultdict(lambda: [0, 0, 0])
        for i, r in enumerate(rows):
            scores = {}
            for b in members:
                others = np.array(
                    [x[2] for j, x in enumerate(rows) if x[0] == b and j != i]
                )
                if len(others):
                    scores[b] = member_score(others, r[2])
            ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
            best, bs = ranked[0]
            rs = ranked[1][1] if len(ranked) > 1 else 0.0
            k = bucket(r[1])
            if bs >= thr and bs - rs >= 0.08:
                res[k][0 if best == r[0] else 1] += 1
            else:
                res[k][2] += 1
        parts = [f"{k}: {v[0]}/{v[1]}/{v[2]}" for k, v in sorted(res.items())]
        print(f"  thr {thr:.2f}  " + "   ".join(parts))
    print(
        "\nPick the lowest threshold with ~0 wrong in the lengths that matter; "
        "set VOICE_MATCH_SCORE / VOICE_MATCH_MARGIN in .env."
    )


if __name__ == "__main__":
    main()
