# Handoff: demo-exotel branch

> Superseded by `AGENTS.md`, which has the current state. Kept for history.

For a coding agent picking this branch up in a fresh session (e.g. a cloud session) with no
memory of earlier work. Read `CLAUDE.md` first; everything there still applies.

## Working rules carried over

- The user is **B** (`nlp_rag/`) and has approval from A, C and D to edit their folders.
  **`contracts.py` changes still need the user's explicit approval, one at a time.**
- Do not commit or push unless the user asks; never push to `main`, never force-push.
- No secrets in the repo. Exotel credentials and the live-feed token live only in files
  outside the repo on the user's machine.
- Tests first for every change. Before finishing: `python -m audio_ml.eval.test_scenarios`
  (must exit 0) and `pytest audio_ml/tests nlp_rag/tests server/tests acquisition`.

## Environment limits in a cloud session

- `models/` (7.3 GB: faster-whisper, BGE-m3, ECAPA, AASIST Model A) is **git-ignored and not
  present**. Tests that need real models will skip or fail there; that is expected, not a
  regression. The last full run on the user's machine: **1413 passed, 2 xfailed**.
- The live Exotel demo (backend + Cloudflare tunnel + models) runs **only on the user's
  machine**. A cloud session does code and model-free tests; the user re-tests live calls.

## State of the branch

The 19-item upgrade plan is merged here: Exotel Stream adapter (`acquisition/exotel/`),
C1 transport-agnostic contracts, session buffer, out-of-band transcript worker,
`SessionRunner` + dispatcher (sinks: app_overlay, guardian, report, live_feed),
escalation persistence, OOD abstention, threat label, caller context, EER / t-DCF eval,
codec augmentation, latency / FP measurement, retention flags, consent, Merkle evidence log.

Live-call fixes from real Exotel calls (latest commit on top of `2fa492f`):

| Problem seen live | Fix | Where |
|---|---|---|
| Exotel sends `encoding: "base64"` | treated as base64-wrapped s16le PCM | `acquisition/exotel/decoder.py` |
| Last ~20 s of a call never scored | reader/consumer split; runner scores only the newest window when behind (`push(score=False)` defers) | `acquisition/exotel/router.py`, `server/pipeline/runner.py` |
| Genuine phone caller read "suspicious" | phone-channel calibration of Model A scores (narrowband detected from audio, `SPOOF_PHONE_THRESHOLD=0.973`) | `audio_ml/spoof.py`, `config.py` |
| Single-window synthetic spike called "cloned" | phone line needs a synthetic run ≥ `SPOOF_PHONE_MIN_SYNTH_RUN_S=6.0` | `audio_ml/spoof.py::_phone_verdict` |
| Stranger read "mismatch" vs enrolled contact (cos 0.61–0.77) | phone line: mismatch below `SPEAKER_PHONE_MISMATCH_FLOOR=0.80` → unknown | `server/orchestrator.py::_phone_channel_identity` |
| Whisper hears "OTP" as "ODP" / "OTB" / "O T P" | variants added to `MK_OTP_SOLICITATION` | `nlp_rag/markers.py` |
| Trust score stuck (session floor only falls) | live feed adds `window_trust_score` / `window_band` | `server/live_feed.py`, `docs/LIVE_FEED.md` |

The user rejected turning Model A off; do not propose that again.

## Open items

1. **Intent too low for "bank caller asks for OTP".** The last live transcript scores
   intent 0.31 (0.35 spelled correctly): `MK_OTP_SOLICITATION` fires alone, no scam family
   or playbook matches, so the band is caution. Option offered to the user, not yet agreed:
   a combined marker or playbook for bank/authority impersonation + OTP request. Re-run the
   12-scenario gate afterwards (legitimate bank IVR must stay non-red, and exculpatory
   markers must still lower risk).
2. Exotel sends `track=None`: caller and victim may be mixed in one stream. Unverified
   whether the stream is caller-only; the user can test by having only the victim speak.
3. Plan follow-ups after the demo (see the plan's Phase 1): flip `USE_REAL_SPOOF` and the
   retention defaults; import-order fix 18b.
