"""Credential-harvesting markers — the category that four scam families share.

WHY THESE EXIST

The eval harness measured 32% of known scams (16 of 50 held-out transcripts) scoring
below the amber floor, meaning the user is shown no concern at all about a call the
corpus already knows is a scam. Every one of those 16 had **zero markers firing**, and
they clustered by family exactly where the corpus was thinnest:

    qr_code_fraud     20% recall      financial_fraud   20%
    sms_fraud         40%             kyc_update        60%

Reading the missed text showed one shared signature the marker set did not cover —
being walked through handing over a credential:

    "read me the number on the front and the three digits at the back"
    "scan karke PIN daal dijiye"
    "application download kar lijiye aur usme apna card number aur PIN daal dijiye"

`MK_OTP_SOLICITATION` misses all of these, and the reason is structural rather than an
oversight: it requires a *solicitation verb* (share / tell / send / read) adjacent to the
credential noun. Hinglish "PIN daal dijiye" puts the verb `daal` (enter) there instead,
and "read me the number on the front" never says the noun "card number" at all.

THE PRECISION PROPERTY

A false incriminating marker silently raises risk on a real call, which is the harm
`CLAUDE.md` names. `test_no_new_marker_fires_on_the_benign_cohort` is therefore the most
important test in this file — it runs all three markers across the entire 103-document
benign cohort and requires zero hits.
"""

from __future__ import annotations

import pytest

from contracts import MarkerType
from nlp_rag import api
from nlp_rag.corpus_loader import load_corpus
from nlp_rag.markers import find_markers

NEW_MARKERS = {"MK_CREDENTIAL_ENTRY", "MK_PIN_TO_RECEIVE", "MK_CARD_READBACK"}


def _ids(text: str) -> set[str]:
    return {m.marker_id for m in find_markers(text)}


# --- the exact held-out transcripts that were missed --------------------------

@pytest.mark.parametrize(
    "text",
    [
        # held-qr-code-001, hi_latn — the furniture-advance QR scam
        "Main aapka furniture kharidna chahta hoon, advance bhej raha hoon. Ye QR code "
        "scan kar lijiye, isse paisa aapke account mein aa jayega. Scan karke apna UPI "
        "PIN daal dijiye, tabhi credit hoga.",
        # held-qr-code-003, hi_latn — the army-posting variant
        "Main army mein hoon, posting ki wajah se aa nahi sakta, isliye advance bhej "
        "raha hoon. Ye scanner bhej diya hai, scan karke PIN daal dijiye, paisa credit "
        "ho jayega.",
        # held-kyc-update-002, hi_latn
        "Aapka bank account KYC pending hai, aaj raat tak block ho jayega. Ek "
        "application download kar lijiye aur usme apna card number aur PIN daal "
        "dijiye, KYC update ho jayegi.",
        # held-credential-002, en — the card read-back
        "I can see a pending debit of nineteen thousand on your account from a merchant "
        "in Delhi. If this is not you, I will block it right now. For that I need to "
        "verify the card, so read me the number on the front and the three digits at "
        "the back, and the code I am sending.",
    ],
)
def test_a_missed_scam_transcript_now_fires_a_marker(text):
    """Each of these scored below amber with no marker at all."""
    fired = _ids(text)
    assert fired & NEW_MARKERS, f"no credential marker fired; got {fired or 'nothing'}"


# --- the precision property, on the real corpus -------------------------------

def test_no_new_marker_fires_on_the_benign_cohort():
    """The test that makes the rest of this file safe to ship.

    103 real benign call transcripts — genuine banks, hospitals, deliveries, police
    callbacks, utilities. A credential marker firing on any of them silently raises a
    real call toward amber, which is the false-accusation harm CLAUDE.md exists to
    prevent. Zero is the only acceptable number.
    """
    corpus = load_corpus(api.CORPUS_DIR)
    offenders = {
        doc.id: sorted(_ids(doc.text) & NEW_MARKERS)
        for doc in corpus.benign
        if _ids(doc.text) & NEW_MARKERS
    }
    assert not offenders, f"credential markers fired on benign documents: {offenders}"


def test_the_new_markers_are_incriminating_and_weighted_sanely():
    """A marker strong enough to matter, bounded enough not to become a verdict."""
    from nlp_rag.markers import MARKERS

    found = {m.marker_id: m for m in MARKERS if m.marker_id in NEW_MARKERS}
    assert set(found) == NEW_MARKERS, f"missing: {NEW_MARKERS - set(found)}"

    for marker in found.values():
        assert marker.marker_type is MarkerType.INCRIMINATING
        assert 0.80 <= marker.weight <= 0.95, (
            f"{marker.marker_id} weight {marker.weight} is outside the band the other "
            "credential markers occupy"
        )
        assert marker.veto, (
            f"{marker.marker_id} has no veto patterns — an advisory warning about this "
            "very fraud would fire it"
        )


# --- vetoes: mentioning a credential is not asking for one --------------------

@pytest.mark.parametrize(
    "text",
    [
        # A real bank's standard disclaimer. The most legitimate call there is.
        "Please remember that bank officials will never ask you to enter your PIN or "
        "share your card number with anyone.",
        "Hamare bank ke log kabhi bhi aapka PIN nahi maangenge, aur na hi card number "
        "puchhenge.",
        "बैंक कभी भी आपका पिन नहीं माँगेगा और न ही कार्ड नंबर पूछेगा।",
        # A genuine fraud-awareness advisory describing the scam.
        "Fraudsters may ask you to enter your UPI PIN to receive money. You do not need "
        "a PIN to receive money. Never enter it.",
    ],
)
def test_warning_about_the_fraud_does_not_fire_the_marker(text):
    """The `kabhi`/`abhi` lesson, generalised.

    An advisory that *describes* credential theft contains every phrase the marker
    matches. Without a veto, the safety warning scores like the crime.
    """
    assert not (_ids(text) & NEW_MARKERS), f"fired on a warning: {_ids(text)}"


# --- MK_PIN_TO_RECEIVE, the arithmetic one ------------------------------------

@pytest.mark.parametrize(
    "text",
    [
        "Scan this QR code and enter your UPI PIN, the money will be credited to you.",
        "Ye QR scan karke apna PIN daaliye, paisa aa jayega.",
        "क्यूआर कोड स्कैन करके अपना पिन डालिए, पैसा आ जाएगा।",
        "To receive the refund just scan the code and put in your PIN.",
    ],
)
def test_pin_demanded_in_order_to_receive_money_always_fires(text):
    """Not a heuristic — arithmetic about how payment rails work.

    No UPI or card flow ever requires a PIN to *credit* you. A PIN authorises money
    leaving an account, never money arriving. A caller who says otherwise is either
    mistaken or lying, and this single pattern is the entire QR-fraud family.
    """
    assert "MK_PIN_TO_RECEIVE" in _ids(text)


def test_a_pin_used_to_pay_is_not_this_marker():
    """Entering a PIN to *send* money is how paying works. Ordinary, not fraud.

    This keeps MK_PIN_TO_RECEIVE meaning what its name says. The generic
    MK_CREDENTIAL_ENTRY may still fire on a directed entry, which is correct — it is
    weaker and represents a different claim.
    """
    text = "Aap apne app se payment kijiye aur PIN daal kar transaction complete kijiye."
    assert "MK_PIN_TO_RECEIVE" not in _ids(text)


# --- the language requirement from PLAN.md §6 ---------------------------------

@pytest.mark.parametrize(
    "text,script",
    [
        ("Please enter your PIN in the application to complete verification.", "en"),
        ("Application mein apna PIN daal dijiye, verification complete ho jayega.", "hi_latn"),
        ("एप्लिकेशन में अपना पिन डालिए, वेरिफिकेशन पूरा हो जाएगा।", "hi"),
    ],
)
def test_every_script_is_covered(text, script):
    """§6: "Every marker gets its Devanagari and Latin-Hinglish forms at the same time."

    A real call arrives in whichever script Whisper picked, and Hinglish is already the
    weakest language in the recall table. An English-only marker widens that gap.
    """
    assert _ids(text) & NEW_MARKERS, f"no marker fired for {script}: {text!r}"


# --- the risk arithmetic these markers are for --------------------------------

def test_a_missed_transcript_now_clears_the_amber_floor():
    """End to end: the point of the whole exercise.

    A marker that fires but does not move the score past the floor changes nothing the
    user sees. `MARKER_DELTA_CAP * tanh(0.85)` is +0.242, and the missed cases sat at
    r_ret 0.043-0.142, so one marker is enough.
    """
    from contracts import TranscriptResult
    from nlp_rag import thresholds
    from nlp_rag.api import analyze_script

    result = analyze_script(
        TranscriptResult(
            text=(
                "Main aapka furniture kharidna chahta hoon, advance bhej raha hoon. Ye "
                "QR code scan kar lijiye, isse paisa aapke account mein aa jayega. Scan "
                "karke apna UPI PIN daal dijiye, tabhi credit hoga."
            ),
            detected_language="hi",
        )
    )

    assert result.risk >= thresholds.AMBER_FLOOR, (
        f"a known QR-fraud transcript scored {result.risk:.3f}, still below the "
        f"{thresholds.AMBER_FLOOR} floor — the user would see no concern"
    )


def test_markers_alone_cannot_produce_high_risk():
    """PLAN.md §5 step 8. Red with no citable document is a verdict without evidence.

    Stacking every credential marker on a transcript that retrieves nothing must still
    stay under the high-risk threshold. `PRD.md` NG2 forbids emitting a verdict.
    """
    from contracts import TranscriptResult
    from nlp_rag import thresholds
    from nlp_rag.api import analyze_script

    result = analyze_script(
        TranscriptResult(
            text=(
                "Scan the code and enter your UPI PIN to receive it, then read me the "
                "number on the front of the card and the three digits at the back."
            ),
            detected_language="en",
        )
    )

    if not result.playbooks:
        assert result.risk < thresholds.SCRIPT_HIGH_RISK, (
            f"markers alone reached {result.risk:.3f} with no citation to support it"
        )
