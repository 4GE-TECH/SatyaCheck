# SatyaCheck

**Verify the voice, not just the number.**

A voice-clone scam detector that answers three questions — *is this the person you think it is*, *is this speech synthetic*, and *what are they actually asking for* — then explains its verdict with cited evidence rather than a confidence number.

Built for India's voice-fraud wave. No telecom integration, no OS-level call access, no model training.

---

## Why it exists

Three seconds of audio from an Instagram reel is enough to clone a voice. A cloned "son" calls a mother, claims an emergency, and asks for money over UPI. Checking the number fails — it's spoofed or newly issued. Trusting your ears fails — cloned voices have crossed the threshold where humans cannot reliably tell.

SatyaCheck supplies a third signal, and shows its working.

---

## How it works

```
audio → normalise → VAD → quality gate → rolling session buffer
   ├── identity      ECAPA-TDNN embedding vs. enrolled voiceprint
   ├── intent        Whisper → BGE-m3 → FAISS over a scam-playbook corpus
   └── authenticity  anti-spoof per segment, gated by intent
→ mode-aware fusion → trust score + band + cited reason codes
```

**Key idea:** synthetic voice is a risk *multiplier*, not a risk *source*. Bank IVRs are synthetic and legitimate. AI voice only matters in the presence of identity mismatch or scam intent.

**Capture without call-audio access:** put the caller on speakerphone and let the mic listen. Mic permission is freely granted; call-audio access is not. Also accepts WhatsApp voice notes and uploaded recordings.

---

## Quick start

### Requirements
Python 3.11+, Node 18+, `ffmpeg` on PATH. CPU-only works.

### Install

```bash
git clone <repo> satyacheck && cd satyacheck
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Download every model to ./models/ — DO THIS FIRST, before anything else
python scripts/download_models.py

cd web && npm install && cd ..
```

### Verify it runs offline

```bash
# turn wifi OFF, then:
python scripts/download_models.py --verify
```
If anything downloads on the second run, it wasn't cached.

### Run

```bash
# terminal 1
uvicorn server.main:app --reload --port 8000

# terminal 2
cd web && npm run dev          # http://localhost:5173
```

### Try it

```bash
# enroll a person
curl -F person_id=arjun -F name=Arjun -F relationship=family \
     -F files=@data/demo_clips/arjun_enroll.wav \
     http://localhost:8000/api/enroll

# screen a call
curl -F file=@data/demo_clips/arjun_cloned_scam.wav \
     http://localhost:8000/api/screen | jq
```

---

## Repo layout

```
satyacheck/
├── contracts.py          frozen Pydantic data contract — do not edit
├── config.py             thresholds and weights
├── audio_ml/             embeddings, enrollment, verification, spoof, fusion
│   └── eval/             the 12-scenario matrix + metrics harness
├── nlp_rag/              ASR, scam corpus, retrieval, markers, reason codes
│   └── corpus/           ~150 scam-playbook documents (bilingual)
├── server/               FastAPI, SQLite, WebSocket, reports
├── web/                  React + Vite frontend
├── models/               downloaded checkpoints (gitignored)
└── data/                 enrollments, cohort, eval set, demo clips
```

---

## Models used (all pretrained, none fine-tuned)

| Model | Purpose |
|---|---|
| `speechbrain/spkrec-ecapa-voxceleb` | 192-dim speaker embedding |
| AASIST-family anti-spoof checkpoint | synthetic-speech probability |
| `faster-whisper` small (int8) | ASR — Hindi / English / Hinglish |
| `BAAI/bge-m3` | multilingual text embedding |
| `snakers4/silero-vad` | voice activity detection |

---

## Tests

```bash
python -m audio_ml.eval.test_scenarios   # 12-scenario matrix, exits non-zero on failure
python -m audio_ml.eval.run_eval         # produces the five metrics + ablation chart
python -m nlp_rag.eval_retrieval         # retrieval precision@3
```

Run the scenario matrix after **any** threshold or fusion change. It catches the case where tightening the speaker threshold silently breaks legitimate-IVR handling.

---

## Reading the output

| Band | Meaning |
|---|---|
| 🟢 `verified` | Voice matches an enrolled person, no scam indicators |
| 🟡 `caution` | Verify before acting — voice is recognised but context is unusual |
| 🟠 `suspicious` | Elevated risk — synthetic voice or partial scam markers; proceed with caution |
| 🔴 `high_risk` | High risk — do not send money or share credentials |
| ⚪ `unverified` | Caller isn't enrolled. Normal for a genuine stranger. **Not the same as safe.** |
| ⬜ `insufficient` | Not enough clear audio to analyse. We decline to guess. |

`unverified` is deliberately not green. Green means "we verified this person," and for a stranger we verified nobody.

`suspicious` differs from `high_risk`: synthetic voice is detected but scam intent is low or absent (e.g. an unrecognised automated caller). It warrants verification, not panic.

---

## Troubleshooting

**Mic doesn't work in the browser.** Browsers only permit `getUserMedia` on `localhost` or HTTPS. Use `http://localhost:5173`, not a LAN IP.

**Models re-download every run.** `models/` isn't being found. Check `MODELS_DIR` in `config.py` and run from the repo root.

**Whisper is slow.** Use `small` with `compute_type="int8"`. `medium` is not viable on a laptop CPU.

**Everything scores amber.** Thresholds are uncalibrated. Run the calibration step on your own recorded clips, then re-run the scenario matrix.

---

## Limitations, stated openly

- Evaluated on ~30 clips from 4 consented speakers. Real deployment needs thousands.
- Speaker verification degrades roughly 7–8% relative at 8 kHz and collapses below 4 kHz.
- Anti-spoof models generalise poorly to unseen synthesis systems — a documented, field-wide problem. This is why we use three independent signals rather than one.
- Distribution is unsolved. The realistic path is through banks, telcos or government portals, not the app store.

---

## Ethics

Voice cloning for demo assets uses **teammates only, with explicit consent** — never a public figure. Output is framed as an assistant, never an accusation. No audio leaves the machine. Enrolled voiceprints are derived embeddings, not recordings.

---

## Docs

- `PRD.md` — problem, users, requirements, success metrics
- `PLAN.md` — 15-hour build plan, roles, gates
- `CLAUDE.md` — coding-agent operating instructions
- `SKILL.md` — reusable skill for working in this codebase
