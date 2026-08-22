"""
audio_ml/api.py — Public import surface for the server.

Thin re-export only. No logic, no wrappers, no error handling.
"""

from audio_ml.enroll import enroll_person, list_persons
from audio_ml.verify import verify_speaker, add_flagged_voice
from audio_ml.spoof import detect_spoof
from audio_ml.fusion import fuse

__all__ = ["enroll_person", "list_persons", "verify_speaker",
           "add_flagged_voice", "detect_spoof", "fuse"]
