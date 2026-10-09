# Merge plan: SIH 2026 repo into the SatyaCheck startup repo

Prepared 2026-09-23 for the pitch at Eureka! 2026 zonals (E-Cell IIT Bombay), 3 Oct 2026.
Read-only inspection. Nothing was changed in either repo apart from creating this file.

| | Path | Branch / HEAD inspected |
|---|---|---|
| Startup repo (target) | `C:\Dev\personal\SatyaCheck_MRDU\SatyaCheck` | `backend-integration` @ `7f9424b` |
| SIH repo (source) | `C:\Dev\personal\SatyaCheck` | `ml` @ `e72b405`, plus uncommitted working-tree changes (see 3.4) and remote branches |

---

## 1. Summary

This repo is ahead on the product. It has a complete three-signal pipeline (ECAPA identity with s-norm and
condition-matched enrollment, a bilingual RAG plus bidirectional marker intent branch with measured recall,
intent-gated fusion, cited reason codes, a FastAPI server with PDF reports, a React UI and a Flutter/Kotlin
client). It also has a 12-scenario behavioural matrix that passes. Its authenticity branch is a stub, though.
`detect_spoof` always returns 0.5 ([audio_ml/spoof.py:87](audio_ml/spoof.py#L87)), `USE_REAL_SPOOF` defaults
to false ([config.py:279](config.py#L279)) and `models/` has no anti-spoof checkpoint. Its evaluation claims
are thin and partly unsupported (section 3).

The SIH repo is ahead on anti-spoof research and measurement. It has a working, pretrained XLS-R + AASIST
scorer and an honest, reproducible record that this scorer fails on real Indian phone audio. It also has
cost-weighted evaluation tooling, a recording protocol, the Exotel/WebRTC acquisition design and a Merkle
evidence design. Its speaker and prosody checks are docstring stubs, its script check depends on the Groq API,
and much of its backend and acquisition code was written by people outside the startup team.

In short: bring over the research, the measurements and the scorer (behind a flag). Leave the SIH backend,
contracts and UI behind.

---

## 2. Inventory

### 2.1 Startup repo (verified by reading code)

| Area | Status | Notes |
|---|---|---|
| `contracts.py` (1087 lines) | Working, frozen | Pydantic v2 shared contract |
| `config.py` | Working | Weights, thresholds, `USE_REAL_*` flags |
| `audio_ml/embed.py`, `enroll.py`, `verify.py`, `codec.py` | Working | ECAPA embeddings, per-condition voiceprints, s-norm, ffmpeg codec degradation |
| `audio_ml/spoof.py` | **Stub** | Returns `score=0.5, verdict="uncertain"` for all input |
| `audio_ml/spoof_aggregate.py` | Working, unused | median / peak / `max_synth_run_s` / timeline; nothing feeds it real scores |
| `audio_ml/fusion.py` | Working, not served | `USE_REAL_FUSION` false; server fuses in `server/orchestrator.py` |
| `audio_ml/eval/test_scenarios.py` | Test (signal level) | 12-scenario matrix |
| `audio_ml/eval/run_eval.py` | Working | Writes `data/eval_results.json`; its inputs `data/eval_set/raw/person*.wav` are not in the repo |
| `audio_ml/tests/` (2 files) | Tests | s-norm, clip verification |
| `nlp_rag/` (17 modules) | Working | faster-whisper ASR, BGE-m3, numpy inner-product index, markers, scoring, reason codes, challenge questions, streaming |
| `nlp_rag/corpus/` | Data | 16 anchors, 76 variants, 103 benign, 50 held-out (245 docs; counted from the YAML files) |
| `nlp_rag/tests/` (24 files) | Tests | |
| `server/` (13 modules) | Working | FastAPI, SQLite, WebSocket, PDF report, guardian alert |
| `server/tests/` (3 files) | Tests | adapter, enroll round-trip, fusion |
| `web/` | Working UI | React + Vite. No test script in `web/package.json` (`dev`, `build`, `lint`, `preview` only) |
| `satyacheck_mobile/` | Working client | Flutter + Kotlin; one Kotlin unit test (`RingBufferTest.kt`) |
| `scripts/` (12 files) | Working tools | ablations, cohort build, live screening, model download |
| `data/` | Data | 22 wav clips in `data/eval_set/clips`, 2 enrollments, cohort, result JSONs |
| `README.md`, `PRD.md`, `PLAN.md`, `CHECKLIST.md`, `DEMO_RUNBOOK.md`, `SKILL.md`, `CLAUDE.md` | Docs | |
| `.agents/` | Vendored agent skills | Not product code |

### 2.2 SIH repo (branch `ml` plus working tree, verified by reading code)

| Area | Status | Notes |
|---|---|---|
| `contracts/` (6 files) | Working schema | Seven-stage pipeline types; uncommitted edits to `checks.py`, `risk.py` |
| `acquisitions/exotel/ws_adapter.py` | Working code | Exotel WebSocket to `AudioChunk` |
| `acquisitions/webrtc/dev_ws_adapter.py` | Working code | Dev WebSocket ingest. Full P2P WebRTC layer only on branches `webrtc_v1` / `webrtc-integration` |
| `backend/app/ingestion`, `pipeline/buffer.py`, `response/dispatcher.py` | Working code | |
| `backend/app/pipeline/transcript_worker.py` | Working code | Runs check 4 out of band |
| `backend/app/fusion/fusion.py` | Working code | Weights 0.85 script / 0.15 fingerprint, 0 to 100 **risk** score |
| `backend/app/evidence/store.py`, `router.py` | Working code, **untracked** | In-memory Merkle store and two GET routes |
| `backend/app/pipeline/reputation.py`, `data/blocklist.json` | Working code, **untracked** | Number reputation |
| `ml/checks/machine_fingerprint/` | **Working** | `SslAasistScorer` (XLS-R + AASIST, published Tak et al. checkpoint), `AasistScorer`, confidence, factory. Needs 1.2 GB of weights outside the repo |
| `ml/checks/speaker_identity/` | **Stub** | `__init__.py` docstring only |
| `ml/checks/prosody/` | **Stub** | `__init__.py` docstring only |
| `ml/checks/stt_llm/` | Working | faster-whisper, then Groq API with local keyword fallback. Network on the critical path |
| `ml/runner/runner.py` | Working code | `ml/README.md:15` still says "Docstring only" |
| `ml/augment/` | Working + tests | G.711 (numpy), AMR-NB/Opus (ffmpeg), gain, noise, room reverb |
| `ml/eval/` | Working + tests | EER, cost-weighted min-DCF, activity gate, confidence, transplant, runlog |
| `ml/tools/` (15 files) | Working tools | baseline, OOD probe, transplant, latency, correlate, handoff, evaluate |
| `ml/train/` | Working + tests | Fine-tunes AASIST. Conflicts with our "we train nothing" rule |
| `ml/tests/` (22 files), `tests/` (16 files) | Tests | Includes `test_transport_invariant.py` |
| `app/`, `web/dashboard-a`, `web/dashboard-b` | README only on `ml` | RN app on `mobile-app`; dashboards on `frontend-a`, `frontend` |
| `README.md`, `AGENTS.md`, `FROZEN.md`, `QUESTIONS.md`, `docs/interfaces.md`, `roles/`, `ml/*.md` | Docs | `ml/README.md` (1450 lines) holds every measured finding |
| `data/results/*.csv` | Tracked results | Includes a row derived from a non-startup member's recording (see 2.4) |
| `results/` | **Untracked** | 1353 wav files (team voices, IFD samples) plus three evaluation reports dated 2026-09-10 and 2026-09-11 |

### 2.3 Test results (run on this machine, 2026-09-23)

| Repo | Command | Result |
|---|---|---|
| Startup | `python -m audio_ml.eval.test_scenarios` | **12/12 PASS**, exit 0. `data/scenario_matrix.json` regenerated byte-identical (no git diff) |
| Startup | `python -m pytest audio_ml/tests server/tests` | 40 passed, 1 xfailed |
| Startup | `python -m pytest nlp_rag/tests` | 944 passed |
| Startup | all three suites in one run | **977 passed, 7 failed**, 1 xfailed. All 7 failures are in `nlp_rag/tests/test_recorded_audio.py` and that file passes 17/17 alone, so this is cross-suite state leakage. Root cause not verified |
| Startup | `python -m nlp_rag.eval_retrieval` (no `--json`, writes nothing) | P@3 strict 98.0%, family 100.0%, MRR 0.950, scam recall at amber 94.0%, benign FP 5.8% (6/103) |
| Startup | `web/`, `satyacheck_mobile/` | Not run (no web test script; Gradle/Flutter not run) |
| SIH | `.venv/Scripts/python.exe -m pytest tests ml` | **579 passed**, 1 warning. Ran on the working tree, which includes uncommitted and untracked tests; a clean-commit run was not done |
| SIH | other branches (`mobile-app`, `frontend*`, `webrtc*`) | Not run |

Environment caveat: the startup tests ran on Python 3.14.7, not the 3.11 that `CLAUDE.md` specifies. The SIH
tests ran in the SIH `.venv` on Python 3.13.15.

### 2.4 Authorship check

Authors in this repo: Nikhil Kotte / Nikhil_Kotte (nikhilkotte24@gmail.com), goutham katthi, mani-4444,
kondameedi-srujan-raj.

SIH authors **not** in this repo's history:

| Author | Email | Commits |
|---|---|---|
| Rahul | bolishettyrahul11@gmail.com | `58b47bf`, `7d0f62b`, `77e05d5`, `50a8adb`, `53f8166` (merged into `ml` via `6ecdd4e`), `f49b3bd` (branch `frontend`) |
| ybharath2302 | bharathchowdhary42@gmail.com | `408430e`, `b4186e6`, `01fac11`, `7332c4e`, `bf8e702` (branch `webrtc_v1`, merged into `webrtc-integration` via `1174cbe`) |

**The brief said one different member; git shows two.** Both are treated as "needs permission, do not port".

Files containing their lines (from `git blame` at each branch head):

| File | Non-startup lines / total |
|---|---|
| `acquisitions/exotel/__init__.py`, `ws_adapter.py` | Rahul 8/7*, 359/359 |
| `acquisitions/webrtc/dev_ws_adapter.py` | Rahul 127/127 |
| `backend/app/ingestion/consumer.py`, `websocket_endpoint.py` | Rahul 71/71, 55/55 |
| `backend/app/pipeline/buffer.py`, `response/dispatcher.py` | Rahul 81/81, 62/62 |
| `backend/app/fusion/fusion.py` | Rahul 97/329 |
| `backend/app/main.py` | Rahul 172/331 |
| `ml/runner/runner.py` | Rahul 101/101 |
| `contracts/acquisition.py` | Rahul 5/127 |
| `docs/interfaces.md`, `AGENTS.md`, `roles/R3.md` | Rahul 34/384, 5/340, 7/103 |
| `tests/test_exotel_adapter.py`, `test_ingestion.py`, `test_session_wiring.py`, `test_pipeline_buffer.py`, `test_response_dispatcher.py`, `test_dev_ws_adapter.py`, `test_webrtc_ingest.py`, `demo_*_client.py`, `demo_risk_listener.py` | Rahul, all lines |
| `tests/test_fusion.py`, `test_runner.py`, `test_machine_fingerprint_check.py` | Rahul 87/370, 104/123, 50/140 |
| `web/landing/**`, `web/dashboard-a/**` on branch `frontend` | Rahul, all lines |
| `acquisitions/webrtc/*` and `webrtc_plan.md` on `webrtc_v1` / `webrtc-integration` | ybharath2302, most lines (mani-4444 has 23 to 128 lines in `adapter.py`, `client.html`, `signalling.py`) |

\* blame reports 8 lines against a 7-line file because of CRLF counting; the whole file is Rahul's.

Other authorship risks git cannot settle:

- **Untracked SIH files have no git author**: `backend/app/evidence/*`, `backend/app/pipeline/reputation.py`,
  `tests/test_evidence.py`, `tests/test_reputation.py`, `data/blocklist.json`, `results/**`. Status: not verified.
- **`results/` evaluates checkpoints of unknown origin** (`Downloads/checkpoints-20260910T135344Z-1-001`, "their
  own best val EER"). Status: not verified.
- **The SIH README says its content comes from the SIH deck and project report** (`README.md:11-16`), which
  the whole SIH team wrote. The git author (Nikhil) is not necessarily the content author.
- **Personal data of a non-startup member**: `data/results/baseline.csv:34` and `ml/README.md:644` name
  `Bharath.mpeg` as the source of `spk_01_source`, and `results/` holds the audio. Do not port these rows or files.

Everything under `ml/checks/machine_fingerprint/`, `ml/augment/`, `ml/eval/`, `ml/*.md`,
`tests/test_transport_invariant.py`, `tests/test_contracts_smoke.py` and `backend/app/pipeline/transcript_worker.py`
blames 100% to nikhilkotte24@gmail.com. `ml/checks/machine_fingerprint/check.py` was first added by Rahul
(`50a8adb`) but its current 205 lines all blame to Nikhil after `7d5770e` / `7e7c6f3`. It is not proposed for
porting anyway.

---

## 3. Classification

Permission column: **OK** means every line blames to a startup-team member. **NEEDS** means non-startup lines.
**UNKNOWN** means the file is untracked or of unverified provenance.

| # | Item | Source path (SIH) | Class | Reason | Effort | Permission |
|---|---|---|---|---|---|---|
| 1 | Research findings and references (lab vs real-world gap, watermark both classes or neither, noise recovery, voice-scam compliance, Family Vault three outcomes) | `README.md:188-321`, `AGENTS.md:198-215, 309-338` | PORT NOW | Pitch Q&A material; explains why we fuse three signals. Keep every *ID not verified* marker | S | OK by git. Content comes from the SIH deck/report (open question 2) |
| 2 | Training rules (train on 8 kHz G.711 / AMR-NB, noisy audio, watermarks) | `README.md:188-201`, `AGENTS.md:235-250` | PORT NOW as context only | We train nothing. Port as "why pretrained CM is weak", not as a rule. The evaluation rules (unseen data only, cost-weighted metrics, Indian-accent FP benchmark) do apply | S | OK, same caveat as #1 |
| 3 | Our own anti-spoof measurements (5/5 genuine flagged, clone inside genuine range, bimodal windows, window-position swing, CPU latency, OOD probe) | `ml/README.md:118-1020`, `docs/interfaces.md:288-292` | PORT NOW (curated) | Only first-party numbers either repo has on real Indian audio. Grounds the "synthetic is a multiplier" design. Strip the `Bharath.mpeg` mapping | S | OK |
| 4 | Exotel 8 kb/s cliff: live G.711 64k scores 0.000, 8 kb/s mp3 export scores 0.999 on 8/8 bonafide | `ml/README.md:700-778` | PORT NOW | Direct answer to "how would this work on real calls". Also a rule: never feed a low-bitrate export | S | OK |
| 5 | Audio acquisition decision (Exotel primary, WebRTC fallback) | `README.md:127-164`, `AGENTS.md:125-177` | PORT NOW as a roadmap design doc | Matches this repo's documented Android capture limit (`CLAUDE.md`). Distribution slide for the pitch. **Design only, no code** | S | OK for the doc text. Code is NEEDS (#15, #16) |
| 6 | Transport-invariant test (AST walk: nothing below ingestion knows the transport) | `tests/test_transport_invariant.py` | REWRITE | Idea fits: mic, upload, voice note, bystander and mobile paths must converge at `server/audio_ingest.py`. Module names differ, so it must be retargeted at `audio_ml/`, `nlp_rag/`, `server/orchestrator.py`. Optional before 3 Oct | S | OK (Nikhil) |
| 7 | XLS-R + AASIST scorer (pretrained Tak et al. checkpoint via HF port) | `ml/checks/machine_fingerprint/ssl_aasist.py`, `ml/eval/activity.py` (`select_windows`) | PORT NOW behind `USE_REAL_SPOOF=false` | Fills our only stub with a pretrained model, so rule 1 holds. Only enable after the gate in 5.5. SIH's own data says it flags genuine phone audio | M | OK for our code. `ssl_aasist/model.py` is third-party (licence not verified) |
| 8 | Recording protocol and scripts | `ml/RECORDING_SESSIONS.md`, `ml/RECORDING_SCRIPTS.md` | PORT NOW | Our "~30 clips, 4 speakers" claim has no manifest behind it (3.2). This is the fastest way to make it true before 3 Oct. Edit out the six-person SIH roster | S | OK |
| 9 | EER and cost-weighted min-DCF | `ml/eval/eer.py`, `ml/eval/cost.py` | PORT LATER | Useful once we have more than one genuine sample. PRD M1/M2 are unmet today. Pure numpy | S | OK |
| 10 | Indian-accent FP benchmark spec | `ml/BENCHMARK_FORMAT.md` | PORT LATER | Post-pitch data programme | S | OK |
| 11 | Augmentation (G.711 numpy, room, noise, gain) | `ml/augment/` | PORT LATER | Useful for building eval conditions. Overlaps our ffmpeg `audio_ml/codec.py`. Not for training | M | OK |
| 12 | OOD confidence estimator (k-NN, AUC 0.951 OOD vs in-domain) | `ml/eval/confidence.py`, `ml/tools/fit_confidence.py` | PORT LATER | Good for an "anti-spoof is out of domain" reason code. Needs an ASVspoof reference set we don't ship | M | OK |
| 13 | Model handoff and verify (SHA256 plus probe rescore) | `ml/tools/handoff.py`, `FROZEN.md` hashes | PORT LATER (hash list used now in 5.5) | We already have `scripts/download_models.py --verify` | S | OK |
| 14 | Alert fingerprint + Merkle evidence | `backend/app/evidence/store.py`, `router.py`, `contracts/evidence.py` | REWRITE, later | Untracked with no git author. In-memory only and the root is never published. Duplicates the last leaf on odd counts, with no leaf/node domain separation (second-preimage ambiguity). Rebuild in `server/` keyed by `IncidentReportPacket.report_id`, no contract change | M | UNKNOWN (store/router), OK (`contracts/evidence.py`) |
| 15 | Exotel adapter | `acquisitions/exotel/ws_adapter.py` + tests | REWRITE, later | Written by a non-startup member; also SIH-contract shaped | L | NEEDS (Rahul) |
| 16 | WebRTC P2P layer | `acquisitions/webrtc/*` on `webrtc_v1` / `webrtc-integration` | SKIP now, REWRITE later if needed | Non-startup author. We already capture via mic/upload/bystander | L | NEEDS (ybharath2302, mixed with mani-4444) |
| 17 | SIH `contracts/` package | `contracts/*.py` | SKIP; adapters only (3.3) | `contracts.py` is frozen. Score direction and verdict semantics conflict | n/a | Mostly OK; `acquisition.py` has 5 Rahul lines |
| 18 | SIH fusion (0.85 script / 0.15 fingerprint, EMA, context in score) | `backend/app/fusion/fusion.py` | SKIP | Our mode-aware, intent-gated fusion is more developed. Feeding context into the score breaks our "no fourth signal" rule | n/a | NEEDS (Rahul 97 lines) |
| 19 | Backend ingestion, buffer, dispatcher, main, runner | `backend/app/**`, `ml/runner/runner.py` | SKIP | Duplicates `server/`. Non-startup author | n/a | NEEDS |
| 20 | stt_llm check (Groq API, keyword fallback) | `ml/checks/stt_llm/`, branch `llm` | SKIP | Network plus LLM on the critical path breaks rules 4 and "no LLM on critical path". Our `nlp_rag` is measured and better | n/a | OK |
| 21 | Fine-tuning pipeline and fine-tuned checkpoints (2.12% EER on 2019 LA eval) | `ml/train/`, `%LOCALAPPDATA%\satyacheck\models\finetuned*` | SKIP | "We train nothing." The 2.12% result also does not transfer to our audio (`ml/README.md:909-944`) | n/a | OK (code); checkpoints in `results/` UNKNOWN |
| 22 | Number reputation / blocklist | `backend/app/pipeline/reputation.py`, `data/blocklist.json` | PORT LATER as explanation-only, rewritten | Caller-ID may enrich the explanation, never the score | S | UNKNOWN (untracked) |
| 23 | Prosody check, speaker_identity check | `ml/checks/prosody/`, `ml/checks/speaker_identity/` | SKIP | Docstring stubs. Prosody would be a fourth weighted signal | n/a | OK |
| 24 | Speaker-probe finding (ECAPA does not separate clone from target, n=3) | `ml/README.md:827-867` | PORT NOW inside #3 | Contradicts our 1/1 clone result (3.2 row 6). Both must be quoted with n | S | OK |
| 25 | Dashboards, landing page, RN app | branches `frontend-a`, `frontend`, `mobile-app` | SKIP | Duplicates `web/` and `satyacheck_mobile/`. `frontend` is Rahul's. The "GeneralizationGapSection" idea can be redone as a slide, not copied | n/a | `frontend-a` OK (goutham), `mobile-app` OK (mani), `frontend` NEEDS |
| 26 | Untracked evaluation reports (C = XLS-R+AASIST: EER 24.64% on 2,321 IFD held-out files) | `results/model_evaluation_abcde/FINAL_EVALUATION_REPORT.md` | PORT LATER, figures only, after provenance check | Strongest out-of-domain number for the production model. Untracked, and the A/B checkpoints are of unknown origin | S | UNKNOWN |
| 27 | Tracked result CSVs | `data/results/*.csv` | SKIP | Machine-specific frozen config. `baseline.csv:34` derives from a non-startup member's voice | n/a | Personal data, do not port |

### 3.1 Contract overlap: SIH `contracts/` vs this repo's `contracts.py`

No edits to `contracts.py` are proposed. Where an SIH shape is needed, the adapter lives in the owner's folder.

| SIH type | Ours | Conflict | Adapter (owner) |
|---|---|---|---|
| `RiskUpdate.score` 0 to 100, **higher = riskier** (`contracts/risk.py`) | `TrustScoreResult.trust_score` 0 to 100, **higher = trusted**; `risk_score` 0 to 1 | Inverted direction | `sih_score = round(100 * risk_score)` if ever needed for an external feed (C, `server/`) |
| `RiskLevel` low/medium/high/critical | `TrustBand` incl. `unverified`, `insufficient` | SIH has no "unverified"; mapping is lossy | Map only for export; never map `unverified` to `low` (C) |
| `RiskVerdict` genuine/synthetic/unknown | none; `AntiSpoofResult.is_synthetic` | We never emit a binary verdict | Do not adopt |
| `ReasonCode` str enum | `ReasonCode` model (code, signal, value, citation, severity) | Shape | Enum value becomes `code`; explanation from our deterministic templates (B) |
| `CheckStatus` ok/degraded/failed/skipped | none | We return neutral defaults | Put status in `AntiSpoofResult.details["status"]` and log why (A) |
| `CallContext`, `NumberReputation` | `CallerMetadata` | SIH folds context into the score | Explanation-only reason code (B) |
| `AudioChunk`, `StreamOpen`, `StreamClose` | `StreamAudioChunkMessage` | Transport-level vs message-level | Only relevant with Exotel (#15), at `server/audio_ingest.py` (C) |
| `CanonicalAudioBatch` (s16le bytes) | audio_ml takes a wav path | Input form | Scorer port reads the wav already normalised by ingest (A) |
| `AlertRecord`, `SealedRecord`, `ChainAnchor` | `GuardianAlert`, `IncidentReportPacket` (`audio_sha256`, `transcript_full`) | No Merkle fields; ours hashes audio and carries the transcript, SIH forbids both in the fingerprint | Separate evidence table keyed by `report_id`, hashing a canonical subset (C) |
| `speaker_identity` `no_enrolment` | `SpeakerVerdict.UNKNOWN` | Same idea, both neutral | None needed |
| `CheckName.PROSODY` | none | Would be a fourth weighted signal | Do not adopt |

---

## 4. Conflicts and inconsistencies

### 4.1 Evaluation numbers: every figure each repo claims

| # | Claim | Where | What the data shows | Status |
|---|---|---|---|---|
| 1 | "Evaluated on ~30 clips from 4 consented speakers" | `README.md:159`, `PRD.md:142`, `PLAN.md:76` | `data/eval_set/manifest.csv` has 5 rows (1 genuine, 1 clone, 3 impostor). `data/eval_set/raw/` is not in the repo. 22 wav files in `data/eval_set/clips`, of which 10 are `held-*` scam-script clips used by nlp_rag tests and 4 are codec test tones | **Not supported**. Speaker count not verified |
| 2 | "Speaker verification degrades roughly 7 to 8% relative at 8 kHz" | `README.md:160`, `SKILL.md:60` | Own ablation: genuine cosine 0.9588 to 0.7365 (-23.2%), separation 0.5987 to 0.4356 (-27.2%), n=1 genuine (`data/eval_results.json:29-54`). No source cited | **Disagrees with own data**; external source not verified |
| 3 | "Three seconds of audio ... is enough to clone a voice" | `README.md:13` | SIH: "roughly 30 seconds" (`SIH README.md:44`, `AGENTS.md:212`) | **Repos disagree**; neither cites a source in-repo |
| 4 | "~150 scam-playbook documents" | `README.md:95` | 16 anchors + 76 variants = 92 scam docs; 245 corpus docs in total | **Disagrees** |
| 5 | "AASIST-family anti-spoof checkpoint" in the models table | `README.md:109` | Stub; no checkpoint in `models/`; `USE_REAL_SPOOF` false | **Not implemented** |
| 6 | Clone detection 1/1 (clone 0.7631 vs genuine 0.9588, threshold 0.85) | `data/eval_results.json:4-15` | SIH: ECAPA clone-vs-target 0.5056 to 0.5923 lies inside same-speaker 0.4888 to 0.7821, so 0/3 caught (`SIH ml/README.md:841-851`) | **Repos disagree**; different clone tools, n=1 vs n=3; neither is a rate |
| 7 | SASV-EER headline (M1), anti-spoof EER (M2) | `PRD.md:128-129`, `CHECKLIST.md:100` (unchecked) | `eval_results.json:9`: "n=1 genuine sample, not statistically meaningful". M2 impossible with a stub | **Not produced** |
| 8 | 12/12 scenario pass | `PRD.md:133`, `CHECKLIST.md:111`, `nlp_rag/PLAN.md:659` | Reproduced 12/12 today | **Verified** (signal level, not audio) |
| 9 | Retrieval P@3 98% / 100%, recall at amber 94%, benign FP 5.8% | `nlp_rag/PLAN.md:649-653` | Reproduced exactly today | **Verified** |
| 10 | Retrieval baseline file: recall 0.68, 56 variants | `nlp_rag/eval_baseline.json:8,17` | Current run is 94% with 76 variants | **Stale file** |
| 11 | "Two tests exist and pass" | `SIH README.md:397-399` | 579 passed | **SIH doc stale** |
| 12 | "`runner/` Docstring only" | `SIH ml/README.md:15` | `ml/runner/runner.py` is 101 lines of code | **SIH doc stale** |
| 13 | "Checks 1 to 3 run locally on open-source checkpoints" | `SIH README.md:77` | Checks 2 and 3 are docstring stubs | **SIH doc overclaims** |
| 14 | 2.12% EER, ASVspoof 2019 LA eval, n=71,237 | `SIH ml/README.md:869-907` | Fine-tuned AASIST (trained by us). Not comparable to Tak 2.85% (2021 DF), as the SIH doc itself says | Not reproducible here; weights outside repo. Not usable under "train nothing" |
| 15 | XLS-R + AASIST on own audio: genuine 0.436 to 0.990 (n=5 recordings, 3 speakers), clone 0.938 | `SIH ml/README.md:628-654`, `data/results/baseline.csv` | Consistent within SIH | Not re-run here (weights absent) |
| 16 | 207 s genuine speech: 326/326 windows LOW with check 4; 42/43 CRITICAL without it | `SIH docs/interfaces.md:288-292` | Consistent with #15 | Not re-run here |
| 17 | XLS-R + AASIST EER 24.64% on 2,321 IFD held-out files | `SIH results/model_evaluation_abcde/FINAL_EVALUATION_REPORT.md:105` | Untracked | Provenance not verified |
| 18 | CPU latency XLS-R + AASIST 415.5 ms per 4.04 s window (i9, 16 threads) | `SIH ml/README.md:1000` | About 0.1 real-time factor | Not measured on our demo laptop |
| 19 | Lab 2.85% to real-world 35.24% | `SIH README.md:207-213` | 35.24% source marked *ID not verified* | Keep marker |

### 4.2 Design and policy conflicts

| Conflict | Startup | SIH |
|---|---|---|
| Training | "We train nothing" (`CLAUDE.md` rule 1) | Fine-tuning is a Round 1 deliverable (`SIH README.md:179`, `ml/train/`) |
| Audio at rest | 22 wav clips committed; `1a038ce` "retain screened chunks per session" | "No call recordings at rest", "No audio is committed" (`SIH README.md:247`, `ml/BENCHMARK_FORMAT.md:249`) |
| Network | No runtime network calls | Check 4 calls Groq (`SIH README.md:80-86`) |
| Context in score | Caller-ID enriches explanation only | Context is part of fusion (`SIH README.md:114-117`) |
| Verdict | Never emit a binary verdict | `RiskVerdict` genuine/synthetic |
| Report hashing | `audio_sha256` + `transcript_full` in `IncidentReportPacket` | Fingerprint excludes audio and transcript (`SIH contracts/evidence.py:1-8`) |

---

## 5. Proposed docs/ structure

```
docs/
  README.md                          index, and the attribution rule below
  research/
    generalisation-gap.md            from SIH README "Findings worth knowing" + AGENTS "Where the numbers live"
    antispoof-measurements.md        curated from SIH ml/README.md findings (items 3, 4, 24)
    references.md                    SIH README References table, ID-not-verified markers kept
  design/
    acquisition-exotel-webrtc.md     SIH README "Audio acquisition" + AGENTS acquisition section (design only)
    transport-invariant.md           the rule; test to be rewritten in server/tests
    evidence-merkle.md               design only; notes the flaws in item 14 and the privacy rule
  evaluation/
    recording-sessions.md            SIH ml/RECORDING_SESSIONS.md, roster removed
    recording-scripts.md             SIH ml/RECORDING_SCRIPTS.md
    benchmark-format.md              later (item 10)
  provenance.md                      one row per ported file: SIH path, SIH commit, git author, date ported
```

Attribution notes:

- Each ported doc opens with: `Ported from the SIH 2026 repo (AI ASTRA), <path> @ <commit>, git author Nikhil Kotte. Content partly derived from the SIH 2026 deck and SIH26104 report.`
- Keep every *ID not verified* marker; a human removes it after checking arXiv.
- Every figure keeps its n and scope line (for example "n=3 speakers, 5 recordings, 1 clone").
- Replace speaker source filenames with `speaker_a/b/c`. Do not carry `Bharath.mpeg`, `Goutham.mp4` or `Nikhil*.mp4`.
- Rewrite SIH-internal terms (R1 to R6, H+4 gate, stage 04, 180 ms budget) where they don't apply here.

---

## 6. Exact steps for each PORT NOW item (not run)

All steps read from a fixed SIH commit so the source is reproducible. Owners follow `CLAUDE.md` folder ownership.

```bash
SIH=/c/Dev/personal/SatyaCheck
REV=e72b405
cd /c/Dev/personal/SatyaCheck_MRDU/SatyaCheck
git switch -c port/sih-research          # from backend-integration
mkdir -p docs/research docs/design docs/evaluation
```

**Items 1, 2: research findings and references (owner: whoever holds docs; review by all)**

```bash
git -C "$SIH" show $REV:README.md > /tmp/sih_readme.md
git -C "$SIH" show $REV:AGENTS.md > /tmp/sih_agents.md
# hand-copy sections into the new files:
#   README.md lines 188-238  -> docs/research/generalisation-gap.md (training rules framed as context)
#   AGENTS.md lines 309-338  -> appended to the same file ("Where the numbers live")
#   README.md lines 302-321  -> docs/research/references.md
```

**Items 3, 4, 24: anti-spoof measurements (owner A)**

```bash
git -C "$SIH" show $REV:ml/README.md > /tmp/sih_ml_readme.md
git -C "$SIH" show $REV:docs/interfaces.md > /tmp/sih_interfaces.md
# hand-copy into docs/research/antispoof-measurements.md:
#   ml/README.md 123-141, 311-365, 366-411, 541-613, 614-660 (drop the SOURCES table at 642-649),
#   661-698, 700-778, 780-825, 827-867, 988-1018; interfaces.md 288-292
grep -n -i 'bharath\|goutham\|nikhil' docs/research/antispoof-measurements.md   # must print nothing
```

**Item 5: acquisition design (owner C)**

```bash
# README.md lines 127-164 and AGENTS.md lines 125-177 -> docs/design/acquisition-exotel-webrtc.md
# Add a header: design only, no Exotel or WebRTC code ported (items 15, 16 need permission).
```

**Item 8: recording protocol (owner A + D, who ran the recording session)**

```bash
git -C "$SIH" show $REV:ml/RECORDING_SESSIONS.md > docs/evaluation/recording-sessions.md
git -C "$SIH" show $REV:ml/RECORDING_SCRIPTS.md  > docs/evaluation/recording-scripts.md
# edit: remove the 6-person SIH roster; set speaker count to what we actually record
```

```bash
# write docs/README.md and docs/provenance.md by hand, then:
git add docs/
git commit -m "docs: port SIH research, measurements and acquisition design"
```

**Item 7: XLS-R + AASIST scorer (owner A), separate branch**

```bash
git switch backend-integration && git switch -c port/sih-antispoof
git -C "$SIH" show $REV:ml/checks/machine_fingerprint/ssl_aasist.py > audio_ml/ssl_aasist.py
git -C "$SIH" show $REV:ml/eval/activity.py > audio_ml/activity.py
# edit imports: ml.paths.require -> audio_ml-local path under ./models/antispoof/
# weights, copied from the SIH machine's %LOCALAPPDATA%\satyacheck\models (not from git):
mkdir -p models/antispoof/ssl_aasist models/antispoof/wav2vec2-xls-r-300m
cp "$LOCALAPPDATA/satyacheck/models/Best_LA_model_for_DF.pth"            models/antispoof/
cp "$LOCALAPPDATA/satyacheck/models/ssl_aasist/model.py"                  models/antispoof/ssl_aasist/
cp "$LOCALAPPDATA/satyacheck/models/ssl_aasist/fairseq_to_hf.json"        models/antispoof/ssl_aasist/
cp "$LOCALAPPDATA/satyacheck/models/wav2vec2-xls-r-300m/config.json"      models/antispoof/wav2vec2-xls-r-300m/
sha256sum models/antispoof/Best_LA_model_for_DF.pth
#   expect 1cf904f1d84c867c278cd42161df5367939d61cc28bfefd239bc995af59c2804 (SIH FROZEN.md:12)
sha256sum models/antispoof/ssl_aasist/model.py models/antispoof/ssl_aasist/fairseq_to_hf.json
#   expect 08b2b99b...56c6 and f1bf1d0f...442b (SIH FROZEN.md:83-84)
```

Code change in `audio_ml/spoof.py` (the adapter; no contract change):

- Replace the Block 3 placeholder with 4.0375 s windows (64,600 samples, fixed by the model). Use hop 1 s so
  `aggregate()` gets a real timeline. Don't tile-pad our 3 s chunks, because that changes the score.
- Per-window `SslAasistScorer.score()` then `spoof_aggregate.aggregate()` gives a `SpoofSignal`, which
  `server/audio_adapter.py` already converts to `AntiSpoofResult`.
- On any failure: log the reason, return the neutral `SpoofSignal`, and set `details["status"]`.
- Keep `USE_REAL_SPOOF=false` in `config.py` until the gate below passes.

Gate before flipping the flag (all must hold):

```bash
python -m audio_ml.spoof                         # smoke test
python -m audio_ml.eval.test_scenarios           # 12/12, exit 0
USE_REAL_SPOOF=true uvicorn server.main:app --port 8000     # terminal 1
python scripts/demo_check.py --run               # terminal 2: streams recorded clips over the phone WebSocket
for f in data/eval_set/clips/*.wav satyacheck_mobile/assets/demo/*.wav; do
  curl -s -F file=@"$f" http://localhost:8000/api/screen > "/tmp/screen_$(basename "$f").json"
done                                             # every clip, not only the demo set
# pass criteria: genuine clips (friend_test, me, me_test2) do not move out of green/unverified;
# the legitimate-IVR scenario stays unverified; latency per clip recorded on the demo laptop
git add audio_ml/ssl_aasist.py audio_ml/activity.py audio_ml/spoof.py
git commit -m "feat(audio_ml): wire pretrained XLS-R + AASIST behind USE_REAL_SPOOF"
```

If the gate fails, leave the flag off. On stage, say the authenticity branch abstains and cite #3 as the reason.

---

## 7. Open questions for the team

1. **Two non-startup authors, not one.** Rahul (bolishettyrahul11@gmail.com) and ybharath2302
   (bharathchowdhary42@gmail.com) both committed to SIH. Which one is "the different member"? Is the other a
   startup member under another identity (kondameedi-srujan-raj appears only here)? Until answered, both stay
   "needs permission".
2. **Deck and report authorship.** The SIH README and AGENTS text are Nikhil's commits but say they transcribe the
   SIH deck and report. Did the non-startup member(s) write any section we'd port (items 1, 2, 5)?
3. **Untracked SIH files.** Who wrote `backend/app/evidence/*`, `reputation.py`, `tests/test_evidence.py`,
   `tests/test_reputation.py` and `results/**`? Where did the checkpoints in `Downloads/checkpoints-20260910T135344Z-1-001` come from?
4. **Anti-spoof for the pitch.** Wire XLS-R + AASIST (item 7) knowing it scores genuine phone audio high, or keep
   the stub and present the measurements as the reason the branch abstains? The gate in section 6 decides it, but
   the team should agree on the fallback story now.
5. **Evaluation claims.** Record the "~30 clips, 4 speakers" set before 3 Oct using item 8, or change
   `README.md:159` / `PRD.md:142` to what exists? Same for the 7 to 8% figure, "~150 documents" and "three seconds".
6. **Clone vs ECAPA.** Our 1/1 and SIH's 0/3 disagree. Which one goes on a slide, with what n?
7. **Audio at rest.** Keep committed clips and per-session chunk retention (`1a038ce`), or adopt the SIH "no
   recordings at rest" rule for the DPDP story in the pitch?
8. **Merkle evidence.** Do we want a tamper-evident report in the Eureka demo, or is it a roadmap slide? If demo,
   item 14 moves to REWRITE now (M, owner C).
9. **Third-party model code.** `ssl_aasist/model.py` and the `Best_LA_model_for_DF.pth` checkpoint come from the
   Tak et al. release. Licence not verified. Someone should check it before we ship or demo it commercially.
10. **Test isolation.** 7 `nlp_rag/tests/test_recorded_audio.py` failures appear only when all suites run
    together. Who owns the fix (A or B), and should CI run suites separately until then?
