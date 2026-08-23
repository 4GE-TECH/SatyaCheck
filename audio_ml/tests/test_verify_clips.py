"""End-to-end speaker verification against the recorded eval clips.

These are the tests that would have caught the demo-day failure. Everything else in
the speaker path can be green while this is broken, because the broken state is
`verdict == "unknown"` — a *legitimate* verdict meaning "nobody enrolled is close".
It is what a genuine stranger returns. So a completely dead identity branch and a
working one look identical in the API response, in the UI and in the logs.

A test that asserts `/api/enroll` returns 200 passes while the feature is broken.
A test that asserts `verify_speaker` returns a `SpeakerSignal` passes too. Only
asserting on the *verdict for known audio* pins the behaviour.

`friend` is the fixture speaker rather than `me`, because the friend clips are the
consistent pair: friend → friend_test drops 0.0536 across sessions where
me → me_test2 drops 0.1834. See `test_known_limitation_...` at the bottom, and the
threshold note in config.py.

Requires the ECAPA checkpoint in models/ecapa/ and the cohort in data/cohort/, so
the whole module skips when they are absent rather than failing a clean checkout.
"""

from __future__ import annotations

import pytest

import config

CLIPS = config.REPO_ROOT / "data" / "eval_set" / "clips"
ECAPA = config.REPO_ROOT / "models" / "ecapa" / "hyperparams.yaml"

pytestmark = pytest.mark.skipif(
    not ECAPA.is_file() or not (CLIPS / "friend.wav").is_file(),
    reason="needs models/ecapa/ and data/eval_set/clips/ (see nlp_rag/INTEGRATION.md §1)",
)


@pytest.fixture
def enrolled(tmp_path, monkeypatch):
    """Enroll into an isolated voiceprint directory, and return an enroll helper.

    Isolation matters more than it looks. `data/enrollments/` ships with
    `alice.npz`, which was enrolled from `me.wav` and therefore matches that clip at
    cosine 1.0000. Left in place it makes genuine-match assertions pass for the
    wrong reason and hides regressions — and `verify_speaker` globs the directory,
    so there is no argument to override.
    """
    from audio_ml import enroll
    from audio_ml.api import enroll_person

    monkeypatch.setattr(enroll, "ENROLLMENTS_DIR", tmp_path)
    monkeypatch.setattr(config, "ENROLLMENTS_DIR", tmp_path)

    def _enroll(person_id: str, *clips: str) -> None:
        person = enroll_person(
            person_id, person_id.title(), "family", [str(CLIPS / f"{c}.wav") for c in clips]
        )
        assert person is not None, "enrollment returned None; ECAPA or audio load failed"
        assert (tmp_path / f"{person_id}.npz").is_file(), (
            "enroll_person reported success but wrote no voiceprint — this is the "
            "silent failure mode the whole module exists to catch"
        )

    _enroll.dir = tmp_path
    return _enroll


def _verify(clip: str):
    from audio_ml.api import verify_speaker

    return verify_speaker(str(CLIPS / f"{clip}.wav"))


def test_enrollment_writes_a_voiceprint_to_disk(enrolled):
    """`verify_speaker` globs its own directory, so the .npz *is* the integration point.

    `server/enroll_router.py` calls `audio_ml.api.enroll_person` for exactly this
    reason: without the file on disk the identity branch has nothing to compare
    against, and returns `unknown` for a person enrolled seconds earlier.
    """
    enrolled("friend", "friend")
    assert (enrolled.dir / "friend.npz").is_file()


def test_the_enrolled_speaker_is_not_unknown(enrolled):
    """The exact demo-day symptom: enroll someone, screen them, get *unverified*.

    A different recording of the enrolled speaker, so this is not a self-match.
    """
    enrolled("friend", "friend")
    signal = _verify("friend_test")

    assert signal.verdict != "unknown", (
        f"a second recording of the enrolled speaker came back 'unknown' "
        f"(raw={signal.raw_cosine:.4f}, norm={signal.norm_score:.4f}) — the "
        "identity branch is measuring nothing"
    )
    assert signal.verdict == "match"
    assert signal.best_match_id == "friend"


def test_a_different_speaker_is_not_matched(enrolled):
    """me.wav is a genuinely different person from the only enrolled speaker."""
    enrolled("friend", "friend")
    signal = _verify("me")

    assert signal.verdict != "match", (
        f"a different speaker matched the enrolled voiceprint "
        f"(raw={signal.raw_cosine:.4f}) — false verification"
    )


def test_the_cloned_voice_is_not_verified(enrolled):
    """The product's core claim, on the one clip that tests it.

    `cloned_scam.wav` is a synthesised voice of the enrolled speaker. Reporting
    `match` would mean telling a user "we verified this is your family member"
    about a clone.
    """
    enrolled("friend", "friend")
    signal = _verify("cloned_scam")

    assert signal.verdict != "match", (
        f"the cloned voice was verified as an enrolled speaker "
        f"(raw={signal.raw_cosine:.4f}, norm={signal.norm_score:.4f})"
    )


def test_the_match_threshold_keeps_both_margins(enrolled):
    """Pin the operating point from both sides.

    Asserting the verdicts alone would let `SPEAKER_MATCH_THRESHOLD` drift to either
    edge of the genuine/clone gap and still pass. Both edges are real failures and
    they pull in opposite directions:

      too high → a genuine family member reads `mismatch`, which fusion treats as
                 identity risk 0.85 *and* feeds into `intent`, pushing a benign
                 call toward red.
      too low  → the clone reads `match`.
    """
    enrolled("friend", "friend")
    genuine = _verify("friend_test").raw_cosine
    clone = _verify("cloned_scam").raw_cosine
    threshold = config.SPEAKER_MATCH_THRESHOLD

    assert genuine > clone, "test premise broken: the clone outscored the genuine probe"
    assert genuine - threshold >= 0.05, (
        f"only {genuine - threshold:.4f} of headroom above the threshold for a "
        f"genuine speaker — too close to false-accusing family"
    )
    assert threshold - clone >= 0.05, (
        f"only {threshold - clone:.4f} of headroom below the threshold for a clone"
    )


def test_norm_score_is_not_saturated_across_clips(enrolled):
    """s-normalisation has to stay informative, not pin everything to a ceiling.

    Before the temperature fix every clip reported norm_score == 0.9933 — the
    sigmoid ceiling — genuine speaker and clone alike. The verdict is decided on raw
    cosine, but a norm_score carrying no information is worse than none: it is
    returned to C, stored in the session, and rendered as evidence.
    """
    enrolled("friend", "friend")
    scores = {clip: _verify(clip).norm_score for clip in ("friend_test", "cloned_scam", "me")}

    assert len(set(round(s, 4) for s in scores.values())) > 1, (
        f"every clip reported the same norm_score: {scores}"
    )


def test_verify_speaker_never_raises_on_bad_input(tmp_path):
    """CLAUDE.md rule 5, on the paths most likely to be hit in a demo."""
    from audio_ml.api import verify_speaker

    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    missing = tmp_path / "nope.wav"

    for path in (str(empty), str(missing), ""):
        signal = verify_speaker(path)
        assert signal.verdict == "unknown"
        assert signal.best_match_id is None


@pytest.mark.xfail(
    reason=(
        "KNOWN LIMITATION, not a threshold bug. me_test2 is a genuine second "
        "recording of the enrolled speaker but scores 0.7857 — only 0.0226 above "
        "cloned_scam (0.7631), so no threshold separates them meaningfully. The "
        "cause is enrollment quality: me->me_test2 drops 0.1834 across sessions "
        "where friend->friend_test drops 0.0536. Fix is multi-session, "
        "condition-matched enrollment per CLAUDE.md, not a lower cut. Left as xfail "
        "so it stays visible and flips to XPASS when enrollment improves."
    ),
    strict=False,
)
def test_known_limitation_single_clip_enrollment_false_mismatches(enrolled):
    enrolled("me", "me")
    assert _verify("me_test2").verdict == "match"
