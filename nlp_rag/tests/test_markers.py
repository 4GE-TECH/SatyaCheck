"""Markers run in both directions, across all three scripts a real call arrives in."""

from __future__ import annotations

from contracts import MarkerType
from nlp_rag.markers import find_markers


def _ids(text: str) -> set[str]:
    return {m.marker_id for m in find_markers(text)}


def _by_id(text: str, marker_id: str):
    return next(m for m in find_markers(text) if m.marker_id == marker_id)


# --- incriminating -----------------------------------------------------------

def test_isolation_demand_detected_in_english():
    assert "MK_ISOLATION_DEMAND" in _ids("Don't tell anyone about this call")


def test_isolation_demand_detected_in_latin_hinglish():
    assert "MK_ISOLATION_DEMAND" in _ids("Phone kisi ko mat dena, samjhe?")


def test_isolation_demand_detected_in_devanagari():
    assert "MK_ISOLATION_DEMAND" in _ids("किसी को मत बताओ")


def test_incriminating_marker_carries_positive_weight():
    marker = _by_id("Don't tell anyone about this call", "MK_ISOLATION_DEMAND")
    assert marker.marker_type is MarkerType.INCRIMINATING
    assert marker.weight == 0.85


def test_urgent_upi_transfer_detected_in_latin_hinglish():
    assert "MK_URGENT_FINANCIAL_UPI" in _ids("turant 50000 bhejo is UPI ID pe")


def test_urgently_is_a_time_pressure_word():
    """The commonest English urgency word in these scripts, and it was missing.

    Without it a genuine-but-unusual money request scored 0.02 — indistinguishable
    from a routine check-in — which breaks PRD §6's second false-positive guard from
    the wrong direction: the call must be amber, not green.
    """
    assert "MK_URGENT_FINANCIAL_UPI" in _ids("I need 20000 urgently for a deposit")


def test_urgent_variants_are_detected():
    for phrase in (
        "please send it urgently",
        "this is an urgent payment",
        "I need the money as soon as possible",
    ):
        assert "MK_URGENT_FINANCIAL_UPI" in _ids(phrase), phrase


def test_kabhi_does_not_fire_the_abhi_urgency_pattern():
    """"kabhi bhi" — "any time at all" — is the *opposite* of time pressure.

    It contains "abhi" as a substring, so an unanchored alternation matches a pharmacy
    saying "collect it whenever you like, or shall we send it to your home?" and scores
    a relaxed offer as a demand for an immediate transfer.
    """
    assert "MK_URGENT_FINANCIAL_UPI" not in _ids(
        "Sir, aapki dawai aa gayi hai. Aap kabhi bhi aake le sakte hain, "
        "ya hum ghar bhej dein?"
    )


def test_abhi_on_its_own_still_fires():
    assert "MK_URGENT_FINANCIAL_UPI" in _ids("abhi paise bhejo")


def test_authority_impersonation_detected():
    assert "MK_AUTHORITY_IMPERSONATION" in _ids("This is Inspector Sharma from the CBI")


def test_otp_solicitation_detected():
    assert "MK_OTP_SOLICITATION" in _ids("Please share the OTP you just received")


# --- exculpatory -------------------------------------------------------------

def test_verification_invite_is_exculpatory():
    marker = _by_id("Call Papa and ask him yourself", "MK_EXCULPATORY_VERIFICATION_INVITE")
    assert marker.marker_type is MarkerType.EXCULPATORY
    assert marker.weight < 0


def test_routine_checkin_is_exculpatory():
    marker = _by_id("Will be home by 7 PM today", "MK_EXCULPATORY_ROUTINE")
    assert marker.marker_type is MarkerType.EXCULPATORY
    assert marker.weight == -0.3


def test_institutional_notification_is_exculpatory():
    marker = _by_id(
        "Dear customer, your HDFC Bank statement for account ending 4402 is ready.",
        "MK_EXCULPATORY_OFFICIAL_NOTIFICATION",
    )
    assert marker.marker_type is MarkerType.EXCULPATORY
    assert marker.weight == -0.2


def test_callback_offer_is_exculpatory():
    assert "MK_EXCULPATORY_CALLBACK_OFFER" in _ids("Call me back on this number anytime")


# --- who owns the callback channel -------------------------------------------
# Two markers with nearly the same name and opposite signs. The distinction is not
# whether a callback is offered, but WHO controls the number it goes to.

def test_callback_to_a_channel_the_recipient_controls_is_exculpatory():
    """A scam does not survive one callback to a number you already had."""
    marker = _by_id("Call me back whenever you like", "MK_EXCULPATORY_CALLBACK_OFFER")
    assert marker.marker_type is MarkerType.EXCULPATORY


def test_callback_to_a_channel_the_caller_supplies_is_incriminating():
    """A caller-supplied helpline is a channel the caller also controls."""
    marker = _by_id(
        "Please call us back on our helpline number", "MK_CALLBACK_REQUEST"
    )
    assert marker.marker_type is MarkerType.INCRIMINATING
    assert marker.weight == 0.25


def test_a_caller_supplied_callback_is_not_treated_as_exculpatory():
    """The failure that matters: crediting a scammer's helpline as a verification offer."""
    ids = _ids("Please call us back on our helpline number to confirm.")
    assert "MK_EXCULPATORY_CALLBACK_OFFER" not in ids


def test_a_recipient_controlled_callback_is_not_treated_as_incriminating():
    assert "MK_CALLBACK_REQUEST" not in _ids("Call me back on this number anytime")


def test_the_two_callback_markers_never_fire_together():
    for text in (
        "Call me back on this number anytime",
        "Please call us back on our helpline number",
    ):
        ids = _ids(text)
        assert not (
            "MK_CALLBACK_REQUEST" in ids and "MK_EXCULPATORY_CALLBACK_OFFER" in ids
        ), text


# --- reporting ---------------------------------------------------------------

def test_matched_text_is_the_exact_snippet_from_the_transcript():
    marker = _by_id("Papa, phone kisi ko mat dena!", "MK_ISOLATION_DEMAND")
    assert marker.matched_text == "kisi ko mat dena"


def test_benign_transcript_produces_no_markers():
    assert find_markers("Hi Ma, I just reached the office.") == []


def test_a_scam_line_fires_both_isolation_and_payment_markers():
    text = "Phone kisi ko mat dena, turant 50000 bhejo is UPI ID pe!"
    assert _ids(text) == {"MK_ISOLATION_DEMAND", "MK_URGENT_FINANCIAL_UPI"}


def test_isolation_and_verification_invite_can_coexist_in_one_transcript():
    """A mixed transcript reports both directions; scoring resolves them, not matching."""
    text = "Don't tell anyone. Actually, call Papa and ask him yourself."
    ids = _ids(text)
    assert "MK_ISOLATION_DEMAND" in ids
    assert "MK_EXCULPATORY_VERIFICATION_INVITE" in ids


# --- mentioning a credential is not soliciting one ---------------------------
# The most legitimate call in the corpus is a bank saying it will never ask for an
# OTP. If the marker fires on the word alone, that call scores like a scam, which is
# the over-flagging failure the whole design exists to prevent.

def test_a_bank_refusing_to_take_an_otp_is_not_soliciting_one():
    assert "MK_OTP_SOLICITATION" not in _ids(
        "I am not able to take any card or OTP details over the phone. "
        "Please raise it in the app under disputes."
    )


def test_an_advisory_warning_never_to_share_an_otp_is_not_soliciting_one():
    assert "MK_OTP_SOLICITATION" not in _ids(
        "The bank will never ask for your OTP, PIN or CVV over a call."
    )


def test_do_not_share_your_otp_is_not_soliciting_one():
    assert "MK_OTP_SOLICITATION" not in _ids("Do not share your OTP with anyone.")


def test_actually_soliciting_an_otp_still_fires():
    for phrase in (
        "Please share the OTP you just received",
        "just read out the OTP to me",
        "tell me the six digit code and your PIN",
    ):
        assert "MK_OTP_SOLICITATION" in _ids(phrase), phrase


# --- exculpatory breadth (PLAN §6) -------------------------------------------
# Isolation and urgency are structurally load-bearing for fraud: remove either and one
# callback destroys the scam. Their opposites are therefore evidence in the other
# direction, and an incriminating-only marker file flags the friend calling about a real
# accident — the harm PRD §9 exists to prevent.

def test_tolerating_delay_is_exculpatory():
    """A scam cannot survive "think about it overnight". Every family in the corpus
    compresses the victim's time; a caller who expands it is doing the opposite."""
    marker = _by_id("Take your time, there is no hurry at all.", "MK_EXCULPATORY_NO_URGENCY")
    assert marker.marker_type is MarkerType.EXCULPATORY
    assert marker.weight < 0


def test_tolerating_delay_detected_in_latin_hinglish():
    assert "MK_EXCULPATORY_NO_URGENCY" in _ids("Koi jaldi nahi hai, aaram se dekh lena.")


def test_tolerating_delay_detected_in_devanagari():
    assert "MK_EXCULPATORY_NO_URGENCY" in _ids("कोई जल्दी नहीं है, आराम से बताइए।")


def test_a_checkable_place_is_exculpatory():
    """Naming somewhere the recipient can physically go is a verification route a
    caller running a script cannot offer."""
    marker = _by_id(
        "Come to the hospital, I am in the emergency ward.",
        "MK_EXCULPATORY_CHECKABLE_PLACE",
    )
    assert marker.marker_type is MarkerType.EXCULPATORY


def test_a_checkable_place_detected_in_latin_hinglish():
    assert "MK_EXCULPATORY_CHECKABLE_PLACE" in _ids(
        "Aap branch aa jaiye, main yahin counter par hoon."
    )


def test_urgency_and_its_absence_do_not_both_fire():
    """"turant bhejo" and "koi jaldi nahi" are contradictory claims about the same
    dimension. A transcript matching both would be scoring noise."""
    ids = _ids("Turant paise bhejo, abhi ke abhi.")
    assert "MK_EXCULPATORY_NO_URGENCY" not in ids


def test_a_scam_demanding_haste_does_not_read_as_patient():
    assert "MK_EXCULPATORY_NO_URGENCY" not in _ids(
        "You must transfer the money immediately or you will be arrested."
    )


# --- gaps found by A's calibration table -------------------------------------
# A supplied four reference transcripts from the audio side. Three scored low, and two of
# those were marker misses rather than calibration: an external test set catching what an
# author's own examples did not.

def test_naming_the_family_member_to_hide_from_is_isolation():
    """"Don't tell Papa" is the family-emergency script almost verbatim, and it is a
    stronger demand than "don't tell anyone" — it names the one person who could verify
    the story in a single phone call."""
    assert "MK_ISOLATION_DEMAND" in _ids("Send 40,000 rupees now, don't tell Papa")


def test_isolation_covers_the_common_relations():
    for phrase in (
        "don't tell Mummy about this",
        "do not tell your father",
        "don't tell Mom, she will worry",
    ):
        assert "MK_ISOLATION_DEMAND" in _ids(phrase), phrase


def test_a_bare_now_after_an_amount_is_time_pressure():
    """"right now" matched; "now" alone did not, so "send 40,000 rupees now" scored as
    though it carried no urgency at all."""
    assert "MK_URGENT_FINANCIAL_UPI" in _ids("Send 40,000 rupees now")


def test_now_without_money_is_not_a_payment_demand():
    """The guard on the above: "now" is one of the commonest words in speech, and a
    payment verb near it is not enough on its own."""
    for phrase in (
        "send me the photos now",
        "I am leaving now",
        "send the documents now please",
    ):
        assert "MK_URGENT_FINANCIAL_UPI" not in _ids(phrase), phrase


def test_telling_someone_is_not_telling_them_to_hide_it():
    """Guard against matching the plain verb: "I told Papa already" is the opposite."""
    assert "MK_ISOLATION_DEMAND" not in _ids("I already told Papa about the accident")
