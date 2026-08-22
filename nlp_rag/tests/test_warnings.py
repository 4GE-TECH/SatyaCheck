"""Spoken warning text, per band and language.

`TrustScoreResult.vernacular_warning` is `Optional[str]` — text, not audio. There is no
TTS engine here. See `nlp_rag/PLAN.md` §10.
"""

from __future__ import annotations

import re

import pytest

from contracts import TrustBand
from nlp_rag.warnings import warning_for

DEVANAGARI = re.compile(r"[ऀ-ॿ]")

WARNED_BANDS = [TrustBand.CAUTION, TrustBand.SUSPICIOUS, TrustBand.HIGH_RISK]
SILENT_BANDS = [TrustBand.VERIFIED, TrustBand.UNVERIFIED, TrustBand.INSUFFICIENT]


@pytest.mark.parametrize("band", WARNED_BANDS)
def test_risky_bands_produce_a_warning(band):
    assert warning_for(band, "en")


@pytest.mark.parametrize("band", SILENT_BANDS)
def test_bands_with_nothing_to_warn_about_stay_silent(band):
    assert warning_for(band, "en") is None


def test_hindi_warning_is_written_in_devanagari():
    assert DEVANAGARI.search(warning_for(TrustBand.HIGH_RISK, "hi"))


def test_english_warning_is_not_written_in_devanagari():
    assert not DEVANAGARI.search(warning_for(TrustBand.HIGH_RISK, "en"))


def test_unsupported_language_falls_back_to_english_rather_than_silence():
    """A missing translation must not silently drop the warning."""
    assert warning_for(TrustBand.HIGH_RISK, "ta") == warning_for(TrustBand.HIGH_RISK, "en")


def test_hinglish_is_served_the_hindi_warning():
    assert warning_for(TrustBand.HIGH_RISK, "hi_latn") == warning_for(
        TrustBand.HIGH_RISK, "hi"
    )


@pytest.mark.parametrize("band", WARNED_BANDS)
@pytest.mark.parametrize("language", ["en", "hi"])
def test_warning_advises_and_never_accuses(band, language):
    """We output a score with evidence, never 'this is a scammer' (PRD NG2).

    False accusation inside a family is a real harm, and this string is the one thing
    the protected person actually hears.
    """
    text = warning_for(band, language).lower()
    for accusation in ("scammer", "fraudster", "criminal", "ठग", "अपराधी"):
        assert accusation not in text


@pytest.mark.parametrize("band", WARNED_BANDS)
def test_high_risk_warning_names_the_action_to_avoid(band):
    """Vague caution is not actionable. The instruction is about money."""
    text = warning_for(TrustBand.HIGH_RISK, "en").lower()
    assert "money" in text or "transfer" in text
