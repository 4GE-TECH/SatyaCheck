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

        import torch

        with torch.no_grad():
            batch = torch.from_numpy(np.stack(chunks)).float()
            _, logits = model(batch, Freq_aug=False)
            p_synthetic = torch.softmax(logits, dim=1)[:, 0].cpu().numpy().tolist()

        result = aggregate(p_synthetic, spans)
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
