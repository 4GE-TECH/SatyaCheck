"""Enrol a voice from audio captured through a real call.

Why this exists
---------------
A voiceprint is only comparable to a probe that travelled the same acoustic path. On this
setup the gap is not subtle:

    same person, clean channel, clean voiceprint      cosine 0.9464   -> match
    same person, close-mic voiceprint, room probe     cosine 0.31     -> unknown

The second number is not a worse recording of a voice; it is a measurement of the room and
the phone speaker. A caller's voice reaches us through their microphone, a cellular codec,
our earpiece speaker, the air, and our microphone. Nothing recorded by holding a phone to
your mouth shares that chain.

`server/ws_router.py` now retains each screened chunk under `data/sessions/<id>/`. This
enrols from those chunks, so the reference and the probe finally match.

Usage
-----
    python -m scripts.enrol_from_call --list
    python -m scripts.enrol_from_call --session call-1787464475879 --name "Nikhil (call)"
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

import config


def sessions_dir() -> Path:
    return config.DATA_DIR / "sessions"


def _retention_hint() -> None:
    # Without this, retention being off looks exactly like no call ever arriving. The flag
    # read here is this shell's, not the server's (the runbook sets it on the uvicorn line
    # only), so it is shown only when nothing is retained and worded as a possibility.
    if not config.RETAIN_SESSION_AUDIO:
        print("RETAIN_SESSION_AUDIO is off by default, and this shell does not set it.")
        print("If the server was started without RETAIN_SESSION_AUDIO=true, it keeps no")
        print("call audio: restart it with RETAIN_SESSION_AUDIO=true, screen a call, retry.")


def list_sessions() -> None:
    root = sessions_dir()
    if not root.is_dir():
        print(f"no retained sessions yet ({root})")
        print("Screen a call first — chunks are kept as they are scored.")
        _retention_hint()
        return
    rows = []
    for d in sorted(root.iterdir()):
        if d.is_dir():
            wavs = sorted(d.glob("chunk_*.wav"))
            if wavs:
                rows.append((d.name, len(wavs), max(w.stat().st_mtime for w in wavs)))
    if not rows:
        print("no session audio retained yet")
        _retention_hint()
        return
    rows.sort(key=lambda r: r[2], reverse=True)
    print(f"{'session':34s} {'chunks':>7s}   newest first")
    for name, n, _ in rows:
        print(f"{name:34s} {n:7d}")


def enrol(session: str, name: str, relation: str, owner: str | None = None) -> int:
    chunks = sorted((sessions_dir() / session).glob("chunk_*.wav"))
    if not chunks:
        print(f"no chunks for session '{session}'", file=sys.stderr)
        return 1

    # Chunks overlap by 3s of a 9s window, so consecutive files share a third of their
    # audio. That is harmless for a centroid — it reweights, it does not corrupt — but
    # skipping every other chunk removes the duplication for free when there are enough.
    selected = chunks[::2] if len(chunks) >= 4 else chunks
    print(f"enrolling from {len(selected)} of {len(chunks)} chunk(s) in {session}")

    import audio_ml.api
    from server import database, voiceprint_store

    vectors = audio_ml.api.compute_voiceprint([str(p) for p in selected])
    if not vectors:
        print("no voiceprint computed — not enough usable speech in that call", file=sys.stderr)
        return 1

    # Person and vectors in one transaction, exactly like /api/enroll: the app lists what
    # the verifier compares against, and a failure stores neither.
    owner = owner or config.DEV_OWNER_ID
    person_id = f"person_{uuid.uuid4().hex[:10]}"
    db = database.owner_session(owner)
    try:
        db.add(database.Person(person_id=person_id, owner_id=owner, name=name, relation=relation))
        db.flush()
        saved = voiceprint_store.save_voiceprints(
            db, owner, person_id, vectors,
            duration_s=vectors["n_samples"] / config.TARGET_SAMPLE_RATE,
            snr_db=0.0,   # not measured for call enrolments
        )
        if not saved:
            db.rollback()
            print("no usable voiceprint vector — nothing stored", file=sys.stderr)
            return 1
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"could not store the voiceprint, nothing saved: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print(f"enrolled {name} as {person_id} (voiceprints: {', '.join(saved)})")
    print("Restart is not required — screening reads the database on every call.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="show retained call sessions")
    ap.add_argument("--session", help="session id to enrol from")
    ap.add_argument("--name", default="Caller")
    ap.add_argument("--relation", default="Family")
    ap.add_argument("--owner", help="account that owns the new contact (default: the dev account)")
    args = ap.parse_args()

    if args.list or not args.session:
        list_sessions()
        return 0
    return enrol(args.session, args.name, args.relation, args.owner)


if __name__ == "__main__":
    raise SystemExit(main())
