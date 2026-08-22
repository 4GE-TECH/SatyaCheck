"""Bidirectional linguistic markers.

Incriminating markers raise scam risk; exculpatory markers lower it. Both directions
are written together, and every marker carries its English, Latin-Hinglish and
Devanagari forms — a real call arrives in whichever script Whisper happened to pick.

An incriminating-only marker file flags the friend calling about a real accident.
See `nlp_rag/PLAN.md` §6.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from contracts import MarkerMatch, MarkerType


@dataclass(frozen=True)
class MarkerDef:
    """A single marker and the patterns that detect it across scripts."""

    marker_id: str
    marker_type: MarkerType
    category: str
    weight: float
    description: str
    patterns: list[str] = field(default_factory=list)
    #: If any of these match, the marker does not fire at all.
    #: Mentioning a credential is not the same as asking for one: a bank saying it will
    #: never ask for an OTP is the most legitimate call there is, and firing on the word
    #: alone scores it like a scam.
    veto: list[str] = field(default_factory=list)


# Weights for markers that appear in `contracts.create_mock_fixture` match the values
# used there, so scoring calibrates against the same numbers C's fixtures assert.
MARKERS: list[MarkerDef] = [
    # --- incriminating -------------------------------------------------------
    MarkerDef(
        marker_id="MK_ISOLATION_DEMAND",
        marker_type=MarkerType.INCRIMINATING,
        category="isolation",
        weight=0.85,
        description="Caller strictly demands isolation and forbids consulting family members",
        patterns=[
            r"don'?t tell (?:anyone|anybody|any ?one|a soul)",
            r"do not tell (?:anyone|anybody|any ?one)",
            r"(?:stay|remain) on the line",
            r"kisi ko (?:mat|nahi|nahin) (?:bata|bola|de|kaho|batana)\w*",
            r"phone (?:mat|nahi|nahin) (?:kaat|kat|rakh)\w*",
            r"किसी को (?:मत|नहीं) (?:बताओ|बताना|बोलना|देना|कहना)",
            r"फ़?ोन (?:मत|नहीं) (?:काटो|काटना|रखना)",
        ],
    ),
    MarkerDef(
        marker_id="MK_URGENT_FINANCIAL_UPI",
        marker_type=MarkerType.INCRIMINATING,
        category="urgent_transfer",
        weight=0.90,
        description="Demanding immediate irreversible fund transfer under time pressure",
        patterns=[
            r"(?:turant|abhi|jaldi|foran)[^.!?]{0,60}?(?:bhej|transfer|paise|paisa|upi)\w*",
            r"(?:immediately|right now|urgent|urgently|as soon as possible|asap"
            r"|within \d+ minutes?)[^.!?]{0,60}?"
            r"(?:transfer|send|pay|deposit|money|rupees|\d{3,})\w*",
            r"(?:transfer|send|pay|deposit|need)[^.!?]{0,60}?"
            r"(?:immediately|right now|urgently|as soon as possible|asap)",
            r"(?:transfer|send|pay)[^.!?]{0,40}?(?:upi|qr code|gift card)",
            r"(?:तुरंत|अभी|जल्दी)[^।!?]{0,60}?(?:भेज|ट्रांसफर|पैसे)\w*",
        ],
    ),
    MarkerDef(
        marker_id="MK_AUTHORITY_IMPERSONATION",
        marker_type=MarkerType.INCRIMINATING,
        category="authority",
        weight=0.70,
        description="Caller claims to represent law enforcement or a financial regulator",
        patterns=[
            r"\b(?:cbi|c\.b\.i|enforcement directorate|narcotics|cyber ?cell|customs)\b",
            r"\b(?:inspector|sub[- ]inspector|police officer|income tax officer)\b",
            r"\b(?:सीबीआई|पुलिस अधिकारी|इंस्पेक्टर|कस्टम)\b",
        ],
    ),
    MarkerDef(
        marker_id="MK_OTP_SOLICITATION",
        marker_type=MarkerType.INCRIMINATING,
        category="credential_request",
        weight=0.88,
        description="Caller solicits a one-time password, PIN or card credential",
        patterns=[
            # Solicitation, not mention. A bare "otp" fires on every advisory that
            # warns about OTPs, including a bank saying it will never ask for one.
            r"(?:share|tell|send|read|give|provide|confirm|repeat)[^.!?]{0,40}?"
            r"\b(?:otp|o\.t\.p|one[- ]time password|pin|cvv|card number|password"
            r"|six digit code|verification code)\b",
            r"\b(?:otp|o\.t\.p|one[- ]time password|pin|cvv|card number|password)\b"
            r"[^.!?]{0,40}?(?:share|batao|bta|bataiye|tell|send|read|likh|type)",
            r"\b(?:ओटीपी|पिन)\b[^।!?]{0,40}?(?:बताइए|बताओ|भेजिए|लिखिए)",
        ],
        veto=[
            r"(?:never|not|cannot|can'?t|don'?t|do not|will not|won'?t|unable)"
            r"[^.!?]{0,40}?(?:ask|take|request|share|need|give)",
            r"(?:kabhi|kabhi bhi)\s+(?:nahi|nahin)[^.!?]{0,30}?(?:maang|puchh)",
            r"कभी (?:नहीं|न)[^।!?]{0,30}?(?:माँग|मांग|पूछ)",
        ],
    ),
    MarkerDef(
        marker_id="MK_ARREST_THREAT",
        marker_type=MarkerType.INCRIMINATING,
        category="threat",
        weight=0.80,
        description="Caller threatens arrest, detention or legal action to force compliance",
        patterns=[
            r"(?:will be|going to be|about to be) arrested",
            r"\b(?:arrest warrant|digital arrest|non[- ]bailable)\b",
            r"(?:giraftar|girftar)\w*",
            r"\b(?:गिरफ़्तार|गिरफ्तार)\w*",
        ],
    ),
    MarkerDef(
        marker_id="MK_CALLBACK_REQUEST",
        marker_type=MarkerType.INCRIMINATING,
        category="callback_request",
        weight=0.25,
        description="Caller directs the recipient to a callback number the caller supplies",
        patterns=[
            r"call (?:us|our office|our team|the helpline) back",
            r"call us back on",
            r"call (?:back )?on (?:our|the) (?:helpline|toll[- ]free|customer care)",
            r"(?:helpline|toll[- ]free) number",
        ],
    ),
    # --- exculpatory ---------------------------------------------------------
    MarkerDef(
        marker_id="MK_EXCULPATORY_VERIFICATION_INVITE",
        marker_type=MarkerType.EXCULPATORY,
        category="verification_invite",
        weight=-0.35,
        description="Caller invites independent verification through a known third party",
        patterns=[
            r"(?:call|phone|talk to|speak to|verify with|ask)\s+"
            r"(?:papa|mumma|mummy|mom|mother|dad|father|bhaiya|didi|"
            r"the doctor|the hospital|the police|your (?:son|daughter|husband|wife))",
            r"(?:पापा|मम्मी|माँ|डॉक्टर)\s*(?:से|को)\s*(?:बात|पूछ|पूछो)\w*",
        ],
    ),
    MarkerDef(
        marker_id="MK_EXCULPATORY_ROUTINE",
        marker_type=MarkerType.EXCULPATORY,
        category="routine_checkin",
        weight=-0.30,
        description="Routine personal update, no financial request",
        patterns=[
            r"(?:will be|i'?ll be|reaching|reached|coming)\s+(?:home|office|back|there)",
            r"(?:ghar|office)\s+(?:pahunch|aa)\w*",
            r"(?:घर|ऑफ़िस|ऑफिस)\s+(?:पहुंच|पहुँच|आ)\w*",
        ],
    ),
    MarkerDef(
        marker_id="MK_EXCULPATORY_OFFICIAL_NOTIFICATION",
        marker_type=MarkerType.EXCULPATORY,
        category="institutional_notification",
        weight=-0.20,
        description="Standard institutional notification, no credential or payment request",
        patterns=[
            r"(?:statement|invoice|receipt|delivery|appointment|order)"
            r"[^.!?]{0,60}?is ready",
            r"(?:your (?:order|parcel|package)) [^.!?]{0,40}?"
            r"(?:has been|will be) (?:delivered|dispatched|shipped)",
        ],
    ),
    MarkerDef(
        marker_id="MK_EXCULPATORY_CALLBACK_OFFER",
        marker_type=MarkerType.EXCULPATORY,
        category="callback_offer",
        weight=-0.25,
        description="Caller accepts a callback on a number the recipient already controls",
        patterns=[
            # Deliberately self-referential. A bare "callback" or "call back on this
            # number" is ambiguous about whose number it is, and crediting a scammer's
            # own helpline as a verification offer is the failure that matters here.
            # See MK_CALLBACK_REQUEST for the caller-supplied direction.
            r"call me back",
            r"call me on (?:my|the) (?:usual|saved|old|same) number",
            r"(?:mujhe|mujhko) wapas call kar\w*",
            r"wapas call kar\w* (?:mujhe|mujhko)",
        ],
    ),
]

_COMPILED: list[tuple[MarkerDef, list[re.Pattern[str]], list[re.Pattern[str]]]] = [
    (
        m,
        [re.compile(p, re.IGNORECASE) for p in m.patterns],
        [re.compile(v, re.IGNORECASE) for v in m.veto],
    )
    for m in MARKERS
]


def find_markers(text: str) -> list[MarkerMatch]:
    """Return every marker present in `text`, at most one match per marker.

    Both directions are reported. Resolving a transcript that contains incriminating
    and exculpatory markers together is scoring's job, not matching's.
    """
    if not text:
        return []

    found: list[MarkerMatch] = []
    for definition, patterns, vetoes in _COMPILED:
        if any(v.search(text) for v in vetoes):
            continue
        for pattern in patterns:
            hit = pattern.search(text)
            if hit is None:
                continue
            found.append(
                MarkerMatch(
                    marker_id=definition.marker_id,
                    marker_type=definition.marker_type,
                    category=definition.category,
                    matched_text=hit.group(0),
                    weight=definition.weight,
                    description=definition.description,
                )
            )
            break
    return found


def marker_spans(text: str) -> dict[str, tuple[int, int]]:
    """Character span of each marker's match, keyed by marker id.

    `MarkerMatch` carries no offsets, so spans stay internal here and are used by
    scoring to suppress markers that double-count the top retrieval hit.
    """
    if not text:
        return {}

    spans: dict[str, tuple[int, int]] = {}
    for definition, patterns, vetoes in _COMPILED:
        if any(v.search(text) for v in vetoes):
            continue
        for pattern in patterns:
            hit = pattern.search(text)
            if hit is None:
                continue
            spans[definition.marker_id] = hit.span()
            break
    return spans


if __name__ == "__main__":  # pragma: no cover - CLI smoke test
    samples = [
        "Phone kisi ko mat dena, turant 50000 bhejo is UPI ID pe!",
        "Hi Ma, I just reached the office. Will be home by 7 PM today.",
        "Dear customer, your HDFC Bank statement for account ending 4402 is ready.",
        "किसी को मत बताओ, तुरंत पैसे भेजो",
    ]
    for sample in samples:
        print(f"\n{sample}")
        for match in find_markers(sample):
            print(f"  {match.weight:+.2f}  {match.marker_id:42} {match.matched_text!r}")
