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
cd web3 && npm run dev         # http://localhost:5175
```

Without a `.env`, the server uses SQLite at `data/satyacheck.db` and `AUTH_MODE=dev`: every
request acts for one local dev account, so nothing needs signing in. Copy `.env.example` to
`.env` to use Postgres and sign-in (below).

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

## Accounts and sign-in

Every person, voiceprint, screening and report belongs to one account. Sign-in is an emailed
6-digit code (Supabase Auth). There are no passwords.

| Setting | Dev (default) | Production |
|---|---|---|
| `AUTH_MODE` | `dev`: requests without a token act as `dev-owner` | `jwt`: a Supabase access token on every request (forced when `SATYACHECK_ENV=production`) |
| Database | SQLite, `data/satyacheck.db` | Postgres with pgvector (Supabase, or the compose `db` service) |
| Isolation | owner filters in every query | owner filters **and** Postgres row-level security as the `satyacheck_app` role |

- **Sockets:** a WebSocket signs in with its first message (`{"type": "auth", "token": ...}`,
  or the `token` field of the v2 `start` message), never with the URL.
- **Web app:** set `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` at build time to turn
  sign-in on. The session is held in memory only; there is no browser storage.
- **Mobile app:** pass `--dart-define=SATYACHECK_SUPABASE_URL=...` and
  `--dart-define=SATYACHECK_SUPABASE_ANON_KEY=...`.
- **Supabase dashboard:** email OTP must be enabled, with an email template that contains
  `{{ .Token }}`.

Migrations run as the database owner (`DATABASE_ADMIN_URL`), never as the app:

```bash
python -m alembic -c server/migrations/alembic.ini upgrade head
python -m server.retention          # retention sweep (cron it daily)
```

`DELETE /api/account?confirm=DELETE` removes everything an account owns.

---

## Deploy

```bash
export POSTGRES_PASSWORD=... SATYACHECK_APP_DB_PASSWORD=... SUPABASE_URL=https://<ref>.supabase.co
docker compose up --build                                                  # CPU
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build  # NVIDIA GPU
```

- **The image:** one image runs on both GPU and CPU. The models are mounted read-only from
  `./models`, and the FAISS index from `./nlp_rag/index`. Neither is baked into the image.
  The container makes no network calls except to fetch the sign-in keys (JWKS).
- **Health:** `/api/ready` answers 503 until the models are warm. The container health check
  and any load balancer should use it.
- **Scaling:** run one worker per container, and scale by adding containers.
  `MAX_LIVE_SESSIONS` and `INFERENCE_CONCURRENCY` set what one container accepts.
- **Device:** the models run on the GPU when one is present (`SATYACHECK_DEVICE=auto`).
  `/api/ready` reports where each model actually loaded, any fallback, and GPU memory.
- **Capacity:** unset, `MAX_LIVE_SESSIONS` follows the device. These are the measured limits
  (`python -m scripts.measure_live_v2`, `data/measurements/live_v2_latency.json`; the gate is
  update p95 ≤ 4 s with no coverage gaps):

  | Device | Voices | Update latency (p50 / p95) | Result |
  |---|---|---|---|
  | RTX 4070 Laptop, 8 GB | 1 | 0.17 / 0.29 s | |
  | RTX 4070 Laptop, 8 GB | 4 | 1.3 / 2.5 s | **limit: 4** |
  | RTX 4070 Laptop, 8 GB | 8 | 3.2 / 5.6 s | fails the gate |
  | CPU | 1 | 2.8 / 3.9 s | **limit: 2** |
  | CPU | 4 | p95 16.7 s | fails, with gaps |

  The server uses about 3.3 GB of GPU memory however many voices it screens.
- **Device parity:** `python -m scripts.device_parity` checks that moving the models between
  CPU and GPU changes no verdict. It compares against a frozen CPU baseline.

## App-to-app calls (WebRTC)

Two people who both have the app can call each other through it, and the backend screens each
voice live for the other person. This is a real-time test path, since Android silences normal
call audio for other apps. It runs on LiveKit, self-hosted next to the backend for the lowest
latency.

- Set-up, API and the Expo app: [`webrtc/README.md`](webrtc/README.md).
- End-to-end check without phones: `python -m scripts.webrtc_smoke`.

## Operate

- **`/metrics`** is a Prometheus endpoint. It exposes request rates and timings by route
  template, inference time and queueing per branch, live sessions and refusals, assessments
  by band, and seconds of audio that could not be screened. It carries no account, number or
  transcript. When `METRICS_TOKEN` is set, a scrape must send it as a Bearer token. In
  production the endpoint answers only with that token.
- **Request IDs:** every response carries `X-Request-ID`, and every log line written while
  the request runs carries the same ID. A well-formed ID from a proxy is kept.
- **Optional LLM intent reading** (`LLM_PROVIDER`, off by default) runs in **shadow mode**.
  It is logged for comparison and has zero influence on any verdict.

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
├── server/               FastAPI, accounts, Postgres/SQLite, WebSockets (v1 + v2), reports
│   └── migrations/       Alembic: tables, the app role, row-level security
├── web3/                 React + Vite web app (sign-in, live listening over v2)
├── satyacheck_mobile/    Flutter Android app
├── models/               downloaded checkpoints (gitignored)
└── data/                 enrollments, cohort, eval set, demo clips
```

---

## Models used

All pretrained except the anti-spoof model, which is AASIST fine-tuned by the team.

| Model | Purpose |
|---|---|
| `speechbrain/spkrec-ecapa-voxceleb` | 192-dim speaker embedding |
| Model A: AASIST ([clovaai/aasist](https://github.com/clovaai/aasist), MIT), fine-tuned on IFD by the team | synthetic-speech probability |
| `faster-whisper` small (int8) | ASR — Hindi / English / Hinglish |
| `BAAI/bge-m3` | multilingual text embedding |
| `snakers4/silero-vad` | voice activity detection |

---

## Tests

```bash
python -m audio_ml.eval.test_scenarios   # 12-scenario matrix, exits non-zero on failure
python -m pytest -q                      # unit and API tests (model-dependent ones skip without ./models)
python -m audio_ml.eval.run_eval         # produces the five metrics + ablation chart
python -m nlp_rag.eval_retrieval         # retrieval precision@3
cd web3 && npm test && npm run test:ui   # web unit + browser tests
cd satyacheck_mobile && flutter test     # mobile tests and goldens
```

Set `TEST_DATABASE_ADMIN_URL` to run the Postgres row-level-security tests against a real
database. They migrate a throwaway schema and drop it afterwards. CI
(`.github/workflows/ci.yml`) runs the scenario gate, pytest, the web tests and the Flutter
suite on every pull request.

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

Voice cloning for demo assets uses **teammates only, with explicit consent** — never a public figure. Output is framed as an assistant, never an accusation. Audio goes only to the screening service you run. Nothing goes to a third party unless an
operator turns on the optional LLM shadow reading, which sends committed transcript text,
never audio. Enrolled voiceprints are derived embeddings, not recordings.

---

## Docs

- `PRD.md` — problem, users, requirements, success metrics
- `PLAN.md` — 15-hour build plan, roles, gates
- `CLAUDE.md` — coding-agent operating instructions
- `SKILL.md` — reusable skill for working in this codebase
