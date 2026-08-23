# What B needs from A

Answering your `GUIDE_FOR_B_NLP.md`. Thank you — your calibration table in §1 found two
real defects in my markers within ten minutes of reading it, described at the bottom.

Ordered by what it unblocks. **Everything under P0 is transport — the audio exists, it
just has not reached the repo.** P1 is convenience, P2 is decisions.

> **Update.** Five of the ten scripts have landed and are measured — see item 2. The
> headline: the intent branch survives real speech (worst case −0.054 against clean text)
> and survives 8 kHz phone audio (worst case −0.074), with every clip still above the
> amber floor. The five still missing are all three Devanagari and two of three Hinglish.

---

## P0 · Blocking

**Transport is solved — thank you.** `data/eval_set/clips/` was exactly the right call:
that path is not gitignored, so the clips came through. `cloned_scam.wav`, `me.wav`,
`friend.wav` and the `nb8k` variants are all readable from `origin/audio_ml`.

### ☑ ~~1. Put the clips somewhere git will take them~~ — done

For the record, in case anyone hits it again: `data/demo_clips/`, `data/cohort/`,
`data/enrollments/` and `data/reports/` are all in `.gitignore`, so `git add` there is a
**no-op that reports nothing** — the add appears to work, the commit succeeds, and the
files never leave the machine. `data/eval_set/` is not ignored, which is why this worked.

### ◐ 2. The recorded scam scripts — **five of ten landed, and they measure well**

Thank you. These are the first evidence any of B's numbers survive a human speaking the
words, and they do:

| script | clean text | **spoken** | **spoken @ 8 kHz** |
|---|---|---|---|
| held-sms-fraud-001 | 0.628 | **0.574** | 0.499 |
| held-telecom-002 | 0.499 | **0.495** | 0.494 |
| held-credential-002 | 0.417 | **0.404** | 0.421 |
| held-family-emergency-001 | 0.343 | **0.407** | above floor |
| held-digital-arrest-004 | 0.259 | **0.278** | 0.278 |

**All five clear the amber floor, wideband and narrowband.** Worst degradation from text to
speech is −0.054, worst from 16 kHz to 8 kHz is −0.074, and two scored *higher* spoken than
written. `held-telecom-002` and `held-sms-fraud-001` retrieve their own family's anchor and
carry a live citation from spoken audio.

Landed as `data/eval_set/clips/held-*.wav` plus `_nb8k` copies, converted to 16 kHz mono
and **named for their script id** — so the filename is the ground-truth label and there is
no manifest to drift. Pinned by `nlp_rag/tests/test_recorded_audio.py`.

Two of the seven files were a casual conversation about a hackathon rather than a script;
removed on the user's instruction.

**Still outstanding — five, and they are the ones that matter most for coverage:**

| script | family | language |
|---|---|---|
| `held-kyc-update-005` | kyc_update | Devanagari |
| `held-utility-004` | utility_disconnection | Devanagari |
| `held-qr-code-004` | qr_code_fraud | Devanagari |
| `held-parcel-customs-004` | parcel_customs | Latin-Hinglish |
| `held-lottery-002` | lottery_advance_fee | Latin-Hinglish |

**All three Devanagari and two of the three Hinglish.** What landed is four English and one
Hinglish, so the languages with no spoken evidence at all are exactly the ones where the
text-only numbers are least safe to trust — Hinglish is still the weakest at 86.7% recall.
Scripts are ready to read in `nlp_rag/scripts_for_a.md`; name each file after its id.

### ☐ 3. Three of the six §4 clips did not come through

Present: `cloned_scam.wav`, `me.wav`, `friend.wav`, plus `friend_test.wav` and its `nb8k`
pair — the last of which quietly covers most of item 4 below.

Missing: `person1.wav`, `person2.wav`, `person3.wav`. `data/eval_set/manifest.csv` lists
them under `data/eval_set/raw/`, but that directory is not in the tree. The manifest also
points at `data/demo_clips/` for two entries that actually live in `clips/` — worth a
tidy so the file matches the layout.

Not blocking: three real voices are plenty for ASR spot-checks. Mentioned because the
manifest currently promises files that are not there, which will confuse whoever reads it
next.

## P1 · Wanted, not blocking

### ☐ 4. An 8 kHz copy of everything

Your §4 is right that real calls arrive degraded and that ASR accuracy drops. I would like
each clip at both wideband and `nb8k` so I can measure the drop rather than assume it.

Easiest if you run `degrade()` yourself and send both — see item 7 for why I would rather
not import it.

### ☐ 5. What your branch returns for `cloned_scam.wav`

Your §7 numbers (genuine 0.9464 match, cloned 0.7631 mismatch) are useful context. For the
one clip we will both be running, knowing your `verdict` and `norm_score` lets me sanity
check the fused result end to end instead of only my own branch.

---

## P2 · Decisions, not artefacts

### ☑ ~~6. Your `contracts.py` is not C's~~ — C bridged it

Resolved without any change to `audio_ml/`. C wrote `server/audio_adapter.py`, which
translates your `SpeakerSignal` and `SpoofSignal` into C's contract models, and it gets
the mapping I was most worried about right: `verdict == "unknown"` maps to `risk = 0.5`,
not 1.0. Unknown is the normal state for every genuine stranger, and treating it as guilty
would make every real bank and delivery driver red.

Kept below for the record, because it explains why §1 of your guide describes a data flow
that does not run.

The underlying divergence is still real.

There are three versions of the "frozen" `contracts.py` in the repo. Yours is **1061 lines
shorter** than C's — not an older copy, a different contract with its own vocabulary:

| yours | C's, which B and D both use |
|---|---|
| `SpeakerSignal` | `SpeakerVerificationResult` |
| `SpoofSignal` | `AntiSpoofResult` |
| `ScriptSignal` | `ScriptAnalysisResult` |
| `FusionResult` | `TrustScoreResult` |
| `Person` | `EnrolledPerson` |

13 classes against 34. Signatures differ too: you have `verify_speaker(wav_path)` where
`server/orchestrator.py` passes `chunks`. As it stands **every
`from audio_ml.api import …` in C's orchestrator returns an object C cannot use.**

So §1 of your guide — "my `fuse()` reads `script.risk` from your `ScriptSignal`" — does not
describe what will run. I emit `ScriptAnalysisResult` from C's contract, and D's TypeScript
mirrors C's models name-for-name.

C's plan is an adapter inside `server/` that translates your models into C's, so **nothing
in `audio_ml/` has to change**. You mainly need to know this is happening, and to confirm
the field mapping is faithful — particularly that `SpeakerSignal.verdict == "unknown"` maps
to `risk = 0.5` and never to 1.0.

### ☐ 7. `audio_ml.codec.degrade` is not on the allowed import list

`CLAUDE.md` limits cross-folder imports to `enroll_person, verify_speaker, detect_spoof,
fuse, add_flagged_voice`. `degrade` is not among them, so I will not import it.

It is pure ffmpeg and subprocess with no model dependency, so either is fine by me:
re-export it through `audio_ml/api.py`, or just send me the ffmpeg parameters and I will
run them myself. Your call — it is your module.

### ☐ 8. `test_scenarios.py` validates a fusion that will not run

`CLAUDE.md` requires `python -m audio_ml.eval.test_scenarios` to exit 0 after any change
that moves a branch score. I have moved `SCRIPT_Z0` (4.0 → 5.5) and added markers, so I owe
you that run and cannot make it until the branches merge.

Worth knowing before then: the file imports `audio_ml.fusion.fuse` and builds inputs with
`SimpleNamespace`, so it does not touch `contracts.py` and **will survive the merge intact**
— but it exercises *your* `fuse`, and C intends to keep their `_compute_fusion` and leave
`USE_REAL_FUSION` false. C's version implements the `CLAUDE.md` formula (intent gates the
CM branch, then a weighted sum) rather than your `risk = max(weighted_sum, script.risk)`.

So the mandated harness would be green while testing a code path the product never
executes. Not urgent, but somebody should decide which fusion is the real one before we
rely on that gate.

---

## Why I am not chasing the rest of your calibration table

Your §1 targets, measured against my branch as it stands:

| your target | B gives | |
|---|---|---|
| "Hi Ma, just calling to check in" · 0.0–0.1 | **0.020** | ok |
| "Your KYC has expired, update it" · 0.3–0.5 | 0.258 | low |
| "Send ₹40,000 now, don't tell Papa" · 0.7–0.85 | **0.605** | low, was 0.275 |
| "CBI, you are under digital arrest…" · 0.9–1.0 | 0.815 | low |

**Two real defects, now fixed.** On the third case *neither marker fired*. `don't tell Papa`
missed because my isolation pattern only matched "anyone/anybody/a soul" — naming the one
person who could verify the story in a single phone call is *stronger* isolation than
"anyone", and it is the family-emergency script almost verbatim. And `send 40,000 now`
missed because I matched "right now" but not bare "now". That case went 0.275 → 0.605 with
no movement in benign false positives, recall or P@3. Thank you — an external test set
caught what my own examples did not.

**The remaining gap is deliberate.** Your targets assume your fusion, where
`risk = max(weighted_sum, script.risk)` makes `script.risk` *become* the band when the
speaker is not a match — so it wants to be band-shaped. Under C's fusion it is one weighted
term of three (0.25 in identity_check, 0.45 in authority_check) that also gates the
anti-spoof branch. Different role, different calibration.

Closing the last 0.1 means lowering `SCRIPT_Z0`, and I have measured that trade on 50
held-out scam transcripts and 103 benign calls:

| `z0` | scam recall @ amber | benign false positives |
|---|---|---|
| 4.0 | 96% | **28.2%** |
| 4.5 | 86% | 11.7% |
| **5.5 (current)** | 68% | **5.8%** |

Buying your 0.9 on digital arrest costs flagging roughly one benign call in four — real
debt collection, genuine police callbacks, hospital deposits. `PRD.md` §6 and the
false-accusation harm in `CLAUDE.md` both point the other way.

**If C ends up running your fusion instead of theirs, this reasoning inverts and I should
recalibrate.** That is item 8, and it is worth settling before H6.
