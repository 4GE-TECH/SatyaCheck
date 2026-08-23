# SatyaCheck — demo runbook

Every number below is measured, not estimated.

---

## Setup, in order

```bash
# 1. Backend (leave running)
python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
curl -s localhost:8000/api/health

# 2. Phone over USB
adb reverse tcp:8000 tcp:8000
adb shell am force-stop com.satyacheck     # it caches reachability at startup
```

`adb reverse` dies on **every** replug. "Cannot reach the screening server" is almost always
that, not a real failure — re-run both lines and reopen the app.

**Tap each demo caller once before presenting.** First inference loads ECAPA, Whisper and
BGE-m3; it costs a few seconds that you do not want on stage. Check media volume is up —
playback rides the music stream, not the ringer.

---

## Track A — the phone (primary)

Three tappable callers under **Demo callers**. Each plays aloud, then the verdict lands
*after* the voice stops. Everything is screened by the real backend — ffmpeg, ECAPA,
Whisper, FAISS, fusion. Nothing is mocked; the only step skipped is the microphone, which
Android forbids during a call anyway.

| tap | audio | speaker | intent | verdict |
|---|---|---|---|---|
| **Friend calling** | enrolled voice, ordinary talk | **0.9464** match | 0.059 | **verified 88.5** |
| **Friend calling — cloned** | same voice, AI clone, asks ₹40,000 | **0.7631** mismatch | **0.671** | **high_risk 21.9** |
| **Unknown number** | stranger, delivery scam | 0.7073 mismatch | 0.574 | high_risk 25.6 |

### The pitch, about ninety seconds

Open on the stakes, not the tech:

> Someone clones your son's voice from an Instagram reel. He calls, panicked — he's had an
> accident and needs ₹40,000 now.

**Tap "Friend calling".** Green.

> A real call from someone we've enrolled. Verified. The evidence panel says why: cosine
> 0.95 against a 0.85 threshold. Not a black box — a number with the bar it cleared.

**Tap "Friend calling — cloned".** Let it play. *Let the silence sit before the card turns.*

> Same person. Same voice. That one was an AI clone.

Then land it:

> Two independent signals agreed. The voice scored 0.76 where the real one scored 0.95 — the
> threshold sits between them. And what it *said* scored 0.67: urgency, a specific amount,
> and "don't tell Papa". That last part is the tell. Isolation is what makes a scam survive;
> one phone call to Papa destroys it.

**Tap "Unknown number"**, then close on the design decision judges remember:

> A stranger never shows green. Green means "we verified this person" — for an unknown
> caller we verified nobody, so we show grey. A tool that cries wolf on every delivery
> driver gets uninstalled by Tuesday.

---

## Track B — live microphone (optional)

```bash
python -m scripts.live_screen --device 2
```

Put a call on speakerphone next to the laptop. Same 9s/3s windows, same `/api/ws/screen`
socket, same fusion. Verified at **31 dB SNR** with verdicts streaming back.

The script auto-probes inputs for one that actually delivers signal — seven of sixteen on
this machine return exact zeros — and refuses to send a silent window.

**Say honestly:** identity is weaker over an acoustic path. A voice picked up through the
air off a speaker loses similarity against a voiceprint recorded on a clean channel, so
expect `unverified` rather than green unless the speaker was enrolled through the same path
(`scripts/enrol_from_call.py`). Transcription and scam-intent hold up well.

---

## Track C — raw API, if a judge wants to see under the hood

```powershell
curl.exe -F "file=@data/eval_set/clips/friend_test.wav"  localhost:8000/api/screen
curl.exe -F "file=@data/eval_set/clips/friend_clone.wav" localhost:8000/api/screen
```

`curl.exe`, not `curl` — in PowerShell `curl` aliases `Invoke-WebRequest`, which has no
`-F`. Quote the argument; a bare leading `@` is PowerShell's splat operator.

Worth pointing at in the response: `weights_used` shows `asv 0.6154, cm 0.0, text 0.3846`.
The design weights are `.40/.35/.25`; the spoof branch did not run, so its 0.35 was dropped
and the rest renormalised. A missing branch degrades the verdict instead of silently
counting as "authentic".

---

## The two hard questions

**"Are you detecting the AI, or just the scam words?"**

> Both, and we're explicit. Identity says *not confidently this person*. Our anti-spoof model
> isn't loaded — and rather than hide that, the app prints it: *"Absence of a synthetic-voice
> warning is not evidence the voice is genuine."* We'd rather under-claim than tell a family
> something we can't prove.

Do not claim synthetic-speech detection. `RC_SPOOF_UNAVAILABLE` is in every response.

**"Why doesn't it record the call itself?"**

Android hands the mic exclusively to the dialer and gives other apps **digital silence**.
Measured: 576,000 consecutive zero samples from a live call. Android's own log says it:

```
rec start ... src:VOICE_COMMUNICATION silenced pack:com.satyacheck
```

`VOICE_CALL` needs `CAPTURE_AUDIO_OUTPUT` (`signature|privileged`); Google closed this in
Android 10 and the accessibility route in Android 11. The deployment answer is a device that
is a **bystander** to the call — which is what Track B is.

---

## If it breaks mid-demo

| symptom | cause | fix |
|---|---|---|
| "cannot reach the screening server" | `adb reverse` dropped | re-run the two setup lines, reopen the app |
| every verdict `unverified` / `insufficient` | audio below the quality gate | backend log prints `quality gate REJECTED` with the SNR |
| `live_screen` prints `SILENT (peak=0)` | wrong input device | `--list-devices`, then `--device N` |
| speaker always `unknown` | probe and enrollment on different channels | enrol via `scripts/enrol_from_call.py` |
| demo tap does nothing | stale capture session | force-stop the app and relaunch |

`server.log` is the source of truth — every scored chunk and every quality-gate rejection is
logged there.

---

## Regression gate

```bash
python -m audio_ml.eval.test_scenarios   # twelve scenarios, must exit 0
```

Run after any threshold or fusion change. It is the only thing standing between a
calibration tweak and silently breaking the legitimate-IVR case.
