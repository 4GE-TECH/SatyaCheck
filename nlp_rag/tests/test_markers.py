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
