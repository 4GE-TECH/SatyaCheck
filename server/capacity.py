"""SatyaCheck — capacity: admission control, a model-inference limit, readiness.

  * Admission: at most MAX_LIVE_SESSIONS live sessions; the next one is told "busy"
    (close 1013, try again later) rather than slowing every call down.
  * Inference slots: at most INFERENCE_CONCURRENCY model calls at once across all
    sessions (speaker, anti-spoof, ASR, embeddings), so N calls share a GPU without
    oversubscribing it. On CPU the limit keeps the machine responsive.
  * Readiness: GET /api/ready is 503 until the models have been warmed (WARM_MODELS),
    so a load balancer never routes a call to a server still loading 7 GB of models.

C owns this file.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time

import config

log = logging.getLogger("satyacheck.capacity")


class Admission:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.active = 0

    def try_acquire(self) -> bool:
        with self._lock:
            limit = max_live_sessions()
            if self.active >= limit:
                log.warning(f"admission: refused a live session ({self.active}/{limit} running)")
                from server.observability import LIVE_REFUSED

                LIVE_REFUSED.inc()
                return False
            self.active += 1
            return True

    def release(self) -> None:
        with self._lock:
            self.active = max(0, self.active - 1)


admission = Admission()
_slots = threading.BoundedSemaphore(max(1, int(config.INFERENCE_CONCURRENCY)))


@contextlib.contextmanager
def inference_slot(name: str):
    """Hold one of the shared model-inference slots for the duration of a model call."""
    from server.observability import INFERENCE_SECONDS, INFERENCE_WAIT_SECONDS

    started = time.monotonic()
    _slots.acquire()
    waited = time.monotonic() - started
    INFERENCE_WAIT_SECONDS.labels(name).observe(waited)
    if waited > 1.0:
        log.info(f"capacity: {name} waited {waited:.1f}s for an inference slot")
    try:
        yield
    finally:
        INFERENCE_SECONDS.labels(name).observe(time.monotonic() - started - waited)
        _trim_gpu_cache()
        _slots.release()


#: Torch keeps freed GPU blocks cached. Measured: 4.1 GB reserved for 2.3 GB in use after
#: loading, and the gap grew with each concurrent voice (BGE-m3 on growing transcripts) until
#: an 8 GB card had no headroom. Past this much slack, the cache is handed back.
GPU_CACHE_SLACK_MB = 768


def _trim_gpu_cache(force: bool = False) -> None:
    try:
        import torch

        if not torch.cuda.is_available():
            return
        slack = (torch.cuda.memory_reserved() - torch.cuda.memory_allocated()) / 2**20
        if force or slack > GPU_CACHE_SLACK_MB:
            torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001 — memory housekeeping must never break a call
        pass


_ready = threading.Event()
_warm_error: list[str] = []


def max_live_sessions() -> int:
    """MAX_LIVE_SESSIONS when set, otherwise the measured limit for the device in use."""
    if config.MAX_LIVE_SESSIONS is not None:
        return int(config.MAX_LIVE_SESSIONS)
    return int(config.MAX_LIVE_SESSIONS_BY_DEVICE.get(config.torch_device(), 2))


def model_devices() -> dict:
    """Where every model actually loaded, from each branch's own report."""
    out: dict = {}
    for name, loader in (("audio_ml", "audio_ml.api"), ("nlp_rag", "nlp_rag.api")):
        try:
            import importlib

            out.update(importlib.import_module(loader).model_devices())
        except Exception as e:  # noqa: BLE001
            out[name] = {"device": None, "fallback": f"{type(e).__name__}: {e}"}
    return out


def _enabled_models() -> list[str]:
    names = []
    if config.USE_REAL_SPEAKER:
        names.append("ecapa")
    if config.USE_REAL_SPOOF:
        names.append("model_a")
    if config.USE_REAL_NLP:
        names += ["whisper", "bge_m3"]
    return names


def _vram() -> dict:
    """Peak torch allocation, plus the whole GPU's used memory (includes CTranslate2)."""
    out: dict = {"torch_peak_mb": None, "gpu_used_mb": None, "gpu_total_mb": None}
    try:
        import torch

        if torch.cuda.is_available():
            out["torch_peak_mb"] = round(torch.cuda.max_memory_allocated() / 2**20)
    except Exception:  # noqa: BLE001
        pass
    try:
        import subprocess

        line = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                              capture_output=True, text=True, timeout=3).stdout.strip().splitlines()[0]
        used, total = (int(x) for x in line.split(","))
        out["gpu_used_mb"], out["gpu_total_mb"] = used, total
    except Exception:  # noqa: BLE001 - no GPU or no nvidia-smi: report nothing, never fail
        pass
    return out


def readiness() -> dict:
    """Ready means warm-up succeeded, every enabled model loaded, and, when the GPU was
    required (SATYACHECK_DEVICE=cuda), every model is on it. A fallback under "auto" stays
    ready (CPU must work) but is reported, and the load gate refuses it."""
    devices = model_devices()
    enabled = _enabled_models()
    problems = []
    if config.WARM_MODELS:
        if not _ready.is_set():
            problems.append("warming up")
        if _warm_error:
            problems.append(f"warm-up failed: {_warm_error[0]}")
        for name in enabled:
            if _ready.is_set() and (devices.get(name) or {}).get("device") is None:
                problems.append(f"{name} did not load")
    if config.DEVICE_PREFERENCE == "cuda":
        for name in enabled:
            device = (devices.get(name) or {}).get("device")
            if device not in (None, "cuda"):
                problems.append(f"{name} is on {device}, cuda was required")
    fallbacks = {name: d["fallback"] for name, d in devices.items() if isinstance(d, dict) and d.get("fallback")}
    return {"ready": not problems, "problems": problems, "warm_models": config.WARM_MODELS,
            "warm_error": _warm_error[0] if _warm_error else None,
            "live_sessions": admission.active, "max_live_sessions": max_live_sessions(),
            "device": config.torch_device(), "models": devices, "fallbacks": fallbacks, "vram": _vram()}


def warm_models() -> None:
    """Load every model once on a short synthetic clip (run in a background thread)."""
    import tempfile
    import wave
    from pathlib import Path

    import numpy as np

    started = time.monotonic()
    try:
        from server import orchestrator

        # Real speech when the repo has it: a pure tone has no speech for the VAD, so the
        # speaker model would never load and readiness could not report where it runs.
        speech = config.REPO_ROOT / "data" / "eval_set" / "clips" / "friend_test.wav"
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "warm.wav"
            if speech.is_file():
                wav.write_bytes(speech.read_bytes())
            else:
                t = np.arange(16000 * 3) / 16000
                pcm = (0.2 * np.sin(2 * np.pi * 220 * t) * 32767).astype("<i2").tobytes()
                with wave.open(str(wav), "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(16000)
                    w.writeframes(pcm)
            if config.USE_REAL_SPEAKER:
                orchestrator._real_speaker_branch(str(wav), None)
            if config.USE_REAL_SPOOF:
                orchestrator._real_spoof_branch(str(wav))
            if config.USE_REAL_NLP:
                orchestrator._real_nlp_branch(str(wav), [])
                from nlp_rag.api import warm

                warm(str(wav))   # the branch may hit the pre-transcribed cache and skip Whisper
        _trim_gpu_cache(force=True)   # loading leaves ~1.8 GB of freed blocks cached
        log.info(f"capacity: models warm in {time.monotonic() - started:.1f}s on {model_devices()}")
    except Exception as e:  # noqa: BLE001 — recorded; readiness stays false and says why
        _warm_error.append(f"{type(e).__name__}: {e}")
        log.error(f"capacity: warm-up failed ({type(e).__name__}: {e}); /api/ready will say not ready")
    finally:
        _ready.set()


if __name__ == "__main__":
    print(readiness())
