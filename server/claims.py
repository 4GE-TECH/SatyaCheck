"""SatyaCheck — who the caller claims to be (upgrade plan, Phase 2).

Three hints are recorded separately, each with its provenance, and none is proof:

  source       where it comes from                          trust      can support a mismatch?
  user         "Who's calling?" pick (CallerMetadata         medium     yes
               .claimed_identity, a person id)
  caller_id    displayed number (CallerMetadata               untrusted  NEVER: numbers are spoofed,
               .claimed_number) vs the contact's numbers                 reassigned and shared
  transcript   spoken self-identification ("Papa bol raha    medium     yes
               hoon") vs names, aliases and relation words

A claim selects whose voiceprint the call is checked against; the voice decides. Every
contact's cosine is already computed by the speaker branch, so resolving claims is cheap
and can happen again whenever a new claim (a transcript) arrives.

The verdict keeps the frozen three values; the outcome is in details["claim_check"]:
match · inconclusive · mismatch · conflict · ambiguous · unconfirmed · no_voiceprint ·
unavailable · open_set_match · open_set_unknown. With no claim, a voice that is not a
strong match is `unknown` — a similar-sounding stranger is never accused.

Caller ID alone never changes the verdict (it only explains it), so CLAUDE.md / PRD FR-17
holds for the number: tests pin that the verdict with and without it is identical.

C owns this file.
"""

from __future__ import annotations

import itertools
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Optional

import config
from contracts import CallerMetadata, SpeakerVerdict, SpeakerVerificationResult

log = logging.getLogger("satyacheck.claims")

TRUST = {"user": "medium", "caller_id": "untrusted", "transcript": "medium"}
ACCUSING_SOURCES = frozenset({"user", "transcript"})


@dataclass(frozen=True)
class PersonRef:
    """What claims can be matched against, for one contact. No vectors."""
    person_id: str
    name: str
    relation: str
    aliases: tuple[str, ...] = ()
    phone_numbers: tuple[str, ...] = ()
    has_voiceprint: bool = False


@dataclass(frozen=True)
class Claim:
    source: str                  # "user" | "caller_id" | "transcript"
    person_ids: frozenset[str]   # contacts it could mean (a shared number or an alias: several)
    said: str                    # what was claimed: a person id, a number, a spoken name


# --- spoken self-identification --------------------------------------------------------------

#: Relation words that work as aliases without anyone typing them in.
RELATION_ALIASES: dict[str, tuple[str, ...]] = {
    "father": ("papa", "pappa", "dad", "daddy", "pitaji", "पापा", "पिताजी"),
    "mother": ("mummy", "mumma", "mom", "maa", "ma", "ammi", "मम्मी", "माँ", "मां"),
    "brother": ("bhaiya", "bhai", "भैया", "भाई"),
    "sister": ("didi", "दीदी"),
    "son": ("beta", "बेटा"),
    "daughter": ("beti", "बेटी"),
    "grandfather": ("dadaji", "nanaji", "dada", "nana", "दादाजी", "नानाजी"),
    "grandmother": ("dadi", "nani", "दादी", "नानी"),
}
_RELATION_WORDS = {w for words in RELATION_ALIASES.values() for w in words}

_NAME = r"([A-Za-z][A-Za-z'.-]*)"
_LATIN_PATTERNS = [
    re.compile(rf"\b(?:main|mai|mein|mei)\s+{_NAME}\s+(?:bol|baat\s+kar)\s+(?:raha|rahi|rha|rhi)\b", re.I),
    re.compile(rf"\b(?:main|mai)\s+{_NAME}\s+(?:hoon|hun|hu|hoo)\b", re.I),
    re.compile(rf"\bthis\s+is\s+{_NAME}\b", re.I),
    re.compile(rf"\bit'?s\s+(?:me,?\s+)?{_NAME}\b", re.I),
    re.compile(rf"\bI\s+am\s+{_NAME}\b", re.I),
    re.compile(rf"\bI'm\s+{_NAME}\b", re.I),
    re.compile(rf"\b{_NAME}\s+here\b", re.I),
]
_DEVANAGARI_PATTERNS = [
    re.compile(r"मैं\s+(\S+)\s+बोल\s+(?:रहा|रही)"),
    re.compile(r"मैं\s+(\S+)\s+(?:हूँ|हूं|हू)"),
]


def _plausible_name(token: str) -> bool:
    """A captured word that could be a name: capitalised (Whisper capitalises names) or a
    relation word. Keeps "I am calling" and "it's urgent" out."""
    return token[:1].isupper() or token.casefold() in _RELATION_WORDS


def extract_spoken_names(text: str) -> list[str]:
    """Names a speaker gives for themselves, in order, without duplicates. Deterministic."""
    if not text:
        return []
    found: list[str] = []
    for pattern in _LATIN_PATTERNS:
        for m in pattern.finditer(text):
            token = m.group(1).strip(".'-")
            if token and _plausible_name(token):
                found.append((m.start(), token))
    for pattern in _DEVANAGARI_PATTERNS:
        for m in pattern.finditer(text):
            found.append((m.start(), m.group(1)))
    out: list[str] = []
    for _, token in sorted(found):
        if token.casefold() not in {t.casefold() for t in out}:
            out.append(token)
    return out


# --- gathering claims ----------------------------------------------------------------------------

def _fold(text: str) -> str:
    return unicodedata.normalize("NFC", text or "").casefold().strip()


def _names_for(person: PersonRef) -> set[str]:
    names = {_fold(person.name), _fold(person.name.split()[0]) if person.name.split() else ""}
    names |= {_fold(a) for a in person.aliases}
    names |= {_fold(a) for a in RELATION_ALIASES.get(_fold(person.relation), ())}
    return {n for n in names if n}


def gather_claims(directory: Iterable[PersonRef], caller: Optional[CallerMetadata],
                  transcript_text: str = "") -> list[Claim]:
    """Every claim that names at least one of this account's contacts."""
    from server.person_views import clean_phone_numbers

    people = list(directory)
    claims: list[Claim] = []
    if caller is not None and caller.claimed_identity:
        if any(p.person_id == caller.claimed_identity for p in people):
            claims.append(Claim("user", frozenset({caller.claimed_identity}), caller.claimed_identity))
        else:
            log.info("claim: 'who is calling' pick is not one of this account's contacts; ignored")
    if caller is not None and caller.claimed_number:
        number = clean_phone_numbers([caller.claimed_number])
        owners = frozenset(p.person_id for p in people if number and number[0] in p.phone_numbers)
        if owners:
            claims.append(Claim("caller_id", owners, number[0]))
    for spoken in extract_spoken_names(transcript_text):
        meant = frozenset(p.person_id for p in people if _fold(spoken) in _names_for(p))
        if meant:
            claims.append(Claim("transcript", meant, spoken))
    return claims


def load_directory(owner_id: str) -> list[PersonRef]:
    """This account's contacts as PersonRefs (names, aliases, numbers; never vectors)."""
    from server.database import Person, Voiceprint, owner_session

    if not owner_id:
        return []
    with owner_session(owner_id) as db:
        with_vp = {pid for (pid,) in db.query(Voiceprint.person_id)
                   .join(Person, Person.person_id == Voiceprint.person_id)
                   .filter(Person.owner_id == owner_id,
                           Voiceprint.model_version == config.SPEAKER_MODEL_VERSION)}
        return [PersonRef(p.person_id, p.name, p.relation, tuple(p.aliases or ()),
                          tuple(p.phone_numbers or ()) + ((p.phone_number,) if p.phone_number else ()),
                          p.person_id in with_vp)
                for p in db.query(Person).filter(Person.owner_id == owner_id)]


# --- resolving ----------------------------------------------------------------------------------

def resolve(speaker: SpeakerVerificationResult, claims: list[Claim], directory: Iterable[PersonRef],
            narrowband: bool = False) -> SpeakerVerificationResult:
    """The identity verdict given the voice scores and the claims. Never raises."""
    try:
        return _resolve(speaker, claims, list(directory), narrowband)
    except Exception as e:  # noqa: BLE001 — rule 5: degrade to the open-set result, logged
        log.error(f"claim resolution failed, keeping the open-set identity: {type(e).__name__}: {e}")
        return speaker.model_copy(update={"details": {k: v for k, v in speaker.details.items() if k != "scores"}})


def _resolve(speaker, claims, directory, narrowband) -> SpeakerVerificationResult:
    scores: dict[str, float] = {str(k): float(v) for k, v in (speaker.details.get("scores") or {}).items()}
    details = {k: v for k, v in speaker.details.items() if k != "scores"}
    channel = "narrowband" if narrowband else "wideband"
    t = config.CLAIM_THRESHOLDS[channel]
    names = {p.person_id: p.name for p in directory}
    effective = [c for c in claims if c.person_ids]
    described = [{"source": c.source, "trust": TRUST.get(c.source, "untrusted"), "said": c.said,
                  "people": sorted(names.get(pid, pid) for pid in c.person_ids)} for c in effective]

    def out(verdict: SpeakerVerdict, outcome: str, person: Optional[str] = None,
            cosine: Optional[float] = None, claimed: Optional[str] = None) -> SpeakerVerificationResult:
        risk = config.FUSION_IDENTITY_RISK[verdict.value]
        named = person if verdict in (SpeakerVerdict.MATCH, SpeakerVerdict.MISMATCH) else None
        check = {"outcome": outcome, "channel": channel, "thresholds": dict(t), "claims": described}
        if cosine is not None:
            check["cosine"] = round(cosine, 4)
        if person is not None:
            check["person"] = names.get(person, person)
        return speaker.model_copy(update={
            "verdict": verdict, "risk": risk, "confidence": abs(risk - 0.5) * 2.0,
            "matched_person_id": named, "matched_person_name": names.get(named) if named else None,
            "claimed_person_id": claimed if claimed is not None else speaker.claimed_person_id,
            "raw_score": cosine if cosine is not None else speaker.raw_score,
            "details": {**details, "claim_check": check},
        })

    # 1. Nobody claimed anything we can map: open set, which never accuses.
    if not effective:
        if not scores:
            return out(SpeakerVerdict.UNKNOWN, "unavailable") if speaker.verdict == SpeakerVerdict.UNKNOWN \
                else speaker.model_copy(update={"details": details})
        best = max(scores, key=scores.get)
        if scores[best] >= t["match"]:
            return out(SpeakerVerdict.MATCH, "open_set_match", best, scores[best])
        return out(SpeakerVerdict.UNKNOWN, "open_set_unknown", None, scores[best])

    # 2. Sources that name different people: report both, accuse nobody.
    if any(a.person_ids.isdisjoint(b.person_ids) for a, b in itertools.combinations(effective, 2)):
        return out(SpeakerVerdict.UNKNOWN, "conflict")

    claimed = frozenset.intersection(*(c.person_ids for c in effective))
    checkable = [pid for pid in sorted(claimed) if pid in scores]
    single = next(iter(claimed)) if len(claimed) == 1 else None
    if not checkable:
        if not scores and any(pid for pid in claimed if pid in {p.person_id for p in directory if p.has_voiceprint}):
            return out(SpeakerVerdict.UNKNOWN, "unavailable", claimed=single)
        return out(SpeakerVerdict.UNKNOWN, "no_voiceprint", claimed=single)

    best = max(checkable, key=scores.get)
    cosine = scores[best]
    if cosine >= t["match"]:
        return out(SpeakerVerdict.MATCH, "match", best, cosine, claimed=best)
    accusing = any(c.source in ACCUSING_SOURCES for c in effective)
    if len(checkable) > 1 and any(c.source in ACCUSING_SOURCES and len(c.person_ids) > 1 for c in effective):
        return out(SpeakerVerdict.UNKNOWN, "ambiguous", None, cosine)
    if cosine >= t["low"]:
        return out(SpeakerVerdict.UNKNOWN, "inconclusive", best, cosine, claimed=best)
    if accusing:
        return out(SpeakerVerdict.MISMATCH, "mismatch", best, cosine, claimed=best)
    return out(SpeakerVerdict.UNKNOWN, "unconfirmed", best, cosine, claimed=best)


if __name__ == "__main__":
    papa = PersonRef("p1", "Ramesh", "Father", (), ("+919800000001",), True)
    for text in ("main Papa bol raha hoon", "This is Rahul"):
        print(text, "->", extract_spoken_names(text))
    claims = gather_claims([papa], CallerMetadata(claimed_number="+919800000001"), "main Papa bol raha hoon")
    r = resolve(SpeakerVerificationResult(details={"scores": {"p1": 0.6}}), claims, [papa])
    print("[OK] claims:", r.verdict.value, r.details["claim_check"]["outcome"])
