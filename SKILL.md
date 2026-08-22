---
name: satyacheck-dev
description: Build, extend, debug, or evaluate the SatyaCheck voice-clone scam detector — a multi-signal system fusing speaker verification (ECAPA-TDNN), anti-spoofing, and RAG-based scam-script matching into an explainable trust score. Use this skill whenever work touches speaker embeddings, voiceprint enrollment, audio deepfake or anti-spoof detection, spoofing-aware speaker verification (SASV), scam-call or vishing detection, scam-script corpora, trust-score fusion, or any file inside audio_ml/, nlp_rag/, or server/. Also use it for adjacent tasks that only mention voice fraud, call screening, deepfake audio, or "is this voice real" — the domain rules here are counterintuitive and getting them wrong silently produces a system that flags every legitimate caller.
---

# SatyaCheck Development

A skill for working on SatyaCheck: a voice-clone scam detector that fuses three independent signals and explains its verdicts with retrieved citations.

## Orientation

Read in this order before writing code:
1. `PRD.md` — what we're building and the product decisions behind it
2. `CLAUDE.md` — hard rules, module boundaries, conventions
3. `PLAN.md` — only if the question is about schedule or scope

## The core mental model

Three independent signals, each answering a different question:

| Signal | Question | Module |
|---|---|---|
| Identity | Is this the enrolled person? | `audio_ml/verify.py` |
| Authenticity | Is this speech synthetic? | `audio_ml/spoof.py` |
| Intent | What are they asking for? | `nlp_rag/retrieve.py` |

They are fused, not averaged: **intent gates authenticity**. Each signal fails for unrelated reasons, so all three failing simultaneously on the same call is unlikely — this is the design answer to the documented brittleness of single-model deepfake detectors on unseen synthesis systems.

## Domain rules that are counterintuitive

Violating any of these produces a system that appears to work and is quietly useless. Do not simplify them.

### `unknown` is not `mismatch`

Speaker verification has **three** verdicts. `unknown` means no enrolled person is close — the normal state for a genuine stranger. It contributes **risk 0.5, neutral**, never guilt. Collapsing three verdicts into two turns every real bank, delivery driver and doctor red.

### Synthetic voice is a multiplier, not a source

```python
intent   = max(script_risk, identity_risk if verdict == "mismatch" else 0.0)
r_cm_eff = r_cm * (CM_FLOOR + (1 - CM_FLOOR) * intent)
```

AI voice is not a crime. Bank IVRs, hospital reminders and delivery confirmations are all synthetic and legitimate. Without this gate, a legitimate automated call scores amber and the product loses credibility on its first false positive.

### Never green for an unverified caller

In `authority_check` mode the band is `unverified`, rendered neutral grey. Green means "we verified this person." A system that confidently reassures about a stranger will eventually get someone robbed.

### Median hides hybrid attacks

Anti-spoof aggregation reports `median` (headline), `peak` (short bursts), `max_synth_run_s` (the real signal), and a segment `timeline`. A scammer who switches to a cloned voice only while asking for the OTP is invisible to a median.

### Markers run both directions

Incriminating markers raise risk; **exculpatory markers lower it**. A genuine emergency invites verification ("call Papa", "talk to the doctor", "come here"); a scam demands isolation ("don't tell anyone", "stay on the line"). Isolation is structurally load-bearing for fraud — one callback destroys it. This asymmetry is the only reliable way to separate a real emergency from a scripted one, and it is what prevents flagging a friend calling about a real accident.

### Enrollment must be condition-matched

Store a voiceprint per acoustic condition (wideband and 8 kHz codec-degraded). Comparing a phone-quality probe against a studio-quality reference measures channel difference as much as speaker difference. Speaker embeddings lose only ~7–8% relative at 8 kHz but collapse below 4 kHz — the 2–4 kHz band carries the speaker information.

### Normalisation is load-bearing

S-normalise every branch score against a background cohort before fusing. The published SASV result — EER 23.83% → 1.71% from plain score-sum with no training — holds **only** with normalised scores. Naive summation of raw scores is meaningless.

### An anomalously perfect match is a replay

Live speech from an enrolled person scores roughly 0.65–0.80. A cosine above 0.95 means the audio *is* a stored recording, played back. Flag `REPLAY_SUSPECTED` rather than treating it as a stronger match. An LA-trained anti-spoof model will not catch replay — replayed human speech genuinely is human speech.

### Refusing to score is correct behaviour

Below 1.5s of speech or 5 dB SNR, return `band: "insufficient"`. Confidently scoring 0.4 seconds of noise destroys trust in every other verdict.

## Workflow

### Adding or changing any signal

1. Read `contracts.py`. It is frozen — extend, never rename or reorder.
2. Implement inside your own folder only.
3. Return a valid contract object on every path, including failure. Never raise into the caller.
4. Add a `__main__` smoke test.
5. **Run `python -m audio_ml.eval.test_scenarios`. It must exit 0.**

### Changing thresholds, weights or calibration

Always re-run the twelve-scenario matrix. It executes at signal level in under a second and is the only thing catching the case where tightening the speaker threshold silently breaks legitimate-IVR handling. Two scenarios exist specifically as over-flagging guards: legitimate AI voice must not be red, and a genuine family member making an unusual request must be amber.

### Extending the scam corpus

Every document needs a real `source_url` — that URL is what makes the evidence panel a citation rather than a claim. Write each script in both English and Hindi/Hinglish as separate documents; real calls are code-switched and an English-only corpus fails silently on actual audio. Rebuild the index after adding documents.

### Debugging "everything scores amber"

Thresholds are uncalibrated. Check in this order: is s-normalisation running against a populated cohort; are enrolled and probe conditions matched; is `CM_FLOOR` too high; is `intent` being computed from `script.risk` or defaulting to zero.

## What not to do

- Do not train or fine-tune anything. If a task seems to need training, the design is wrong.
- Do not add a fourth weighted signal. Caller-ID metadata enriches the explanation, never the score.
- Do not put an LLM on the critical path. `ENABLE_LLM_REWRITE` defaults to `False`; reason codes are deterministic templates.
- Do not emit binary verdicts. Output a score with evidence, never "this is a scammer." False accusation inside a family is a real harm.
- Do not use browser storage APIs in `web/`.
- Do not make runtime network calls. Everything loads from `./models/`.

## Ethics

Voice cloning for test or demo assets uses consenting teammates only — never a public figure or a real third party. The system is positioned as an assistant that recommends verification, never as an authority that determines fraud.
