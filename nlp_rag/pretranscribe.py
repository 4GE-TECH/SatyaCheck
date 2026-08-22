"""Pre-transcribed demo clips — the latency mitigation the risk register names.

`PLAN.md` §8 asks for this and §8.1 measured why. faster-whisper pads every input to a
30-second mel window, so decoding costs roughly ~1.2s fixed plus ~0.1s per second of
speech no matter how short the clip is. On stage that is the difference between a meter
that moves and one an audience watches spin.

Build it once, with the clips present::

    python -m nlp_rag.pretranscribe data/demo_clips

`api.transcribe` then consults the cache before the decoder, and misses fall through
silently. Nothing else changes: C keeps calling `transcribe(wav_path or waveform)`.

**Keyed on the SHA-256 of the audio, never its path.** A clip renamed or moved between
rehearsal and demo must still hit; a clip quietly re-recorded must miss rather than serve
the previous take's transcript. This is the same reasoning as the content hashes in
`index_store.py`, and for the same reason: a cache that silently serves stale content is
worse than no cache, because nothing reports it.

The cache is a demo convenience and never a correctness dependency — every failure path
here returns None and lets the real decoder run.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Iterable, Sequence

from contracts import TranscriptResult

logger = logging.getLogger(__name__)

#: `PLAN.md` §3 puts build artefacts here rather than in root `data/`, which has no owner.
DEFAULT_CACHE = Path(__file__).resolve().parent / "index" / "pretranscribed.json"

#: What `build` will look at. faster-whisper decodes more, but the demo clips are WAVs.
AUDIO_SUFFIXES = (".wav", ".mp3", ".m4a", ".ogg", ".flac")


def audio_hash(path: str | Path) -> str:
    """SHA-256 of the file's bytes, read in chunks so a long clip is not held in memory."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write(entries: dict[str, dict[str, Any]], path: str | Path = DEFAULT_CACHE) -> None:
    """Persist the cache, creating the directory if needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


def _load(path: str | Path) -> dict[str, Any]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("pre-transcription cache unavailable (%s)", exc)
        return {}


def lookup(
    source: str | Path | Sequence[float], path: str | Path = DEFAULT_CACHE
) -> TranscriptResult | None:
    """Return the stored transcript for `source`, or None to fall through to the decoder.

    A raw waveform is always a miss: C calls `transcribe(wav_path or waveform)`, and a
    buffer has no file to hash. That is the streaming path, which is live audio and could
    not have been pre-transcribed anyway.
    """
    try:
        if not isinstance(source, (str, Path)):
            return None
        audio = Path(source)
        if not audio.is_file():
            return None

        entry = _load(path).get(audio_hash(audio))
        if not entry:
            return None

        return TranscriptResult(
            text=entry.get("text", ""),
            segments=[],
            detected_language=entry.get("language", "unknown") or "unknown",
            confidence=float(entry.get("confidence", 0.0)),
        )
    except Exception as exc:  # noqa: BLE001 - a broken cache must never break a request
        logger.warning("pre-transcription lookup failed (%s); decoding instead", exc)
        return None


def build(
    clip_dir: str | Path, out_path: str | Path = DEFAULT_CACHE
) -> dict[str, dict[str, Any]]:
    """Transcribe every clip under `clip_dir` and write the cache. Returns what was stored.

    Clips the decoder could not read are **skipped, not stored empty**. Persisting an empty
    transcript would pin a silent result for a clip that merely failed once — and the
    failure would then be invisible, because a cache hit looks identical to a success.
    """
    from nlp_rag import asr

    entries: dict[str, dict[str, Any]] = {}
    for clip in _clips(clip_dir):
        try:
            result = asr.transcribe_file(str(clip))
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s: transcription raised (%s); skipped", clip.name, exc)
            continue

        if not result.text.strip():
            logger.warning("%s: produced no transcript; skipped", clip.name)
            continue

        entries[audio_hash(clip)] = {
            "clip": clip.name,  # human-readable only; lookup never reads it
            "text": result.text,
            "language": result.detected_language,
            "confidence": result.confidence,
        }
        logger.info("%s: %s", clip.name, result.text[:70])

    write(entries, out_path)
    return entries


def _clips(clip_dir: str | Path) -> Iterable[Path]:
    directory = Path(clip_dir)
    if not directory.is_dir():
        return []
    return sorted(
        p for p in directory.iterdir() if p.suffix.lower() in AUDIO_SUFFIXES
    )


if __name__ == "__main__":  # pragma: no cover - CLI, run once with the clips present
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    source = sys.argv[1] if len(sys.argv) > 1 else "data/demo_clips"
    stored = build(source)
    if not stored:
        print(f"no clips transcribed from {source} — is the directory populated?")
    else:
        print(f"\n{len(stored)} clips cached → {DEFAULT_CACHE}")
