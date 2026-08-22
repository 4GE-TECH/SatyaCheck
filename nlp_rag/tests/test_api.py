"""The public boundary.

`CLAUDE.md`: "Nothing else crosses a folder boundary. Ever." These four functions are
the entire contract with C, and rule 5 says none of them may raise — a branch failing
must degrade the verdict, not fail the request.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from contracts import (
    OperatingMode,
    ScriptAnalysisResult,
    TranscriptResult,
    TrustBand,
    create_mock_fixture,
)
from nlp_rag import api
from nlp_rag.tests.fakes import FakeEncoder

SCAM = (
    "Papa emergency ho gaya hai, police ne pakad liya hai. "
    "Phone kisi ko mat dena, turant 50000 bhejo is UPI ID pe."
)


@pytest.fixture(autouse=True)
def wired():
    """Inject the fake encoder at the composition root, then restore."""
    api.configure(encoder=FakeEncoder())
    yield
    api.reset()


def transcript(text: str, confidence: float = 0.95) -> TranscriptResult:
    return TranscriptResult(
        text=text, segments=[], detected_language="hi", confidence=confidence
    )


# --- the boundary itself -----------------------------------------------------

def test_the_four_public_functions_are_importable():
    from nlp_rag.api import (  # noqa: F401
        analyze_script,
        build_reason_codes,
        challenge_question,
        transcribe,
    )


# --- analyze_script ----------------------------------------------------------

def test_scam_transcript_is_scored_as_high_intent_risk():
    assert api.analyze_script(transcript(SCAM)).risk >= 0.90


def test_scam_transcript_returns_a_cited_playbook():
    playbooks = api.analyze_script(transcript(SCAM)).playbooks
    assert playbooks
    assert playbooks[0].source_url.startswith("https://")


def test_benign_transcript_is_scored_as_low_intent_risk():
    result = api.analyze_script(
        transcript("Hi Ma, I just reached the office. Will be home by 7 PM today.")
    )
    assert result.risk <= 0.10


def test_empty_transcript_returns_the_neutral_result():
    assert api.analyze_script(TranscriptResult.empty()).risk == 0.0


def test_hallucinated_repetition_is_not_scored():
    """A Whisper decoder loop must not become a confident intent risk."""
    looped = transcript("Thanks for watching. " * 6, confidence=0.4)
    assert api.analyze_script(looped).risk == 0.0


def test_gate_rejection_is_visible_rather_than_silent():
    looped = transcript("Thanks for watching. " * 6, confidence=0.4)
    details = api.analyze_script(looped).details
    assert details.get("gate_reason") == "repetition"


def test_analyze_script_returns_a_valid_result_for_garbage_input():
    for junk in (None, 42, "not a transcript", object()):
        result = api.analyze_script(junk)  # type: ignore[arg-type]
        assert isinstance(result, ScriptAnalysisResult)


def test_analyze_script_degrades_to_markers_only_without_an_encoder(monkeypatch):
    """No BGE-m3 means no retrieval. Markers still work; risk stays uncorroborated.

    The absent-encoder state is forced rather than inherited from the machine. This
    test previously passed only because models/ happened to be empty, so it started
    failing the moment BGE-m3 was downloaded -- it was asserting on the environment,
    not on the degradation path.
    """
    import nlp_rag.embed

    monkeypatch.setattr(nlp_rag.embed, "load_encoder", lambda: None)
    api.reset()
    result = api.analyze_script(transcript(SCAM))

    assert isinstance(result, ScriptAnalysisResult)
    assert result.playbooks == []
    assert result.incriminating_markers
    assert result.risk < 0.75  # no citation, so it cannot reach red


# --- transcribe --------------------------------------------------------------

def test_transcribe_returns_an_empty_result_when_the_asr_backend_is_absent(tmp_path: Path):
    """faster-whisper is not installed yet. That degrades; it does not raise."""
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"RIFF....WAVEfmt ")
    assert api.transcribe(audio).text == ""


def test_transcribe_returns_an_empty_result_for_a_missing_file():
    assert api.transcribe("does/not/exist.wav") == TranscriptResult.empty()


def test_transcribe_returns_an_empty_result_for_garbage_input():
    for junk in (None, 42, object()):
        assert isinstance(api.transcribe(junk), TranscriptResult)  # type: ignore[arg-type]


# --- build_reason_codes ------------------------------------------------------

def test_reason_codes_are_produced_from_the_script():
    """C merges B's codes onto A's, so the public form takes the script alone.

    The whole-panel variant still exists as `nlp_rag.reason_codes.build_reason_codes`
    and is covered in test_reason_codes.py.
    """
    codes = api.build_reason_codes(create_mock_fixture("red").script)
    assert any(rc.code == "RC_SCAM_SCRIPT_MATCH" for rc in codes)


def test_reason_codes_degrade_to_an_empty_list_on_garbage_input():
    assert api.build_reason_codes(None) == []  # type: ignore[arg-type]


# --- challenge_question ------------------------------------------------------

def test_challenge_question_is_none_without_an_enrolled_person():
    assert api.challenge_question(None, TrustBand.HIGH_RISK) is None


def test_challenge_question_degrades_to_none_on_garbage_input():
    assert api.challenge_question(42, "nonsense") is None  # type: ignore[arg-type]


# --- the vernacular warning rides on details ---------------------------------

def test_vernacular_warnings_are_delivered_through_script_details():
    """There is no fifth public function, so the warnings travel in `details`."""
    details = api.analyze_script(transcript(SCAM)).details
    assert details["vernacular_warnings"]["high_risk"]


def test_vernacular_warnings_are_supplied_even_for_a_benign_transcript():
    """Not a judgement about this transcript — a menu for C to select from.

    A benign intent branch can still fuse into a risky band on identity and
    authenticity alone, and that verdict still has to be speakable.
    """
    details = api.analyze_script(
        transcript("Hi Ma, I just reached the office. Will be home by 7 PM today.")
    ).details
    assert details["vernacular_warnings"]["high_risk"]


# --- concurrency safety: C runs the three branches together ------------------

def test_repeated_calls_return_consistent_results():
    first = api.analyze_script(transcript(SCAM)).risk
    for _ in range(5):
        assert api.analyze_script(transcript(SCAM)).risk == first


def test_operating_mode_is_not_required_to_score_intent():
    """The intent branch is independent of identity; it must not need the mode."""
    assert api.analyze_script(transcript(SCAM)).risk > 0
    assert OperatingMode.AUTHORITY_CHECK is not None  # mode belongs to fusion, not here
