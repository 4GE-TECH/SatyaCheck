"""Challenge questions select a stored secret; they do not invent one.

`SharedSecret` is populated at enrollment via `EnrollmentRequest.shared_secrets`, so this
is selection and formatting, not generation. See `nlp_rag/PLAN.md` §10.
"""

from __future__ import annotations

import pytest

from contracts import EnrolledPerson, SharedSecret, TrustBand
from nlp_rag.challenge import select_challenge

SECRETS = [
    SharedSecret(
        secret_id="s1",
        question="What is the name of our hometown dog?",
        answer_hash="a" * 64,
        category="pet",
    ),
    SharedSecret(
        secret_id="s2",
        question="Which city did we visit for Diwali last year?",
        answer_hash="b" * 64,
        category="family_memory",
    ),
]


@pytest.fixture
def person() -> EnrolledPerson:
    return EnrolledPerson(
        person_id="p_rahul_01", name="Rahul", relation="Son", shared_secrets=SECRETS
    )


# --- when a challenge is offered ---------------------------------------------

@pytest.mark.parametrize(
    "band", [TrustBand.CAUTION, TrustBand.SUSPICIOUS, TrustBand.HIGH_RISK]
)
def test_challenge_is_offered_when_identity_is_in_doubt(person, band):
    assert select_challenge(person, band) is not None


@pytest.mark.parametrize(
    "band", [TrustBand.VERIFIED, TrustBand.UNVERIFIED, TrustBand.INSUFFICIENT]
)
def test_no_challenge_when_there_is_nothing_to_challenge(person, band):
    assert select_challenge(person, band) is None


def test_no_challenge_without_an_enrolled_person():
    """In authority_check there is no enrolled person, so there is no shared secret."""
    assert select_challenge(None, TrustBand.HIGH_RISK) is None


def test_no_challenge_when_the_person_has_no_shared_secrets():
    bare = EnrolledPerson(person_id="p1", name="Asha", relation="Mother")
    assert select_challenge(bare, TrustBand.HIGH_RISK) is None


# --- shape -------------------------------------------------------------------

def test_question_is_framed_as_an_instruction_to_the_listener(person):
    challenge = select_challenge(person, TrustBand.HIGH_RISK)
    assert challenge.question_text.startswith("Ask the caller:")


def test_question_carries_the_stored_secret_verbatim(person):
    challenge = select_challenge(person, TrustBand.HIGH_RISK)
    assert any(s.question in challenge.question_text for s in SECRETS)


def test_answer_hash_is_passed_through_unchanged(person):
    challenge = select_challenge(person, TrustBand.HIGH_RISK)
    expected = {s.answer_hash for s in SECRETS}
    assert challenge.expected_answer_hash in expected


def test_relation_context_names_the_relationship(person):
    challenge = select_challenge(person, TrustBand.HIGH_RISK)
    assert "Son" in challenge.relation_context


def test_question_id_identifies_the_secret_used(person):
    challenge = select_challenge(person, TrustBand.HIGH_RISK)
    assert challenge.question_id in {"s1", "s2"}


# --- selection ---------------------------------------------------------------

def test_an_excluded_secret_is_not_reused(person):
    challenge = select_challenge(person, TrustBand.HIGH_RISK, exclude={"s1"})
    assert challenge.question_id == "s2"


def test_returns_none_when_every_secret_is_excluded(person):
    assert select_challenge(person, TrustBand.HIGH_RISK, exclude={"s1", "s2"}) is None


def test_selection_is_deterministic_for_the_same_inputs(person):
    first = select_challenge(person, TrustBand.HIGH_RISK)
    second = select_challenge(person, TrustBand.HIGH_RISK)
    assert first.question_id == second.question_id
