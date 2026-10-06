"""Sector and threat label for a scam family (item 10).

Shown beside the reason codes so a guardian, a bank helpdesk or the 1930 report sees at
a glance which kind of fraud the call resembles — "banking / KYC update fraud".

Deterministic, like every other piece of explanation here (CLAUDE.md: no generated
text). Worded as a *pattern*, never as a judgement of the caller: the label says what
the call resembles, and fusion only attaches it to a warning band (server/orchestrator.py).

`nlp_rag/tests/test_threat_labels.py` fails if a family is added to the corpus without a
label here.
"""

from __future__ import annotations

from typing import Optional

#: scam_family -> (sector, threat). Keys mirror corpus_loader.VALID_FAMILIES.
THREAT_LABELS: dict[str, tuple[str, str]] = {
    "digital_arrest": ("law_enforcement_impersonation", "Digital arrest / fake police or agency"),
    "family_emergency": ("family", "Family emergency impersonation"),
    "kyc_update": ("banking", "KYC update fraud"),
    "financial_fraud": ("banking", "Financial fraud"),
    "qr_code_fraud": ("payments", "QR-code payment fraud"),
    "utility_disconnection": ("utilities", "Utility disconnection threat"),
    "telecom_impersonation": ("telecom", "Telecom / SIM impersonation"),
    "sms_fraud": ("telecom", "SMS link fraud"),
    "parcel_customs": ("logistics", "Parcel or customs fraud"),
    "lottery_advance_fee": ("prize_and_lottery", "Lottery / advance-fee fraud"),
}

#: Families that describe no threat: benign transcripts, and the non-indexed reporting
#: guidance anchors (which citations.py uses but retrieval never returns).
NO_LABEL_FAMILIES: frozenset[str] = frozenset({"none", "reporting"})


def threat_label_for(family: Optional[str]) -> Optional[dict]:
    """`{"sector", "threat", "family"}` for a scam family, or None. Never raises."""
    entry = THREAT_LABELS.get(family or "")
    if entry is None:
        return None
    sector, threat = entry
    return {"sector": sector, "threat": threat, "family": family}
