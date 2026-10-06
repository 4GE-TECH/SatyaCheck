"""Telephony augmentation: G.711, AMR-NB and additive noise (item 13).

    python -m audio_ml.augment --manifest <dir>/manifest.csv --out <dir> \\
        --conditions g711_ulaw g711_alaw amr_nb amr_nb+noise10 [--splits test] [--seed 0]

Builds narrowband copies of a manifest's audio so the authenticity branch can be
measured (``audio_ml.eval.eval_spoof``) and Model A retrained on the channel real calls
arrive through. Training itself happens outside this repo (CLAUDE.md rule 1); this
module only produces data.

A condition is ``codec``, ``noise<SNR dB>``, or ``noise<SNR>+codec`` in either order.
Noise is always applied first: it is acoustic, it happens in the caller's room, before
the phone network encodes anything.

**This module raises; `codec.degrade` does not.** `degrade` serves enrollment, where a
plain 8 kHz copy is an acceptable stand-in when an encoder is missing. For a dataset it
is not: a file labelled AMR-NB that silently is not would corrupt every number measured
on it. So every codec is verified by probing the encoded intermediate, and any failure
is an `AugmentError` (the CLI exits non-zero). This is an offline tool, never imported
by the server, so CLAUDE.md rule 5 ("public functions never raise") does not apply.

The output manifest keeps every source row's split, speaker and label and records the
condition, SNR, codec and the source file's SHA-256. Noise is seeded from the source's
content, so byte-identical sources stay byte-identical after augmentation and the
leakage checks in `eval_spoof` still hold over the augmented set. The manifest is
written only when every file succeeded; a failed run leaves none.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

logger = logging.getLogger(__name__)

SR = 16_000
CHANNEL_SR = 8_000

#: codec name -> ffmpeg encoder arguments. Every one encodes at 8 kHz mono.
CODECS: dict[str, list[str]] = {
    "g711_ulaw": ["-acodec", "pcm_mulaw"],
    "g711_alaw": ["-acodec", "pcm_alaw"],
    "amr_nb": ["-acodec", "libopencore_amrnb", "-b:a", "12.2k"],  # highest AMR-NB mode
}
_CONTAINER = {"amr_nb": ".amr"}  # others go in WAV
_NOISE = re.compile(r"^noise(\d+(?:\.\d+)?)$")


class AugmentError(RuntimeError):
    """The requested condition could not be applied faithfully."""


# --- codecs ------------------------------------------------------------------------

def _ffmpeg(args: list[str]) -> None:
    result = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
                            capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise AugmentError(f"ffmpeg failed: {(result.stderr or '').strip()[:300]}")


def _probe(path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=codec_name,sample_rate", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    streams = json.loads(result.stdout or "{}").get("streams") or []
    if result.returncode != 0 or not streams:
        raise AugmentError(f"ffprobe could not read {path}: {(result.stderr or '').strip()[:200]}")
    return streams[0]


def apply_codec(in_path: Path, out_path: Path, codec: str) -> dict:
    """Encode through `codec` at 8 kHz, decode back to 16 kHz mono PCM WAV.

    Returns what the encoded intermediate actually contained. Raises AugmentError, and
    leaves no output file, if the codec is unknown or was not really applied.
    """
    if codec not in CODECS:
        raise AugmentError(f"unknown codec {codec!r}; known: {sorted(CODECS)}")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            encoded = Path(tmp) / f"encoded{_CONTAINER.get(codec, '.wav')}"
            _ffmpeg(["-i", str(in_path), "-ar", str(CHANNEL_SR), "-ac", "1", *CODECS[codec], str(encoded)])
            probed = _probe(encoded)
            _ffmpeg(["-i", str(encoded), "-ar", str(SR), "-ac", "1", "-acodec", "pcm_s16le", str(out_path)])
    except Exception:
        out_path.unlink(missing_ok=True)
        raise
    info = {"intermediate_codec": probed.get("codec_name"),
            "intermediate_sample_rate": int(probed.get("sample_rate") or 0)}
    if info["intermediate_sample_rate"] != CHANNEL_SR:
        out_path.unlink(missing_ok=True)
        raise AugmentError(f"{codec}: encoded at {info['intermediate_sample_rate']} Hz, not 8 kHz")
    return info


# --- noise --------------------------------------------------------------------------

def _pink(n: int, rng: np.random.Generator) -> np.ndarray:
    """1/f power spectrum: shape white noise by 1/sqrt(f) in the frequency domain."""
    spectrum = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n)
    spectrum[1:] /= np.sqrt(f[1:])
    spectrum[0] = 0.0
    return np.fft.irfft(spectrum, n)


def _noise_from_dir(noise_dir: Path, n: int, rng: np.random.Generator) -> np.ndarray:
    files = sorted(Path(noise_dir).glob("*.wav"))
    if not files:
        raise AugmentError(f"no .wav noise files in {noise_dir}")
    audio, sr = read_wav(files[int(rng.integers(len(files)))])
    if sr != SR:
        raise AugmentError(f"noise files must be {SR} Hz mono; got {sr} Hz")
    if not np.any(audio):
        raise AugmentError("noise file is silent")
    reps = int(np.ceil((n + len(audio)) / len(audio)))
    tiled = np.tile(audio, reps)
    start = int(rng.integers(len(audio)))
    return tiled[start:start + n]


def add_noise(
    audio: np.ndarray, snr_db: float, rng: np.random.Generator,
    kind: str = "white", noise_dir: Optional[Path] = None,
) -> np.ndarray:
    """Return `audio` plus noise scaled to exactly `snr_db` over the whole clip."""
    audio = np.asarray(audio, dtype=np.float64)
    signal_power = float(np.mean(audio ** 2))
    if signal_power == 0.0:
        raise AugmentError("cannot set an SNR against silent audio")
    n = len(audio)
    if noise_dir is not None:
        noise = _noise_from_dir(noise_dir, n, rng)
    elif kind == "white":
        noise = rng.standard_normal(n)
    elif kind == "pink":
        noise = _pink(n, rng)
    else:
        raise AugmentError(f"unknown noise kind {kind!r}")
    noise = noise * np.sqrt(signal_power / (10 ** (snr_db / 10)) / np.mean(noise ** 2))
    return audio + noise


# --- WAV I/O -------------------------------------------------------------------------

def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            raise AugmentError(f"{path}: expected 16-bit PCM")
        frames = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float64) / 32768.0
        channels = w.getnchannels()
        if channels > 1:
            frames = frames.reshape(-1, channels).mean(axis=1)
        return frames, w.getframerate()


def write_wav(path: Path, audio: np.ndarray, sr: int = SR) -> float:
    """Write 16-bit mono. Scales the whole clip down if it would clip (SNR unchanged).
    Returns the gain applied."""
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    gain = 0.99 / peak if peak > 0.99 else 1.0
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((audio * gain * 32767).astype("<i2").tobytes())
    return gain


def _load_16k(path: Path, tmp: Path) -> np.ndarray:
    try:
        audio, sr = read_wav(path)
        if sr == SR:
            return audio
    except (AugmentError, wave.Error):
        pass
    normalised = tmp / "source_16k.wav"
    _ffmpeg(["-i", str(path), "-ar", str(SR), "-ac", "1", "-acodec", "pcm_s16le", str(normalised)])
    return read_wav(normalised)[0]


# --- conditions and the CLI ----------------------------------------------------------------

def parse_condition(text: str) -> tuple[Optional[float], Optional[str]]:
    """'amr_nb+noise10' -> (10.0, 'amr_nb'). Raises AugmentError on anything else."""
    snr, codec = None, None
    for part in text.split("+"):
        match = _NOISE.match(part)
        if match and snr is None:
            snr = float(match.group(1))
        elif part in CODECS and codec is None:
            codec = part
        else:
            raise AugmentError(f"bad condition {text!r}: use a codec {sorted(CODECS)}, "
                               "noise<SNR>, or noise<SNR>+codec")
    return snr, codec


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while chunk := fh.read(1 << 16):
            h.update(chunk)
    return h.hexdigest()


def augment_file(src: Path, dst: Path, condition: str, rng: np.random.Generator,
                 noise_kind: str = "white", noise_dir: Optional[Path] = None) -> dict:
    snr, codec = parse_condition(condition)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        audio = _load_16k(src, tmp)
        gain = 1.0
        if snr is not None:
            audio = add_noise(audio, snr, rng, kind=noise_kind, noise_dir=noise_dir)
        if codec is None:
            gain = write_wav(dst, audio)
            return {"codec": "", "snr_db": snr, "gain": gain}
        staged = tmp / "staged.wav"
        gain = write_wav(staged, audio)
        info = apply_codec(staged, dst, codec)
    return {"codec": info["intermediate_codec"], "snr_db": snr, "gain": gain}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--audio-root", type=Path, help="defaults to the manifest's directory")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--conditions", nargs="+", required=True)
    ap.add_argument("--splits", nargs="+", help="only augment these splits (default: all)")
    ap.add_argument("--noise-kind", choices=["white", "pink"], default="white")
    ap.add_argument("--noise-dir", type=Path, help="16 kHz mono .wav noise to sample from")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    try:
        for c in args.conditions:
            parse_condition(c)
    except AugmentError as e:
        logger.error("%s", e)
        return 1
    if not args.manifest.is_file():
        logger.error("manifest not found: %s", args.manifest)
        return 1
    root = args.audio_root or args.manifest.parent

    with args.manifest.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        source_fields = list(reader.fieldnames or [])
        rows = [r for r in reader if not args.splits or r["split"] in args.splits]

    fields = source_fields + ["condition", "codec", "snr_db", "gain", "source_filepath", "source_sha256", "seed"]
    args.out.mkdir(parents=True, exist_ok=True)
    final = args.out / "manifest.csv"
    partial = args.out / "manifest.csv.partial"
    # A run overwrites the previous run's audio, so its manifest is stale from here on.
    # The manifest only appears, by rename, once every row is written: a partially
    # augmented set with silent gaps is the failure this module exists to prevent.
    final.unlink(missing_ok=True)
    written = 0
    try:
        with partial.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            for i, row in enumerate(rows):
                src = Path(root) / row["filepath"]
                try:
                    source_sha = _sha256(src)
                except OSError as e:
                    logger.error("%s: %s — stopping, no manifest written", row["filepath"], e)
                    return 4
                for ci, condition in enumerate(args.conditions):
                    rel = Path(condition) / row["filepath"]
                    try:
                        # Seed from the source *content*, not its row: byte-identical
                        # sources then get identical noise, so eval_spoof's hash check
                        # still sees a train/test duplicate after augmentation.
                        rng = np.random.default_rng([args.seed, int(source_sha[:16], 16), ci])
                        info = augment_file(src, args.out / rel, condition, rng,
                                            noise_kind=args.noise_kind, noise_dir=args.noise_dir)
                    except (AugmentError, OSError, subprocess.SubprocessError) as e:
                        logger.error("%s (%s): %s — stopping, no manifest written",
                                     row["filepath"], condition, e)
                        return 4
                    writer.writerow({**row, "filepath": rel.as_posix(), "condition": condition,
                                     "codec": info["codec"], "snr_db": info["snr_db"] if info["snr_db"] is not None else "",
                                     "gain": round(info["gain"], 6), "source_filepath": row["filepath"],
                                     "source_sha256": source_sha, "seed": args.seed})
                    written += 1
                if (i + 1) % 500 == 0:
                    logger.info("augmented %d/%d source files", i + 1, len(rows))
        partial.replace(final)
    finally:
        partial.unlink(missing_ok=True)
    logger.info("wrote %d files and %s", written, args.out / "manifest.csv")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    sys.exit(main())
