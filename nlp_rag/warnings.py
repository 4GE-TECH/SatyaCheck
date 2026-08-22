"""Spoken warning text, per band and language.

`TrustScoreResult.vernacular_warning` is `Optional[str]`. This module produces the
string; rendering it to audio is not B's and needs no model.

The protected person hears this sentence and nothing else — no dashboard, no meter, no
reason codes. So it advises and never accuses. We output a score with evidence, never
"this is a scammer" (`PRD.md` NG2), and a false accusation inside a family is a real
harm. The copy names the irreversible action to avoid and the safe action to take.
"""

from __future__ import annotations

from contracts import TrustBand

#: Languages that share a template. Hinglish speakers are served the Hindi string.
_LANGUAGE_ALIASES: dict[str, str] = {"hi_latn": "hi", "hi-en": "hi", "hin": "hi"}

_FALLBACK_LANGUAGE = "en"

_TEMPLATES: dict[TrustBand, dict[str, str]] = {
    TrustBand.HIGH_RISK: {
        "en": (
            "Please stop. Do not transfer any money and do not share any code. "
            "Hang up and call the person back on their saved number."
        ),
        "hi": (
            "कृपया रुकिए। अभी कोई पैसा ट्रांसफ़र न करें और कोई कोड साझा न करें। "
            "फ़ोन रखिए और उस व्यक्ति को उनके सेव किए हुए नंबर पर वापस कॉल कीजिए।"
        ),
    },
    TrustBand.SUSPICIOUS: {
        "en": (
            "Please be careful. Do not send money yet. "
            "Call the person back on their saved number and confirm first."
        ),
        "hi": (
            "कृपया सावधान रहिए। अभी पैसे मत भेजिए। "
            "पहले उस व्यक्ति को उनके सेव किए हुए नंबर पर कॉल करके पुष्टि कीजिए।"
        ),
    },
    TrustBand.CAUTION: {
        "en": (
            "Something about this call is unusual. "
            "Before you send any money, check with someone you trust."
        ),
        "hi": (
            "इस कॉल में कुछ असामान्य है। "
            "पैसे भेजने से पहले किसी भरोसेमंद व्यक्ति से बात कर लीजिए।"
        ),
    },
}


def warning_for(band: TrustBand, language: str = "en") -> str | None:
    """Return the spoken warning for `band` in `language`, or None if none is warranted.

    An unsupported language falls back to English rather than returning None — a missing
    translation must never silently drop the warning entirely.
    """
    try:
        templates = _TEMPLATES.get(band)
        if templates is None:
            return None
        key = _LANGUAGE_ALIASES.get(language, language)
        return templates.get(key) or templates[_FALLBACK_LANGUAGE]
    except Exception:  # noqa: BLE001 - rule 5: degrade, never raise into the caller
        return None


def warnings_by_band(language: str = "en") -> dict[str, str]:
    """Every warranted warning, keyed by `TrustBand` value.

    The intent branch cannot know the fused band — identity and authenticity have not
    been combined yet at the point `analyze_script` runs. So it returns all of them and
    fusion selects with the band it actually produced.

    Bands with nothing to warn about are omitted rather than mapped to None, so a
    caller can treat presence in this dict as "there is something to say".
    """
    result: dict[str, str] = {}
    for band in _TEMPLATES:
        text = warning_for(band, language)
        if text:
            result[band.value] = text
    return result


if __name__ == "__main__":  # pragma: no cover - CLI smoke test
    for band in TrustBand:
        for language in ("en", "hi"):
            text = warning_for(band, language)
            print(f"  {band.value:14} {language}  {text or '—'}")
