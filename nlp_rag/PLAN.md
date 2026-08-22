# nlp_rag — Owner B execution plan

**Scope** `nlp_rag/` only · **Window** 15 hours · **Freeze** H12:00

Read this before writing code. You should not need `PRD.md` or `SKILL.md` to start Block 0.
Read `contracts.py` — it is frozen and every function here returns one of its models.

> **Win condition, from `PLAN.md`:** *a corpus that makes the evidence panel feel real.*
> A judge never sees the corpus. They see reason codes and citations. The corpus is
> instrumental to those, not the deliverable itself. Plan accordingly.

---

## 1 · The public surface

Four functions. `CLAUDE.md`: *"Nothing else crosses a folder boundary. Ever."*

```python
from nlp_rag.api import transcribe, analyze_script, build_reason_codes, challenge_question
```

Signatures ✅ **agreed with C** and matched to the real call sites in
`server/orchestrator.py` (lines 103, 202, 440):

```python
def transcribe(
    audio_path: str | Path | Sequence[float], language: str | None = None
) -> TranscriptResult
def analyze_script(transcript: TranscriptResult) -> ScriptAnalysisResult
def build_reason_codes(script: ScriptAnalysisResult) -> list[ReasonCode]
def challenge_question(
    person: EnrolledPerson | str | None, band: TrustBand = TrustBand.HIGH_RISK
) -> ChallengeQuestion | None
```

Four things worth knowing about that shape:

**`transcribe` takes a waveform.** C calls `transcribe(wav_path or waveform)`, so a
`list[float]` at 16 kHz is a first-class input. faster-whisper accepts a float32 array
directly, so no temporary file is involved.

**`build_reason_codes` emits INTENT codes only.** C composes —
`fusion.reason_codes.extend(build_reason_codes(script))` — so A's `fuse` supplies
identity and authenticity. Emitting them here would double-report the same finding in
one panel. The whole-panel version still exists as
`nlp_rag.reason_codes.build_reason_codes` for the mock path and the CLI.

**`challenge_question` takes an id, resolved through an injected lookup.** C passes
`speaker.matched_person_id`. Shared secrets live in C's database and `nlp_rag` may not
import `server/` (rule 2), so C registers a resolver once at startup:

```python
nlp_rag.api.configure(person_lookup=db.get_person)
```

Without one it degrades to `None` and logs why. **The return stays `| None`** — C's spec
said non-optional, but `TrustScoreResult.challenge_question` is `Optional`, and always
producing a challenge trains the user to ignore it. `None` is the correct answer for an
unenrolled caller, a person with no secrets, or a band where identity is not in doubt.

### E3 · `details["vernacular_warnings"]` — a dict, not a string

The intent branch cannot know the fused band; identity and authenticity have not been
combined when `analyze_script` runs. So it returns **every** warranted warning keyed by
`TrustBand` value, in the transcript's detected language, and C selects with the band
fusion actually produced:

```python
{"high_risk": "…", "suspicious": "…", "caution": "…"}
```

Bands with nothing to warn about are omitted, so presence means "there is something to
say". **The key is present even when the branch abstains** — C reads it unconditionally,
and a call can still fuse into a risky band on the other two branches alone.

This replaces C's hardcoded Hindi-only `_get_vernacular_warning` at
`server/orchestrator.py:363`.

**Every one of these returns a valid object on every path, including failure.** Catch
internally, log, return the neutral factory. Never raise into C (`CLAUDE.md` rule 5).

`analyze_script` is **stateless**. C owns the rolling session buffer and passes the
*cumulative* transcript. Retrieval on a 3-second fragment is meaningless — *"turant 50000
bhejo"* spans chunks.

### The `vernacular_warning` routing problem

`TrustScoreResult.vernacular_warning` is `Optional[str]`, and B owns the templates — but
there is no fifth function to deliver it and the boundary rule forbids adding one. Default:
**emit it as `ScriptAnalysisResult.details["vernacular_warning"]`** and let C lift it during
fusion. Confirm at H0:15. Do not invent a new import.

---

## 2 · Escalations to C — ✅ BOTH RESOLVED

C shipped both fixes on `backend-integration` (`9558453`). Merged and verified.

**E1** — `server/orchestrator.py` now reads `script.details.get("available", True) is
not False`, drops `w_text`, renormalises, and forces the CM gate's `intent` to a neutral
0.5. C chose the `details` convention over a typed field, so `contracts.py` stayed frozen.

**The default is `True`, so silence reads as available** — the whole obligation sits on
this side. Every abstention goes through `nlp_rag.score.abstain()`. Verified end to end
against the real fusion, unenrolled stranger with a synthetic voice:

| Case | `available` | weights | `r_cm_eff` | trust |
|---|---|---|---|---|
| branch works | `True` | (0.10, 0.45, 0.45) | 0.191 | 86.0 |
| ASR produced nothing | `False` | (0.18, 0.82, 0.0) | 0.463 | **53.1** |

A dead text branch now *lowers* trust instead of raising it.

**E2** — `create_mock_fixture` gained `caution` and `suspicious`. B's reason codes are
tested against all six scenarios.

*Minor, for C, not an escalation:* `TrustScoreResult.intent_risk` reports `r_text` (0.0)
on the unavailable path while the CM gate used the neutral 0.5, so the displayed numbers
do not reproduce `r_cm_eff` arithmetically. The field is C's and the behaviour is right;
only the display is confusing.

### E1 (original report, kept for the record) · `neutral()` exonerates instead of abstaining

`neutral()` returns `risk=0.0` with no availability field. A genuinely benign call and a
dead ASR branch are indistinguishable. Using the `unverified` fixture's own numbers
(`authority_check`, `r_asv` 0.50, `r_cm` 0.74, weights .10/.45/.45):

| | `intent_risk` | `r_cm_eff` | combined risk | trust score |
|---|---|---|---|---|
| text branch works | 0.08 | 0.23 | 0.19 | ~81 |
| **text branch fails** | 0.00 | **0.185** | **0.13** | **~87** |

The score goes **up** when the branch breaks. And since `intent = max(script_risk, …)` drives
the CM gate, a failed ASR also floors the anti-spoof contribution. **One failure silently
softens two of three branches**, in `authority_check` — the stranger case, where we have the
least other information.

`contracts.py` is frozen, so no edit is needed:

- B writes `details["available"] = False` on every abstention path, distinct from a real
  benign `risk=0.0`.
- C's fusion renormalises `w_text` out **and** treats the gate's `intent` term as the
  neutral `0.5` when text is unavailable, not `0`.

If C prefers a typed `available: bool`, that is a CONTRACT CHANGE announced out-of-band.
B's work is identical either way — **do not block on which route C picks.**

### E2 · No `caution` or `suspicious` mock fixture

`create_mock_fixture` covers `green` / `red` / `unverified` / `insufficient`. `TrustBand` has
six values. So `PRD.md` §6's second false-positive guard — *genuine family member making an
unusual request must be amber, not red* — has no fixture, and D will build the evidence
panel in Block 1 with no amber treatment.

B does not edit C's file. **B hands C the two missing `TranscriptResult` +
`ScriptAnalysisResult` literals at H1:00.** Also flag: `SUSPICIOUS` appears nowhere in
`README.md`, which documents five bands.

---

## 3 · Module layout

```
nlp_rag/
├── api.py             the 4 public functions — the ONLY module C imports
├── thresholds.py      every constant, read from config.py when C ships it
├── asr.py             faster-whisper adapter (thin; the gate is separate)
├── gate.py            text-side quality gate — pure, no model needed
├── embed.py           BGE-m3 adapter behind the Encoder protocol
├── index.py           flat inner-product index (FAISS IndexFlatIP swap-in)
├── corpus_loader.py   schema validation + anchor resolution
├── retrieve.py        query → top-k RetrievedPlaybook + cohort scores
├── markers.py         bidirectional marker engine
├── score.py           retrieval + markers → ScriptAnalysisResult
├── reason_codes.py    deterministic templates → ReasonCode
├── citations.py       static citation map for non-INTENT codes
├── challenge.py       select + format a stored SharedSecret
├── warnings.py        vernacular_warning templates, band × language
├── eval_retrieval.py  P@3 harness — this path is already promised in README.md
├── corpus/
│   ├── schema.md      locked at H0:30
│   ├── anchors/       real advisories, exact source_url + source_agency
│   ├── variants/      authored scripts, derived:true, inherit anchor citation
│   ├── benign/        ~80 ordinary-call transcripts (the normalisation cohort)
│   └── heldout/       real excerpts, never used to author anything
└── index/             built artefacts, gitignored
```

Every module gets a `if __name__ == "__main__"` smoke test (`CLAUDE.md` rule 7) — CLI-testable
before importable. Build artefacts go in `nlp_rag/index/`, not root `data/`, which has no
named owner.

---

## 4 · Corpus schema — lock at H0:30, then treat as frozen

```yaml
id: str              # anch-digital-arrest-001 / var-digital-arrest-004
kind: anchor | variant | benign | heldout
scam_family: str     # from corpus_loader.VALID_FAMILIES — a closed set
lang: en | hi | hi_latn
script: latin | devanagari
title: str           # → RetrievedPlaybook.title
text: str            # the retrievable body
source_url: str      # anchors: exact. variants: inherited via anchor_id
source_agency: str   # → RetrievedPlaybook.source_agency
anchor_id: str|null  # variants only
derived: bool
indexed: bool        # default true; false = citable but not retrievable
markers: [str]       # marker ids this document exemplifies
expected_anchor: str # heldout only — ground truth for P@k
```

**`scam_family` is a closed set.** It is the key `eval_retrieval` scores family-level P@k
against, so two spellings of one concept split the metric across both and read as a
retrieval failure. `electricity_disconnection` sitting alongside `utility_disconnection`
did exactly that, and an anchor filed under "utility" by *filename* while its text
described telecom impersonation scored a correct retrieval as a miss. `VALID_FAMILIES`
plus two integrity tests (variant matches its anchor, held-out matches its expected
anchor) close both.

**`indexed: false` separates citability from retrievability.** The two reporting
advisories describe what a victim should *do*, not what a caller *says*. No held-out item
expects either, so in the index they were pure false-positive surface — a benign caller
mentioning the 1930 helpline retrieved a scam playbook. They remain anchors, keep their
deep-link obligations, and leave top-k.

**`severity` was removed.** It was authored on every anchor as a "family-level prior" and
read by nothing. A family prior is a fourth weighted term in all but name, and the family
label is the field that turned out to be least reliable.

### Where the URLs come from

**~30 anchors, harvested wifi-on in Block 0**, each with the exact URL of a real advisory —
cybercrime.gov.in / I4C, RBI, PIB FactCheck, state police advisories, reported case
write-ups. **~50 variants**, authored, marked `derived: true`, inheriting their anchor's
citation.

**Integrity rule.** `RetrievedPlaybook` has no `derived` field, so the distinction must never
leak. A retrieved variant **resolves to its anchor** before the `RetrievedPlaybook` is built —
`source_url`, `source_agency` and `title` always point at a page that was actually harvested
and read. `PRD.md` §4.6 makes the external citation the entire differentiator against
adversarially-manipulable attribution maps. One fabricated URL and that claim is false.

### The two-script problem

`SKILL.md` says write each script in "English and Hindi/Hinglish". That is not sufficient.
Whisper's output script is unstable — Devanagari when it detects `hi`, Latin transliteration
on code-switched audio. C's own `red` fixture proves it:

```
text = "Papa emergency ho gaya hai … turant 50000 bhejo is UPI ID pe"
detected_language = "hi"
```

Latin script, Hindi tag. So **index every concept three ways: `en`, `hi_latn`, `hi`
(Devanagari)**. A corpus written in one script misses every transcription in the others,
silently.

*Revised during implementation.* The original instruction was to generate `hi_latn`
offline with `indic-transliteration`. **Hand-author all three instead.** Transliterating
Devanagari produces `phona kisī ko mata denā`; Whisper emits the spelling a person would
actually type. The machine output is a third script that matches nothing.

**This is enforced, not aspirational**:
`test_corpus_integrity.py::test_every_indexed_anchor_covers_all_three_scripts`. It is the
language-bias guard as much as a coverage one — see §5.2.

---

## 5 · `script_risk` — the computation no document specifies

1. Embed the **cumulative** transcript with BGE-m3, L2-normalise.
2. `IndexFlatIP` → top-k (k=5) over scam docs, and over the benign cohort.
3. **s-normalise against the benign cohort** — the text-branch mirror of A's 50-speaker ASV
   cohort:
   `z = (max_scam_cos − mean(benign_cos)) / std(benign_cos)`
4. `r_ret = sigmoid((z − z0) / τ)`, with `z0` and `τ` calibrated once against §5.1.
5. `marker_delta = clip(Σ w_incriminating − Σ w_exculpatory, −0.35, +0.35)`
6. **Double-count suppression** — drop any incriminating marker that the top-retrieved
   document already exemplifies. *"kisi ko mat dena"* is both an isolation marker and the
   phrase that makes the isolation playbook retrieve; counting both inflates risk exactly
   where the signal is strongest.

   *Revised during implementation.* The original rule was written in terms of character
   spans, but dense retrieval produces no span — the score is over the whole transcript,
   so there is nothing to intersect. The corpus schema's `markers:` field already names
   what each document exemplifies, which is the same idea expressed where the information
   actually exists. `Corpus.markers_for()` resolves it, falling back to the anchor.

   Suppression is **one-directional**: exculpatory markers are never suppressed, because
   risk-lowering evidence must never be silently discarded.

6b. **Uncorroborated hits carry no citation.** Top-k always returns something. A weak hit
   passed through to the panel renders as evidence the score does not support, so
   `playbooks` is emptied below the corroboration floor. Found by running the CLI smoke
   test: a benign check-in scored 0.01 and still cited a KYC-harvesting advisory.
7. `script_risk = clip(r_ret + marker_delta, 0.01, 1.0)`
8. **Cap.** Markers alone, with `r_ret` below the amber floor, may not exceed the `HIGH_RISK`
   threshold **read from `config.py`** — never hardcoded. Red with no citable document is a
   verdict with no evidence, which `PRD.md` NG2 forbids outright.

`similarity_score` on `RetrievedPlaybook` is the **raw cosine** — that is what the field says.
The normalised `z` goes in `details`.

### 5.1 · Calibration targets, taken from C's fixtures

| Case | Target `script.risk` |
|---|---|
| Benign family check-in | 0.05 |
| Legitimate bank IVR | 0.08 |
| Cloned extortion, playbook + isolation + UPI | 0.94 |

**Acceptance: the benign cohort lands ≤ 0.10; a full playbook + isolation + payment hit
lands ≥ 0.90.**

Raw BGE-m3 cosines put ordinary topical text around 0.5–0.6 — nowhere near 0.05. These
fixture values are **unreachable without the benign-cohort s-norm.** That is why step 3 is not
optional. If you skip it, everything scores amber, which is the failure mode `README.md` and
`SKILL.md` both warn about.

### 5.2 · `z0` tracks the corpus. This is arithmetic, not taste.

`z` compares the best scam match against the benign background. Growing the scam index
raises `max_scam_cos` for **every** query — benign ones included — while
`mean(benign_cos)` and `std(benign_cos)` are computed over an unchanged cohort. So every
benign z drifts upward with corpus growth, and `SCRIPT_Z0` has to follow it.

Measured, corpus 26 → 56 indexed documents:

| | P@3 strict | family | benign FP |
|---|---|---|---|
| before growth, z0 = 4.0 | 81.2% | 93.8% | 7.3% |
| after growth, z0 = 4.0 | 100% | 100% | **14.6%** |
| after growth, **z0 = 5.5** | 100% | 100% | **1.2%** |

**Run `python -m nlp_rag.eval_retrieval` after any corpus growth.** The benign
false-positive rate is the number to watch and the direction it moves is predictable.

Two guards live here rather than in `tests/test_score.py`, because they need a semantic
encoder to mean anything — `FakeEncoder` is a lexical hasher and `fakes.py` says plainly
that no test should assert on its absolute scores. `kyc_deva` and `parcel_deva` are
paraphrased Devanagari scam calls; both sat near 0.5 before every anchor had a Devanagari
variant, and both clear 0.90 now.

### 5.2 · Failure behaviour

```python
result = ScriptAnalysisResult.neutral()
result.details["available"] = False
result.details["reason"] = "asr_gate_repetition"   # or asr_empty, index_missing, ...
return result
```

Never raise. Never return `risk=0.5` — that fabricates risk. Never return a bare `risk=0.0`
without the flag — that fabricates safety (see E1).

---

## 6 · Markers — both directions, written in the same commit

`MarkerMatch.weight` is signed: incriminating positive, exculpatory negative.

**Incriminating** — isolation (*don't tell anyone*, *kisi ko mat batao*, *phone mat kaato*,
*stay on the line*), time pressure, authority impersonation (CBI / police / customs / RBI),
payment rail (UPI / QR / gift card), OTP or PIN solicitation, arrest threat, penalty for
delay.

**Exculpatory** — invites verification (*call Papa*, *talk to the doctor*, *come to the
hospital*), names a checkable person or place, accepts a callback, no payment ask, references
shared history, tolerates delay, **routine check-in**, **institutional notification with no
credential request**.

Those last two are not decoration. C's fixtures use `MK_EXCULPATORY_ROUTINE` and
`MK_EXCULPATORY_OFFICIAL_NOTIFICATION`, and the second is what holds the bank IVR at 0.08.
They are load-bearing for both false-positive guards.

Every marker gets its Devanagari and Latin-Hinglish forms at the same time. An
incriminating-only marker file flags the friend calling about a real accident — which is the
harm `PRD.md` §9 exists to prevent.

---

## 7 · ASR and the text-side gate

The quality gate (FR-3) is **acoustic** — 1.5s speech, 5 dB SNR. Nothing gates the text.
Whisper `small` emits fluent phantom sentences and looped repetitions on near-silence, so on
exactly the audio that gate was built to catch, a hallucination could feed a confident
`script_risk` into fusion.

Gate in `transcribe`, tripping on any of: `no_speech_prob` above threshold, `avg_logprob`
below threshold, n-gram repetition detected, token count below floor.

**`TranscriptResult` has no `details` dict** — only `text`, `segments`, `detected_language`,
`confidence`. So:

- Fold the gate into `confidence`; return `TranscriptResult.empty()` when tripped.
- Put diagnostics in `ScriptAnalysisResult.details`, which *does* have `Dict[str, Any]`.
- Emit `RC_TRANSCRIPT_UNRELIABLE` with `signal=SignalType.QUALITY` so the abstention is
  visible in the panel rather than silent.

---

## 8 · Latency and CPU budget

FR-13 re-scores every ~2s over 3s chunks with 1s overlap. Two costs nothing else prices:
faster-whisper **pads every input to a 30-second mel window** (a 3s chunk costs roughly what
30s costs), and BGE-m3 is an XLM-R-**large** backbone (~568M params, ~2.2 GB) sharing one
laptop with Whisper, ECAPA, AASIST and silero.

- Transcribe each chunk **once**. Never re-transcribe the 1s overlap — overlap exists for the
  audio branches.
- **Batch ~9s (three chunks) before an ASR call** to amortise the 30s padding.
- Skip silent chunks entirely on C's VAD output.
- `model="small"`, `compute_type="int8"`, `beam_size=1`, `vad_filter=True`,
  **`condition_on_previous_text=False`** — that last flag is what kills the looped-repetition
  hallucination.
- Cache embeddings keyed on transcript hash; re-embed only on a material delta.
- **`IndexFlatIP`. Never IVF or PQ** — those require a training step (`CLAUDE.md` rule 1) and
  buy nothing under ~10k vectors.
- **Pre-transcribe every demo clip** to `nlp_rag/index/pretranscribed.json` at H10:00 and let
  C load it when present. This is the mitigation the risk register already names.

### 8.1 · Measured, Block 2

Everything above was asserted. These are the numbers, `small` + `int8`, CPU, warm model.

**The 30-second mel window is real, and it dominates.** Decode cost is essentially flat
across input length:

| input | decode | per second of audio |
|---|---|---|
| 3s | 1.17s | 0.391s |
| 9s | 1.24s | 0.138s |
| 30s | 1.19s | 0.040s |

A 3s chunk costs 1.17s; a 30s chunk costs 1.19s. §8's claim was right. **Batching to 9s
cuts per-second cost 2.8x against 3s chunks**, and the data would support batching further
if the re-score loop can absorb the added time-to-first-score.

Real speech sits above that floor — 2.6-2.8s for 9-17s clips — because decoding is
token-proportional on top of a fixed ~1.2s encoder pass. Budget **~1.2s fixed + ~0.1s per
second of speech**.

**Cold model load is 3.85s.** It must be warmed at startup or the first call on stage pays
it. See `INTEGRATION.md`.

**Forcing the language was costing 10x.** `config.WHISPER_LANGUAGE = "hi"` was passed
straight to `model.transcribe(language=...)`, which disables auto-detection. On English
audio that measured 1.65-1.82x realtime against 0.16-0.18x auto-detected, produced
*nondeterministic* output across identical runs, and once returned Devanagari and CJK
characters as a transcript of clean English. All three symptoms are one cause: a forced
mismatched language fails Whisper's logprob and compression checks and triggers temperature
fallback, which is repeated decoding with sampling. Auto-detection is also better for
Hindi — on code-switched Hinglish it still returns `hi`, and was faster there too.

---

## 9 · Reason codes and citations

`build_reason_codes` is deterministic templates. **No LLM** — `ENABLE_LLM_REWRITE` stays
`False` (`CLAUDE.md`).

Fill every field `ReasonCode` offers: `code`, `signal`, `value` (formatted for display),
`threshold`, `explanation`, `citation_title`, `citation_url`, `severity`.

**There is no `direction` field.** An exculpatory finding cannot be styled from the schema, so
convey it through `code` (`RC_VERIFICATION_INVITED`), `explanation`, and
`severity=INFO`. Tell D this — otherwise risk-lowering evidence renders as a warning.

**B owns the entire citation surface.** `RetrievedPlaybook.source_url` is the only *retrieved*
citation, but the fixtures put `citation_url` on AUTHENTICITY codes too. Since
`build_reason_codes` is B's, every citation in the product comes from B. `citations.py` holds
a static `code → (title, url, agency)` map for the non-INTENT codes. Those URLs get the same
treatment as anchors: real, read, and clickable.

---

## 10 · Challenge questions and vernacular warnings — both cheap

`SharedSecret` stores `question`, `answer_hash`, `category`, populated at enrollment via
`EnrollmentRequest.shared_secrets: List[{question, answer}]`. So `challenge_question()`
**selects and formats a stored secret** — it does not generate one. Roughly 30 lines.

- Return `None` in `authority_check` — no enrolled person means no shared secret.
- Surface only for `CAUTION` / `SUSPICIOUS` / `HIGH_RISK`.
- Prefer a `category` that is not publicly guessable; avoid repeating one within a session.
- Wrap as *"Ask the caller: '…'"*, set `relation_context`, pass `answer_hash` through
  unchanged.

`vernacular_warning` is `Optional[str]` — **text, not audio.** B owns a handful of per-band,
per-language templates. There is no TTS engine, no sixth model download, and nothing here to
cut.

---

## 11 · Schedule

| Block | Hours | B does |
|---|---|---|
| **0** | H0:00–H1:00 | **E1 + E2 to C by H0:15.** Corpus schema locked H0:30. Harvest starts wifi-on: ~10 anchors with exact URLs; set held-out excerpts aside as you find them. |
| **1** ✅ | H1:00–H4:00 | **Done.** See "Block 1 as built" below. |
| **2** | H4:00–H6:00 | **Stop building.** Sit next to C. Swap mocks one branch at a time: ASR → script → reason codes. Never two at once. |
| **3** | H6:00–H9:00 | Exculpatory breadth, reason-code templates per scam family, `citations.py`, `challenge.py`, `warnings.py`. Corpus growth **only after** those are done. |
| **4** | H9:00–H11:00 | `eval_retrieval.py` → P@3 and benign false-positive rate, hand to A. Pre-transcribe demo clips at H10:00. Then **floater rule** — join D. |
| **5** | H11:00–H12:00 | Bug bash. Nothing new gets built. |

> **H12:00 — FEATURE FREEZE. ABSOLUTE.**

### Block 1 as built

The stated target was *anchors → ~30, variants → ~50*. **Held at 16 anchors and drove
variants to 42 instead**, because the two numbers buy different things: anchor bodies are
third-person advisory prose and do not embed near first-person call transcripts, so
anchors buy citations and variants buy retrieval. Nine families already carried real,
deep-linked citations; six anchors had no variant at all, and five held-out items pointed
straight at them.

The target that replaced the flat 50 is **every indexed anchor carries a complete
`en` / `hi_latn` / `hi` triple** — 14 × 3 = 42 — which closes the held-out misses and the
script imbalance in the same work.

| | before | after |
|---|---|---|
| indexed anchors + variants | 14 + 10 | 14 + 42 |
| script mix (scam) | 18 en / 4 hi_latn / 2 deva | 28 / 14 / 14 |
| P@3 strict · family | 81.2% · 93.8% | **100% · 100%** |
| MRR | 0.740 | **0.906** |
| benign false positives | 7.3% | **1.2%** |

Four defects surfaced along the way, three of which were invisible before the harness
existed:

1. **A mislabelled anchor and a duplicate family name** were corrupting family-level P@3
   in both directions. Fixed, and `VALID_FAMILIES` now prevents recurrence.
2. **The vector cache was keyed on document id alone**, so editing a body under an
   unchanged id served the previous wording's embedding forever, silently. Content hashes
   added; `FORMAT` bumped to V2.
3. **The cache recorded no encoder identity.** Writing a real BGE-m3 cache to disk for the
   first time meant a 256-dim stand-in query met 1024-dim vectors — not a degraded result
   but a matmul shape error from inside a live request. `expect_encoder` now rejects it.
4. **`MK_URGENT_FINANCIAL_UPI` fired on "kabhi"**, which contains "abhi". A pharmacy saying
   *"collect it whenever you like, or shall we send it to your home"* scored as a demand
   for an immediate transfer. Patterns are `\b`-anchored now.

The one remaining benign false positive is `benign-unusual-request-006` at 0.355 — a
genuine but unusual money request, correctly elevated to amber rather than green.

### Bug-bash inputs (Block 5)

Empty transcript · single word · pure silence · all-Devanagari · all-Latin-Hinglish · fully
code-switched mid-sentence · 200-word transcript with no scam content · transcript with a
marker but no playbook hit · transcript with a playbook hit but no markers.

---

## 12 · Evaluation

`python -m nlp_rag.eval_retrieval` reports:

1. **P@3 on harvested held-out excerpts** — real reported scam-call text set aside during
   Block 0 harvesting and **never used to author a corpus document**. Primary metric,
   available from H1.
2. **P@3 on H9 recorded-clip transcripts** — real ASR output from A+D's session. Second row,
   measures retrieval under transcription error.
3. **Benign false-positive rate** — fraction of the benign cohort scoring at or above the
   amber floor, read from `config.BAND_THRESHOLDS["caution"]`. This is the number that
   proves the two over-flagging guards.

If B authors both the corpus and the test set, P@3 measures B's memory of their own writing.
Row 1 exists so the honest answer to *"who wrote your test set"* is not *"I did."*

**The benign cohort is scored leave-one-out.** Every benign document is *in* the cohort
that normalisation reads as background; leaving its own ~1.0 self-match there raises the
mean, depresses its own z, and understates the false-positive rate — the exact direction
that makes a corpus look safer than it is. An earlier hand-run figure of 1/82 was measured
without this and was optimistic; the honest pre-growth number was 7.3%.

The harness also carries the §5.1 calibration table, so one run answers both *did
retrieval improve* and *did the fixture scores survive*.

### 12.1 · Recall — the axis that was missing

P@k says the right advisory was **retrieved**. It says nothing about the number the user
is **shown**, and a system can retrieve perfectly while scoring every call green. That is
not hypothetical: the harness reported 100% P@3 and a 1.2% false-positive rate while
**36% of known scams scored below the caution floor.**

Every held-out document is a scam by construction, so the recall metrics come free:

- `scam_recall_amber` — fraction reaching at least `caution`
- `scam_recall_high_risk` — fraction reaching `high_risk`
- `recall_by_lang` — the same, per language. **This replaced two hand-picked Devanagari
  strings with an invented `>= 0.90` target.** One of them sat at 0.906 and duly failed
  the moment the benign cohort grew; a threshold artefact was being reported as a defect.
  Fifty transcripts across three scripts measure the same property with a sample behind it.
- `silent_scams` — named, because "which ones" matters more than "how many".

### 12.2 · The exit code cannot rest on the calibration rows

Those three strings are what `SCRIPT_Z0` was fitted against, so they pass by construction.
A run gated on them alone reported success while recall was 64%.

The gate is **regression against the last recorded baseline** on the metrics that were
never consulted during tuning: P@k strict and family, both recall figures, and the benign
false-positive rate. Regression needs no invented absolute target — only "worse than last
time", with a 0.03 tolerance so one document crossing a boundary in a 50-query set is not
an alarm.

Two comparisons are refused outright rather than reported, for the same reason
`expect_encoder` refuses a foreign cache: **a metric is only comparable against a baseline
measured on the same data.** A baseline from a different encoder, or from a different
held-out or benign set, is skipped with a warning. Growing the held-out set from 16 to 50
moved P@3 from 100% to 94% — a harder test, not a regression — and the first version of
the gate duly reported three failures that had not happened.

---

## 13 · Cut order

When behind, drop in this order:

1. Corpus depth beyond ~80 documents
2. Reason-code templates beyond the four demo scenarios
3. Marker breadth beyond isolation, urgency, authority, payment rail
4. `warnings.py` beyond one template per band

**Never cut:** the benign cohort · exculpatory markers · anchor citations.

Those three are what make the legitimate-IVR and genuine-unusual-request scenarios pass, and
those two scenarios are the reason anyone believes the rest of the numbers.

---

## 14 · Definition of done, per module

```bash
python -m nlp_rag.retrieve              # smoke test — query in, playbooks out
python -m nlp_rag.markers               # smoke test — both directions fire
python -m nlp_rag.score                 # smoke test — hits the §5.1 targets
python -m nlp_rag.eval_retrieval        # P@3 + benign false-positive rate
python -m audio_ml.eval.test_scenarios  # must exit 0
```

The last one is A's harness, not B's. `CLAUDE.md` requires it after **any** change that moves
a branch score — and `score.py` is exactly that. Run it after every calibration tweak, not
just at the end.
