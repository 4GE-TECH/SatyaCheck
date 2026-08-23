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


#: Shared by every credential-request marker.
#:
#: Mentioning a credential is not the same as asking for one, and the most legitimate
#: call there is — a bank's "we will never ask for your PIN" — contains every phrase
#: these markers match. So does a genuine fraud-awareness advisory *describing* the
#: scam. Without this, the safety warning scores like the crime.
#:
#: Same lesson as the "kabhi"/"abhi" defect: match phrases, never substrings, and always
#: ask what a legitimate caller saying these words would sound like.
_CREDENTIAL_VETO: list[str] = [
    # "will never ask", "we do not request", "you should not share"
    r"(?:never|not|cannot|can'?t|don'?t|do not|will not|won'?t|unable|no one|nobody)"
    r"[^.!?]{0,40}?(?:ask|take|request|share|need|give|require|enter)",
    # "you do not need a PIN to receive money" — the advisory's central sentence
    r"(?:do not|don'?t|never)\s+(?:need|require)[^.!?]{0,30}?"
    r"\b(?:pin|otp|password|cvv)\b",
    r"(?:kabhi|kabhi bhi)\s+(?:nahi|nahin)[^.!?]{0,40}?"
    r"(?:maang|puchh|puch|share|batao)",
    r"(?:nahi|nahin|na)\s+(?:maangte|maangenge|puchhte|puchhenge)",
    r"कभी (?:नहीं|न)[^।!?]{0,40}?(?:माँग|मांग|पूछ|शेयर)",
    r"(?:नहीं|न) (?:माँगेगा|मांगेगा|पूछेगा|माँगते|मांगते)",
]


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
            r"(?:don'?t|do not|never) tell\s+(?:anyone|anybody|any ?one|a soul"
            r"|papa|pappa|mummy|mumma|mum|mom|mama|maa|ma\b|dad|daddy|father|mother"
            r"|bhai|didi|your (?:father|mother|husband|wife|son|daughter|family))",
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
            # Anchored on \b. "kabhi" contains "abhi", so an unanchored alternation
            # reads "kabhi bhi aake le lena" — "collect it whenever you like", the
            # opposite of time pressure — as a demand for an immediate transfer.
            r"\b(?:turant|abhi|jaldi|foran)\b[^.!?]{0,60}?"
            r"\b(?:bhej|transfer|paise|paisa|upi)\w*",
            r"\b(?:immediately|right now|urgent|urgently|as soon as possible|asap"
            r"|within \d+ minutes?)\b[^.!?]{0,60}?"
            r"\b(?:transfer|send|pay|deposit|money|rupees|\d{3,})\w*",
            r"\b(?:transfer|send|pay|deposit|need)\b[^.!?]{0,60}?"
            r"\b(?:immediately|right now|urgently|as soon as possible|asap)\b",
            r"\b(?:transfer|send|pay)\b[^.!?]{0,40}?\b(?:upi|qr code|gift card)\b",
            r"\b(?:transfer|send|pay|deposit)\b[^.!?]{0,30}?"
            r"\b(?:\d{3,}|rupees|rs\.?|lakh|lakhs|thousand|hazaar|hazar)\b"
            r"[^.!?]{0,20}?\bnow\b",
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
    # --- credential harvesting -----------------------------------------------
    #
    # Four scam families share one signature the markers above do not reach: the caller
    # walks the victim through *handing over* a credential. MK_OTP_SOLICITATION requires
    # a solicitation verb (share / tell / send / read) beside the credential noun, and
    # these scripts put a different verb there ("PIN daal dijiye" — enter) or never name
    # the noun at all ("the number on the front").
    #
    # Measured before being written: 0 hits across the whole 103-document benign cohort.
    # See nlp_rag/tests/test_markers_credential.py, which re-checks that on every run.
    MarkerDef(
        marker_id="MK_PIN_TO_RECEIVE",
        marker_type=MarkerType.INCRIMINATING,
        category="credential_request",
        weight=0.90,
        description=(
            "Caller demands a PIN or QR scan in order to RECEIVE money — no payment "
            "rail works this way"
        ),
        patterns=[
            # The strongest marker here, and the only one that is arithmetic rather than
            # heuristic: a PIN authorises money *leaving* an account, never money
            # arriving. "Enter your PIN and the money will be credited" is false on every
            # rail that exists, so the caller is either mistaken or lying.
            r"\b(?:scan|qr|q\.r|scanner)\w*\b[^.!?]{0,70}?"
            r"\b(?:pin|upi pin|password)\b[^.!?]{0,70}?"
            r"\b(?:credit|receive|refund|aa ?jay|aayeg|mil ?jay|paisa|money)\w*",
            r"\b(?:receive|credit|refund|get)\w*\b[^.!?]{0,70}?"
            r"\b(?:enter|put|daal|daliye|daaliye|dal)\w*\b[^.!?]{0,30}?"
            r"\b(?:pin|upi pin)\b",
            r"\b(?:pin|upi pin)\b[^.!?]{0,40}?\b(?:to|and)\b[^.!?]{0,25}?"
            r"\b(?:receive|get|credit)\b",
            r"\b(?:scan|qr|scanner)\w*\b[^.!?]{0,50}?\bpin\b[^.!?]{0,40}?"
            r"\b(?:daal|daliye|daaliye|dal)\w*",
            r"(?:स्कैन|क्यूआर)[^।!?]{0,60}?पिन[^।!?]{0,50}?(?:डाल|डालिए|डालो)",
            r"पिन[^।!?]{0,40}?(?:डाल|डालिए|डालो)[^।!?]{0,60}?"
            r"(?:पैसा|राशि|क्रेडिट|आ जाए|मिल जाए)",
        ],
        veto=_CREDENTIAL_VETO,
    ),
    MarkerDef(
        marker_id="MK_CARD_READBACK",
        marker_type=MarkerType.INCRIMINATING,
        category="credential_request",
        weight=0.88,
        description="Caller asks the recipient to read back card digits, CVV or expiry",
        patterns=[
            # Deliberately covers the phrasings that never say "card number" — a real
            # scammer says "the number on the front" and "the three digits at the back",
            # which is exactly why MK_OTP_SOLICITATION's noun list missed this.
            r"\b(?:read|tell|give|share|confirm|repeat|batao|bataiye|likho)\w*\b"
            r"[^.!?]{0,50}?\b(?:card number|number on the (?:front|card|back)"
            r"|three digits|3 digits|last (?:four|4) digits|cvv"
            r"|expiry(?: date)?|valid(?:ity| thru))\b",
            r"\b(?:three digits|3 digits|cvv)\b[^.!?]{0,45}?"
            r"\b(?:at the back|on the back|behind|peeche)\b",
            r"\bcard\b[^.!?]{0,30}?\b(?:number|no\.?)\b[^.!?]{0,35}?"
            r"\b(?:batao|bataiye|bta|likhiye|send|share)\b",
            r"(?:कार्ड (?:नंबर|नम्बर)|सीवीवी|पीछे के तीन (?:अंक|नंबर))"
            r"[^।!?]{0,45}?(?:बताइए|बताओ|भेजिए|लिखिए)",
        ],
        veto=_CREDENTIAL_VETO,
    ),
    MarkerDef(
        marker_id="MK_CREDENTIAL_ENTRY",
        marker_type=MarkerType.INCRIMINATING,
        category="credential_request",
        weight=0.85,
        description=(
            "Caller directs the recipient to enter a PIN, password or card detail, "
            "often into an app or link the caller supplied"
        ),
        patterns=[
            # The generic case, weaker than the two above. "daal/daliye/dalna" is the
            # Hinglish verb that carries this in practice and appears in no solicitation
            # verb list, which is why every Hinglish QR-fraud transcript was missed.
            r"\b(?:enter|type|put|key ?in|feed|fill(?: in)?)\b[^.!?]{0,35}?"
            r"\b(?:pin|upi pin|password|cvv|card number|atm pin|net ?banking)\b",
            r"\b(?:pin|upi pin|password|cvv|card number|atm pin)\b"
            r"[^.!?]{0,35}?\b(?:daal|daliye|daaliye|dalna|dale|daalna|type|enter)\w*",
            r"\b(?:open|click|download|install)\b[^.!?]{0,45}?"
            r"\b(?:link|app|application|apk|form)\b[^.!?]{0,90}?"
            r"\b(?:account number|card number|pin|password|otp|net ?banking"
            r"|login|user ?id)\b",
            r"(?:पिन|पासवर्ड|कार्ड (?:नंबर|नम्बर)|सीवीवी)"
            r"[^।!?]{0,35}?(?:डाल|डालिए|डालो|भरिए|भरो)",
            r"(?:लिंक|ऐप|एप्लिकेशन)[^।!?]{0,70}?"
            r"(?:पिन|पासवर्ड|खाता (?:नंबर|संख्या)|कार्ड (?:नंबर|नम्बर))",
        ],
        veto=_CREDENTIAL_VETO,
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
        marker_id="MK_EXCULPATORY_NO_URGENCY",
        marker_type=MarkerType.EXCULPATORY,
        category="tolerates_delay",
        weight=-0.30,
        description="Caller explicitly removes time pressure and invites the recipient to take their time",
        patterns=[
            # Time pressure is structurally load-bearing for fraud: every family in the
            # corpus compresses the victim's decision window, because a scam does not
            # survive "think about it overnight". A caller who widens that window is
            # doing the opposite of the thing the scam requires.
            r"take your time",
            r"(?:there'?s |there is )?no (?:hurry|rush|urgency)",
            r"whenever (?:you|it) (?:can|like|suit|are|is|want)\w*",
            r"no need to (?:hurry|rush|decide) (?:now|today|immediately)",
            r"koi jaldi nahi",
            r"jaldi nahi hai",
            r"aaram se (?:dekh|soch|bata|kar)\w*",
            r"कोई जल्दी नहीं",
            r"आराम से (?:देख|सोच|बता)\w*",
        ],
        veto=[
            # A transcript claiming both haste and patience is scoring noise. Urgency is
            # the incriminating claim, so it wins and this marker stands down.
            r"\b(?:turant|abhi|jaldi karo|foran)\b",
            r"\b(?:immediately|right now|urgently|as soon as possible|asap)\b",
            r"(?:तुरंत|अभी)",
        ],
    ),
    MarkerDef(
        marker_id="MK_EXCULPATORY_CHECKABLE_PLACE",
        marker_type=MarkerType.EXCULPATORY,
        category="checkable_place",
        weight=-0.25,
        description="Caller names a physical place the recipient can go to and verify",
        patterns=[
            # A caller running a script cannot offer somewhere to turn up in person.
            # Deliberately requires a movement verb: merely mentioning a hospital is what
            # the family-emergency scam does, while inviting you to come to one is not.
            r"(?:come|come down|come over|reach|visit)\s+(?:to\s+)?(?:the\s+)?"
            r"(?:hospital|clinic|branch|station|office|counter|ward|reception)",
            r"i(?:'| a)?m (?:at|in) the (?:hospital|clinic|branch|station|office|counter|ward)",
            r"(?:aap )?(?:hospital|branch|station|office|counter)\s+(?:aa|aaiye|aa jaiye|pahunch)\w*",
            r"main (?:yahin|yahan) (?:counter|branch|hospital|station)",
            r"(?:अस्पताल|शाखा|थाने|दफ़्तर|काउंटर)\s*(?:पर|में)?\s*(?:आ|आइए|आ जाइए)\w*",
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
