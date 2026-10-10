"""Whisper hears "OTP" as "ODP" on 8 kHz phone audio (seen live on an Exotel call:
"we have sent you an ODP can you please tell me what is the ODP?"), so the credential
markers must accept the common mishearings — and still respect their vetoes."""

from __future__ import annotations

import pytest

from nlp_rag.markers import find_markers

LIVE = ("Hello, we are calling from bank we are your customer services so we have sent you "
        "an ODP can you please tell me what is the ODP? The ODP is 2625.")


def _ids(text):
    return {m.marker_id for m in find_markers(text)}


def test_the_live_call_transcript_fires_the_otp_marker():
    assert "MK_OTP_SOLICITATION" in _ids(LIVE)


@pytest.mark.parametrize("heard", ["ODP", "O D P", "O.D.P", "OTB", "O T P", "one time pin"])
def test_common_mishearings_of_otp_are_solicitation(heard):
    assert "MK_OTP_SOLICITATION" in _ids(f"Please tell me the {heard} you just received.")


def test_a_bank_that_never_asks_for_an_odp_is_still_exculpated():
    assert "MK_OTP_SOLICITATION" not in _ids("We will never ask you to share your ODP with anyone.")
