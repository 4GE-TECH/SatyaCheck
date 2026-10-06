"""
audio_ml/spoof.py — Synthetic voice detection with Model A (fine-tuned AASIST).

Model A is raw-waveform AASIST, 16 kHz, fixed 64,600-sample input, fine-tuned by
Nikhil on IFD (checkpoint `best_model.pth`, "baseline" run: clean-audio training). It
is the one fine-tuned model in this build — CLAUDE.md rule 1 ("we train nothing") has
this documented exception; everything else is pretrained inference.

Files, all under models/antispoof/ (gitignored, loaded by path, never downloaded at
runtime — CLAUDE.md rule 4):

    AASIST.py      model definition, official clovaai/aasist (MIT, NAVER Corp)
    AASIST.conf    official model_config for that architecture
    LICENSE        clovaai/aasist licence, kept beside the code it covers
    model_a.pth    the checkpoint (a wrapper dict with `state_dict`)

Inference is deterministic: `model.eval()`, `Freq_aug=False`, no random cropping —
every window is a fixed slice of the file, and audio shorter than one window is tiled
(repeated), not zero-padded or randomly placed.

Output convention (clovaai): logits[:, 1] is bonafide, logits[:, 0] is spoof, so
P(synthetic) = softmax(logits)[:, 0].

It is a risk *multiplier* gated by intent (server/orchestrator.py fusion), never a
standalone verdict. If anything is missing or fails, `detect_spoof` returns the
neutral SpoofSignal(score=0.5, verdict="uncertain", n_chunks=0) and logs why;
server/audio_adapter.py then marks the branch unavailable so fusion drops its weight.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import threading
from pathlib import Path
from typing import List, Tuple

import numpy as np

from . import embed
from .spoof_aggregate import aggregate
from .ood import hf_power_ratio, load_reference, ood_verdict
from audio_ml.signals import SpoofSignal

logger = logging.getLogger(__name__)

try:
    import config as _config
except ImportError:  # pragma: no cover
    _config = None

_MODELS_DIR = Path(getattr(_config, "MODELS_DIR", Path(__file__).resolve().parent.parent / "models"))
ANTISPOOF_DIR: Path = _MODELS_DIR / "antispoof"
WEIGHTS_NAME = "model_a.pth"

TARGET_SR = 16000
WINDOW_SAMPLES = 64600                                     # fixed by the architecture
HOP_S: float = float(getattr(_config, "SPOOF_HOP_S", 2.0))  # timeline granularity

_model = None
_load_attempted = False
_lock = threading.Lock()


def model_files_present() -> bool:
    return all((ANTISPOOF_DIR / f).is_file() for f in ("AASIST.py", "AASIST.conf", WEIGHTS_NAME))


def _neutral() -> SpoofSignal:
    return SpoofSignal(score=0.5, verdict="uncertain")


def _load_model():
    """Load once and cache. Never retry a failure — this sits in the request path."""
    global _model, _load_attempted
    if _load_attempted:
        return _model
    with _lock:
        if _load_attempted:
            return _model
        _load_attempted = True

        if not model_files_present():
            logger.warning(
                "anti-spoof: Model A not found in %s (need AASIST.py, AASIST.conf, %s); "
                "branch abstains", ANTISPOOF_DIR, WEIGHTS_NAME,
            )
            return None
        try:
            import torch

            spec = importlib.util.spec_from_file_location("satyacheck_aasist", ANTISPOOF_DIR / "AASIST.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            d_args = json.loads((ANTISPOOF_DIR / "AASIST.conf").read_text())["model_config"]
            model = module.Model(d_args)

            checkpoint = torch.load(ANTISPOOF_DIR / WEIGHTS_NAME, map_location="cpu", weights_only=False)
            state = checkpoint.get("state_dict", checkpoint) if isinstance(checkpoint, dict) else checkpoint
            model.load_state_dict(state, strict=True)
            model.eval()
            _model = model
            logger.info("anti-spoof: Model A loaded (epoch %s)", checkpoint.get("epoch") if isinstance(checkpoint, dict) else "?")
        except Exception as exc:  # noqa: BLE001 - any load failure degrades identically
            logger.error("anti-spoof: Model A failed to load (%s: %s); branch abstains", type(exc).__name__, exc)
            _model = None
        return _model


def _windows(audio: np.ndarray, sr: int) -> Tuple[List[np.ndarray], List[Tuple[float, float]]]:
    """Deterministic fixed-length windows covering the whole file.

    Shorter than one window: tile (repeat) to length — the same padding the model was
    trained with. Longer: windows every HOP_S, plus one final window aligned to the end
    so the tail is always scored.
    """
    n = len(audio)
    if n == 0:
        return [], []
    if n <= WINDOW_SAMPLES:
        reps = int(np.ceil(WINDOW_SAMPLES / n))
        return [np.tile(audio, reps)[:WINDOW_SAMPLES]], [(0.0, n / sr)]

    hop = max(1, int(HOP_S * sr))
    starts = list(range(0, n - WINDOW_SAMPLES + 1, hop))
    if starts[-1] != n - WINDOW_SAMPLES:
        starts.append(n - WINDOW_SAMPLES)
    chunks = [audio[s:s + WINDOW_SAMPLES] for s in starts]
    spans = [(s / sr, (s + WINDOW_SAMPLES) / sr) for s in starts]
    return chunks, spans


_ood_ref = None
_ood_attempted = False


def _ood_reference():
    """The OOD reference bank, loaded once. None if absent (logged by load_reference)."""
    global _ood_ref, _ood_attempted
    if not _ood_attempted:
        _ood_attempted = True
        path = getattr(_config, "SPOOF_OOD_REF_PATH", ANTISPOOF_DIR / "ood_ref.npz")
        _ood_ref = load_reference(path)
    return _ood_ref


def _infer(model, chunks) -> Tuple[List[float], np.ndarray]:
    """P(synthetic) and AASIST's penultimate embedding (`last_hidden`) per window."""
    import torch

    with torch.no_grad():
        batch = torch.from_numpy(np.stack(chunks)).float()
        hidden, logits = model(batch, Freq_aug=False)
        p_synthetic = torch.softmax(logits, dim=1)[:, 0].cpu().numpy().tolist()
    return p_synthetic, hidden.cpu().numpy()


def window_embeddings(wav_path: str) -> np.ndarray:
    """AASIST embedding per window, shape (n_windows, d); empty on any failure. Never raises."""
    try:
        model = _load_model()
        if model is None:
            return np.zeros((0, 0), dtype=np.float32)
        audio, sr = embed.load_audio(wav_path)
        chunks, _ = _windows(np.asarray(audio, dtype=np.float32), sr)
        if not chunks:
            return np.zeros((0, 0), dtype=np.float32)
        return _infer(model, chunks)[1]
    except Exception as exc:  # noqa: BLE001
        logger.error("window_embeddings(%s): %s: %s", wav_path, type(exc).__name__, exc)
        return np.zeros((0, 0), dtype=np.float32)


def _narrowband_ratio(audio, sr: int, wav_path: str):
    """hf_power_ratio, or None (logged) if the measurement itself fails."""
    try:
        return hf_power_ratio(audio, sr)
    except Exception as exc:  # noqa: BLE001
        logger.warning("detect_spoof(%s): narrowband check failed (%s: %s); rule skipped",
                       wav_path, type(exc).__name__, exc)
        return None


def _ood_update(audio, sr: int, hidden: np.ndarray, wav_path: str) -> dict:
    """Fields to set on the SpoofSignal when SPOOF_OOD_ENABLED is on.

    Two independent rules; either one abstains. The narrowband-channel rule is checked
    first and named as the reason when both fire, because it is the one a person can
    act on ("this came through a phone line"). The k-NN fraction is still reported.
    """
    update: dict = {}
    reason = None

    if getattr(_config, "SPOOF_OOD_NARROWBAND_ENABLED", True):
        ratio = _narrowband_ratio(audio, sr, wav_path)
        if ratio is not None:
            update["hf_ratio"] = round(ratio, 8)
            threshold = getattr(_config, "SPOOF_NARROWBAND_HF_RATIO_THRESHOLD", 1e-4)
            if ratio < threshold:
                reason = "narrowband_channel"
                logger.info("detect_spoof(%s): narrowband channel (%.2e of power above 4.5 kHz "
                            "< %.2e); branch abstains", wav_path, ratio, threshold)

    ref = _ood_reference()
    if ref is not None:
        try:
            is_far, fraction = ood_verdict(
                hidden, ref, getattr(_config, "SPOOF_OOD_MAX_WINDOW_FRACTION", 0.5))
            update["ood_score"] = round(fraction, 4)
            if is_far:
                logger.info("detect_spoof(%s): out of distribution (%.0f%% of windows)",
                            wav_path, 100 * fraction)
                reason = reason or "embedding_distance"
        except Exception as exc:  # noqa: BLE001
            logger.warning("detect_spoof(%s): embedding OOD check failed (%s: %s); rule skipped",
                           wav_path, type(exc).__name__, exc)

    update["ood"] = reason is not None
    update["ood_reason"] = reason
    return update


def calibrate_phone_scores(scores, threshold: float) -> list:
    """Rescale P(synthetic) for a narrowband channel: s -> max(0, (s - T) / (1 - T))."""
    span = max(1e-9, 1.0 - threshold)
    return [max(0.0, (float(s) - threshold) / span) for s in scores]


def _phone_verdict(verdict: str, max_synth_run_s: float, median: float) -> str:
    """On a phone line, 'partial_synthetic' needs more than a single-window spike."""
    if verdict == "partial_synthetic" and max_synth_run_s < getattr(_config, "SPOOF_PHONE_MIN_SYNTH_RUN_S", 6.0):
        return "bonafide"
    return verdict


def detect_spoof(wav_path: str) -> SpoofSignal:
    """P(synthetic) per window, aggregated to median / peak / max run / timeline.

    Never raises. Neutral SpoofSignal (0.5, "uncertain", n_chunks=0) on any failure.
    """
    try:
        model = _load_model()
        if model is None:
            return _neutral()

        audio, sr = embed.load_audio(wav_path)
        if len(audio) == 0:
            logger.warning("detect_spoof(%s): empty audio; branch abstains", wav_path)
            return _neutral()

        chunks, spans = _windows(np.asarray(audio, dtype=np.float32), sr)
        if not chunks:
            return _neutral()

        p_synthetic, hidden = _infer(model, chunks)
        result = aggregate(p_synthetic, spans)

        if getattr(_config, "SPOOF_PHONE_CALIBRATION_ENABLED", True):
            ratio = _narrowband_ratio(audio, sr, wav_path)
            if ratio is not None and ratio < getattr(_config, "SPOOF_NARROWBAND_HF_RATIO_THRESHOLD", 1e-4):
                threshold = getattr(_config, "SPOOF_PHONE_THRESHOLD", 0.973)
                raw_median = result.score
                result = aggregate(calibrate_phone_scores(p_synthetic, threshold), spans)
                result = result.model_copy(update={
                    "calibration": "phone_channel", "raw_median": round(raw_median, 4),
                    "hf_ratio": round(ratio, 8),
                    "verdict": _phone_verdict(result.verdict, result.max_synth_run_s, result.score)})
                logger.info("detect_spoof(%s): phone channel; median %.3f -> %.3f (T=%.3f)",
                            wav_path, raw_median, result.score, threshold)

        if getattr(_config, "SPOOF_OOD_ENABLED", False):
            result = result.model_copy(update=_ood_update(audio, sr, hidden, wav_path))
        logger.info(
            "detect_spoof(%s): %d window(s), median=%.3f peak=%.3f verdict=%s",
            wav_path, len(chunks), result.score, result.peak, result.verdict,
        )
        return result
    except Exception as exc:  # noqa: BLE001
        logger.error("detect_spoof(%s): %s: %s", wav_path, type(exc).__name__, exc)
        return _neutral()


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")
    print("=" * 60)
    print("audio_ml.spoof smoke test")
    print("=" * 60)

    neutral = detect_spoof("/nonexistent/file.wav")
    assert isinstance(neutral, SpoofSignal) and neutral.verdict == "uncertain"
    print("  ok: missing file -> neutral")

    if not model_files_present():
        print(f"  skip: Model A not installed in {ANTISPOOF_DIR}")
        sys.exit(0)

    clips = Path(__file__).resolve().parent.parent / "data" / "eval_set" / "clips"
    for name in ("friend_test", "me", "cloned_scam", "friend_clone"):
        s = detect_spoof(str(clips / f"{name}.wav"))
        print(f"  {name:<14} median={s.score:.4f} peak={s.peak:.4f} "
              f"run={s.max_synth_run_s:.1f}s windows={s.n_chunks} verdict={s.verdict}")
    sys.exit(0)
