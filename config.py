"""SatyaCheck — Configuration

All thresholds, weights, paths, and feature flags live here.
Nobody hardcodes magic numbers inside their module — import from config instead.

This file is owned by C (Backend / Integration).
"""

from __future__ import annotations

import os
from pathlib import Path

# =====================================================================
# Base Paths
# =====================================================================

REPO_ROOT: Path = Path(__file__).parent.resolve()

MODELS_DIR: Path = REPO_ROOT / "models"
DATA_DIR: Path = REPO_ROOT / "data"
DB_PATH: Path = DATA_DIR / "satyacheck.db"
CORPUS_DIR: Path = REPO_ROOT / "nlp_rag" / "corpus"
ENROLLMENTS_DIR: Path = DATA_DIR / "enrollments"
COHORT_DIR: Path = DATA_DIR / "cohort"
FLAGGED_DIR: Path = DATA_DIR / "flagged"
DEMO_CLIPS_DIR: Path = DATA_DIR / "demo_clips"
REPORTS_DIR: Path = DATA_DIR / "reports"
SCENARIO_MATRIX_PATH: Path = DATA_DIR / "scenario_matrix.json"

# Create directories if missing (idempotent)
for _d in [DATA_DIR, MODELS_DIR, ENROLLMENTS_DIR, COHORT_DIR, FLAGGED_DIR,
           DEMO_CLIPS_DIR, REPORTS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# =====================================================================
# Offline model resolution — CLAUDE.md rule 4, "the demo runs with wifi off"
# =====================================================================
#
# Every HuggingFace-backed library (speechbrain, sentence-transformers,
# transformers) and torch.hub resolve their caches from these two variables.
# `scripts/download_models.py` sets them before downloading; the *server* has to
# set them too, or it looks in ~/.cache/huggingface at request time and the demo
# dies the moment the wifi does.
#
# `config` is imported before any model library on every path into the app,
# which is the only reason setting them here works. setdefault, so an operator
# who exports their own cache location still wins.
os.environ.setdefault("HF_HOME", str(MODELS_DIR / "hf"))
os.environ.setdefault("TORCH_HOME", str(MODELS_DIR / "torch"))

# One silero checkout, named the way torch.hub names it under TORCH_HOME. Both
# `server/audio_ingest.py` and `audio_ml/embed.py` load VAD from here; they used to
# look in two different places, so populating one left the other silently falling
# back to fixed sliding windows.
SILERO_VAD_DIR: Path = MODELS_DIR / "torch" / "hub" / "snakers4_silero-vad_master"


# =====================================================================
# Server
# =====================================================================

HOST: str = os.getenv("SATYACHECK_HOST", "0.0.0.0")
PORT: int = int(os.getenv("SATYACHECK_PORT", "8000"))

# Allow D's Vite dev server and production origin
CORS_ORIGINS: list[str] = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]

MAX_UPLOAD_SIZE_MB: int = 50
MAX_UPLOAD_SIZE_BYTES: int = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# =====================================================================
# Audio Processing
# =====================================================================

TARGET_SAMPLE_RATE: int = 16_000          # Hz — normalise everything to this
FFMPEG_TIMEOUT_S: int = 30               # ffmpeg subprocess timeout

# VAD / streaming chunks
VAD_CHUNK_S: float = 3.0                  # chunk window in seconds
VAD_OVERLAP_S: float = 1.0               # overlap between consecutive chunks

# Minimum enrollment quality.
#
# 15s, not 30s. Every recorded clip tops out at 23.1s of VAD-detected speech
# (me.wav 23.1 · friend.wav 22.3 · me_test2.wav 19.1), so a 30s floor rejected all
# of them and *nobody could enrol through the UI at all* — the identity branch had
# nothing to compare against no matter how correct the rest of the pipeline was.
#
# 15s is a floor, not a target: more enrollment audio, from more sessions, is what
# shrinks the cross-session cosine drop discussed at SPEAKER_MATCH_THRESHOLD below.
# Raise this back toward 30 once longer recordings exist, and re-measure.
ENROLL_MIN_SPEECH_S: float = 15.0        # minimum active speech to accept an enrollment

# =====================================================================
# Quality Gate Thresholds
# =====================================================================

MIN_SPEECH_DURATION_S: float = 1.5       # FR-3: refuse to score below this
MIN_SNR_DB: float = 5.0                  # FR-3: refuse to score below this

# =====================================================================
# Speaker Verification (audio_ml)
# =====================================================================

# S-normalisation cohort
COHORT_SIZE_TARGET: int = 50             # 50-speaker background cohort

# --- Thresholds consumed by C's fusion (server/orchestrator.py) ---------------
# These are on a raw z-score scale, which is why one of them is negative.
ASV_MATCH_THRESHOLD: float = 1.20        # norm_score > this → MATCH
ASV_MISMATCH_THRESHOLD: float = -0.80   # norm_score < this → MISMATCH
# Between thresholds → UNKNOWN (neutral 0.5 risk)

# --- Thresholds consumed by A's verifier (audio_ml/verify.py) -----------------
# DIFFERENT SCALE, deliberately not unified. These are **raw cosine** cut points,
# which is what A calibrated against and what measurement confirms discriminates.
#
# Measured on the eval clips with the real ECAPA checkpoint (2026-08-22):
#
#   probe          vs enrolled   raw cosine   s-norm z    truth
#   friend         friend           1.0000      —          self-match
#   friend_test    friend           0.9464      16.9       genuine, 2nd session
#   me             me               0.9691      —          self-match
#   me_test2       me               0.7857      10.2       genuine, 2nd session
#   cloned_scam    friend           0.7631      12.4       CLONE
#   me             friend           0.3730       5.2       impostor
#
# The first two rows reproduce A's own measurements (0.9464 genuine / 0.7631 clone)
# to four decimals, which is the check that these conditions match theirs.
#
# Two conclusions, both measured rather than assumed.
#
# 1. Raw cosine separates the clone; **the s-norm z-score does not.** The clone's z
#    (12.4) lands inside the genuine band [10.2, 16.9], so no z threshold can accept
#    a genuine second session and reject the clone. That is why `verify.py` decides
#    the verdict on raw cosine — see the longer note there.
#
# 2. MATCH stays at A's 0.85 even though it false-mismatches `me_test2` (0.7857).
#    That is a real cost — CLAUDE.md names false accusation inside a family as a
#    harm — but lowering the cut to admit it is worse. me_test2 sits 0.0226 above a
#    known clone, so a threshold that accepts it is not discriminating, it is
#    guessing. Compare the two enrolled speakers' cross-session drop:
#
#      friend → friend_test   1.0000 → 0.9464   drop 0.0536
#      me     → me_test2      0.9691 → 0.7857   drop 0.1834   ← 3.4x worse
#
#    So this is an enrollment/recording problem, not a threshold problem. The fix is
#    the condition-matched, multi-sample enrollment CLAUDE.md already mandates: `me`
#    was enrolled from a single clip, and `ENROLL_MIN_SPEECH_S` is a floor, not a
#    target. Enroll from several sessions and the drop shrinks.
#
# CAVEAT: two enrolled speakers and one clone. Re-measure once A's ten recorded
# scripts land (nlp_rag/NEEDS_FROM_A.md item 2) and treat this as an operating
# point, not a constant of nature.
SPEAKER_MATCH_THRESHOLD: float = 0.85    # raw cosine ≥ this → match
SPEAKER_UNKNOWN_FLOOR: float = 0.60      # ≥ this → mismatch; below → unknown

# s-normalisation shaping. `snorm` z-scores land in roughly [3, 18] against a
# 40-speaker cohort, and sigmoid saturates to 0.9933 above z=5 — which made every
# probe, clone included, report an identical norm_score. Dividing by a temperature
# keeps the reported score monotone and readable across that range.
SNORM_TEMPERATURE: float = 4.0
SNORM_Z_CLAMP: float = 12.0

# Replay detection — live speech scores 0.65–0.80; above 0.95 is a recording
REPLAY_COSINE_THRESHOLD: float = 0.95

# =====================================================================
# Anti-Spoof (audio_ml)
# =====================================================================

# Synthetic probability thresholds per chunk (0=bonafide, 1=spoof)
CM_SYNTHETIC_THRESHOLD: float = 0.40    # per-chunk threshold to flag as synthetic
CM_RISK_THRESHOLD: float = 0.50         # aggregate risk threshold for HIGH_RISK trigger

# Intent gating — synthetic voice is a multiplier, not a source
CM_FLOOR: float = 0.25                  # r_cm_eff = r_cm * (CM_FLOOR + (1 - CM_FLOOR) * intent)

# =====================================================================
# Fusion Weights (both operating modes)
# =====================================================================

# identity_check: caller matches/mismatches an enrolled person
WEIGHTS_IDENTITY_CHECK: dict[str, float] = {
    "asv": 0.40,
    "cm": 0.35,
    "text": 0.25,
}

# authority_check: no enrolled person close — speaker branch largely abstains
WEIGHTS_AUTHORITY_CHECK: dict[str, float] = {
    "asv": 0.10,
    "cm": 0.45,
    "text": 0.45,
}

# =====================================================================
# Trust Band Boundaries
# Map combined risk score (0.0–1.0) to TrustBand
# =====================================================================
# Note: authority_check mode overrides VERIFIED → UNVERIFIED regardless of score

BAND_THRESHOLDS: dict[str, tuple[float, float]] = {
    # band_name: (min_risk_inclusive, max_risk_exclusive)
    "verified":    (0.00, 0.15),
    "caution":     (0.15, 0.40),
    "suspicious":  (0.40, 0.65),
    "high_risk":   (0.65, 1.01),
}

def risk_to_trust_score(risk: float) -> float:
    """Convert fused risk (0–1) to trust score (0–100)."""
    return round((1.0 - max(0.0, min(1.0, risk))) * 100, 1)

def risk_to_band(risk: float, is_authority_check: bool = False) -> str:
    """Convert fused risk to trust band string.
    
    CRITICAL: authority_check mode suppresses 'verified' — returns 'unverified' instead.
    """
    from contracts import TrustBand  # local import to avoid circular
    for band, (lo, hi) in BAND_THRESHOLDS.items():
        if lo <= risk < hi:
            if band == "verified" and is_authority_check:
                return TrustBand.UNVERIFIED
            return TrustBand(band)
    return TrustBand.HIGH_RISK

# =====================================================================
# NLP / RAG (nlp_rag)
# =====================================================================

WHISPER_MODEL_SIZE: str = "small"        # Use 'small' + int8 — medium is too slow on CPU
WHISPER_COMPUTE_TYPE: str = "int8"
WHISPER_LANGUAGE: str = "hi"            # Primary language; Whisper auto-detects Hinglish

BGE_MODEL_NAME: str = "BAAI/bge-m3"
FAISS_INDEX_PATH: Path = DATA_DIR / "faiss_index.bin"
FAISS_DOCSTORE_PATH: Path = DATA_DIR / "faiss_docstore.pkl"

RAG_TOP_K: int = 3                       # Top-k retrieval matches
RAG_SIMILARITY_THRESHOLD: float = 0.60  # Minimum cosine similarity to include a playbook

# =====================================================================
# Feature Flags
# =====================================================================

# LLM rewrite of reason code text — default OFF (latency variance kills demos)
ENABLE_LLM_REWRITE: bool = os.getenv("ENABLE_LLM_REWRITE", "false").lower() == "true"

# WebSocket streaming
ENABLE_WEBSOCKET: bool = True

# Guardian alerts pub/sub
ENABLE_GUARDIAN_ALERTS: bool = True

# Negative voiceprint list (FR-15)
ENABLE_FLAGGED_VOICE_LIST: bool = True

# PDF report generation (FR-14)
ENABLE_PDF_REPORTS: bool = True

# Use real module implementations vs mocked stubs
# Flipped to True one branch at a time during Block 2 integration
USE_REAL_SPEAKER: bool = os.getenv("USE_REAL_SPEAKER", "true").lower() == "true"

# Anti-spoof is CUT — PLAN.md's H6:00 contingency, exercised.
# `audio_ml/spoof.py` has no model: it returns a hardcoded
# SpoofSignal(score=0.5, verdict="uncertain") with the real implementation
# commented out beneath. Turning this on does not add a third signal, it feeds a
# constant into fusion and calls it authenticity. Off, the branch abstains and
# fusion renormalises over the two signals that are real.
# Set USE_REAL_SPOOF=true only once a checkpoint is actually wired.
USE_REAL_SPOOF: bool = os.getenv("USE_REAL_SPOOF", "false").lower() == "true"

USE_REAL_NLP: bool = os.getenv("USE_REAL_NLP", "true").lower() == "true"

# C's `_compute_fusion` is the real fusion, not A's `audio_ml.api.fuse`.
# Deliberate and permanent for this build: C's implements the documented
# intent-gated, mode-aware formula with weight renormalisation, and is the one
# B's calibration was measured against. See nlp_rag/NEEDS_FROM_A.md item 8.
USE_REAL_FUSION: bool = os.getenv("USE_REAL_FUSION", "false").lower() == "true"

# =====================================================================
# Logging
# =====================================================================

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


if __name__ == "__main__":
    print("=== SatyaCheck Config ===")
    print(f"REPO_ROOT       : {REPO_ROOT}")
    print(f"MODELS_DIR      : {MODELS_DIR}")
    print(f"DB_PATH         : {DB_PATH}")
    print(f"MIN_SPEECH_S    : {MIN_SPEECH_DURATION_S}")
    print(f"MIN_SNR_DB      : {MIN_SNR_DB}")
    print(f"ASV_MATCH_THOLD : {ASV_MATCH_THRESHOLD}")
    print(f"CM_FLOOR        : {CM_FLOOR}")
    print(f"WEIGHTS_IC      : {WEIGHTS_IDENTITY_CHECK}")
    print(f"WEIGHTS_AC      : {WEIGHTS_AUTHORITY_CHECK}")
    print(f"ENABLE_LLM      : {ENABLE_LLM_REWRITE}")
    print(f"USE_REAL_SPEAKER: {USE_REAL_SPEAKER}")
    print(f"USE_REAL_SPOOF  : {USE_REAL_SPOOF}")
    print(f"USE_REAL_NLP    : {USE_REAL_NLP}")
    print(f"USE_REAL_FUSION : {USE_REAL_FUSION}")
