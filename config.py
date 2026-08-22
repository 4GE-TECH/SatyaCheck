"""
config.py — shared constants.

Owner: Member C. Member A updates the threshold values after calibration at
H8:30 and tells C. Everyone else reads, nobody else writes.

After ANY change here, run:
    python -m audio_ml.eval.test_scenarios
It must exit 0. This is the only thing standing between a threshold tweak and
silently breaking the legitimate-IVR case.
"""

import os

# ------------------------------------------------------------------ paths --
MODELS_DIR = os.path.abspath("models")
DATA_DIR = os.path.abspath("data")
ENROLL_DIR = os.path.join(DATA_DIR, "enrollments")
COHORT_DIR = os.path.join(DATA_DIR, "cohort")
FLAGGED_DIR = os.path.join(DATA_DIR, "flagged")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "satyacheck.db")

# ------------------------------------------------------------------ audio --
SAMPLE_RATE = 16000
CHUNK_S = 3.0
CHUNK_OVERLAP_S = 1.0

# Quality gate. Below either of these we return band="insufficient" and DO NOT
# score. Confidently scoring 0.4 seconds of noise destroys trust in every other
# verdict we produce.
MIN_SPEECH_S = 1.5
MIN_SNR_DB = 5.0

# --------------------------------------------------------------- speaker ---
# CALIBRATE THESE at H8:30 on your own recorded clips. The defaults are guesses.
SPEAKER_MATCH_THRESHOLD = 0.85     # >= this  -> "match"
SPEAKER_UNKNOWN_FLOOR = 0.60       # >= this  -> "mismatch"; below -> "unknown"
REPLAY_COSINE = 0.95               # an anomalously perfect match is a replay

# ----------------------------------------------------------------- spoof ---
SPOOF_SYNTHETIC_THRESHOLD = 0.65
SPOOF_BONAFIDE_THRESHOLD = 0.35
MIN_SYNTH_RUN_S = 3.0              # shorter synthetic stretches are noise

# ----------------------------------------------------------------- bands ---
BAND_GREEN = 70
BAND_AMBER = 40

# ---------------------------------------------------------------- fusion ---
# Speaker branch ABSTAINS when nobody enrolled is close; weight shifts to the
# two branches that actually carry information about this call.
W_IDENTITY = {"asv": 0.40, "cm": 0.35, "text": 0.25}
W_AUTHORITY = {"asv": 0.10, "cm": 0.45, "text": 0.45}

TAU = 0.12          # sigmoid steepness around the speaker threshold
CM_FLOOR = 0.25     # weight of synthetic-voice evidence at ZERO intent.
                    # Raise it and a legitimate bank IVR goes amber.
                    # Lower it and hybrid human/AI attacks weaken.
PARTIAL_BLEND = 0.5 # how much of `peak` counts for partial_synthetic calls

# ------------------------------------------------------------------ flags --
ENABLE_LLM_REWRITE = False   # keep OFF for the demo — latency variance kills it
