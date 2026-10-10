"""
audio_ml/api.py — Public import surface for the server.

Thin re-export only. No logic, no wrappers, no error handling.
"""

from audio_ml.enroll import (compute_voiceprint, delete_person, enroll_person, legacy_candidates,
                             list_persons)
from audio_ml.verify import verify_speaker, add_flagged_voice
from audio_ml.spoof import detect_spoof
from audio_ml.fusion import fuse
from audio_ml.fusion_core import authenticity_base, fuse_risk
from audio_ml.codec import degrade
from audio_ml.devices import model_devices

__all__ = ["compute_voiceprint", "enroll_person", "legacy_candidates", "list_persons", "delete_person",
           "verify_speaker", "add_flagged_voice", "detect_spoof", "fuse", "fuse_risk",
           "authenticity_base", "degrade", "model_devices"]

