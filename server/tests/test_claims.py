"""Upgrade plan, Phase 2: identity with claim provenance and no automatic accusation.

Three hints, recorded separately, none treated as proof:

  user        "Who's calling?" pick (CallerMetadata.claimed_identity)   medium; can support a mismatch
  caller_id   displayed number (CallerMetadata.claimed_number)          untrusted; NEVER accuses alone
  transcript  "Papa bol raha hoon"                                       medium; can support a mismatch

Outcomes (verdict stays the frozen three-way enum; detail in details["claim_check"]):
match · inconclusive (grey zone, no accusation) · mismatch (below LOW and backed by user or
transcript) · conflict (sources disagree) · ambiguous (alias fits two people) · unconfirmed
(caller ID only, voice doesn't match) · no_voiceprint. With no claim: open-set match, else
unknown — a similar-voiced stranger is never accused.
"""

from __future__ import annotations

import pytest

import config
from contracts import CallerMetadata, SpeakerVerdict, SpeakerVerificationResult
from server.claims import Claim, PersonRef, extract_spoken_names, gather_claims, resolve
from server.tests.isolated_db import isolated_db  # noqa: F401  (fixture)

PAPA = PersonRef("p_papa", "Ramesh", "Father", ("Papa",), ("+919800000001",), True)
MAMA = PersonRef("p_mama", "Sunita", "Mother", (), ("+919800000001",), True)   # shared landline
RAHUL = PersonRef("p_rahul", "Rahul", "Brother", (), ("+919800000002",), True)
PAPA2 = PersonRef("p_papa2", "Mohan", "Father-in-law", ("Papa",), (), True)
NOVP = PersonRef("p_novp", "Asha", "Aunt", (), (), False)
DIRECTORY = [PAPA, MAMA, RAHUL, NOVP]

WB = config.CLAIM_THRESHOLDS["wideband"]
NB = config.CLAIM_THRESHOLDS["narrowband"]


def _speaker(scores: dict) -> SpeakerVerificationResult:
    """What the speaker branch returns: open-set result plus every contact's cosine."""
    return SpeakerVerificationResult(verdict=SpeakerVerdict.UNKNOWN, risk=0.5, details={"scores": scores})


def _resolve(scores, claims=(), narrowband=False, directory=DIRECTORY):
    return resolve(_speaker(scores), list(claims), directory, narrowband=narrowband)


def _check(result):
    return result.details["claim_check"]


# --- no claim: open set, never an accusation -------------------------------------------------

def test_no_claim_and_a_strong_voice_match_is_recognised():
    r = _resolve({"p_papa": 0.93, "p_rahul": 0.4})
    assert r.verdict == SpeakerVerdict.MATCH and r.matched_person_id == "p_papa"
    assert _check(r)["outcome"] == "open_set_match"


@pytest.mark.parametrize("best", [0.84, 0.80, 0.70, 0.55])
def test_a_similar_voiced_stranger_with_no_claim_is_never_accused(best):
    r = _resolve({"p_papa": best})
    assert r.verdict == SpeakerVerdict.UNKNOWN and r.risk == 0.5
    assert r.matched_person_id is None


# --- user pick ---------------------------------------------------------------------------------

def test_user_pick_and_matching_voice_is_a_corroborated_match():
    r = _resolve({"p_papa": 0.95, "p_rahul": 0.3}, [Claim("user", frozenset({"p_papa"}), "p_papa")])
    assert r.verdict == SpeakerVerdict.MATCH and r.matched_person_id == "p_papa"
    assert r.claimed_person_id == "p_papa" and _check(r)["outcome"] == "match"


def test_a_genuine_low_score_caller_in_the_grey_zone_is_inconclusive_not_red():
    """me_test2 measured 0.7912 against its own voiceprint (data/measurements/claim_calibration.json)."""
    r = _resolve({"p_papa": 0.7912}, [Claim("user", frozenset({"p_papa"}), "p_papa")])
    assert r.verdict == SpeakerVerdict.UNKNOWN and r.risk == 0.5
    assert _check(r)["outcome"] == "inconclusive"


def test_a_claimed_papa_clone_is_a_mismatch():
    """The clean clone measured 0.7619 against Friend's voiceprint."""
    r = _resolve({"p_papa": 0.7619}, [Claim("user", frozenset({"p_papa"}), "p_papa")])
    assert r.verdict == SpeakerVerdict.MISMATCH and r.risk == config.FUSION_IDENTITY_RISK["mismatch"]
    assert r.claimed_person_id == "p_papa" and r.matched_person_name == "Ramesh"
    assert _check(r)["outcome"] == "mismatch"


# --- caller ID: untrusted, never accuses ------------------------------------------------------

def test_a_spoofed_number_selecting_the_wrong_contact_is_no_mismatch():
    r = _resolve({"p_papa": 0.30}, [Claim("caller_id", frozenset({"p_papa"}), "+919800000001")])
    assert r.verdict == SpeakerVerdict.UNKNOWN and r.risk == 0.5
    assert _check(r)["outcome"] == "unconfirmed"


@pytest.mark.parametrize("cos", [0.1, 0.5, 0.7, 0.77, 0.8, 0.84, 0.85, 0.9, 0.99])
@pytest.mark.parametrize("narrowband", [False, True])
def test_caller_id_alone_never_changes_the_verdict(cos, narrowband):
    """FR-17: the number explains, it never scores. Same verdict as with no claim at all."""
    with_number = _resolve({"p_papa": cos}, [Claim("caller_id", frozenset({"p_papa"}), "+919800000001")],
                           narrowband=narrowband)
    without = _resolve({"p_papa": cos}, narrowband=narrowband)
    assert (with_number.verdict, with_number.risk) == (without.verdict, without.risk)


def test_a_shared_family_number_resolves_to_whoever_the_voice_matches():
    claim = Claim("caller_id", frozenset({"p_papa", "p_mama"}), "+919800000001")
    r = _resolve({"p_papa": 0.40, "p_mama": 0.93}, [claim])
    assert r.verdict == SpeakerVerdict.MATCH and r.matched_person_id == "p_mama"
    assert _check(r)["outcome"] == "match"


# --- transcript claims, aliases, conflicts ----------------------------------------------------

def test_an_ambiguous_alias_prompts_a_pick_instead_of_guessing():
    directory = DIRECTORY + [PAPA2]
    claim = Claim("transcript", frozenset({"p_papa", "p_papa2"}), "Papa")
    r = _resolve({"p_papa": 0.6, "p_papa2": 0.5}, [claim], directory=directory)
    assert r.verdict == SpeakerVerdict.UNKNOWN and _check(r)["outcome"] == "ambiguous"
    strong = _resolve({"p_papa": 0.6, "p_papa2": 0.93}, [claim], directory=directory)
    assert strong.verdict == SpeakerVerdict.MATCH and strong.matched_person_id == "p_papa2"


def test_sources_that_disagree_are_a_conflict_not_an_accusation():
    claims = [Claim("caller_id", frozenset({"p_papa"}), "+919800000001"),
              Claim("transcript", frozenset({"p_rahul"}), "Rahul")]
    r = _resolve({"p_papa": 0.2, "p_rahul": 0.3}, claims)
    assert r.verdict == SpeakerVerdict.UNKNOWN and r.risk == 0.5
    check = _check(r)
    assert check["outcome"] == "conflict"
    assert {c["source"] for c in check["claims"]} == {"caller_id", "transcript"}


def test_a_claim_about_someone_without_a_voiceprint_cannot_be_checked():
    r = _resolve({}, [Claim("transcript", frozenset({"p_novp"}), "Asha")])
    assert r.verdict == SpeakerVerdict.UNKNOWN and _check(r)["outcome"] == "no_voiceprint"


def test_phone_lines_use_the_narrowband_thresholds():
    claim = [Claim("user", frozenset({"p_papa"}), "p_papa")]
    between = (WB["match"] + NB["match"]) / 2         # matches on wideband, not on a phone line
    assert _resolve({"p_papa": between}, claim).verdict == SpeakerVerdict.MATCH
    assert _resolve({"p_papa": between}, claim, narrowband=True).verdict == SpeakerVerdict.UNKNOWN
    assert _check(_resolve({"p_papa": between}, claim, narrowband=True))["channel"] == "narrowband"


def test_resolution_strips_the_per_contact_scores_from_the_response():
    r = _resolve({"p_papa": 0.93, "p_rahul": 0.4})
    assert "scores" not in r.details


def test_no_scores_means_identity_was_not_measured():
    r = resolve(SpeakerVerificationResult.neutral(), [Claim("user", frozenset({"p_papa"}), "p_papa")], DIRECTORY)
    assert r.verdict == SpeakerVerdict.UNKNOWN and _check(r)["outcome"] == "unavailable"


# --- extracting spoken self-identification --------------------------------------------------

@pytest.mark.parametrize("text,names", [
    ("Hello beta, main Papa bol raha hoon", ["Papa"]),
    ("Haan ji, mai Rahul bol rahi hu", ["Rahul"]),
    ("This is Rahul from the bank", ["Rahul"]),
    ("Hi, it's me, Rahul", ["Rahul"]),
    ("Rahul here, call me back", ["Rahul"]),
    ("I am Sunita", ["Sunita"]),
    ("मैं पापा बोल रहा हूँ", ["पापा"]),
    ("Papa ko bolo mujhe call kare", []),
    ("I am calling from HDFC bank", []),
    ("", []),
])
def test_spoken_self_identification(text, names):
    assert extract_spoken_names(text) == names


def test_gather_claims_maps_every_source_to_people():
    ctx = CallerMetadata(claimed_identity="p_rahul", claimed_number="+91 98000-00001", channel_type="telephony")
    claims = gather_claims(DIRECTORY, ctx, "main Papa bol raha hoon")
    by_source = {c.source: c.person_ids for c in claims}
    assert by_source == {"user": {"p_rahul"}, "caller_id": {"p_papa", "p_mama"}, "transcript": {"p_papa"}}


def test_gather_claims_ignores_what_the_directory_does_not_know():
    ctx = CallerMetadata(claimed_identity="p_someone_elses", claimed_number="+911111111111")
    assert gather_claims(DIRECTORY, ctx, "this is Vikram") == []


def test_relation_words_work_as_aliases():
    claims = gather_claims(DIRECTORY, None, "Hello, main Mummy bol rahi hoon")
    assert [(c.source, c.person_ids) for c in claims] == [("transcript", {"p_mama"})]


# --- end to end: resolution -> fusion -> evidence ------------------------------------------

def _fused(speaker, spoof_risk, text_risk, synthetic=False):
    from contracts import AntiSpoofResult, ScriptAnalysisResult
    from server.orchestrator import _compute_fusion

    spoof = AntiSpoofResult(risk=spoof_risk, median_score=spoof_risk, peak_score=spoof_risk,
                            is_synthetic=synthetic, details={"available": True})
    return _compute_fusion(speaker, spoof, ScriptAnalysisResult(risk=text_risk))


def _codes(fusion):
    return [c.code for c in fusion.reason_codes]


def test_a_claimed_papa_clone_with_a_scam_script_is_high_risk():
    speaker = _resolve({"p_papa": 0.7619}, [Claim("transcript", frozenset({"p_papa"}), "Papa")])
    fusion = _fused(speaker, 0.94, 0.88, synthetic=True)
    assert fusion.band.value == "high_risk"
    assert "RC_SPEAKER_MISMATCH" in _codes(fusion)
    mismatch = next(c for c in fusion.reason_codes if c.code == "RC_SPEAKER_MISMATCH")
    assert "Ramesh" in mismatch.explanation and "call" in mismatch.explanation.lower()


def test_a_genuine_grey_zone_caller_on_a_normal_call_is_not_red():
    speaker = _resolve({"p_papa": 0.7912}, [Claim("user", frozenset({"p_papa"}), "p_papa")])
    fusion = _fused(speaker, 0.07, 0.10)
    assert fusion.band.value not in ("suspicious", "high_risk")
    assert "RC_CLAIM_INCONCLUSIVE" in _codes(fusion)
    assert "RC_SPEAKER_MISMATCH" not in _codes(fusion)


def test_a_spoofed_number_on_a_benign_call_is_not_red_and_says_so():
    speaker = _resolve({"p_papa": 0.30}, [Claim("caller_id", frozenset({"p_papa"}), "+919800000001")])
    fusion = _fused(speaker, 0.05, 0.05)
    assert fusion.band.value not in ("suspicious", "high_risk")
    unconfirmed = next(c for c in fusion.reason_codes if c.code == "RC_CLAIM_UNCONFIRMED")
    assert "spoofed or shared" in unconfirmed.explanation


def test_no_identity_explanation_accuses_anyone():
    """Product rule: a level with evidence, never 'this is a scammer'."""
    for scores, claims in [({"p_papa": 0.3}, [Claim("caller_id", frozenset({"p_papa"}), "+919800000001")]),
                           ({"p_papa": 0.6}, [Claim("transcript", frozenset({"p_papa"}), "Papa")]),
                           ({"p_papa": 0.2, "p_rahul": 0.2}, [Claim("caller_id", frozenset({"p_papa"}), "+91"),
                                                             Claim("transcript", frozenset({"p_rahul"}), "Rahul")])]:
        for code in _fused(_resolve(scores, claims), 0.5, 0.5).reason_codes:
            text = code.explanation.lower()
            assert "scammer" not in text and "fraudster" not in text and "liar" not in text


def test_the_orchestrator_resolves_claims_from_the_accounts_contacts(isolated_db):
    import asyncio

    from contracts import AntiSpoofResult, TranscriptResult
    from server import voiceprint_store
    from server.database import Person, owner_session
    from server.orchestrator import _resolve_identity

    owner = "account-a"
    with owner_session(owner) as db:
        db.add(Person(person_id="p_papa", owner_id=owner, name="Ramesh", relation="Father",
                      phone_numbers=["+919800000001"]))
        db.flush()
        voiceprint_store.save_voiceprints(db, owner, "p_papa", {"wb": [1.0] + [0.0] * 191}, duration_s=20, snr_db=20)
        db.commit()
    speaker = _speaker({"p_papa": 0.70})
    spoof = AntiSpoofResult(details={"available": True})
    said = TranscriptResult(text="Hello beta, main Papa bol raha hoon")
    resolved = asyncio.run(_resolve_identity(speaker, spoof, said, None, owner))
    assert resolved.verdict == SpeakerVerdict.MISMATCH and resolved.matched_person_name == "Ramesh"
    other = asyncio.run(_resolve_identity(speaker, spoof, said, None, "account-b"))
    assert other.verdict == SpeakerVerdict.UNKNOWN, "another account's contacts were consulted"
