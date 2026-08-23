# `nlp_rag` integration — for C

Everything B owes the server layer, and what is left to turn the intent branch on.

The branch is **verified working end to end on real audio**. Nothing here is theoretical —
the numbers below were measured, not estimated.

**Status:** the three original requests are all implemented (§3). The remaining item is a
single flag — `USE_REAL_NLP` is still `false` while speaker and spoof are live.

---

## 1 · Prerequisites you must run locally

Both artefacts are **gitignored**, so pulling the code is not enough.

### 1.1 · faster-whisper (~461MB, once, wifi on)

`nlp_rag/asr.py` looks for `models/faster-whisper-{config.WHISPER_MODEL_SIZE}`, i.e.
**`models/faster-whisper-small/`**. Four files are needed: `config.json`, `model.bin`,
`tokenizer.json`, `vocabulary.txt`.

```bash
hf download Systran/faster-whisper-small --local-dir models/faster-whisper-small
```

**If `hf` is "not recognized"** it is installed but not on PATH — it lives in the
user-site `Scripts/` directory, not the interpreter's. `python -m huggingface_hub` does
not exist as an entry point; use the full path to `hf.exe` or the Python API.

**If you get `CERTIFICATE_VERIFY_FAILED`**, something on the network is intercepting TLS.
B hit this: certifi reported "unable to get local issuer certificate" while the Windows
store reported "Basic Constraints of CA cert not marked critical" — a malformed re-signing
root that browsers tolerate and OpenSSL does not. Python cannot download; PowerShell can,
because it uses the Windows TLS stack:

```powershell
$base = "https://huggingface.co/Systran/faster-whisper-small/resolve/main"
New-Item -ItemType Directory -Force -Path models\faster-whisper-small | Out-Null
foreach ($f in @("config.json","tokenizer.json","vocabulary.txt","model.bin")) {
  Invoke-WebRequest -Uri "$base/$f" -OutFile "models\faster-whisper-small\$f" -UseBasicParsing -TimeoutSec 900
}
```

Do **not** disable certificate verification to get past this.

### 1.2 · BGE-m3 (~2.2GB) and the index artefacts

```bash
hf download BAAI/bge-m3 --local-dir models/bge-m3
python -m nlp_rag.index_store        # writes config.FAISS_INDEX_PATH / FAISS_DOCSTORE_PATH
```

**Skipping the second command is not fatal but is expensive**: without it every server
boot re-encodes 173 corpus documents through BGE-m3. With it, `configure()` logs
`index cache hit: 173 vectors`.

The artefacts carry the encoder that produced them. A cache written by BGE-m3 and read by
anything else is **refused and rebuilt**, not used — 1024-dim vectors against a 256-dim
query is a matmul shape error raised from inside a live request, not a graceful
degradation.

---

## 2 · Switch-on order

`PLAN.md` §11 says one branch at a time, never two at once.

```bash
USE_REAL_NLP=true        # this is the whole switch
```

1. **Build the index artefacts** — `python -m nlp_rag.index_store`. Not fatal to skip,
   but every boot otherwise re-encodes 173 documents through BGE-m3.
2. **Flip `USE_REAL_NLP`.** Check a real call produces non-empty `transcript.text` and a
   `script.risk` that is not 0.0, and that `details["available"]` is `True`.
3. Confirm the evidence panel shows an INTENT reason code with a `citation_url`. That is
   the corpus becoming visible; while the flag is off you are seeing fixture text.

Everything else is already wired — see §3.

**Rollback is `USE_REAL_NLP=false`.** No code change, no restart of anything else.

---

## 3 · Requests — all three are done

Written when B was reading the stale copy of `server/` carried on the `nlp_rag` branch. On
`backend-integration` they were already implemented, and C has since gone further. Kept so
nobody re-does them.

- **☑ R1** — `configure(person_lookup=get_person_by_id)` in `lifespan`
  ([main.py:58](server/main.py#L58)), wrapped in its own try/except so a DB failure degrades
  rather than blocking startup. It also warms BGE-m3, moving ~7.9s off the first request.
- **☑ R2** — `build_reason_codes` is called in the `_compute_fusion` path
  ([orchestrator.py:306](server/orchestrator.py#L306)), not only under `USE_REAL_FUSION`. So
  intent codes and citations reach the evidence panel **without** waiting on
  `audio_ml.api.fuse`, which is better than what B asked for.
- **☑ R3** — `_get_vernacular_warning(band, script)` reads
  `script.details["vernacular_warnings"]` and falls back to the hardcoded table.

C has also merged all four branches into `backend-integration`, added
`server/audio_adapter.py` to bridge A's models, and turned on `USE_REAL_SPEAKER` and
`USE_REAL_SPOOF`.

### The one thing left · `USE_REAL_NLP` is still `false`

```python
USE_REAL_SPEAKER = "true"    # on
USE_REAL_SPOOF   = "true"    # on
USE_REAL_NLP     = "false"   # off
```

Speaker and spoof are live; the intent branch is not. It is the branch that needed **no**
adapter and is the one already verified end to end on real audio — a clone-extortion
script scores 0.999 with the right citation, a routine check-in 0.010, and silence
abstains with `available=False`.

While it is off, `_mock_nlp_branch` supplies the transcript and script risk, so the
evidence panel shows fixture text rather than the corpus, and none of the intent work is
visible.

Prerequisite before flipping it, if not already done:

```bash
python -m nlp_rag.index_store     # else every boot re-encodes 173 documents
```

Rollback is setting it back to `false`. Nothing else changes.

## 3.1 · One request for C · wire `StreamingTranscriber` into the WS session

**Only affects `/api/ws/screen`. The upload path — what the demo uses — needs nothing.**

`server/ws_router.py` currently ingests and transcribes each 3-second chunk on its own.
Whisper does not stay quiet on too-little audio; it invents fluent sentences. Measured on
`friend_test.wav`, same clip, two ways:

```
3s chunks:    'alert can product us from with the minger next week'    langs en/hi/unknown
accumulated:  'never send money to unknown people and always verify…'  lang  en (pinned)
```

The first is not a transcript, and it is fed to retrieval and markers as though it were.
The ASR gate does not catch it — that gate checks `no_speech_prob` and repetition, and a
hallucination trips neither. The flapping language also changes which vernacular warning is
spoken, so it can switch language between two rescores two seconds apart.

`nlp_rag.api.StreamingTranscriber` holds both rules. It buffers until ~9s of audio has
arrived, decodes the whole growing window, and pins the language after the first confident
detection. On `SessionState`:

```python
from nlp_rag.api import StreamingTranscriber

class SessionState:
    def __init__(self, session_id: str) -> None:
        ...
        self.stream = StreamingTranscriber()      # one per session
```

Then, where the chunk is handled — pass the waveform in and use what comes back, rather
than letting the orchestrator transcribe the 3-second chunk:

```python
transcript = state.stream.push(ingested.waveform, sample_rate=ingested.sample_rate)
```

`push` returns the current best transcript **every** time, so you can keep rescoring at
whatever cadence you like; it only *decodes* when enough new audio has arrived. Between
decodes it returns the previous transcript unchanged rather than an empty one — important,
because an empty result would make `details["available"]` flap and your fusion would drop
and restore `w_text` on alternate rescores.

Two more calls worth wiring:

- `state.stream.flush()` when `is_final` arrives — decodes the tail, so a final four-second
  utterance (often the one naming the payment) is not discarded.
- `state.stream.reset()` on your existing `reset` message — a new call is a new language.

Never raises; a decoder failure returns the last good transcript.

## 4 · What "working" looks like

Measured on B's machine with real audio through the real decoder. If you see materially
different numbers, something is degrading silently.

| Call | `detected_language` | `script.risk` | `details["available"]` |
|---|---|---|---|
| Clone-extortion script, English | `en` | **0.999** | `True` |
| Routine family check-in, English | `en` | **0.010** | `True` |
| Scam script, code-switched Hinglish | `hi` | 0.19–0.9 † | `True` |
| Silence, noise, or <1.5s of audio | `unknown` | **0.0** | **`False`** |

† **Settled, with a human recording.** This footnote used to say the Hinglish figure was
soft because the test audio was a TTS voice reading romanised Hindi. A real recording of
`held-family-emergency-001` now scores **0.407** — above its own clean-text score of 0.343,
even though Whisper rendered the Hinglish as badly-corrupted Devanagari. Four more spoken
scripts land 0.278–0.574, all above the amber floor, and 8 kHz copies cost at most 0.074
more. See `PLAN.md` "Recorded audio, as measured".

### The one field that matters most

```python
script.details["available"]
```

Your fusion already reads it at `orchestrator.py:154`. **It defaults to `True`, so silence
reads as available** — the whole obligation sits on B's side, and every abstention path
goes through `nlp_rag.score.abstain()`. Verified against your real fusion:

| Case | `available` | weights | `r_cm_eff` | trust |
|---|---|---|---|---|
| branch works | `True` | (0.10, 0.45, 0.45) | 0.191 | 86.0 |
| ASR produced nothing | `False` | (0.18, 0.82, 0.0) | 0.463 | **53.1** |

A dead text branch lowers trust instead of raising it. That behaviour depends on this flag.

---

## 5 · Two notes on `config.py` — B did not edit it

### `WHISPER_LANGUAGE` no longer forces the decoder

```python
WHISPER_LANGUAGE: str = "hi"   # Primary language; Whisper auto-detects Hinglish
```

The comment describes the intent, but the value was being passed to
`model.transcribe(language=...)`, and passing that parameter is exactly what *disables*
auto-detection. Measured cost of forcing `hi` on English audio:

- **~10x slower** — 1.65–1.82x realtime against 0.16–0.18x auto-detected
- **nondeterministic** — identical input and settings, different output between runs
- **lower quality** — one run returned Devanagari and CJK characters as a transcript of
  clean English speech

One cause for all three: a forced mismatched language fails Whisper's logprob and
compression-ratio checks, triggering temperature fallback — repeated decodes at rising
temperature, and temperature above zero is sampling.

Auto-detection is better for Hindi too, not a trade-off: on code-switched Hinglish it still
returns `hi`, and was faster there as well (6.4s against 16.6s on the same clip).

`asr.py` now decodes with auto-detection always. **`WHISPER_LANGUAGE` is still used** — as
the prior it is documented to be, reported as the language label when Whisper's own
detection is below `ASR_MIN_LANGUAGE_PROB` (0.60). Clean English detects at p=1.00;
code-switched Hinglish lands at p=0.54–0.57, which is genuinely uncertain and exactly where
the deployment's primary language is the better answer. **No change is needed on your
side** — this is recorded so the value's meaning is not a surprise.

### `FAISS_INDEX_PATH` / `FAISS_DOCSTORE_PATH` are not FAISS

The paths are honoured because they are the agreed integration location, but the payload is
a numpy inner-product index — behaviourally identical to `IndexFlatIP` at this corpus size,
with one fewer wheel to install. Every artefact carries a `FORMAT` string so anyone opening
one learns what it is. Suggest renaming to `RAG_INDEX_PATH` / `RAG_DOCSTORE_PATH` when
convenient; B will follow the rename.

---

## 6 · If something looks wrong

| Symptom | Cause |
|---|---|
| `script.risk` is always 0.0 and `available` is `False` | `models/faster-whisper-small` missing. `asr.py` logs `faster-whisper not found at …` once at load. |
| Every server boot takes ~30s | `python -m nlp_rag.index_store` was never run. |
| `challenge_question` always `None` | R1 not applied. |
| No citations in the evidence panel | Expected — R2, blocked on `audio_ml.api.fuse`. |
| Vernacular warning is Hindi on an English call | R3 not applied. |
| Risk scores look uniformly low | Check `python -m nlp_rag.eval_retrieval` exits 0. |

B's smoke tests, all runnable standalone:

```bash
python -m nlp_rag.asr <some.wav>     # real transcript from the real model
python -m nlp_rag.score              # §5.1 calibration targets
python -m nlp_rag.eval_retrieval     # P@3, scam recall, benign false positives
python -m pytest nlp_rag/tests -q    # full suite
```
