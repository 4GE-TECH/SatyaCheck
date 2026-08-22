"""Reason codes: deterministic templates, driven by C's own mock fixtures.

`ReasonCode` has no `direction` field, so risk-lowering evidence has to be conveyed
through the code name and an INFO severity. That is a real constraint, and these tests
pin it down so D can style the panel against something stable.
"""

from __future__ import annotations

import pytest

from contracts import SeverityLevel, SignalType, TrustBand, create_mock_fixture
from nlp_rag.reason_codes import build_reason_codes


def codes_for(scenario: str) -> list:
    fixture = create_mock_fixture(scenario)
    return build_reason_codes(
        quality=fixture.quality,
        speaker=fixture.speaker,
        spoof=fixture.spoof,
        script=fixture.script,
        mode=fixture.fusion.mode,
    )


def ids_for(scenario: str) -> set[str]:
    return {rc.code for rc in codes_for(scenario)}


# --- one code per scenario ---------------------------------------------------

def test_genuine_call_reports_a_verified_speaker():
    assert "RC_SPEAKER_VERIFIED" in ids_for("green")


def test_genuine_call_reports_bonafide_audio():
    assert "RC_AUDIO_BONAFIDE" in ids_for("green")


def test_cloned_call_reports_synthetic_voice():
    assert "RC_SYNTHETIC_VOICE_DETECTED" in ids_for("red")


def test_cloned_call_reports_the_scam_script_match():
    assert "RC_SCAM_SCRIPT_MATCH" in ids_for("red")


def test_unenrolled_caller_is_reported_as_unverified():
    assert "RC_UNKNOWN_CALLER_UNVERIFIED" in ids_for("unverified")


def test_unenrolled_caller_is_never_reported_as_verified():
    """Green means 'we verified this person'. In authority_check we verified nobody."""
    assert "RC_SPEAKER_VERIFIED" not in ids_for("unverified")


def test_legitimate_synthetic_voice_is_not_reported_as_a_deepfake():
    """A bank IVR is synthetic and legitimate. Intent gating is what separates them."""
    ids = ids_for("unverified")
    assert "RC_SYNTHETIC_VOICE_DETECTED" not in ids
    assert "RC_LEGIT_AUTOMATED_VOICE" in ids


def test_genuine_unusual_request_reports_markers_without_claiming_a_playbook_match():
    """PRD §6 guard two: a real family member asking for money must be amber, not red."""
    ids = ids_for("caution")
    assert "RC_RISK_MARKERS_PRESENT" in ids
    assert "RC_SCAM_SCRIPT_MATCH" not in ids


def test_genuine_unusual_request_surfaces_the_verification_invite():
    assert "RC_EXCULPATORY_EVIDENCE" in ids_for("caution")


def test_genuine_unusual_request_raises_nothing_critical():
    assert all(rc.severity is not SeverityLevel.CRITICAL for rc in codes_for("caution"))


def test_synthetic_caller_making_a_request_is_not_called_legitimate():
    """The suspicious fixture is synthetic AND asking for something.

    Emitting 'no suspicious request' beside a list of suspicious requests puts two
    contradictory statements in the same panel.
    """
    ids = ids_for("suspicious")
    assert "RC_RISK_MARKERS_PRESENT" in ids, "precondition: a request was detected"
    assert "RC_LEGIT_AUTOMATED_VOICE" not in ids


def test_synthetic_caller_making_a_request_is_reported_as_unverified_synthesis():
    assert "RC_SYNTHETIC_VOICE_UNVERIFIED" in ids_for("suspicious")


def test_synthetic_caller_making_a_request_is_still_not_called_a_deepfake():
    """Uncorroborated. Between 'legitimate' and 'deepfake' there has to be a middle."""
    assert "RC_SYNTHETIC_VOICE_DETECTED" not in ids_for("suspicious")


def test_bank_ivr_with_no_requests_is_still_called_legitimate():
    """The intent gate must survive the fix above: zero markers means zero suspicion."""
    fixture = create_mock_fixture("unverified")
    assert not fixture.script.incriminating_markers, "precondition"
    assert "RC_LEGIT_AUTOMATED_VOICE" in ids_for("unverified")


def test_insufficient_audio_reports_only_a_quality_code():
    codes = codes_for("insufficient")
    assert [rc.code for rc in codes] == ["RC_QUALITY_INSUFFICIENT"]
    assert codes[0].signal is SignalType.QUALITY


# --- citations ---------------------------------------------------------------

def test_scam_script_code_cites_the_retrieved_playbook():
    match = next(rc for rc in codes_for("red") if rc.code == "RC_SCAM_SCRIPT_MATCH")
    fixture_playbook = create_mock_fixture("red").script.playbooks[0]
    assert match.citation_url == fixture_playbook.source_url
    assert match.citation_title == fixture_playbook.title


def test_synthetic_voice_code_carries_a_citation():
    match = next(rc for rc in codes_for("red") if rc.code == "RC_SYNTHETIC_VOICE_DETECTED")
    assert match.citation_url is not None
    assert match.citation_url.startswith("https://")


# --- exculpatory evidence has to survive a schema with no direction field ----

def test_exculpatory_markers_produce_an_informational_code():
    ids = ids_for("green")
    assert "RC_EXCULPATORY_EVIDENCE" in ids
    code = next(rc for rc in codes_for("green") if rc.code == "RC_EXCULPATORY_EVIDENCE")
    assert code.severity is SeverityLevel.INFO


def test_exculpatory_code_names_the_marker_that_lowered_risk():
    code = next(rc for rc in codes_for("green") if rc.code == "RC_EXCULPATORY_EVIDENCE")
    assert "Will be home by 7 PM" in code.value or "Will be home by 7 PM" in code.explanation


# --- shape -------------------------------------------------------------------

@pytest.mark.parametrize("scenario", ["green", "caution", "suspicious", "red", "unverified", "insufficient"])
def test_every_code_is_displayable(scenario: str):
    for rc in codes_for(scenario):
        assert rc.value, rc.code
        assert rc.explanation, rc.code
        assert isinstance(rc.signal, SignalType), rc.code


@pytest.mark.parametrize("scenario", ["green", "caution", "suspicious", "red", "unverified"])
def test_codes_are_ordered_most_severe_first(scenario: str):
    order = {
        SeverityLevel.CRITICAL: 0,
        SeverityLevel.HIGH: 1,
        SeverityLevel.MEDIUM: 2,
        SeverityLevel.LOW: 3,
        SeverityLevel.INFO: 4,
    }
    ranks = [order[rc.severity] for rc in codes_for(scenario)]
    assert ranks == sorted(ranks)


def test_a_thresholded_code_reports_the_threshold_it_was_measured_against():
    match = next(rc for rc in codes_for("red") if rc.code == "RC_SYNTHETIC_VOICE_DETECTED")
    assert match.threshold


# --- never raises ------------------------------------------------------------

def test_returns_a_list_when_every_branch_is_neutral():
    from contracts import (
        AntiSpoofResult,
        OperatingMode,
        QualityGateResult,
        ScriptAnalysisResult,
        SpeakerVerificationResult,
    )

    codes = build_reason_codes(
        quality=QualityGateResult.passed_default(speech_duration_s=4.0, snr_db=20.0),
        speaker=SpeakerVerificationResult.neutral(),
        spoof=AntiSpoofResult.neutral(),
        script=ScriptAnalysisResult.neutral(),
        mode=OperatingMode.AUTHORITY_CHECK,
    )
    assert isinstance(codes, list)


def test_malformed_input_degrades_instead_of_raising():
    """Rule 5: a branch failing must degrade the verdict, not fail the request."""
    codes = build_reason_codes(
        quality=None, speaker=None, spoof=None, script=None, mode=None  # type: ignore[arg-type]
    )
    assert codes == []
