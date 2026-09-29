"""Model A (fine-tuned AASIST) behind `detect_spoof`.

Pins three things:
  * with the checkpoint present, `detect_spoof` returns real per-window scores, not
    the 0.5 "uncertain" placeholder;
  * inference is deterministic — the same file scores identically twice (no random
    cropping, no dropout, no frequency augmentation at inference);
  * the known clone clips in the repo score higher than the genuine clips. This is a
    tiny sample (2 clones, 4 genuine, 2 speakers) — a sanity check that the class
    index is not inverted, not an accuracy claim.

And one failure path: a missing checkpoint degrades to the neutral 0.5, never raises.
"""

from __future__ import annotations

import statistics

import pytest

import config
from audio_ml import spoof

CLIPS = config.REPO_ROOT / "data" / "eval_set" / "clips"
CLONES = ["cloned_scam", "friend_clone"]
GENUINE = ["friend", "friend_test", "me", "me_test2"]

needs_model = pytest.mark.skipif(
    not spoof.model_files_present(),
    reason="Model A not installed under models/antispoof/ (see audio_ml/spoof.py)",
)


@needs_model
def test_detect_spoof_returns_real_scores_not_the_placeholder():
    signal = spoof.detect_spoof(str(CLIPS / "friend_test.wav"))
    assert signal.n_chunks > 0, "no windows were scored"
    assert signal.verdict != "uncertain", signal
    assert signal.timeline, "real scoring must produce a timeline"


@needs_model
def test_inference_is_deterministic():
    a = spoof.detect_spoof(str(CLIPS / "cloned_scam.wav"))
    b = spoof.detect_spoof(str(CLIPS / "cloned_scam.wav"))
    assert [s.score for s in a.timeline] == [s.score for s in b.timeline]
    assert a.score == b.score and a.peak == b.peak


@needs_model
def test_known_clones_score_higher_than_genuine_clips():
    clone = {c: spoof.detect_spoof(str(CLIPS / f"{c}.wav")).score for c in CLONES}
    genuine = {g: spoof.detect_spoof(str(CLIPS / f"{g}.wav")).score for g in GENUINE}
    print("\nclone  :", {k: round(v, 4) for k, v in clone.items()})
    print("genuine:", {k: round(v, 4) for k, v in genuine.items()})
    assert statistics.median(clone.values()) > statistics.median(genuine.values()), (
        f"clones did not score above genuine: clone={clone} genuine={genuine}"
    )


def test_missing_checkpoint_degrades_to_neutral(monkeypatch, tmp_path):
    monkeypatch.setattr(spoof, "ANTISPOOF_DIR", tmp_path / "nowhere")
    monkeypatch.setattr(spoof, "_model", None)
    monkeypatch.setattr(spoof, "_load_attempted", False)
    signal = spoof.detect_spoof(str(CLIPS / "friend_test.wav"))
    assert signal.score == 0.5 and signal.verdict == "uncertain" and signal.n_chunks == 0
