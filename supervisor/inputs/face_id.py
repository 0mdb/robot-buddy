"""Who is this face: OpenCV SFace embeddings matched against the household's enrolled faces.

- **Model:** ``face_recognition_sface_2021dec.onnx`` (opencv_zoo, Apache-2.0, 37 MB), fetched
  into ``supervisor/models`` by ``deploy/fetch_models.sh`` (not in git). It aligns the face
  with YuNet's five landmarks and returns a 128-d embedding; ~32 ms per face on the Pi 5.
- **Gallery:** embeddings keyed by roster member id (``personality/roster.py``), never by
  name, in ``household_faces/gallery.json`` beside the roster, so "forget everyone" deletes
  them with it. Robot-local and git-ignored, like the roster.
- **Match:** the best cosine similarity over a member's samples; at or above the threshold
  (OpenCV's SFace figure is 0.363) the face is that member. One frame is not enough to
  name someone: the tracker averages each member's score over a face's checks and names
  the face only when the best member leads the next by ``MATCH_MARGIN`` (a single
  off-angle frame named Ben's face as a child at 0.384, 2026-11-18).
- **Naming bar:** a wrong name is worse than a generic hello, and a name also sets a
  person's NEARBY limits. A face gets a *new* name only when the averaged score reaches
  ``NAME_SCORE`` (above SFace's 0.363) over at least ``NAME_CHECKS`` checks; once named it
  keeps the name while that member stays above ``MATCH_THRESHOLD``. (2026-11-18: Ben, at
  1 m and off to one side, was greeted as his son at 0.438 / 0.432: his own live scores
  were only 0.38-0.45, so the 0.08 lead alone did not stop it.) Both are live params
  (``vision.face_name_score``, ``vision.face_name_checks``).
- **Runner-up:** every face reports the second-best member and score
  (``id_runner`` / ``id_runner_score``), so a mix-up can be read from the logs.
- **Samples vary:** enrollment skips a frame nearly identical to one already taken, and a
  full gallery drops its most redundant sample, not its oldest: 20 near-copies from one
  sitting (0.90 alike) matched live faces at only 0.37-0.6.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_MODEL = (
    Path(__file__).resolve().parent.parent
    / "models"
    / "face_recognition_sface_2021dec.onnx"
)
GALLERY_DIR = "household_faces"
MATCH_THRESHOLD = 0.363
MATCH_MARGIN = 0.08  # best member's averaged score over the runner-up's
NAME_SCORE = 0.50  # averaged score needed to give a face a new name
NAME_CHECKS = 2  # checks of this face before it can get a new name
MAX_SAMPLES = 20
SAME_SAMPLE_SIM = (
    0.95  # enrollment: a frame this alike to one already taken adds nothing
)
_GALLERY_VERSION = 1


def gallery_path(roster_path: str | Path) -> Path:
    """The face gallery lives in the roster's sidecar directory."""
    return Path(roster_path).parent / GALLERY_DIR / "gallery.json"


class FaceGallery:
    """Member id -> list of unit-length embeddings, persisted as JSON. Re-read when the
    file changes on disk (a parent's "forget everyone" removes it)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._members: dict[str, list[Any]] = {}
        # (inode, mtime_ns, size): every save is a new file (os.replace), so the inode
        # changes even when two writes land within one mtime tick.
        self._stamp: tuple[int, int, int] | None = None

    def refresh(self) -> None:
        try:
            st = self.path.stat()
        except FileNotFoundError:
            self._members, self._stamp = {}, None
            return
        stamp = (st.st_ino, st.st_mtime_ns, st.st_size)
        if stamp == self._stamp:
            return
        self._stamp = stamp
        try:
            import numpy as np

            raw = json.loads(self.path.read_text())
            members = raw.get("members", {}) if isinstance(raw, dict) else {}
            self._members = {
                str(mid): [np.asarray(e, dtype=np.float32) for e in embs]
                for mid, embs in members.items()
                if isinstance(embs, list)
            }
        except Exception as e:  # noqa: BLE001 -- a bad file means no matches, not a crash
            log.warning("face gallery unreadable (%s); treating as empty", e)
            self._members = {}

    def counts(self) -> dict[str, int]:
        return {mid: len(embs) for mid, embs in self._members.items()}

    def add(self, member_id: str, embeddings: list[Any]) -> int:
        """Append samples for a member and save. Past MAX_SAMPLES the most redundant
        sample goes (the one most like another), so captures in new places and light
        replace near-copies instead of the oldest."""
        import numpy as np

        embs = self._members.get(member_id, []) + list(embeddings)
        while len(embs) > MAX_SAMPLES:
            m = np.stack(embs) @ np.stack(embs).T
            np.fill_diagonal(m, -1.0)
            embs.pop(int(np.argmax(m.max(axis=1))))
        self._members[member_id] = embs
        self._save()
        return len(self._members[member_id])

    def forget(self, member_id: str) -> bool:
        if member_id not in self._members:
            return False
        del self._members[member_id]
        self._save()
        return True

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": _GALLERY_VERSION,
            "members": {
                mid: [[round(float(v), 6) for v in e] for e in embs]
                for mid, embs in self._members.items()
            },
        }
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data))
        os.replace(tmp, self.path)
        st = self.path.stat()
        self._stamp = (st.st_ino, st.st_mtime_ns, st.st_size)

    def scores(self, embedding: Any) -> dict[str, float]:
        """Each member's similarity: the best over their samples."""
        import numpy as np

        return {
            mid: float(np.max(np.stack(embs) @ embedding))
            for mid, embs in self._members.items()
            if embs
        }

    def match(self, embedding: Any) -> tuple[str | None, float]:
        """(member id, similarity) of the best match, or (None, best) below threshold."""
        sc = self.scores(embedding)
        if not sc:
            return None, -1.0
        best_id = max(sc, key=sc.__getitem__)
        if sc[best_id] >= MATCH_THRESHOLD:
            return best_id, sc[best_id]
        return None, sc[best_id]


class FaceEmbedder:
    """Lazy SFace wrapper; ``embed`` returns None when the model is missing."""

    def __init__(self, model_path: str | Path = DEFAULT_MODEL) -> None:
        self._model_path = str(model_path)
        self._rec: Any | None = None
        self._failed = False
        self.error = ""

    @property
    def available(self) -> bool:
        return not self._failed and Path(self._model_path).is_file()

    def embed(self, frame_bgr: Any, row: Any) -> Any | None:
        """Unit-length 128-d embedding of the face described by a YuNet row (in
        ``frame_bgr``'s pixel coordinates)."""
        if not self.available:
            return None
        try:
            import cv2
            import numpy as np

            if self._rec is None:
                self._rec = cv2.FaceRecognizerSF.create(self._model_path, "")
                log.info("face recognizer loaded (%s)", Path(self._model_path).name)
            crop = self._rec.alignCrop(frame_bgr, row)
            feat = np.asarray(self._rec.feature(crop), dtype=np.float32).reshape(-1)
            n = float(np.linalg.norm(feat))
            return feat / n if n > 0 else None
        except Exception as e:  # noqa: BLE001 -- vision keeps running without identities
            self._failed = True
            self.error = f"face recognizer: {e}"
            log.warning("face recognition disabled: %s", e)
            return None


def _scaled_row(row: Any, scale: float) -> Any:
    """A YuNet row from the detection frame mapped onto a frame ``scale`` times larger
    (box and landmarks; the score stays)."""
    import numpy as np

    r = np.asarray(row, dtype=np.float32).copy()
    r[:14] *= scale
    return r


class FaceIdTracker:
    """Adds ``member_id`` / ``id_score`` to detected faces, a few faces a second.

    Recognition costs ~32 ms a face, so it runs at ``id_hz`` on one face per pass:
    an unidentified face first, otherwise the one checked longest ago. Between passes a
    face keeps the identity of the nearest face from the previous detection.

    Enrollment (``start_enroll``) collects ``samples`` embeddings of a member while exactly
    one clear face is in view, then adds them to the gallery; ``take_result`` reports it.
    """

    ENROLL_MIN_SCORE = 0.75
    ENROLL_MIN_WIDTH = 0.06  # of the frame width: closer than ~2 m
    ENROLL_INTERVAL_S = 0.25
    ENROLL_TIMEOUT_S = 20.0
    ENROLL_MIN_KEEP = (
        3  # at the timeout, keep a capture with at least this many samples
    )
    CARRY_DIST = 0.15

    def __init__(
        self,
        embedder: FaceEmbedder,
        gallery: FaceGallery,
        id_hz: float = 3.0,
        name_score: float = NAME_SCORE,
        name_checks: int = NAME_CHECKS,
    ) -> None:
        self.embedder = embedder
        self.gallery = gallery
        self.id_hz = id_hz
        self.name_score = name_score
        self.name_checks = name_checks
        self.ms = 0.0
        self._prev: list[dict] = []
        self._last_id_t = 0.0
        self._last_refresh_t = -1e9
        self._enroll: dict | None = None
        self._result: dict | None = None

    # -- enrollment ---------------------------------------------------------

    def start_enroll(self, member_id: str, samples: int, now: float) -> None:
        self._enroll = {
            "member_id": member_id,
            "want": max(1, min(MAX_SAMPLES, int(samples))),
            "embs": [],
            "deadline": now + self.ENROLL_TIMEOUT_S,
            "last_t": 0.0,
        }

    @property
    def enrolling(self) -> str | None:
        return self._enroll["member_id"] if self._enroll else None

    def take_result(self) -> dict | None:
        r, self._result = self._result, None
        return r

    def forget(self, member_id: str) -> bool:
        self.gallery.refresh()
        return self.gallery.forget(member_id)

    def _enroll_step(self, pairs: list, frame: Any, scale: float, now: float) -> None:
        e = self._enroll
        assert e is not None
        if now > e["deadline"] and len(e["embs"]) >= self.ENROLL_MIN_KEEP:
            self._finish_enroll()  # enough to keep; the rest were too alike
            return
        if now > e["deadline"]:
            self._result = {
                "member_id": e["member_id"],
                "ok": False,
                "samples": len(e["embs"]),
                "error": "no single clear face in view (stand alone, facing Buddy, "
                "within about 2 m)",
            }
            self._enroll = None
            return
        if len(pairs) != 1 or now - e["last_t"] < self.ENROLL_INTERVAL_S:
            return
        face, row = pairs[0]
        if face["score"] < self.ENROLL_MIN_SCORE or face["w"] < self.ENROLL_MIN_WIDTH:
            return
        emb = self.embedder.embed(frame, _scaled_row(row, scale))
        if emb is None:
            self._result = {
                "member_id": e["member_id"],
                "ok": False,
                "samples": 0,
                "error": self.embedder.error or "face recognizer unavailable",
            }
            self._enroll = None
            return
        e["last_t"] = now
        if any(float(x @ emb) >= SAME_SAMPLE_SIM for x in e["embs"]):
            return  # the same view again: wait for the person to move a little
        e["embs"].append(emb)
        if len(e["embs"]) >= e["want"]:
            self._finish_enroll()

    def _finish_enroll(self) -> None:
        e = self._enroll
        assert e is not None
        self.gallery.refresh()
        total = self.gallery.add(e["member_id"], e["embs"])
        self._result = {
            "member_id": e["member_id"],
            "ok": True,
            "samples": total,
            "error": "",
        }
        self._enroll = None

    # -- recognition --------------------------------------------------------

    EV_ALPHA = 0.5  # weight of the newest check in a face's running score per member

    def _decide(self, face: dict, scores: dict[str, float]) -> tuple[str | None, float]:
        """Fold one check into the face's running scores and name it if one member leads
        clearly: at or above ``name_score``, ``MATCH_MARGIN`` over the runner-up, after
        ``name_checks`` checks. Otherwise the face keeps the name it already had while that
        member still clears ``MATCH_THRESHOLD``. Sets ``_runner`` / ``_runner_score`` on
        the face (the second-best member)."""
        face["_n"] = int(face.get("_n", 0)) + 1
        ev: dict[str, float] = face.setdefault("_ev", {})
        for mid, sim in scores.items():
            ev[mid] = (
                sim
                if mid not in ev
                else (1 - self.EV_ALPHA) * ev[mid] + self.EV_ALPHA * sim
            )
        for mid in [m for m in ev if m not in scores]:
            del ev[mid]  # forgotten meanwhile
        if not ev:
            return None, -1.0
        ranked = sorted(ev.items(), key=lambda kv: kv[1], reverse=True)
        best_id, best = ranked[0]
        runner_id, runner = ranked[1] if len(ranked) > 1 else (None, -1.0)
        face["_runner"], face["_runner_score"] = runner_id, runner
        prior = face.get("member_id")
        if (
            best_id == prior
            and best >= MATCH_THRESHOLD
            and best - runner >= MATCH_MARGIN
        ):
            return best_id, best
        if (
            best >= self.name_score
            and best - runner >= MATCH_MARGIN
            and face["_n"] >= self.name_checks
        ):
            return best_id, best
        if prior is not None and ev.get(prior, -1.0) >= MATCH_THRESHOLD:
            return prior, ev[prior]
        return None, best

    def process(self, pairs: list, frame: Any, scale: float, now: float) -> list[dict]:
        """Faces (from ``pairs``) with identities. ``frame`` is the full-resolution picture,
        ``scale`` its size over the detection frame's."""
        if now - self._last_refresh_t >= 2.0:
            self._last_refresh_t = now
            self.gallery.refresh()

        faces = [dict(f) for f, _ in pairs]
        # Carry identities over from the previous detection by position.
        for f in faces:
            best, best_d2 = None, self.CARRY_DIST**2
            for p in self._prev:
                d2 = (f["cx"] - p["cx"]) ** 2 + (f["cy"] - p["cy"]) ** 2
                if d2 <= best_d2:
                    best, best_d2 = p, d2
            if best is not None and best.get("member_id") is not None:
                f["member_id"] = best["member_id"]
                f["id_score"] = best.get("id_score", 0.0)
                f["_id_t"] = best.get("_id_t", 0.0)
            else:
                f["member_id"] = None
                f["_id_t"] = best.get("_id_t", 0.0) if best is not None else 0.0
            f["_ev"] = dict(best.get("_ev", {})) if best is not None else {}
            f["_n"] = best.get("_n", 0) if best is not None else 0
            if best is not None and "id_runner" in best:
                f["id_runner"] = best["id_runner"]
                f["id_runner_score"] = best["id_runner_score"]

        if self._enroll is not None:
            self._enroll_step(pairs, frame, scale, now)
        elif (
            faces
            and self.gallery.counts()
            and now - self._last_id_t >= 1.0 / max(0.1, self.id_hz)
        ):
            self._last_id_t = now
            # Unidentified first, then the identity checked longest ago.
            i = min(
                range(len(faces)),
                key=lambda k: (faces[k]["member_id"] is not None, faces[k]["_id_t"]),
            )
            import time

            t0 = time.perf_counter()
            emb = self.embedder.embed(frame, _scaled_row(pairs[i][1], scale))
            self.ms = (time.perf_counter() - t0) * 1000.0
            if emb is not None:
                mid, sim = self._decide(faces[i], self.gallery.scores(emb))
                faces[i]["member_id"] = mid
                faces[i]["id_score"] = round(sim, 3)
                faces[i]["_id_t"] = now
                faces[i]["id_runner"] = faces[i].get("_runner")
                faces[i]["id_runner_score"] = round(
                    float(faces[i].get("_runner_score", -1.0)), 3
                )

        self._prev = faces
        return [{k: v for k, v in f.items() if not k.startswith("_")} for f in faces]
