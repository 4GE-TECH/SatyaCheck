# SatyaCheck — Master Project Checklist

**15 Hours · 4 Roles · Feature Freeze at H12:00**

---

## 🎯 Role Overview & Responsibilities

| Role | Domain | Folder | Status |
|---|---|---|---|
| **Role A** | Audio ML (Speaker Verification, Anti-Spoof, SASV) | `audio_ml/` | 🟡 In Progress (Awaiting `audio_ml/api.py`) |
| **Role B** | NLP / RAG (ASR, Scam Playbooks, Markers, Reason Codes) | `nlp_rag/` | 🟢 Complete & Integrated (304 tests passing) |
| **Role C** | Backend / Integration (FastAPI, SQLite, Pipeline, Streaming) | `server/`, `contracts.py`, `config.py` | 🟢 Ready for Integration |
| **Role D** | Frontend / Demo (React + Vite + Tailwind, Meter, Evidence) | `web/` | 🟡 In Progress (Connecting to API) |

---

## ⏱️ Timeline & Gate Progress

### Block 0 · H0:00–H1:00 · Foundation
- [x] **C**: `contracts.py` created and frozen with all Pydantic v2 schemas.
- [x] **C**: `config.py` created with thresholds, weights, and `USE_REAL_*` flags.
- [x] **C**: Mock API (`GET /api/mock/screen/*`) providing all 6 fixture bands (`verified`, `caution`, `suspicious`, `high_risk`, `unverified`, `insufficient`).
- [ ] **A**: Download and cache models locally in `./models/` (offline verification).
- [x] **B**: Corpus schema locked and seed documents written.
- [ ] **D**: Vite + React + Tailwind scaffold connected to mock API.
- [x] **GATE C0 (H1:00)**: Backend mock API running and serving trust fixtures to D.

---

### Block 1 · H1:00–H4:00 · Parallel Core
- [ ] **A**: `audio_ml/` modules:
  - [ ] `embed.py` (ECAPA-TDNN 192-dim speaker embeddings)
  - [ ] `enroll.py` (Wideband + 8 kHz narrowband condition-matched voiceprints)
  - [ ] `verify.py` (Three-verdict logic: `match`, `mismatch`, `unknown` with s-normalisation)
  - [ ] `spoof.py` (Anti-spoofing scoring with median, peak, max synthetic run, and timeline)
  - [ ] 50-speaker background cohort built in `data/cohort/`
- [x] **B**: `nlp_rag/` modules:
  - [x] Bilingual scam-playbook corpus in `nlp_rag/corpus/`
  - [x] FAISS index & docstore generation (`index_store.py`)
  - [x] `asr.py` & `api.py:transcribe()` (Whisper Hindi/English/Hinglish)
  - [x] `markers.py` (Bidirectional incriminating and exculpatory markers)
  - [x] `score.py` & `api.py:analyze_script()` (Intent risk scoring & RAG retrieval)
  - [x] `reason_codes.py` & `citations.py` (Citations from PIB / I4C)
  - [x] `challenge.py` (Dynamic challenge questions)
  - [x] `warnings.py` (Band-keyed vernacular warning copy)
  - [x] 304 unit & integration tests passing (`pytest nlp_rag/tests`)
- [x] **C**: `server/` modules:
  - [x] SQLite schema with WAL mode (`server/database.py`)
  - [x] Audio ingestion pipeline with ffmpeg normalisation & SHA-256 (`server/audio_ingest.py`)
  - [x] Silero VAD chunking & SNR quality gate (`server/audio_ingest.py`)
  - [x] Concurrent multi-branch orchestrator skeleton (`server/orchestrator.py`)
  - [x] Enrolled persons CRUD API (`server/persons_router.py`)
  - [x] Audio enrollment endpoint (`server/enroll_router.py`)
  - [x] Screening endpoints (`server/screen_router.py`)
  - [x] Integration resolver `get_person_by_id` registered with `nlp_rag`
- [ ] **D**: Screen implementations:
  - [ ] Enrollment screen (mic capture / file upload + shared secrets)
  - [ ] Screening screen with animated trust meter
  - [ ] Evidence panel rendering reason codes, citations, and markers
- [x] **GATE C1 (H4:00)**: A scores a WAV from CLI · B retrieves from CLI · C ingests upload · D has 3 screens.

---

### Block 2 — The Tree

**Owner:** Role C (Integration)  
**Goal:** Assemble the first full pipeline (GATE C2).

- [x] **C:** Unify the tree. `backend-integration` absorbs `audio_ml`, `nlp_rag`, and `frontend`.
- [x] **C:** Write `server/audio_adapter.py`.
- [x] **C:** One voiceprint store (SQLite metadata + `.npz` disk).
- [x] **C:** Enable `USE_REAL_SPEAKER` and `USE_REAL_SPOOF`.
- [x] **B:** Fix the FAISS index cache bug.
- [x] **B:** Grow the RAG corpus to ≥50 documents.
- [x] **B:** `eval_retrieval.py` proving P@3 ≥ 80%.
- [x] **B:** ASR deployed without forcing the Hindi decoder.
- [x] **C:** `python -m audio_ml.eval.test_scenarios` exits 0.

**GATE C2:** Upload a WAV through the web UI and get a real trust score from three live ML branches.
  - [ ] *Contingency*: If spoof branch fails at H6:00, cut it immediately and ship two signals.

---

### Block 3 · H6:00–H9:00 · Depth
- [ ] **A**: Codec augmentation, condition-matched centroids, adaptive s-norm, replay heuristic (cosine > 0.95), negative voiceprint list.
- [x] **B**: Exculpatory markers, challenge questions from shared secrets, cached vernacular warnings.
- [x] **C**: Depth deliverables:
  - [x] WebSocket streaming: 3s chunks, 1s overlap, ~2s re-scoring (`server/ws_router.py`)
  - [x] Monotone trust score escalation inside streaming sessions
  - [x] Incident Report Packet JSON + PDF formatted for 1930 / Chakshu (`server/report_router.py`)
  - [x] Guardian real-time alert pub/sub WebSocket (`server/guardian.py`, `server/ws_router.py`)
  - [x] System metrics endpoint (`GET /api/metrics`)
- [ ] **D**: Segment timeline strip, report preview screen, metrics dashboard screen.

---

### Block 4 · H9:00–H11:00 · Assets, Evaluation & Offline Verification
- [ ] **A + D**: Record ~30 test clips (genuine, cloned family emergency, escalation, IVR) duplicated at 8 kHz.
- [ ] **A**: Run evaluation suite, compute 5 metrics (SASV-EER, anti-spoof EER, 8kHz ablation, cross-attack gap) + ablation chart.
- [ ] **B**: Compute retrieval Precision@3 on held-out transcripts.
- [x] **C**: Demo reset endpoint (`POST /api/demo/reset`) & status check (`GET /api/demo/status`).
- [ ] **ALL**: **H10:30 — Turn WiFi OFF and run the full flow offline.**
- [ ] **D**: **H11:00 — Record backup video on two separate laptops.**
- [ ] **GATE C3 (H11:00)**: Backup demo video exists on two machines.

---

### Block 5 · H11:00–H12:00 · Bug Bash
- [ ] Edge cases tested: silence, 1-second clip, unenrolled stranger, empty transcript.
- [ ] `python -m audio_ml.eval.test_scenarios` exits 0 (12/12 scenario matrix pass).
- [ ] **H12:00 — ABSOLUTE FEATURE FREEZE**: Zero new code additions.

---

### Block 6 & 7 · H12:00–H15:00 · Rehearsals & Deck
- [ ] 8-slide deck completed with evaluation numbers.
- [ ] Four timed rehearsals on the demo machine with WiFi OFF (2:00 max each).
- [ ] Buffer and sleep rotation.

---

## 🔌 API Endpoint Status Summary

| Endpoint | Method | Purpose | Status |
|---|---|---|---|
| `/api/health` | GET | Server health & real-branch flag status | 🟢 Live |
| `/api/mock/screen/{scenario}` | GET | Return mock fixtures (`green`, `caution`, `suspicious`, `red`, `unverified`, `insufficient`) | 🟢 Live |
| `/api/persons` | GET / POST | List all enrolled contacts / create contact | 🟢 Live |
| `/api/persons/{person_id}` | GET / DELETE | Get or delete single contact | 🟢 Live |
| `/api/enroll` | POST | Ingest audio, store voiceprints & shared secrets | 🟢 Live |
| `/api/screen` | POST | Full audio screening (quality → 3 branches → fusion) | 🟢 Live |
| `/api/screen/{session_id}` | GET | Retrieve stored screening result | 🟢 Live |
| `/api/ws/screen/{session_id}` | WebSocket | Real-time streaming with monotone score escalation | 🟢 Live |
| `/api/ws/guardian` | WebSocket | Real-time push alert subscription for guardians | 🟢 Live |
| `/api/report/{session_id}` | GET | Get incident report JSON (1930 / Chakshu format) | 🟢 Live |
| `/api/report/{session_id}/pdf` | GET | Download pre-filled PDF incident report | 🟢 Live |
| `/api/metrics` | GET | System metrics & band distribution stats | 🟢 Live |
| `/api/demo/reset` | POST | Wipe sessions/results, preserve enrolled persons | 🟢 Live |
| `/api/demo/status` | GET | Demo readiness checklist status | 🟢 Live |
