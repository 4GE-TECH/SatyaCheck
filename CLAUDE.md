# CLAUDE.md

Operating instructions for any coding agent working in this repository.
Read this before writing code. Read `PRD.md` for product intent and `PLAN.md` for schedule.

---

## What this is

SatyaCheck detects voice-cloning scam calls and explains why it flagged them. Given audio, it fuses three independent signals — **identity** (is this the enrolled person), **authenticity** (is the speech synthetic), and **intent** (what is being asked) — into a trust score with cited reason codes.

Hackathon build: 15 hours, 4 people, hard feature freeze.

---

## Hard rules

1. **We train nothing.** Every model is pretrained inference. If a task seems to need training, the design is wrong — re-read the PRD.
2. **Folder ownership is absolute.** `audio_ml/` → A · `nlp_rag/` → B · `server/` + `contracts.py` + `config.py` → C · `web/` → D. Never edit another owner's folder. Propose the change instead.
3. **`contracts.py` is frozen.** Three people code against it. Do not rename, reorder or "improve" fields. Contract changes are announced out-of-band before being made.
4. **No runtime network calls.** Everything loads from `./models/`. The demo runs with wifi off.
5. **Public functions never raise.** Catch internally, log, return the neutral default from the contract. A branch failing must degrade the verdict, not fail the request.
6. **CPU must work.** GPU is an optimisation, never a requirement.
7. **CLI-testable before importable.** Every module gets a `if __name__ == "__main__"` smoke test.

---

## Architecture

```
audio (mic / upload / voice note)
  → ffmpeg normalise 16k mono → VAD → quality gate
  → rolling session buffer (3s chunks, 1s overlap, state persists)
      ├─ identity      : ECAPA-TDNN embedding vs enrolled voiceprint
      ├─ intent        : faster-whisper → BGE-m3 → FAISS + regex markers
      └─ authenticity  : anti-spoof per chunk, GATED BY INTENT
  → mode-aware fusion (renormalised) → trust score + band
  → reason codes with citations → actions
```

### Module boundaries — the only cross-folder imports

```python
from audio_ml.api import enroll_person, verify_speaker, detect_spoof, fuse, add_flagged_voice
from nlp_rag.api  import transcribe, analyze_script, build_reason_codes, challenge_question
```

Nothing else crosses a folder boundary. Ever.

---

## Domain rules that are easy to get wrong

These encode decisions that took real thought. Do not "simplify" them.

### Speaker identity has THREE verdicts
`match` · `mismatch` · `unknown`.

**`unknown` is neutral (risk 0.5), not guilty.** It means no enrolled person is close — which is the normal state for a genuine stranger. Treating it as guilty makes every real bank, delivery driver and doctor red, and the product becomes noise.

### Two modes, auto-selected
`unknown` → `authority_check`, speaker branch abstains, weights shift to `{asv .10, cm .45, text .45}`.
Otherwise → `identity_check`, weights `{asv .40, cm .35, text .25}`.

### Never show green in `authority_check`
Band is `unverified`, rendered neutral grey. Green means "we verified this person." We verified nobody.

### Synthetic voice is a multiplier, not a source
```python
intent   = max(script_risk, identity_risk if verdict == "mismatch" else 0.0)
r_cm_eff = r_cm * (CM_FLOOR + (1 - CM_FLOOR) * intent)
```
Bank IVRs are synthetic and legitimate. Without this gate, every legitimate automated call goes amber.

### Spoof aggregation reports THREE statistics
`median` (headline) · `peak` (short bursts) · `max_synth_run_s` (the real signal) · plus a segment `timeline`.
Median alone hides hybrid attacks, where a scammer switches to a cloned voice only for the sensitive part.

### Markers are bidirectional
Incriminating markers raise risk. **Exculpatory markers lower it.** A genuine emergency invites verification ("call Papa," "talk to the doctor"); a scam demands isolation ("don't tell anyone," "stay on the line"). Isolation is structurally load-bearing for fraud — remove it and one callback destroys the scam. This is what prevents us from flagging a real friend calling about a real accident.

### Enrollment is condition-matched
Store a voiceprint per acoustic condition (wideband + 8 kHz codec-degraded). Comparing a phone-quality probe against a studio-quality reference measures channel difference as much as speaker difference.

### Score normalisation is not optional
Z-normalise / s-normalise each branch score before fusing. The published SASV result (EER 23.83% → 1.71% from plain score-sum, no training) holds **only** with normalised scores. Uncalibrated summation is meaningless.

### Refusing to score is a feature
Below 1.5s of speech or 5 dB SNR, return `band: "insufficient"` and do not score. A system that outputs a confident number on 0.4 seconds of noise is a system nobody should trust.

---

## Conventions

- Python 3.11, type hints on public functions, `from __future__ import annotations`
- Pydantic v2 for all contract objects
- FastAPI + uvicorn + SQLite (sqlalchemy)
- React 18 + TypeScript + Tailwind + Recharts. No component library. **No browser storage APIs.**
- Handle Hindi, English and code-switched Hinglish everywhere. Never assume English-only input.
- Sentence case in UI copy. Large type — a judge reads this from three metres away.
- Run the three branches **concurrently** (`asyncio.to_thread` / `ThreadPoolExecutor`). They are independent; serial execution triples latency for nothing.

---

## Before you commit

```bash
python -m audio_ml.eval.test_scenarios   # must exit 0
```

The twelve-scenario matrix runs at signal level in under a second. Run it after **any** threshold or fusion change. It is the only thing standing between a calibration tweak and silently breaking the legitimate-IVR case.

---

## Do not

- Add a fourth weighted signal. Caller-ID metadata enriches the *explanation*, never the score — a fourth weight means recalibrating everything.
- Put an LLM on the critical path. `ENABLE_LLM_REWRITE` exists and defaults to `False`. Latency variance kills demos.
- Replace deterministic reason-code templates with generated text.
- Use `localStorage` or `sessionStorage` anywhere in `web/`.
- Emit a binary verdict. We output a score with evidence, never "this is a scammer." False accusation inside a family is a real harm.
- Add features after the freeze.
