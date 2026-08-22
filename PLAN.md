# SatyaCheck — Execution Plan

**15 hours · 4 people · feature freeze at H12:00**

Read `PRD.md` for what we're building and why. This file is only about how and when.

---

## Roles

| | Owner | Folder | Wins by |
|---|---|---|---|
| **A** | Audio ML | `audio_ml/` | Producing the five numbers on the metrics slide |
| **B** | NLP / RAG | `nlp_rag/` | A corpus that makes the evidence panel feel real |
| **C** | Backend / integration | `server/`, `contracts.py`, `config.py` | Nobody ever being blocked |
| **D** | Frontend / demo | `web/`, deck, assets | The judge looking up from their laptop |

**You only write inside your own folder.** Cross-folder changes go through the owner. This single rule prevents most hackathon merge disasters.

D is not the junior role. A and B produce numbers; D produces the two minutes that are actually scored.

---

## Timeline

### Block 0 · H0:00–H1:00 · Foundation

The **first command anyone types**, before any planning discussion, is A starting model downloads in a background terminal. Venue wifi will betray you at hour nine.

| Who | Deliverable |
|---|---|
| C | Repo, branches, `contracts.py` + `config.py`, **FROZEN at H0:45**. Mock API returning three fixtures (green / red / unverified). |
| A | All 5 models cached locally and verified with wifi off. **20-minute timeboxed clone smoke test.** |
| B | Corpus schema locked, 10 seed documents written. |
| D | Vite + React + Tailwind scaffold, trust meter rendering from C's mock. |

> **GATE C0 (H1:00)** — D's browser shows a meter driven by C's mock API.

### Block 1 · H1:00–H4:00 · Parallel core

Nobody touches the server except C. A and B build importable modules with CLI wrappers, tested on files.

| Who | Deliverable |
|---|---|
| A | `embed.py`, `enroll.py`, `verify.py` (three-verdict logic), `spoof.py`, 50-speaker cohort built |
| B | Corpus → 60 bilingual docs, FAISS index, `retrieve.py`, `markers.py` v1 |
| C | SQLite schema, ffmpeg ingestion, quality gate, VAD chunking, `/api/persons`, orchestration skeleton with mocked branch calls |
| D | Enrollment screen, screening screen with animated meter, evidence panel against mock JSON |

> **GATE C1 (H4:00)** — A scores a wav from CLI · B retrieves from CLI · C ingests an upload · D has three screens.

### Block 2 · H4:00–H6:00 · Integration 1

C owns this block. A and B stop building and sit next to him.

Swap mocks for real imports **one branch at a time**: speaker → spoof → ASR → script → fusion → reason codes. Never all at once, or you won't know which one broke.

> **GATE C2 (H6:00) — HARD**
> Upload a WAV in the real UI → a real trust score from all three real branches.
>
> **If this fails, cut the spoof branch immediately and ship two signals.** Make the call at 6:00, not 9:00. Hesitating here is the most common way capable teams lose.

### Block 3 · H6:00–H9:00 · Depth

| Who | Deliverable |
|---|---|
| A | Codec augmentation, condition-matched centroids, adaptive s-norm, threshold calibration, **intent gating**, **spoof timeline**, replay heuristic, negative voiceprint list |
| B | Corpus → 150+, **exculpatory markers**, reason-code engine, challenge questions, cached TTS warnings |
| C | WebSocket streaming (3s chunks, 1s overlap, re-scored ~2s), report packet + PDF, guardian pub/sub, `/api/metrics` |
| D | Evidence panel on real reason codes, **segment timeline strip**, report screen, metrics screen |

### Block 4 · H9:00–H11:00 · Assets, evaluation, backup

The block teams skip and then lose.

- **A + D:** recording session. ~30 clips, all duplicated at 8 kHz.
- **A:** run the eval, produce the five numbers and the ablation chart.
- **B:** retrieval P@3 on held-out transcripts → hand to A.
- **C:** demo reset endpoint. **H10:30 — turn wifi OFF and run the full flow.**
- **D:** **record the backup video at H11:00, while everything works.**

**Floater rule:** at H9:00, whoever is furthest ahead joins D. Model polish at hour ten has near-zero marginal value; a tighter pitch has enormous marginal value.

> **GATE C3 (H11:00)** — backup video exists on two laptops. From here, no failure can cost you the demo.

### Block 5 · H11:00–H12:00 · Bug bash
Every screen exercised. Edge cases: silence, 1-second clip, unenrolled speaker, empty transcript. `test_scenarios.py` must exit 0. **Nothing new gets built.**

> ### H12:00 — FEATURE FREEZE. ABSOLUTE.
> Weak teams die from not finishing. Strong teams die from not stopping. Every good engineer at hour thirteen has one more idea. The freeze exists to protect you from your own competence.

### Block 6 · H12:00–H13:30 · Deck and rehearsal
8 slides. **Four timed rehearsals on the demo machine, wifi off**, at 2:00 each. A prepares Q&A answers.

### Block 7 · H13:30–H15:00 · Buffer
Sleep rotation, two at a time. Cosmetic only. The buffer is the plan, not slack in it.

---

## Recording priority (Block 4)

Stop when time runs out; this order preserves the demo.

1. Scenarios 1 + 4 (genuine, cloned family emergency) — **must have**
2. Scenario 11 (escalation — one 2-minute continuous take)
3. Scenarios 2 + 10 (the false-positive guards)
4. Scenario 12 (splice a clone segment into a real recording)
5. Scenarios 3, 8, 9 — **no cloning needed**, cheapest rows
6. Scenarios 5, 6, 7

---

## Demo: four scenarios live, twelve on a slide

| Order | Scenario | Time | Why |
|---|---|---|---|
| 1 | Genuine call | 10s | Baseline — without it, red means nothing |
| 2 | Cloned family emergency | 25s | Flagship |
| 3 | Gradual escalation | 30s | Proves real-time; the meter *moves* |
| 4 | Legit AI voice, or genuine unusual request | 20s | Proves we don't over-flag |

Then one slide: "12 scenarios tested," populated from `data/scenario_matrix.json`.

Run entirely from local files, wifi off, no live mic.

---

## Cut order

1. LLM explanation rewrite
2. PDF report
3. Guardian second window
4. Caller-ID metadata
5. Replay heuristic
6. Timeline strip
7. WebSocket streaming
8. Codec augmentation
9. Spoof branch → two-signal system
10. Live mic → recorded clips only

Cuts 1–5 cost almost nothing. **You should never reach 8.**

---

## Risk register

| Risk | P | Mitigation | Owner |
|---|---|---|---|
| Model download fails on venue wifi | High | Downloaded at H0, verified offline | A |
| Contract drift breaks the frontend | High | Frozen H0:45; changes announced as "CONTRACT CHANGE" | C |
| Clone quality too poor to convince | Med | Smoke-tested at H1 with a 20-min timebox | A |
| Whisper too slow on the demo laptop | Med | `small` + int8; pre-transcribe demo clips | B |
| Threshold recalibration silently breaks a scenario | Med | `test_scenarios.py` after every change | A |
| Four strong modules that don't fit together | **High** | Frozen contract + one-branch-at-a-time integration | C |
| Live mic fails on stage | High | Never planned as primary | D |
| Under-investing in the pitch | **High** | Floater rule + four rehearsals | All |

---

## Non-negotiables

1. You only write in your own folder.
2. Contract frozen at H0:45.
3. No new features after H12:00.
4. Backup video at H11:00.
5. Every A/B function returns a valid object on failure — never raise into C.
6. All models downloaded at H0.
7. The demo runs with wifi OFF. Verified at H10:30.
