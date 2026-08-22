"""The call sites C actually uses in server/orchestrator.py.

    line 103  transcribe(wav_path or waveform)
    line 202  cq_fn(speaker.matched_person_id)          # Optional[str], often None
    line 440  extra_codes = build_reason_codes(script_result)
              fusion.reason_codes.extend(extra_codes)   # merged onto A's codes

C composes: A's `fuse` supplies identity and authenticity codes, B supplies intent
codes, C concatenates. So B's public `build_reason_codes` takes the script alone.
"""

from __future__ import annotations

import pytest

from contracts import (
    EnrolledPerson,
    ReasonCode,
    ScriptAnalysisResult,
    SharedSecret,
    SignalType,
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
    api.configure(encoder=FakeEncoder())
    yield
    api.reset()


# --- transcribe accepts a raw waveform, not just a path ----------------------

def test_transcribe_accepts_a_waveform_list():
    """C passes `wav_path or waveform`, so a list[float] is a first-class input."""
    result = api.transcribe([0.0] * 16_000)
    assert isinstance(result, TranscriptResult)


def test_transcribe_still_accepts_a_path():
    assert isinstance(api.transcribe("does/not/exist.wav"), TranscriptResult)


def test_a_waveform_is_not_mistaken_for_a_file_path():
    from nlp_rag.asr import prepare_audio

    prepared = prepare_audio([0.1, -0.2, 0.3])
    assert not isinstance(prepared, str)
    assert getattr(prepared, "dtype", None) is not None, "expected a float32 array"


def test_an_empty_waveform_degrades_rather_than_raising():
    assert api.transcribe([]) == TranscriptResult.empty()


# --- E3: vernacular_warnings is a dict keyed by band -------------------------

def test_vernacular_warnings_is_a_dict_keyed_by_band():
    """The intent branch cannot know the fused band, so it supplies every option
    and C selects with the band fusion actually produced."""
    warnings = api.analyze_script(
        TranscriptResult(text=SCAM, detected_language="hi")
    ).details["vernacular_warnings"]

    assert isinstance(warnings, dict)
    assert warnings["high_risk"]
    assert warnings["suspicious"]
    assert warnings["caution"]


def test_vernacular_warnings_keys_match_trustband_values():
    warnings = api.analyze_script(
        TranscriptResult(text=SCAM, detected_language="hi")
    ).details["vernacular_warnings"]
    valid = {b.value for b in TrustBand}
    assert set(warnings) <= valid


def test_vernacular_warnings_omit_bands_with_nothing_to_warn_about():
    warnings = api.analyze_script(
        TranscriptResult(text=SCAM, detected_language="hi")
    ).details["vernacular_warnings"]
    assert "verified" not in warnings
    assert "unverified" not in warnings


def test_vernacular_warnings_follow_the_detected_language():
    import re

    devanagari = re.compile(r"[ऀ-ॿ]")
    hindi = api.analyze_script(
        TranscriptResult(text=SCAM, detected_language="hi")
    ).details["vernacular_warnings"]
    english = api.analyze_script(
        TranscriptResult(text=SCAM, detected_language="en")
    ).details["vernacular_warnings"]

    assert devanagari.search(hindi["high_risk"])
    assert not devanagari.search(english["high_risk"])


def test_vernacular_warnings_present_even_when_the_branch_abstains():
    """C reads this key unconditionally; an abstention must not KeyError."""
    details = api.analyze_script(TranscriptResult.empty()).details
    assert isinstance(details.get("vernacular_warnings"), dict)


# --- build_reason_codes takes the script alone -------------------------------

def test_build_reason_codes_accepts_the_script_alone():
    script = create_mock_fixture("red").script
    codes = api.build_reason_codes(script)
    assert codes and all(isinstance(rc, ReasonCode) for rc in codes)


def test_build_reason_codes_returns_only_intent_codes():
    """A's fuse supplies identity and authenticity; duplicating them double-reports."""
    codes = api.build_reason_codes(create_mock_fixture("red").script)
    assert {rc.signal for rc in codes} == {SignalType.INTENT}


def test_build_reason_codes_cites_the_playbook():
    codes = api.build_reason_codes(create_mock_fixture("red").script)
    match = next(rc for rc in codes if rc.code == "RC_SCAM_SCRIPT_MATCH")
    assert match.citation_url.startswith("https://")


def test_build_reason_codes_is_safe_to_extend_onto_an_existing_list():
    fusion = create_mock_fixture("red").fusion
    before = len(fusion.reason_codes)
    fusion.reason_codes.extend(api.build_reason_codes(create_mock_fixture("red").script))
    assert len(fusion.reason_codes) > before


@pytest.mark.parametrize("junk", [None, 42, "nonsense"])
def test_build_reason_codes_degrades_on_garbage(junk):
    assert api.build_reason_codes(junk) == []


def test_build_reason_codes_on_an_abstaining_script_returns_nothing():
    assert api.build_reason_codes(ScriptAnalysisResult.neutral()) == []


# --- challenge_question is called with matched_person_id ---------------------

def test_challenge_question_accepts_a_person_id():
    """C passes speaker.matched_person_id. Without a registered lookup B cannot
    resolve it, and returning None is the correct degradation."""
    assert api.challenge_question("p_rahul_01") is None


def test_challenge_question_accepts_none_person_id():
    """matched_person_id is None whenever the verdict is UNKNOWN."""
    assert api.challenge_question(None) is None


def test_challenge_question_resolves_a_person_id_through_a_registered_lookup():
    person = EnrolledPerson(
        person_id="p_rahul_01",
        name="Rahul",
        relation="Son",
        shared_secrets=[
            SharedSecret(secret_id="s1", question="Our dog's name?",
                         answer_hash="a" * 64, category="pet")
        ],
    )
    api.configure(encoder=FakeEncoder(), person_lookup=lambda pid: person)

    challenge = api.challenge_question("p_rahul_01")
    assert challenge is not None
    assert challenge.question_id == "s1"


def test_challenge_question_still_accepts_an_enrolled_person_directly():
    person = EnrolledPerson(
        person_id="p1", name="Asha", relation="Mother",
        shared_secrets=[
            SharedSecret(secret_id="s9", question="Where were you born?",
                         answer_hash="b" * 64, category="family_memory")
        ],
    )
    assert api.challenge_question(person) is not None


def test_challenge_question_degrades_when_the_lookup_raises():
    def boom(_pid):
        raise RuntimeError("db down")

    api.configure(encoder=FakeEncoder(), person_lookup=boom)
    assert api.challenge_question("p_rahul_01") is None
