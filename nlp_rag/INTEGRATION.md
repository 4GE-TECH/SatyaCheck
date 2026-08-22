# `nlp_rag` integration — for C

Everything B owes the server layer, and the three things B cannot do because
`CLAUDE.md` rule 2 puts `server/` on your side of the line.

The branch is **verified working end to end on real audio** on B's machine. Nothing here
is theoretical — the numbers below were measured, not estimated.

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

1. **Flip `USE_REAL_NLP`.** Check a real call produces non-empty `transcript.text` and a
   `script.risk` that is not 0.0.
2. **Apply R1** (below) so `challenge_question` stops returning `None`.
3. **R3** if you want language-correct vernacular copy.
4. **R2** is already wired and waits on A.

**Rollback is `USE_REAL_NLP=false`.** No code change, no restart of anything else.

---

## 3 · The three requests

### R1 — required · register the person lookup at startup

`challenge_question` needs to resolve `speaker.matched_person_id` into an `EnrolledPerson`.
Shared secrets live in your database and `nlp_rag` may not import `server/`, so the
resolver is injected once at startup.

In `server/main.py`, inside `lifespan`, beside the existing `init_db()`:

```python
    try:
        from server.database import init_db, get_person
        init_db()
        log.info("  DB init: OK")

        import nlp_rag.api
        nlp_rag.api.configure(person_lookup=get_person)
        log.info("  NLP configure: OK")
    except ImportError:
        log.warning("  server.database not yet available — skipping DB init (Block 0 mode)")
```

`configure()` also warms BGE-m3 and loads the index cache, which takes **7.9s**. Doing it
at startup rather than on the first request moves that cost off the demo.

**Skip this and** `challenge_question` returns `None` on every call — silently, by design,
since public functions never raise. The red-band demo features the challenge prominently.

Any callable taking a person id and returning an `EnrolledPerson` (or `None`) works; the
name `get_person` is a guess at your API.

### R2 — blocked on A · no action now

`build_reason_codes` is already called at `server/orchestrator.py:437`, inside
`if config.USE_REAL_FUSION:`. That flag needs `audio_ml.api.fuse`, which does not exist yet.

**Known and accepted consequence: until A ships `fuse`, the evidence panel shows identity
and authenticity codes only.** No INTENT codes, no citations — none of the corpus work is
visible. Your `_build_reason_codes` emits no INTENT codes, and B deliberately did not ask
you to add a temporary call in the `_compute_fusion` path that would have to be removed
later and risks double-appending.

Recorded here so it is a decision, not a surprise, when the panel looks thin.

### R3 — optional · language-aware vernacular warnings

`server/orchestrator.py:219` calls `_get_vernacular_warning(band)`, which is hardcoded
Hindi regardless of the caller's language. B emits the full set instead:

```python
script.details["vernacular_warnings"]   # {"high_risk": "…", "suspicious": "…", "caution": "…"}
```

Keyed by `TrustBand` value, in the transcript's detected language. Bands with nothing to
warn about are omitted, so presence means there is something to say.

```python
    warnings = script.details.get("vernacular_warnings") or {}
    vernacular_warning = warnings.get(band.value) or _get_vernacular_warning(band)
```

**The key is present even when the branch abstains** — read it unconditionally. A call can
still fuse into a risky band on the other two branches alone, and that verdict still has to
be speakable.

---

## 4 · What "working" looks like

Measured on B's machine with real audio through the real decoder. If you see materially
different numbers, something is degrading silently.

| Call | `detected_language` | `script.risk` | `details["available"]` |
|---|---|---|---|
| Clone-extortion script, English | `en` | **0.999** | `True` |
| Routine family check-in, English | `en` | **0.010** | `True` |
| Scam script, code-switched Hinglish | `hi` | 0.19–0.9 † | `True` |
| Silence, noise, or <1.5s of audio | `unknown` | **0.0** | **`False`** |

† The Hinglish figure is soft because B's test audio is a text-to-speech voice reading
romanised Hindi, which transcribes poorly. It is a limitation of the *test audio*, not a
measured property of the branch. Real recordings (A+D, H9) are what will settle it.

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
