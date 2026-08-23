"""The intent branch measured on real spoken audio, wideband and 8 kHz.

Every other number this branch reports — 94% recall, 5.8% benign false positives, P@3 98%
— was measured on **written text**, because until now that is all that existed. These are
human recordings of five held-out scripts, so this is the first evidence any of it
survives a person actually speaking the words and Whisper transcribing them.

The clips are named for their script ids, so the filename is the ground-truth label and
no manifest can drift out of sync (`nlp_rag/scripts_for_a.md`).

TWO THINGS THESE GUARD

**Speech is not text.** ASR introduces errors the corpus never contains. Measured, the
worst degradation from clean text to spoken audio was −0.054, and two clips scored
*higher* spoken than written.

**Real calls are narrowband.** Speakerphone and phone audio are closer to 8 kHz than to a
clean recording, and 8 kHz discards everything above 4 kHz — the band carrying most
consonant discrimination. Measured, the worst degradation was −0.074 and every clip stayed
above the amber floor.

The most interesting row is `held-family-emergency-001`: spoken in Hinglish, transcribed by
Whisper into badly-corrupted Devanagari (*"पप्पा मेरे अख्स्टेण्ट लोग अस्प्टल मे हु"*), and it
still scores above amber. That is the multilingual corpus and the marker set working on
genuinely degraded input, which is the case they were built for.
"""

from __future__ import annotations

import pytest

import config
from nlp_rag import thresholds
from nlp_rag.api import analyze_script, transcribe

CLIPS = config.REPO_ROOT / "data" / "eval_set" / "clips"
WHISPER = config.MODELS_DIR / f"faster-whisper-{config.WHISPER_MODEL_SIZE}"

#: clip id -> the held-out script it records. The filename IS the label.
RECORDED = [
    "held-digital-arrest-004",
    "held-telecom-002",
    "held-credential-002",
    "held-sms-fraud-001",
    "held-family-emergency-001",
]

pytestmark = pytest.mark.skipif(
    not WHISPER.is_dir() or not (CLIPS / "held-telecom-002.wav").is_file(),
    reason="needs the whisper checkpoint and the recorded clips (INTEGRATION.md §1.1)",
)


def _risk(clip: str) -> float:
    return analyze_script(transcribe(str(CLIPS / f"{clip}.wav"))).risk


@pytest.mark.parametrize("clip", RECORDED)
def test_a_spoken_scam_script_clears_the_amber_floor(clip):
    """A real person reading a real scam script must raise concern.

    This is the end-to-end claim the whole branch exists to support, on audio rather
    than on the text the corpus was tuned against.
    """
    risk = _risk(clip)
    assert risk >= thresholds.AMBER_FLOOR, (
        f"{clip} spoken aloud scored {risk:.3f}, below the {thresholds.AMBER_FLOOR} "
        "floor — the user would see no concern at all"
    )


@pytest.mark.parametrize("clip", RECORDED)
def test_the_same_script_at_8khz_still_clears_the_floor(clip):
    """Narrowband is the normal case, not an edge case.

    Real calls arrive degraded: 8 kHz discards everything above 4 kHz, which is where
    most consonant discrimination lives. A branch that only works on studio audio does
    not work.
    """
    risk = _risk(f"{clip}_nb8k")
    assert risk >= thresholds.AMBER_FLOOR, (
        f"{clip} at 8 kHz scored {risk:.3f} — the branch does not survive phone audio"
    )


@pytest.mark.parametrize("clip", RECORDED)
def test_narrowband_does_not_collapse_the_score(clip):
    """Bounded degradation, not merely "still above the floor".

    A clip that scraped past the floor after losing 0.3 would pass the test above while
    telling us the branch is one bad recording away from silence.
    """
    wideband, narrowband = _risk(clip), _risk(f"{clip}_nb8k")
    assert narrowband >= wideband - 0.15, (
        f"{clip}: {wideband:.3f} wideband -> {narrowband:.3f} at 8 kHz, a drop of "
        f"{wideband - narrowband:.3f}"
    )


def test_the_recordings_transcribe_to_something_usable():
    """If ASR returns nothing the risk scores above are meaningless.

    Guards the case where a clip is re-recorded badly, or an ffmpeg change breaks the
    conversion: without this, every score would fall to the abstention path and the
    floor assertions would fail with a confusing message about risk rather than about
    the transcript.
    """
    for clip in RECORDED:
        transcript = transcribe(str(CLIPS / f"{clip}.wav"))
        assert transcript.text.strip(), f"{clip} produced no transcript at all"
        assert len(transcript.text.split()) >= 10, (
            f"{clip} produced only {transcript.text!r} — too short to retrieve against"
        )


def test_spoken_scripts_retrieve_their_own_family():
    """Citations have to survive speech, not just text.

    Not every clip clears the corroboration floor — that gate is deliberately strict and
    §12.1 measures the recall cost. But when a citation *is* shown for a spoken clip it
    must point at that scam's own family, or the evidence panel is citing the wrong
    advisory to a frightened relative.
    """
    from nlp_rag.corpus_loader import load_corpus
    from nlp_rag import api

    corpus = load_corpus(api.CORPUS_DIR)
    families = {doc.id: doc.scam_family for doc in corpus.anchors}
    cited = 0

    for clip in RECORDED:
        script = analyze_script(transcribe(str(CLIPS / f"{clip}.wav")))
        for playbook in script.playbooks[:1]:
            expected = clip.replace("held-", "").rsplit("-", 1)[0]
            actual = families.get(playbook.playbook_id, "")
            cited += 1
            assert expected.replace("-", "_") in actual or actual in expected.replace("-", "_"), (
                f"{clip} cited {playbook.playbook_id} (family {actual!r}), "
                f"which is not the {expected!r} family"
            )

    assert cited, "no spoken clip retrieved a citable playbook at all"
