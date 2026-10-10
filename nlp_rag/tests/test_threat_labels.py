"""Item 10: every scam family maps to a sector and a threat, worded as a pattern.

The label names what the call *resembles* — "banking / KYC update fraud" — beside the
reason codes. It is never an accusation (PRD NG2: no binary verdicts; false accusation
inside a family is a real harm), so the wording is checked as well as the coverage.
"""

from __future__ import annotations

import re

import pytest

from contracts import TranscriptResult
from nlp_rag import api
from nlp_rag.corpus_loader import VALID_FAMILIES
from nlp_rag.tests.fakes import FakeEncoder
from nlp_rag.threat_labels import NO_LABEL_FAMILIES, THREAT_LABELS, threat_label_for

ACCUSATORY = re.compile(r"\b(scammer|fraudster|criminal|culprit|guilty|thief)\b", re.I)


def test_every_scam_family_has_a_label():
    """Adding a family to the corpus without a label must fail here, not ship unlabelled."""
    assert set(THREAT_LABELS) | NO_LABEL_FAMILIES == set(VALID_FAMILIES)
    assert not set(THREAT_LABELS) & NO_LABEL_FAMILIES


def test_benign_and_guidance_families_get_no_label():
    for family in ("none", "reporting", None, "not-a-family"):
        assert threat_label_for(family) is None


@pytest.mark.parametrize("family", sorted(THREAT_LABELS))
def test_labels_name_a_pattern_never_a_person(family):
    label = threat_label_for(family)
    assert label["family"] == family
    assert label["sector"] and label["threat"]
    assert not ACCUSATORY.search(label["threat"]), label


def test_kyc_is_banking():
    assert threat_label_for("kyc_update")["sector"] == "banking"


@pytest.fixture
def wired():
    saved = (api._retriever, api._configured, api._person_lookup)
    api.configure(encoder=FakeEncoder())
    yield
    api._retriever, api._configured, api._person_lookup = saved


@pytest.fixture
def real_retriever():
    """The BGE-m3 retriever the root conftest preloads. FakeEncoder cites no playbook
    for real scam text, which would make the label test pass vacuously (None == None)."""
    saved = (api._retriever, api._configured, api._person_lookup)
    if api._retriever is None or not api._configured:
        api.configure()
    if api._retriever is None or type(api._retriever._encoder).__name__ == "FakeEncoder":
        api._retriever, api._configured, api._person_lookup = saved
        pytest.skip("needs the real BGE-m3 retriever (models/bge-m3)")
    yield
    api._retriever, api._configured, api._person_lookup = saved


def test_analyze_script_reports_the_label_of_the_cited_family(real_retriever):
    text = ("This is CBI officer, your Aadhaar is linked to money laundering, "
            "you are under digital arrest, do not disconnect.")
    result = api.analyze_script(TranscriptResult(text=text, detected_language="en"))
    assert result.playbooks, "no playbook cited — the test would prove nothing"
    assert result.details["scam_family"] == "digital_arrest"
    assert result.details["threat_label"] == threat_label_for("digital_arrest")


def test_a_benign_call_has_no_label(wired):
    result = api.analyze_script(TranscriptResult(text="Hi Ma, reached office, home by seven.",
                                                 detected_language="en"))
    assert result.details.get("threat_label") is None
