"""Item 10 / C2: fusion attaches the threat label only when the verdict is a warning.

The intent branch reports which family a cited playbook belongs to whatever the risk,
because fusion owns the band. A genuine, benign call that loosely resembles a KYC script
must not carry "banking / KYC update fraud" under a green or grey verdict — so the label
is attached only for caution and worse, and only when a playbook was actually cited.
"""

from __future__ import annotations

from contracts import (
    AntiSpoofResult,
    RetrievedPlaybook,
    ScriptAnalysisResult,
    SpeakerVerdict,
    SpeakerVerificationResult,
    ThreatLabel,
    TrustBand,
    create_mock_fixture,
)
from server.orchestrator import _compute_fusion

LABEL = {"sector": "banking", "threat": "KYC update fraud", "family": "kyc_update"}
PLAYBOOK = RetrievedPlaybook(playbook_id="pb", title="KYC fraud advisory", category="Bank KYC",
                             similarity_score=0.9, matched_excerpt="...",
                             source_url="https://example.invalid", source_agency="RBI")


def _speaker(verdict=SpeakerVerdict.UNKNOWN, risk=0.5):
    return SpeakerVerificationResult(verdict=verdict, risk=risk)


def _spoof(risk=0.0):
    return AntiSpoofResult(risk=risk, details={"available": True})


def _script(risk, label=LABEL, playbooks=(PLAYBOOK,)):
    return ScriptAnalysisResult(risk=risk, playbooks=list(playbooks),
                                details={"available": True, "threat_label": label})


def test_a_warning_carries_the_label():
    fusion = _compute_fusion(_speaker(), _spoof(0.9), _script(0.95))
    assert fusion.band in (TrustBand.SUSPICIOUS, TrustBand.HIGH_RISK)
    assert fusion.threat_label == ThreatLabel(**LABEL)


def test_a_calm_verdict_never_carries_a_label():
    fusion = _compute_fusion(_speaker(SpeakerVerdict.MATCH, 0.05), _spoof(0.0), _script(0.02))
    assert fusion.band in (TrustBand.VERIFIED, TrustBand.UNVERIFIED)
    assert fusion.threat_label is None


def test_no_cited_playbook_means_no_label():
    fusion = _compute_fusion(_speaker(), _spoof(0.9), _script(0.95, playbooks=()))
    assert fusion.threat_label is None


def test_a_malformed_label_is_dropped_not_raised():
    fusion = _compute_fusion(_speaker(), _spoof(0.9), _script(0.95, label={"sector": "banking"}))
    assert fusion.threat_label is None


def test_old_responses_without_a_label_still_load():
    data = create_mock_fixture("red").model_dump(mode="json")
    data["fusion"].pop("threat_label", None)
    assert type(create_mock_fixture("red")).model_validate(data).fusion.threat_label is None
