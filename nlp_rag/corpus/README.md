# Corpus

Four kinds of document, one YAML schema. See `nlp_rag/PLAN.md` §4.

| Directory | Kind | Retrievable | Citable |
|---|---|---|---|
| `anchors/` | `anchor` | yes | **yes** — carries the exact `source_url` |
| `variants/` | `variant` | yes | no — resolves to its anchor |
| `benign/` | `benign` | no | no — the s-normalisation cohort |
| `heldout/` | `heldout` | no | no — the evaluation set |

## The integrity rule

`RetrievedPlaybook` has no `derived` field. A variant that retrieves **resolves to its
anchor** before the contract object is built, so every `source_url` the evidence panel
renders points at a page that was actually opened and read.

`PRD.md` §4.6 makes retrieved external evidence the differentiator against attribution
maps. One fabricated URL and that claim is false — and the demo runs wifi-off, so nobody
can check at demo time, which makes it *more* important not to fabricate, not less.

## Two outstanding tasks, both Block 0

### 1. Deep-link every anchor

`anchors/seed_anchors.yaml` currently cites the authoritative **landing page** for each
agency (`cybercrime.gov.in`, `rbi.org.in`, `sancharsaathi.gov.in`, `pib.gov.in`). Those
domains are correct and the advisories are real, but a landing page is a weaker citation
than the advisory itself.

Replace each `source_url` with the deep link to the specific advisory, and open each one
to confirm it resolves. Do this with wifi on, at H0, before the corpus grows.

### 2. Harvest the held-out set

`heldout/` is **deliberately empty**. Held-out documents must be real reported scam-call
excerpts — news write-ups, complaint threads, advisory case studies — that were never
used to author a corpus document.

Authoring them yourself makes P@3 a measurement of your own memory. If B writes both the
corpus and the test set, the honest answer to *"who wrote your test set"* is *"I did"*,
and M4 stops being evidence. Harvest these during Block 0 alongside the anchors.

## Adding documents

```bash
python -m nlp_rag.corpus_loader    # loads, validates, prints resolved citations
python -m pytest nlp_rag/tests/test_corpus.py -q
```

Authoring mistakes fail loudly at load: a dangling `anchor_id`, an anchor with no
`source_url`, a duplicate id, an unknown `lang` or `kind`. `nlp_rag.api` catches and
degrades, so a broken corpus never raises into the server — but it will make the intent
branch abstain, which is visible in the evidence panel.

Write each concept in `en`, `hi_latn` and `hi`. Whisper's output script is not stable:
it emits Devanagari when it detects `hi` and Latin transliteration on code-switched
audio. `paise bhejo` and `पैसे भेजो` are the same utterance and do not embed identically.
