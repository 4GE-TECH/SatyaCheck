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
DEMO_CLIPS_DIR: Path = DATA_DIR / "demo_clips"
REPORTS_DIR: Path = DATA_DIR / "reports"
SCENARIO_MATRIX_PATH: Path = DATA_DIR / "scenario_matrix.json"

# Create directories if missing (idempotent)
for _d in [DATA_DIR, MODELS_DIR, ENROLLMENTS_DIR, COHORT_DIR, DEMO_CLIPS_DIR, REPORTS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

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

# Minimum enrollment quality
ENROLL_MIN_SPEECH_S: float = 30.0        # at least 30s of active speech for enrollment

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

# Cosine similarity thresholds (post s-normalisation)
ASV_MATCH_THRESHOLD: float = 1.20        # norm_score > this → MATCH
ASV_MISMATCH_THRESHOLD: float = -0.80   # norm_score < this → MISMATCH
# Between thresholds → UNKNOWN (neutral 0.5 risk)

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
USE_REAL_SPOOF: bool = os.getenv("USE_REAL_SPOOF", "true").lower() == "true"
USE_REAL_NLP: bool = os.getenv("USE_REAL_NLP", "false").lower() == "true"
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
