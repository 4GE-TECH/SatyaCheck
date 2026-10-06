"""Out-of-distribution check for the authenticity branch (item 8).

Model A was fine-tuned on IFD. Measured on IFD itself its EER is 9.7% on clean audio
but 17.2% through G.711 and 25.5% through AMR-NB (data/spoof_eval_ifd*.json): on audio
unlike its training data, P(synthetic) stops meaning much. This module decides when a
clip is that far away, so the branch can abstain instead of guessing.

Non-parametric and training-free (CLAUDE.md rule 1): a stored bank of AASIST's own
penultimate embeddings (`last_hidden`) for IFD training windows. A window's distance is
the mean cosine distance to its k nearest bank neighbours; the threshold is a percentile
of that distance over IFD validation windows. Build the bank with
`python -m audio_ml.eval.build_ood_ref`.

Never raises at inference: a missing or broken bank loads as None and changes nothing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OodReference:
    embeddings: np.ndarray   # (n, d), L2-normalised
    threshold: float         # cosine-distance cut, from validation windows
    k: int
    percentile: float
    n_reference: int

    def save(self, path: Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, embeddings=self.embeddings.astype(np.float32), threshold=self.threshold,
                 k=self.k, percentile=self.percentile, n_reference=self.n_reference)


def _normalise(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    return x / np.maximum(norms, 1e-12)


def knn_distance(queries: np.ndarray, bank: np.ndarray, k: int) -> np.ndarray:
    """Mean cosine distance from each query row to its k nearest rows of `bank`."""
    sims = _normalise(queries) @ _normalise(bank).T
    k = max(1, min(k, sims.shape[1]))
    nearest = -np.partition(-sims, k - 1, axis=1)[:, :k]
    return 1.0 - nearest.mean(axis=1)


def ood_verdict(window_embeddings: np.ndarray, ref: OodReference,
                max_window_fraction: float) -> tuple[bool, float]:
    """(is_ood, fraction of windows beyond the threshold)."""
    if len(window_embeddings) == 0:
        return False, 0.0
    distances = knn_distance(window_embeddings, ref.embeddings, ref.k)
    fraction = float(np.mean(distances > ref.threshold))
    return fraction >= max_window_fraction, fraction


def load_reference(path: Path) -> Optional[OodReference]:
    """The bank at `path`, or None (logged) if it is missing or unreadable."""
    path = Path(path)
    if not path.is_file():
        logger.warning("anti-spoof OOD check: no reference bank at %s; check disabled", path)
        return None
    try:
        data = np.load(path)
        return OodReference(
            embeddings=_normalise(data["embeddings"]),
            threshold=float(data["threshold"]),
            k=int(data["k"]),
            percentile=float(data["percentile"]),
            n_reference=int(data["n_reference"]),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("anti-spoof OOD check: unreadable bank %s (%s); check disabled", path, exc)
        return None


# --- narrowband-channel rule ------------------------------------------------------------
#
# The k-NN gate above does not see the phone channel: measured on 200 IFD test clips per
# condition it flags 14% of clean, 11% of G.711 and 10.5% of AMR-NB clips, i.e. codec
# audio looks *more* in-domain to it than clean audio does. The channel itself is easy to
# see, though: every 8 kHz telephony codec (G.711, AMR-NB, GSM) is sampled at 8 kHz, so
# nothing survives above its 4 kHz Nyquist, whatever the codec does below it. A clip whose
# energetic frames carry essentially no power above ~4 kHz came through such a channel,
# and Model A (fine-tuned on wideband IFD) is out of its domain there.

NB_FRAME = 512             # samples per analysis frame (32 ms at 16 kHz)
NB_HOP = 256
NB_HF_LOW_HZ = 4500.0      # above the 4 kHz telephony Nyquist AND clear of resampler roll-off
NB_LOW_CUT_HZ = 50.0       # ignore DC / mains hum in the denominator
NB_TOP_FRACTION = 0.95     # ignore the last 5% below Nyquist (resampler roll-off)
NB_SILENCE_RMS = 1e-4      # -80 dBFS: a frame quieter than this is silence
NB_RELATIVE_GATE_DB = 40.0  # keep frames within this of the loudest frame


def hf_power_ratio(audio, sr: int) -> Optional[float]:
    """Share of spectral power above ~4 kHz, over the energetic frames of the whole clip.

    The power spectrum is averaged over every frame within `NB_RELATIVE_GATE_DB` of the
    loudest one (silence and faint hiss between words are ignored, not averaged in), so a
    long silent opening or one loud click cannot decide the answer.

    Returns None — unknown, never "narrowband" — when there is nothing to measure
    (empty, too short, silent, non-finite input); the reason is logged. Never raises.
    """
    try:
        if audio is None:
            logger.info("narrowband check: no audio; channel unknown")
            return None
        x = np.asarray(audio, dtype=np.float64).ravel()
        if x.size < NB_FRAME:
            logger.info("narrowband check: %d samples is shorter than one frame; channel unknown", x.size)
            return None
        if not np.all(np.isfinite(x)):
            logger.warning("narrowband check: non-finite samples; channel unknown")
            return None
        n_frames = 1 + (x.size - NB_FRAME) // NB_HOP
        idx = np.arange(NB_FRAME)[None, :] + NB_HOP * np.arange(n_frames)[:, None]
        frames = x[idx]
        frames = frames - frames.mean(axis=1, keepdims=True)
        rms = np.sqrt(np.mean(frames ** 2, axis=1))
        loudest = float(rms.max())
        if loudest < NB_SILENCE_RMS:
            logger.info("narrowband check: clip is silent (peak frame RMS %.2e); channel unknown", loudest)
            return None
        keep = (rms >= NB_SILENCE_RMS) & (rms >= loudest * 10 ** (-NB_RELATIVE_GATE_DB / 20))
        if sr <= 2 * NB_HF_LOW_HZ:
            return 0.0  # nothing can exist above Nyquist: narrowband by definition
        spec = np.abs(np.fft.rfft(frames[keep] * np.hanning(NB_FRAME), axis=1)) ** 2
        power = spec.mean(axis=0)
        freqs = np.fft.rfftfreq(NB_FRAME, 1.0 / sr)
        top = NB_TOP_FRACTION * sr / 2
        total = float(power[(freqs >= NB_LOW_CUT_HZ) & (freqs <= top)].sum())
        if total <= 0.0:
            logger.info("narrowband check: no in-band power; channel unknown")
            return None
        return float(power[(freqs >= NB_HF_LOW_HZ) & (freqs <= top)].sum()) / total
    except Exception as exc:  # noqa: BLE001
        logger.error("narrowband check failed (%s: %s); channel unknown", type(exc).__name__, exc)
        return None


def is_narrowband(audio, sr: int, threshold: float) -> bool:
    """True when the clip is band-limited like an 8 kHz phone channel. Unknown -> False."""
    ratio = hf_power_ratio(audio, sr)
    return ratio is not None and ratio < threshold


if __name__ == "__main__":  # CLI smoke test: python -m audio_ml.ood [clip.wav ...]
    import sys

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")
    from scipy.signal import resample_poly

    import config

    thr = config.SPOOF_NARROWBAND_HF_RATIO_THRESHOLD
    noise = 0.1 * np.random.default_rng(0).standard_normal(48_000)
    narrow = resample_poly(resample_poly(noise, 1, 2), 2, 1)
    assert not is_narrowband(noise, 16_000, thr)
    assert is_narrowband(narrow, 16_000, thr)
    assert hf_power_ratio(np.zeros(16_000), 16_000) is None
    print(f"  ok: white noise {hf_power_ratio(noise, 16_000):.2e}, through 8 kHz "
          f"{hf_power_ratio(narrow, 16_000):.2e}, silence unknown (threshold {thr:.1e})")
    if len(sys.argv) > 1:
        from audio_ml import embed

        for p in sys.argv[1:]:
            audio, sr = embed.load_audio(p)
            ratio = hf_power_ratio(audio, sr)
            print(f"  {p}: hf_ratio={ratio} narrowband={is_narrowband(audio, sr, thr)}")
    sys.exit(0)
