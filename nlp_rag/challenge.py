"""Out-of-band challenge questions.

`SharedSecret` is captured at enrollment (`EnrollmentRequest.shared_secrets` is a list of
`{question, answer}` pairs), so this module **selects and formats** a stored secret. It
does not generate one, and it never sees the answer — only the hash, which it passes
through untouched.

A challenge is only offered when identity is actually in doubt. Offering one for a
verified caller trains the user to ignore it; offering one in `authority_check` is
impossible, because an unenrolled stranger shares no secret with anyone.
"""

from __future__ import annotations

from collections.abc import Collection

from contracts import ChallengeQuestion, EnrolledPerson, SharedSecret, TrustBand

#: Bands where the caller's identity is genuinely in question.
CHALLENGEABLE_BANDS: frozenset[TrustBand] = frozenset(
    {TrustBand.CAUTION, TrustBand.SUSPICIOUS, TrustBand.HIGH_RISK}
)

#: Categories a stranger could plausibly research are used last.
_CATEGORY_PRIORITY: dict[str, int] = {
    "family_memory": 0,
    "pet": 1,
    "milestone": 2,
    "personal": 3,
}


def _rank(secret: SharedSecret) -> tuple[int, str]:
    return _CATEGORY_PRIORITY.get(secret.category, 99), secret.secret_id


def select_challenge(
    person: EnrolledPerson | None,
    band: TrustBand,
    exclude: Collection[str] = (),
) -> ChallengeQuestion | None:
    """Pick a shared secret to challenge the caller with, or None.

    `exclude` holds secret ids already used in this session, so a caller who is still on
    the line is not asked the same question twice.
    """
    try:
        if person is None or band not in CHALLENGEABLE_BANDS:
            return None

        excluded = set(exclude)
        candidates = [s for s in person.shared_secrets if s.secret_id not in excluded]
        if not candidates:
            return None

        secret = sorted(candidates, key=_rank)[0]
        return ChallengeQuestion(
            question_id=secret.secret_id,
            question_text=f"Ask the caller: '{secret.question}'",
            relation_context=f"Known only to {person.name} ({person.relation}) and family",
            expected_answer_hash=secret.answer_hash,
        )
    except Exception:  # noqa: BLE001 - rule 5: degrade, never raise into the caller
        return None


if __name__ == "__main__":  # pragma: no cover - CLI smoke test
    demo = EnrolledPerson(
        person_id="p_rahul_01",
        name="Rahul",
        relation="Son",
        shared_secrets=[
            SharedSecret(secret_id="s1", question="What is our hometown dog's name?",
                         answer_hash="a" * 64, category="pet"),
            SharedSecret(secret_id="s2", question="Where did we go for Diwali?",
                         answer_hash="b" * 64, category="family_memory"),
        ],
    )
    for band in TrustBand:
        challenge = select_challenge(demo, band)
        print(f"  {band.value:14} {challenge.question_text if challenge else '—'}")
