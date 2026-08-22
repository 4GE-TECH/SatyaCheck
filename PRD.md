# SatyaCheck — Product Requirements Document

**Version** 1.0 · **Status** Hackathon build · **Owner** Team SatyaCheck

---

## 1. Problem

A caller says something. The listener must decide, within sixty seconds and under emotional pressure, whether to send money.

Two defences exist today and both are broken:

| Defence | Why it fails |
|---|---|
| Check the caller's number | Spoofed, or a freshly-issued bulk SIM. No spam list has seen it. |
| Trust your ears | Voice cloning has crossed the threshold where humans cannot reliably distinguish cloned from authentic speech. |

Three seconds of audio harvested from an Instagram reel is enough to clone a voice. Instant payment rails make the transfer irreversible in seconds. The victim is not being careless — they have no reliable signal available.

**SatyaCheck supplies a third signal that is not the listener's ears, and explains itself with citable evidence.**

---

## 2. Users

| Role | Who | What they do |
|---|---|---|
| **Guardian** (primary) | Digitally-native adult child, bank branch helpdesk, CSC operator | Installs, enrolls the family, receives alerts |
| **Protected person** | Elderly or semi-urban parent with UPI and low fraud literacy | Hears a spoken warning; never asked to interpret a dashboard |
| **Enrolled contacts** | Family, close friends, colleagues | Record a 60-second voiceprint once |

**Explicit design decision:** the victim is not the installer. A product requiring the target of a scam to install a security app and read a trust meter mid-call will not be adopted. Enrollment is a family act; alerts fan out to people who are not panicking.

---

## 3. Goals and non-goals

### Goals
- **G1** Determine whether a caller is a specific enrolled person, not merely whether the voice is synthetic.
- **G2** Explain every verdict with signal, value, threshold and an external citation.
- **G3** Work on 8 kHz telephony-quality audio, not just clean studio recordings.
- **G4** Handle Hindi, English and code-switched Hinglish.
- **G5** Compress time-to-report from hours to seconds with a pre-filled evidence packet.
- **G6** Operate without any telecom, bank or OS-level call-audio access.

### Non-goals
- **NG1** Blocking calls. We inform; we do not intercept.
- **NG2** Binary verdicts. We output a score with evidence, never "this is a scammer."
- **NG3** Training or fine-tuning any model.
- **NG4** Real-time on-device inference. Analysis is server-side.
- **NG5** Solving distribution. Deployment runs through institutions, not the app store. Acknowledged and out of scope.

---

## 4. Key product decisions

### 4.1 Speakerphone capture, not call interception
iOS forbids call-audio access and Android heavily restricts it. Microphone access is granted freely. The caller goes on speakerphone; we listen through the mic — the same path every voice assistant uses. Also supports WhatsApp voice notes and uploaded recordings.

### 4.2 Three verdicts for speaker identity, never two
`match` · `mismatch` · **`unknown`**

`unknown` is **neutral** (risk 0.5), not guilty. Treating unknown as guilty turns every genuine stranger — a real bank, a delivery driver, a doctor — red, and the product becomes noise users learn to ignore.

### 4.3 Two operating modes, selected automatically

| Mode | Trigger | Behaviour |
|---|---|---|
| `identity_check` | Caller matches or mismatches an enrolled person | All three branches contribute |
| `authority_check` | No enrolled person is close | Speaker branch abstains; weight shifts to authenticity and intent |

### 4.4 Never show green in `authority_check`
Green means "we verified this person." We verified nobody. The band is `unverified`, rendered neutral grey, with honest copy. A system that confidently reassures about a stranger will eventually get someone robbed.

### 4.5 Synthetic voice is a multiplier, not a source
AI voice is not a crime — bank IVRs, hospital reminders and delivery confirmations are all synthetic and legitimate. Authenticity evidence is gated by intent:

```
intent   = max(script_risk, identity_risk if mismatch else 0)
r_cm_eff = r_cm * (0.25 + 0.75 * intent)
```

### 4.6 Explanation is retrieved, not attributed
Mainstream explainable deepfake detection produces internal attribution maps over spectrograms. Those have been shown to be adversarially manipulable while the prediction stays unchanged. Our explanation is an **external retrieved document with a source URL** — a different evidence type with a different attack surface.

---

## 5. Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-1 | Enroll a person from 60s of audio; store condition-matched voiceprints (wideband + 8 kHz) | P0 |
| FR-2 | Ingest audio from mic, upload, or voice note; normalise to 16 kHz mono | P0 |
| FR-3 | Quality gate: refuse to score below 1.5s speech or 5 dB SNR | P0 |
| FR-4 | Speaker verification with adaptive s-normalisation and three verdicts | P0 |
| FR-5 | Anti-spoof scoring with median, peak, max-synthetic-run and segment timeline | P0 |
| FR-6 | ASR (Hindi/English/Hinglish) → retrieval over scam-playbook corpus | P0 |
| FR-7 | Bidirectional markers: incriminating and **exculpatory** | P0 |
| FR-8 | Intent-gated, mode-aware fusion → trust score 0–100 and band | P0 |
| FR-9 | Reason codes with signal, value, threshold, citation | P0 |
| FR-10 | Spoken vernacular warning, pre-cached at enrollment | P1 |
| FR-11 | Challenge question from enrolled shared secrets | P1 |
| FR-12 | Guardian alert to a second subscribed client | P1 |
| FR-13 | Streaming session: re-scored every ~2s, monotone escalation | P1 |
| FR-14 | Report packet (JSON + PDF) with audio SHA-256, formatted for 1930 / Chakshu | P1 |
| FR-15 | Negative voiceprint list of previously-reported callers | P2 |
| FR-16 | Replay detection via anomalously high cosine (> 0.95) | P2 |
| FR-17 | Optional `claimed_number` / `claimed_identity` metadata enriching explanation only | P2 |

---

## 6. The twelve scenarios

The system is validated against twelve scenarios covering genuine calls, legitimate AI voice, human scammers, cloned family members, spoofed numbers, replay, digital arrest, Hinglish fraud, genuine-but-unusual requests, gradual escalation, and hybrid human/AI calls.

Regression harness: `audio_ml/eval/test_scenarios.py`. Runs at signal level in under a second, exits non-zero on failure, and emits `data/scenario_matrix.json`.

**Two scenarios exist specifically to prove we do not over-flag:**
- Legitimate AI voice (bank IVR) must **not** be red.
- Genuine family member making an unusual request must be **amber**, not red.

---

## 7. Success metrics

| # | Metric | Purpose |
|---|---|---|
| M1 | SASV-EER, fused vs. speaker-only baseline | Headline. Published reference: 23.83% → 1.71% via score-sum |
| M2 | Anti-spoof EER on an ASVspoof 2019 LA subset | Branch sanity |
| M3 | 8 kHz ablation: wideband / naive narrowband / condition-matched | Answers the loudest objection |
| M4 | Retrieval precision@3 on held-out transcripts | Corpus quality |
| M5 | Cross-attack generalisation (calibrate on TTS-A, test on TTS-B) | **Published even though it will look bad** |
| M6 | 12/12 scenario matrix pass | Behavioural correctness |

M5 is reported deliberately. Generalisation is the central open problem in the field; publishing our own gap is more credible than hiding it.

---

## 8. Out of scope, stated openly

- Distribution to non-technical households. Realistic path is via banks, telcos or government portals.
- Evaluation at scale. The hackathon build uses ~30 clips from 4 consented speakers.
- Real telephony integration.
- Legal determination of fraud. SatyaCheck is an assistant, not an authority.

---

## 9. Ethics

- Voice cloning for demo assets uses **teammates only, with explicit consent**. Never a public figure.
- Output is framed as an assistant, never an accusation. False accusation inside a family is a real harm.
- No audio leaves the machine in the hackathon build.
- Enrolled voiceprints are derived embeddings, not recordings.
