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


def list_sessions() -> None:
    root = sessions_dir()
    if not root.is_dir():
        print(f"no retained sessions yet ({root})")
        print("Screen a call first — chunks are kept as they are scored.")
        return
    rows = []
    for d in sorted(root.iterdir()):
        if d.is_dir():
            wavs = sorted(d.glob("chunk_*.wav"))
            if wavs:
                rows.append((d.name, len(wavs), max(w.stat().st_mtime for w in wavs)))
    if not rows:
        print("no session audio retained yet")
        return
    rows.sort(key=lambda r: r[2], reverse=True)
    print(f"{'session':34s} {'chunks':>7s}   newest first")
    for name, n, _ in rows:
        print(f"{name:34s} {n:7d}")


def enrol(session: str, name: str, relation: str) -> int:
    chunks = sorted((sessions_dir() / session).glob("chunk_*.wav"))
    if not chunks:
        print(f"no chunks for session '{session}'", file=sys.stderr)
        return 1

    # Chunks overlap by 3s of a 9s window, so consecutive files share a third of their
    # audio. That is harmless for a centroid — it reweights, it does not corrupt — but
    # skipping every other chunk removes the duplication for free when there are enough.
    selected = chunks[::2] if len(chunks) >= 4 else chunks
    print(f"enrolling from {len(selected)} of {len(chunks)} chunk(s) in {session}")

    from audio_ml.api import enroll_person

    person_id = f"person_{uuid.uuid4().hex[:10]}"
    result = enroll_person(
        person_id=person_id,
        name=name,
        relationship=relation,
        wav_paths=[str(p) for p in selected],
    )
    if not result:
        print("enroll_person returned nothing — not enough usable speech in that call",
              file=sys.stderr)
        return 1

    npz = config.ENROLLMENTS_DIR / f"{person_id}.npz"
    if not npz.is_file():
        print(f"no voiceprint written at {npz}", file=sys.stderr)
        return 1

    # The DB row is what the app's "Known voices" list reads; without it the matcher would
    # compare against a person the user cannot see.
    try:
        from server.database import SessionLocal, Person
        db = SessionLocal()
        db.add(Person(person_id=person_id, name=name, relation=relation))
        db.commit()
        db.close()
    except Exception as e:
        print(f"warning: voiceprint saved but DB row failed: {e}", file=sys.stderr)

    print(f"enrolled {name} as {person_id}")
    print(f"  voiceprint: {npz}")
    print("Restart is not required — verify_speaker globs this directory per call.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="show retained call sessions")
    ap.add_argument("--session", help="session id to enrol from")
    ap.add_argument("--name", default="Caller")
    ap.add_argument("--relation", default="Family")
    args = ap.parse_args()

    if args.list or not args.session:
        list_sessions()
        return 0
    return enrol(args.session, args.name, args.relation)


if __name__ == "__main__":
    raise SystemExit(main())
