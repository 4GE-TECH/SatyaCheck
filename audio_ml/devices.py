"""Where the audio models actually run (GPU plan, Phase 0).

Readiness and the load gate read this rather than "is a GPU present", because a model can
fall back to CPU (or never load) on a machine that has one.

    python -m audio_ml.devices     # smoke test
"""

from __future__ import annotations


def model_devices() -> dict:
    """Where each audio model loaded ("cuda" | "cpu" | None if not loaded yet), and any
    fallback away from the requested device. Never raises."""
    try:
        from audio_ml import embed, spoof

        return {
            "ecapa": {"device": embed.ECAPA_DEVICE, "fallback": embed.ECAPA_FALLBACK},
            "model_a": {"device": spoof.MODEL_DEVICE, "fallback": spoof.MODEL_FALLBACK},
        }
    except Exception as exc:  # noqa: BLE001 - rule 5
        return {"error": f"{type(exc).__name__}: {exc}"}


if __name__ == "__main__":
    print(model_devices())
