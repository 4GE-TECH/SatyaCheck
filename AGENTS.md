# AGENTS.md: onboarding for Codex

You are picking up SatyaCheck mid-stream on branch `demo-exotel`, with no memory of earlier
sessions. This file is what you need to work safely here. Read it first, then `CLAUDE.md`,
which is binding for every agent (not only Claude). `PRD.md` covers product intent and
`PLAN.md` covers schedule.

---

## 1. What SatyaCheck does

It screens a phone call for voice-cloning scams. Three independent signals are fused into a
trust score (0–100) with cited reason codes:

| Signal | Question | Model |
|---|---|---|
| identity | Is this the enrolled person? | ECAPA-TDNN embedding vs voiceprint |
| authenticity | Is the speech synthetic? | "Model A", AASIST fine-tuned by the team |
| intent | What is being asked? | faster-whisper → BGE-m3 + FAISS retrieval + regex markers |

The output is a band (`verified`, `unverified`, `caution`, `suspicious`, `high_risk`,
`insufficient`), never a binary "scammer" verdict.

---

## 2. Rules you must follow

**From the user:**
- **Do not commit or push** unless the user asks you to in this session. Never push to `main`
  and never force-push. If asked to push, push to `demo-exotel` only.
- **`contracts.py` is frozen.** Any field change needs the user's explicit approval, one change
  at a time. Propose it; don't make it.
- Folder ownership: `audio_ml/` → A, `nlp_rag/` → B, `server/` + `contracts.py` + `config.py` → C,
  `web/` → D, `acquisition/` → person 2. The user is **B** and has approval from A, C and D to
  edit their folders, so you may edit all of them. Contract changes still need approval.
- **No secrets in the repo.** The Exotel credentials and the live-feed token live only outside
  the repo, on the user's machine. Never write them into files, logs or commit messages.
- **Model A stays on** (`USE_REAL_SPOOF=true`). The user has rejected turning it off. Do not
  propose that.
- **Write the tests first.** Each fix starts with a failing test that describes the live
  symptom.

**From `CLAUDE.md`. These are the ones most often broken:**
- We train nothing. All models are pretrained inference (Model A is the one documented exception).
- No runtime network calls: everything loads from `./models/`. CPU must work.
- Public functions never raise. They catch, log and return the neutral default. When a branch
  degrades, **log why**: silent neutral defaults are this codebase's recurring bug.
- `unknown` speaker = neutral risk 0.5, not guilty. Never show green in `authority_check`.
- A synthetic voice is a **multiplier gated by intent**, not a risk source on its own. Bank
  IVRs are synthetic and legitimate.
- Markers work both ways. Exculpatory markers ("call Papa", "talk to the doctor") lower risk.
- Never validate an audio source by sample count. Check amplitude.
- No LLM on the critical path. No generated reason-code text. No 4th weighted signal.

---

### Accounts and data isolation (upgrade plan, Phase 1)

- **Every request acts for one account** (`server/auth.py`): a Supabase access token
  (RS256/ES256 from the project's JWKS), or in `AUTH_MODE=dev` (never production) the
  dev account `DEV_OWNER_ID`. WebSockets authenticate with their first message
  `{"type": "auth", "token": ...}`, never in the URL.
- **Every query is owner-scoped.** Routers take `owner_id = Depends(current_owner)` and
  `db = Depends(get_owner_db)`, and still filter by `owner_id` themselves (SQLite has no
  RLS). Every `voiceprint_store` function has a required `owner_id`. Screening passes the
  owner down to `_speaker_candidates(owner_id)`; with no owner it compares against nobody.
  Another account's row must answer exactly like a missing one (404, not 403).
- **Postgres row-level security** is the second wall (`server/migrations/`): the app role
  is filtered by `app.owner_id`, set per transaction in `server/database.py`.
- **Retention:** audio 30 days, results 90 days, voiceprints until deleted
  (`server/retention.py`, `python -m server.retention` daily). `DELETE /api/account?confirm=DELETE`
  erases one account.
- **Not yet erased by account deletion:** the evidence log (append-only Merkle tree, off
  by default). Its leaves hold an alert summary; redaction that keeps proofs valid is an
  open item.

## 3. Environment

- **The Python on the user's machine is 3.14** (CLAUDE.md says 3.11). Windows 11; Git Bash and
  PowerShell are both available.
- `models/` (7.3 GB) is **git-ignored**. If it's missing (e.g. in a cloud sandbox), tests that
  need real models skip or fail. That is expected, not a regression; say so rather than
  "fixing" it.
- The user's main checkout is `C:\Dev\personal\SatyaCheck_MRDU\SatyaCheck`. This branch lives
  in the worktree `C:\Dev\personal\SatyaCheck_MRDU\wt-demo`, where `models/` is a junction.
- `data/sessions/`, `*.db` and `models/` are git-ignored. Never add `data/satyacheck.db.bak`
  or call audio to a commit.

### Commands

```bash
python -m audio_ml.eval.test_scenarios        # 12-scenario fusion gate: must exit 0 after ANY threshold/fusion change
python -m pytest audio_ml/tests nlp_rag/tests server/tests acquisition -q   # full suite, ~6 min with models
python -m pytest server/tests/test_runner.py -q                             # fast, targeted
```

The last full run passed (1413 passed, 2 xfailed) before the latest round of changes, which
is listed in section 6. That round has only had targeted tests and a replay.

### Live demo (user's machine only)

The backend runs from `wt-demo` with uvicorn on port 8000, behind a Cloudflare quick tunnel
(`--protocol quic`, because the network intercepts TLS). Exotel's Stream applet connects
to `wss://<tunnel>/<EXOTEL_WS_PATH>` with Basic auth. The user's private start script sets
the environment:

```
ENABLE_EXOTEL=true  EXOTEL_BASIC_USER/PASS=<secret>  LIVE_FEED_TOKEN=<secret>
RETAIN_SESSION_AUDIO=true  EXOTEL_TRACK=inbound  LOG_LEVEL=INFO
```

The backend log is at `C:\Dev\personal\SatyaCheck_MRDU\backend.log.err`. You can't run the
live demo yourself. The user places test calls and pastes the log.

---

## 4. Where things are

```
acquisition/            transport adapters → 16 kHz s16le AudioFrames (contracts C1)
  exotel/decoder.py     Exotel JSON events (connected/start/media/stop) → frames; counters + summary log
  exotel/router.py      WS endpoint: auth, reader/consumer queue (keeps up with real time)
  exotel/codec.py       mu-law decode, streaming resampler 8k → 16k
  app_ws.py, upload.py  the app's WS chunks and uploaded files → frames
  _stream_session.py    shared reader/consumer queue (Exotel, WebRTC)
  webrtc/agent.py       LiveKit screening agent: one per app-to-app call, a voice per listener
  webrtc/frames.py      LiveKit 10 ms int16 buffers → 0.5 s AudioFrames
server/webrtc_*.py      app-to-app calls: router (verified sign-in only), call codes, tokens + agents
server/live_presenter.py what a live listener is shown (alerts, band, coverage); v2 WS and WebRTC
webrtc/                 hand-off docs and LiveKit config for the Expo app (EXPO.md, BACKEND_API.md)
server/pipeline/
  buffer.py             SessionBuffer: 9 s windows, 2 s hop
  transcript_worker.py  out-of-band ASR (verdicts never wait for it)
  runner.py             SessionRunner: per window → screen_window → session logic → dispatch
  dispatcher.py         sinks: app_overlay, guardian, report, live_feed (+ evidence)
server/orchestrator.py  screen_window / screen_audio, _compute_fusion (calls the core), _phone_channel_identity
audio_ml/fusion_core.py THE fusion arithmetic (gate, weights, renormalisation, floors); the gate
                        and the live path both call it. USE_REAL_FUSION is gone.
server/voiceprint_store.py  the one voiceprint store (DB): save_voiceprints / get_candidates
server/person_views.py  persons/enroll responses: no embeddings, no answer hashes
scripts/import_npz_voiceprints.py  legacy data/enrollments/*.npz -> DB (--dry-run, --owner,
                        --archive, --reconcile, --rollback)
server/escalation.py    EscalationGate: persistence (N windows) + optional latch
server/main.py          app, /api/health, _RetainingRunner (saves Exotel call audio), mount_exotel
server/live_feed.py     /api/ws/live message (contract: docs/LIVE_FEED.md, SCHEMA_VERSION 1)
audio_ml/spoof.py       detect_spoof, phone-channel calibration, _phone_verdict
nlp_rag/asr.py          faster-whisper + per-segment confidence gating
nlp_rag/markers.py      MK_* regex markers (incriminating + exculpatory)
nlp_rag/thresholds.py   ASR / retrieval thresholds
config.py               every flag; read env at import
```

Cross-folder imports are allowed only through `audio_ml.api`, `nlp_rag.api` and `acquisition.api`.

**Voiceprints live in the database only.** `/api/enroll` computes vectors in memory
(`audio_ml.api.compute_voiceprint`) and writes person + vectors + secrets in one
transaction; screening passes `voiceprint_store.get_candidates()` to `verify_speaker`.
The legacy `.npz` people were deleted on 2026-10-10; `LEGACY_NPZ_FALLBACK` is off by
default (opt-in for dev only, forced off when `SATYACHECK_ENV=production`).

---

## 5. Lessons from live Exotel calls

Each lesson below was a real bug. Don't undo the fixes.

| Seen live | Cause | Fix (where) |
|---|---|---|
| No audio arrived | Exotel flow ended right after the Stream applet | The flow needs a Connect applet after Stream (Exotel config, not code) |
| Media rejected | Exotel sends `encoding: "base64"` | Treated as base64 s16le PCM (`decoder.py`) |
| Last ~20 s never scored | The reader was blocked by scoring | Reader/consumer split; `runner.push(score=False)` defers and scores the newest window (`router.py`, `runner.py`) |
| Genuine caller read "suspicious" | Model A scores high on 8 kHz audio | Narrowband detected from the audio → scores calibrated, `SPOOF_PHONE_THRESHOLD=0.973` (`spoof.py`) |
| One-window spike flagged "cloned" | | Phone line needs a synthetic run of at least `SPOOF_PHONE_MIN_SYNTH_RUN_S=6.0` |
| Stranger read "mismatch" (cosine 0.61–0.77) | Phone audio inflates similarity | Below `SPEAKER_PHONE_MISMATCH_FLOOR=0.80` → `unknown` (`orchestrator.py`) |
| "OTP" heard as "ODP" / "OTB" / "O T P" | Whisper on 8 kHz audio | Variants in `MK_OTP_SOLICITATION` (`markers.py`) |
| Transcript always `low_confidence` | Mean logprob over the whole call; garbled bits sank clear ones | Per-segment gating; logs counts, never text (`asr.py`) |
| Clear speech gated `no_speech` | Cloned voice: no_speech 0.76 at logprob −0.24 | A confident segment (≥ −0.5) is speech unless no_speech ≥ 0.9 (`asr.py`, `thresholds.py`) |
| Final said "not synthetic" after ~25 synthetic windows | Final verdict = last window only | 3 synthetic windows in a row (`SESSION_SYNTH_LATCH_WINDOWS`) latch the call's authenticity (`runner._session_authenticity`) |
| Harmless synthetic call stuck at suspicious 39.8 | Session latch + trust floor; intent read as 0.5 before the transcript arrived | `SESSION_LATCH_WARNINGS=false` (default): the session follows its evidence, and the final verdict is the whole call's own fusion (`escalation.py`, `runner._emit`) |

Exotel sends `track=None`, and the callee is audible in the stream, so treat it as both
sides mixed.

**What a real voice can reach (changed by the upgrade plan, Phase 0).** Fusion now has the
intent floor: unless the caller matched an enrolled person, risk is at least the script
risk. A genuine human reading a blatant bank-OTP script (intent ~0.71) now reaches
**high_risk**, where it used to top out at caution. A verified contact damps intent to
0.55x (an odd request from real family lands caution). Floors live in config
(`FUSION_*`) and `audio_ml/fusion_core.py`.

---

## 6. Current state and open items

**Not yet committed (latest round, live on the user's backend):** per-segment ASR gating,
the `no_speech` rule, Exotel call-audio retention (`_RetainingRunner`), the synthetic run
latch, the non-latching session plus whole-call final verdict, and their tests
(`test_asr_segment_gate.py`, `test_exotel_retention.py`, `test_escalation_no_latch.py`, and
additions to `test_runner.py`).

**Not yet run on that round:** the full suite and `test_scenarios`. Run both before
anything else.

**Open, with nothing decided yet:**
1. **Synthetic voice with no transcript yet.** The live score dips to ~40 for 9–14 s, because
   intent defaults to 0.5 until speech recognition catches up. Option: don't confirm a warning
   when it rests only on authenticity with text abstaining. Ask the user first.
2. **Strong scam wording with a real voice ends at caution.** The user may want
   "bank/authority impersonation + OTP" to reach suspicious on its own: a combined marker or
   playbook, followed by a re-run of `test_scenarios` (the legitimate bank-IVR case must stay
   non-red).
3. **The app WebSocket path (`ws_router`) still latches** unless `USE_PIPELINE_RUNNER` is on.
   Only the Exotel runner path got the new session rules.
4. **Post-demo flips (PLAN Phase 1):** `USE_REAL_SPOOF` default off, the retention defaults to
   private, and import-order fix 18b.

**Replaying a call.** Retained calls are saved to `data/sessions/<id>/chunk_0000.wav`. Feed
them through `SessionRunner` with real branches and a temp SQLite DB (not
`data/satyacheck.db`) to reproduce a live verdict offline.

---

## 7. How to report back

Say what changed, which tests ran and what they printed, and what you couldn't verify (e.g.
"no models in this sandbox"). The user re-tests live calls themselves.
