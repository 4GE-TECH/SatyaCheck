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


def read_dotenv(path: Path) -> dict[str, str]:
    """KEY=VALUE lines of a .env file ('#' comments, optional quotes). {} if absent."""
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


# Secrets (database URLs, tokens) live in the git-ignored .env or the real environment,
# which wins. Never under pytest: a test run must not reach a real database because a
# developer's .env happens to point at one. Tests that want Postgres read it explicitly.
if "pytest" not in __import__("sys").modules:
    for _k, _v in read_dotenv(REPO_ROOT / ".env").items():
        os.environ.setdefault(_k, _v)

# SATYACHECK_MODELS_DIR: weights somewhere else (a mounted volume, or an empty dir to test a
# machine without models, as CI is).
MODELS_DIR: Path = Path(os.getenv("SATYACHECK_MODELS_DIR", str(REPO_ROOT / "models")))
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
# Extra origins for a dashboard served from another host that calls the API directly
# (not through Vite's dev proxy), comma separated: SATYACHECK_CORS_ORIGINS=https://a,https://b
CORS_ORIGINS += [o.strip() for o in os.getenv("SATYACHECK_CORS_ORIGINS", "").split(",") if o.strip()]

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

# Live WebSocket streaming (server/ws_router.py): the app sends small chunks
# (3s, no overlap — the backend buffers) so the overlay can update responsively, but
# Whisper hallucinates fluent, wrong sentences on isolated 3s slices mid-sentence —
# see satyacheck_mobile's CallAudioService.kt comment on the same measurement, made
# against this same ASR. Every chunk is instead scored against the trailing window
# of buffered audio, long enough to be Whisper-safe.
STREAM_CONTEXT_S: float = 9.0             # trailing window used to score each chunk
STREAM_HOP_S: float = 2.0                 # server/pipeline/buffer.py: a window every hop (FR-13 "~2s")
# Coverage (upgrade plan, Phase 3). Behind real time the runner scores the newest window
# first; older windows wait in a queue (at most COVERAGE_CATCHUP_MAX_S of hops) and are
# caught up oldest-first, COVERAGE_CATCHUP_PER_PUSH per scoring step. A window that falls
# off the queue, or is still queued when the call ends, becomes an explicit unscored gap.
COVERAGE_CATCHUP_MAX_S: float = float(os.getenv("COVERAGE_CATCHUP_MAX_S", "20"))
COVERAGE_CATCHUP_PER_PUSH: int = int(os.getenv("COVERAGE_CATCHUP_PER_PUSH", "1"))
# Where the torch models run (ECAPA, Model A, BGE-m3). "auto" uses the GPU when torch can see
# one and falls back to CPU otherwise; CPU must always work (CLAUDE.md rule 6). Whisper has its
# own WHISPER_DEVICE (below) because CTranslate2 finds the GPU separately from torch.
DEVICE_PREFERENCE: str = os.getenv("SATYACHECK_DEVICE", "auto").lower()   # auto | cuda | cpu
_resolved_device: list[str] = []


def torch_device() -> str:
    """"cuda" or "cpu" for the torch models. Imports torch only when first called."""
    if not _resolved_device:
        device = "cpu"
        if DEVICE_PREFERENCE in ("auto", "cuda"):
            try:
                import torch

                if torch.cuda.is_available():
                    device = "cuda"
            except Exception:  # noqa: BLE001 - no torch, no GPU: CPU
                pass
        _resolved_device.append(device)
    return _resolved_device[0]


# Capacity (server/capacity.py). Live sessions beyond MAX_LIVE_SESSIONS are told "busy";
# at most INFERENCE_CONCURRENCY model calls run at once across all sessions.
# Unset means "by device": measured per device (scripts/measure_live_v2.py), see
# MAX_LIVE_SESSIONS_BY_DEVICE. Set it to override.
MAX_LIVE_SESSIONS: int | None = int(os.environ["MAX_LIVE_SESSIONS"]) if os.getenv("MAX_LIVE_SESSIONS") else None
# Measured (data/measurements/live_v2_latency.json, RTX 4070 Laptop 8 GB): 4 voices keep
# update p95 at 2.5 s with no coverage gaps and 3.3 GB of GPU memory; 8 voices reach 5.6 s.
# CPU: 1 voice 3.9 s p95; 4 voices 16.7 s with gaps.
MAX_LIVE_SESSIONS_BY_DEVICE: dict[str, int] = {"cpu": 2, "cuda": 4}
INFERENCE_CONCURRENCY: int = int(os.getenv("INFERENCE_CONCURRENCY", "2"))
WARM_MODELS: bool = os.getenv("WARM_MODELS", "false").lower() == "true"   # load models at startup
# Live ASR: the bounded committing transcriber (true) or the whole-call re-decoder (false).
STREAM_COMMITTING_ASR: bool = os.getenv("STREAM_COMMITTING_ASR", "true").lower() == "true"
STREAM_MAX_SESSION_S: float = 1800.0      # stop scoring after 30 min of audio, loudly

# Escalation persistence (server/escalation.py, item 9). A warning band is shown only
# after this many consecutive windows reach it; once shown it latches for the session.
# 1 = escalate on a single window, the behaviour the demo was measured with. Raise it
# only after measuring false positives on genuine calls (item 14): each step delays the
# first alert by one hop (~2 s at the app's chunk rate).
ESCALATION_PERSISTENCE_N: int = int(os.getenv("ESCALATION_PERSISTENCE_N", "1"))
# Session runner: whether a confirmed warning latches for the rest of the call (and the
# trust score only falls). Off: the session follows the current persistence run, so it
# recovers when later evidence contradicts an early warning, and the final verdict is
# the whole call's own fusion (full transcript, session authenticity), not a floor.
SESSION_LATCH_WARNINGS: bool = os.getenv("SESSION_LATCH_WARNINGS", "false").lower() == "true"

# Audio at rest (item 15). Voice is biometric data under the DPDP Act 2023; the default
# end state is that no call audio outlives the request that scored it.
#
# RETAIN_SESSION_AUDIO: copy every streamed chunk to data/sessions/<id>/. This is what
# scripts/enrol_from_call.py enrols from — the only way to enrol over the same acoustic
# chain a call arrives on (see DEMO_RUNBOOK, "speaker always unknown").
# CLEANUP_TEMP_AUDIO: delete the normalised temp WAV every ingest_audio writes, once the
# branches have read it. Off, those accumulate in the OS temp directory indefinitely.
#
# Defaults keep no audio (item 15b): retention off, cleanup on. The demo machine sets
# RETAIN_SESSION_AUDIO=true (DEMO_RUNBOOK.md) so enrol_from_call has chunks to read.
RETAIN_SESSION_AUDIO: bool = os.getenv("RETAIN_SESSION_AUDIO", "false").lower() == "true"
CLEANUP_TEMP_AUDIO: bool = os.getenv("CLEANUP_TEMP_AUDIO", "true").lower() == "true"

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

# Enrollment consent (item 16). A voiceprint is biometric personal data under the DPDP Act
# 2023. When required, /api/enroll refuses -- before touching the audio -- unless the form
# carries consent=true. Off until the app and web send it; then flip.
REQUIRE_ENROLL_CONSENT: bool = os.getenv("REQUIRE_ENROLL_CONSENT", "false").lower() == "true"
CONSENT_TEXT_VERSION: str = "2026-10-v1"     # bump whenever the consent wording changes

# Deployment environment. "production" turns off every dev-only fallback below.
SATYACHECK_ENV: str = os.getenv("SATYACHECK_ENV", "dev").lower()

# =====================================================================
# Accounts, authentication and the database (upgrade plan, Phase 1)
# =====================================================================

# Where the data lives. SQLite for dev and tests; Postgres (Supabase, pgvector, row-level
# security) when DATABASE_URL says so. The app connects as `satyacheck_app`, a role RLS
# cannot bypass; DATABASE_ADMIN_URL (the project owner) runs migrations and the retention
# sweep only. Secrets come from the environment or the git-ignored .env, never the repo.
DATABASE_URL: str = os.getenv("DATABASE_URL", "")            # "" -> sqlite at DB_PATH
DATABASE_ADMIN_URL: str = os.getenv("DATABASE_ADMIN_URL", "")
DB_SCHEMA: str = os.getenv("SATYACHECK_DB_SCHEMA", "public")  # tests use a throwaway schema
DB_APP_ROLE: str = os.getenv("DB_APP_ROLE", "satyacheck_app")  # the role RLS policies apply to
DB_APP_PASSWORD: str = os.getenv("SATYACHECK_APP_DB_PASSWORD", "")  # set when migrating: creates/updates the role

# "jwt": every request carries a Supabase access token. "dev": a request without one acts
# as DEV_OWNER_ID, so the apps work before they have a sign-in screen (Phase 5). Dev mode
# is refused outright in production.
AUTH_MODE: str = os.getenv("AUTH_MODE", "dev").lower()
if SATYACHECK_ENV == "production":
    AUTH_MODE = "jwt"
DEV_OWNER_ID: str = os.getenv("DEV_OWNER_ID", "dev-owner")
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "").rstrip("/")
AUTH_ISSUER: str = os.getenv("AUTH_ISSUER", f"{SUPABASE_URL}/auth/v1" if SUPABASE_URL else "")
AUTH_JWKS_URL: str = os.getenv("AUTH_JWKS_URL",
                               f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json" if SUPABASE_URL else "")
AUTH_AUDIENCE: str = os.getenv("AUTH_AUDIENCE", "authenticated")
AUTH_ALGORITHMS: list[str] = ["RS256", "ES256"]
# A WebSocket authenticates with its first message ({"type": "auth", "token": ...}),
# never in the URL, which ends up in proxy and server logs.
WS_AUTH_TIMEOUT_S: float = float(os.getenv("WS_AUTH_TIMEOUT_S", "10"))
# Who owns calls that arrive from Exotel (no user token on a telephony stream).
EXOTEL_OWNER_ID: str = os.getenv("EXOTEL_OWNER_ID", "")

# The local copy of call audio (data/sessions/) is a dev-only debugging aid.
if SATYACHECK_ENV == "production":
    RETAIN_SESSION_AUDIO = False

# Retention (days). Raw and session audio, then derived results (screenings, transcripts,
# reports). Voiceprints stay until their person or account is deleted. The sweep is
# server/retention.py: run `python -m server.retention` daily (needs DATABASE_ADMIN_URL on
# Postgres).
RETENTION_AUDIO_DAYS: int = int(os.getenv("RETENTION_AUDIO_DAYS", "30"))
RETENTION_RESULTS_DAYS: int = int(os.getenv("RETENTION_RESULTS_DAYS", "90"))

# The embedding model a stored voiceprint came from. Vectors from different models are not
# comparable, so verification only reads rows whose model_version matches this. Change it
# whenever models/ecapa/ is replaced, then re-enroll.
SPEAKER_MODEL_VERSION: str = "speechbrain/spkrec-ecapa-voxceleb"

# The database is the one store of voiceprints (upgrade plan, Phase 0). The legacy
# data/enrollments/*.npz people were deleted on 2026-10-10, so this is off by default. A
# checkout that still has such files can opt in (dev only) until it runs
# scripts/import_npz_voiceprints.py. Never in production.
LEGACY_NPZ_FALLBACK: bool = (
    os.getenv("LEGACY_NPZ_FALLBACK", "false").lower() == "true" and SATYACHECK_ENV != "production"
)

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

# Claim checks (upgrade plan, Phase 2; server/claims.py). Per channel:
#   cosine >= match         match         (no measured clone or stranger reaches it)
#   low <= cosine < match   inconclusive  (no accusation: suggest the challenge question)
#   cosine < low            mismatch, only when a user pick or a spoken claim backs it
# Measured by scripts/calibrate_claims.py (data/measurements/claim_calibration.json,
# 2026-10-10): genuine 0.791-0.946 wideband, 0.798-0.933 on G.711/AMR-NB; clones
# 0.762-0.837; strangers up to 0.820. Wideband `match` stays at SPEAKER_MATCH_THRESHOLD
# (the data would allow 0.819, but two speakers cannot justify loosening it). Small set,
# no speakerphone: re-measure with real calls. On a phone line clones land in the grey
# zone, not below `low` — voice alone cannot call them out there.
CLAIM_THRESHOLDS: dict[str, dict[str, float]] = {
    "wideband": {"match": 0.85, "low": 0.771},
    "narrowband": {"match": 0.857, "low": 0.778},
}
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
# 0.12, not 0.25 (2026-10-10). At 0.25 a legitimate synthetic IVR (median 0.92, script 0.05)
# fused to risk 0.19 = caution (amber), exactly the false alarm this gate exists to prevent;
# the old scenario gate hid it by running on fallback thresholds. 0.12 puts it at 0.14
# (unverified) with every scenario and production check passing. Thin margin: 0.15 is
# not enough. Re-measure on real IVR recordings.
CM_FLOOR: float = 0.12                  # r_cm_eff = r_cm * (CM_FLOOR + (1 - CM_FLOOR) * intent)

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

# Fusion floors and input rules (audio_ml/fusion_core.py, the one fusion implementation).
# Floors only ever raise the weighted risk.
#
# Intent sufficiency: a low anti-spoof score is not evidence of safety — a human scammer
# is genuinely human. Unless the caller is a verified enrolled person, risk is at least
# the script risk; a verified caller dampens it to this fraction (an odd request from real
# family lands caution, "verify before paying", never red).
FUSION_MATCHED_TEXT_FLOOR: float = 0.55
FUSION_FLAGGED_RISK_FLOOR: float = 0.85  # a hit on the reported-scammer voice list is near-decisive
# An anomalously perfect match is a recording: never verified, but on its own only caution
# (amber, "verify before acting"). 0.55 here was audio_ml's old value, which was amber on
# its fallback scale and is SUSPICIOUS (red) on production's bands.
FUSION_REPLAY_RISK_FLOOR: float = 0.35
FUSION_PARTIAL_BLEND: float = 0.5        # share of (peak - median) added back for partial_synthetic
# Identity risk from the verifier's verdict. Not interpolated from a score: the verifier
# already applied its thresholds, and re-deriving would count that decision twice.
FUSION_IDENTITY_RISK: dict[str, float] = {"match": 0.15, "unknown": 0.5, "mismatch": 0.85}

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
WHISPER_COMPUTE_TYPE: str = "int8"       # CPU fallback compute type
WHISPER_LANGUAGE: str = "hi"            # Primary language; Whisper auto-detects Hinglish

# GPU decoding — measured on the demo laptop's RTX 4070: a 9s window took 5 to 15s on
# CPU int8, which cannot keep pace with a live call. CUDA float16 is the target; "auto"
# tries it first and falls back to CPU int8 on any load failure (missing driver, no
# GPU, missing cuBLAS/cuDNN DLLs), so the demo still works on a CPU-only machine.
WHISPER_DEVICE: str = os.getenv("WHISPER_DEVICE", "auto")     # "auto" | "cuda" | "cpu"
WHISPER_GPU_COMPUTE_TYPE: str = "float16"

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

# LLM intent, SHADOW ONLY (upgrade plan, Phase 4; nlp_rag/llm_intent.py, server/llm_shadow.py).
# Logged beside the deterministic score, zero influence. It runs only with all three set:
# the provider, a recorded caller-facing processing disclosure, and the provider
# data-retention configuration that was approved (free text: what, who, when).
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "off").lower()            # "off" | "anthropic"
LLM_DISCLOSURE_RECORDED: bool = os.getenv("LLM_DISCLOSURE_RECORDED", "false").lower() == "true"
LLM_RETENTION_RECORD: str = os.getenv("LLM_RETENTION_RECORD", "")
LLM_INTENT_MODEL: str = os.getenv("LLM_INTENT_MODEL", "claude-haiku-5-5")
LLM_TIMEOUT_S: float = float(os.getenv("LLM_TIMEOUT_S", "8"))

# WebSocket streaming
ENABLE_WEBSOCKET: bool = True

# Guardian alerts pub/sub
ENABLE_GUARDIAN_ALERTS: bool = True

# Negative voiceprint list (FR-15)
ENABLE_FLAGGED_VOICE_LIST: bool = True

# Verdict dispatch (item 6, server/pipeline/dispatcher.py). Each sink runs isolated,
# under its own timeout, so one slow output never delays the overlay.
DISPATCH_SINKS: list[str] = ["app_overlay", "guardian", "report", "live_feed"]  # + "bank_api" (stub)

# Live verdict feed (/api/ws/live, docs/LIVE_FEED.md). Messages carry call transcripts:
# whenever the server is reachable through a public tunnel, set a token and give it only
# to the dashboard/app (they connect with ?token=...). Empty = no token required.
LIVE_FEED_TOKEN: str = os.getenv("LIVE_FEED_TOKEN", "")

# Prometheus scrape endpoint (/metrics, upgrade plan Phase 6): aggregate counts and timings
# only, never an account, transcript or score of one call. When set, a scrape must send
# "Authorization: Bearer <token>". Production refuses to serve it without one.
METRICS_TOKEN: str = os.getenv("METRICS_TOKEN", "")
DISPATCH_SINK_TIMEOUT_S: float = 2.0

# Streaming runner (item 5, server/pipeline/runner.py). On: the WebSocket feeds frames
# to SessionRunner — a verdict every STREAM_HOP_S of audio, speaker + anti-spoof scored
# per window, ASR out of band, outputs through the dispatcher. Off: the per-chunk
# screen_audio loop in server/ws_router.py, unchanged. Read per connection.
USE_PIPELINE_RUNNER: bool = os.getenv("USE_PIPELINE_RUNNER", "false").lower() == "true"

# Streaming windows shorter than one anti-spoof input (64,600 samples, fixed by AASIST —
# audio_ml/spoof.py WINDOW_SAMPLES) are scored with the anti-spoof branch abstaining
# (server/orchestrator.py screen_window). The buffer's first windows are 2 and 4 s, and
# with no transcript yet nothing gates the CM score. Measured on friend_test.wav, a
# genuine call: P(synthetic) 0.998 on the 2 s window, 0.874 on 4 s, 0.38-0.61 on full
# windows — the 2 s window latched the call suspicious. 0 disables.
STREAM_SPOOF_MIN_WINDOW_S: float = 64600 / TARGET_SAMPLE_RATE

# --- Exotel Stream applet (item 1, acquisition/exotel) ---------------------------------
# Documented: Exotel connects to us as a WebSocket client and sends JSON text frames
# (developer.exotel.com/docs/agentstream/websocket-protocol); 8000 Hz is the default rate,
# 16000/24000 selectable with '?sample-rate=' on the URL. NOT confirmed for the Stream
# applet specifically: Basic auth in the URL (documented for Voicebot), the encoding (base
# docs say raw s16le, the extension guide says mu-law — both are decoded), which call leg
# is streamed, and behaviour when our socket drops. Off by default; the offline demo never
# needs it (it requires a public wss:// endpoint).
ENABLE_EXOTEL: bool = os.getenv("ENABLE_EXOTEL", "false").lower() == "true"
EXOTEL_WS_PATH: str = os.getenv("EXOTEL_WS_PATH", "/api/exotel/stream")
EXOTEL_DEFAULT_SAMPLE_RATE: int = int(os.getenv("EXOTEL_DEFAULT_SAMPLE_RATE", "8000"))
EXOTEL_TRACK: str = os.getenv("EXOTEL_TRACK", "inbound")      # 'inbound' | 'outbound' | 'any'
EXOTEL_BASIC_USER: str = os.getenv("EXOTEL_BASIC_USER", "")   # secrets: environment only
EXOTEL_BASIC_PASS: str = os.getenv("EXOTEL_BASIC_PASS", "")
EXOTEL_ALLOWED_IPS: list[str] = [x.strip() for x in os.getenv("EXOTEL_ALLOWED_IPS", "").split(",") if x.strip()]
EXOTEL_ALLOW_UNAUTHENTICATED: bool = os.getenv("EXOTEL_ALLOW_UNAUTHENTICATED", "false").lower() == "true"

# App-to-app calls over WebRTC (LiveKit; webrtc/README.md). Two signed-in people call each
# other through the app; a hidden screening agent in the same LiveKit room hears each voice
# and sends the verdict about it to the *other* person only. Mounted only in AUTH_MODE=jwt:
# every call needs two real, distinct accounts. Secrets: environment only.
ENABLE_WEBRTC: bool = os.getenv("ENABLE_WEBRTC", "false").lower() == "true"
LIVEKIT_URL: str = os.getenv("LIVEKIT_URL", "ws://localhost:7880")   # what phones connect to
# What the backend's agent connects to. Same server, but the agent runs beside it, so
# localhost by default even when phones use a public address.
LIVEKIT_AGENT_URL: str = os.getenv("LIVEKIT_AGENT_URL", "") or LIVEKIT_URL
LIVEKIT_API_KEY: str = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET: str = os.getenv("LIVEKIT_API_SECRET", "")
WEBRTC_TOKEN_TTL_S: int = int(os.getenv("WEBRTC_TOKEN_TTL_S", "600"))     # a phone's room token
WEBRTC_CALL_TTL_S: int = int(os.getenv("WEBRTC_CALL_TTL_S", "900"))       # an unjoined call code
WEBRTC_MAX_CALLS: int = int(os.getenv("WEBRTC_MAX_CALLS", "2"))           # each call screens 2 voices, and
                                                                          # takes 2 admission slots
WEBRTC_JOIN_ATTEMPTS_PER_MIN: int = int(os.getenv("WEBRTC_JOIN_ATTEMPTS_PER_MIN", "10"))  # per account
WEBRTC_HEARTBEAT_S: float = float(os.getenv("WEBRTC_HEARTBEAT_S", "5"))   # full-state resend interval

# Tamper-evident evidence log of guardian alerts (item 17, server/evidence.py)
ENABLE_EVIDENCE_LOG: bool = os.getenv("ENABLE_EVIDENCE_LOG", "false").lower() == "true"

# PDF report generation (FR-14)
ENABLE_PDF_REPORTS: bool = True

# Use real module implementations vs mocked stubs
# Flipped to True one branch at a time during Block 2 integration
USE_REAL_SPEAKER: bool = os.getenv("USE_REAL_SPEAKER", "true").lower() == "true"

# Anti-spoof: Model A (fine-tuned AASIST) in audio_ml/spoof.py, loaded from
# models/antispoof/. On by default. If the checkpoint is missing or fails to load,
# detect_spoof scores no windows, server/audio_adapter.py marks the branch
# unavailable, and fusion drops w_cm and renormalises — the same outcome as off.
# USE_REAL_SPOOF=false forces it off (e.g. for a two-signal demo).
USE_REAL_SPOOF: bool = os.getenv("USE_REAL_SPOOF", "true").lower() == "true"

# Out-of-distribution abstention for Model A (item 8, audio_ml/ood.py). Off by default;
# needs the reference bank built by `python -m audio_ml.eval.build_ood_ref`.
SPOOF_OOD_ENABLED: bool = os.getenv("SPOOF_OOD_ENABLED", "false").lower() == "true"
SPOOF_OOD_REF_PATH: Path = MODELS_DIR / "antispoof" / "ood_ref.npz"
SPOOF_OOD_K: int = 10                     # neighbours averaged per window
SPOOF_OOD_PERCENTILE: float = 95.0        # threshold = this percentile of val-window distance
SPOOF_OOD_MAX_WINDOW_FRACTION: float = 0.5  # abstain when at least this share of windows is OOD

# Narrowband-channel rule (item 8, audio_ml/ood.hf_power_ratio). The k-NN gate above does
# not see the phone channel, so this one looks at it directly: an 8 kHz codec leaves no
# power above 4 kHz. Only effective when SPOOF_OOD_ENABLED is on.
SPOOF_OOD_NARROWBAND_ENABLED: bool = os.getenv("SPOOF_OOD_NARROWBAND_ENABLED", "true").lower() == "true"
# Abstain when the share of power at 4.5-7.6 kHz (energetic frames, whole clip) is below
# this. Calibrated on IFD train/val only, n=400 clips balanced by label (seed 1), plus the
# same 400 through G.711 mu-law and AMR-NB 12.2k (audio_ml.augment.apply_codec):
#   clean   median 3.4e-3, p5 1.2e-4 -> 4.50% (18/400) below 1e-4
#   g711    median 7.4e-8, p95 5.6e-7 -> 0.25% (1/400) at or above 1e-4
#   amr_nb  median 6.0e-8, p95 7.0e-6 -> 0.50% (2/400) at or above 1e-4
# 1e-4 is the error-minimising cut on that set (21/1200 errors). The band starts at
# 4.5 kHz, not 4.0, because resampler roll-off leaks an 8 kHz channel's content up to
# ~4.4 kHz: with a 4.2 kHz edge the same set gives 28/1200 errors. The clean clips below
# the cut are mostly IFD files that are themselves band-limited (e.g. Speaker-22/-29/-49
# deepfakes at orig_sr 16000), so abstaining on them is the rule working, not a false alarm.
# Test-split numbers: data/spoof_ood_measurement.json.
SPOOF_NARROWBAND_HF_RATIO_THRESHOLD: float = 1e-4

# Phone-channel calibration for Model A (independent of SPOOF_OOD_ENABLED). On a narrowband
# (8 kHz) channel the per-window score is rescaled s -> max(0, (s - T) / (1 - T)): measured on
# IFD test, Model A's EER threshold is 0.71 clean but 0.973 through G.711 (0.985 AMR-NB), and a
# genuine Exotel caller scored 0.79-0.93. Model A keeps scoring; only the channel's bias goes.
SPOOF_PHONE_CALIBRATION_ENABLED: bool = os.getenv("SPOOF_PHONE_CALIBRATION_ENABLED", "true").lower() == "true"
SPOOF_PHONE_THRESHOLD: float = float(os.getenv("SPOOF_PHONE_THRESHOLD", "0.973"))
# On a phone line, "partly synthetic" needs a synthetic run longer than one 4.04 s window:
# a single-window spike over the threshold was seen on a genuine Exotel caller.
SPOOF_PHONE_MIN_SYNTH_RUN_S: float = float(os.getenv("SPOOF_PHONE_MIN_SYNTH_RUN_S", "6.0"))
# On a phone line, an enrolled-voice similarity below this reads "unknown" (a stranger),
# not "mismatch" (an impostor): a stranger scored 0.61-0.77 over Exotel.
# A call whose anti-spoof verdict is synthetic for this many windows in a row (9 s windows,
# 2 s hop: 3 = ~13 s of audio) stays synthetic for the rest of the session, final verdict
# included. Seen live: a cloned voice scored synthetic for ~25 windows, then the call
# ended on a few bonafide windows and the final verdict read "not synthetic".
SESSION_SYNTH_LATCH_WINDOWS: int = int(os.getenv("SESSION_SYNTH_LATCH_WINDOWS", "3"))
# SPEAKER_PHONE_MISMATCH_FLOOR (a phone-line mismatch below 0.80 read as unknown) is gone:
# with claims (server/claims.py) a voice is only ever a mismatch against someone the
# caller or the user named, using the per-channel CLAIM_THRESHOLDS above.

# Anti-spoof window hop in seconds. Windows are fixed at 64,600 samples (4.04 s) by the
# architecture; the hop sets timeline granularity. Measured on this laptop's CPU.
SPOOF_HOP_S: float = 2.0

USE_REAL_NLP: bool = os.getenv("USE_REAL_NLP", "true").lower() == "true"

# Fusion: one implementation, audio_ml/fusion_core.py, used by the live path and the
# scenario matrix alike. (USE_REAL_FUSION, which chose between two, is gone.)

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
