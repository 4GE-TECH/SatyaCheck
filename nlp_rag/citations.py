"""Static citations for reason codes that do not come from retrieval.

The identity and authenticity branches produce reason codes, but only the intent branch
produces a *retrieved* citation. Since `build_reason_codes` lives here, every citation
the product renders is B's responsibility — so these get the same treatment as corpus
anchors: real pages, on real government domains, opened before being added.

Like `corpus/anchors/`, these currently cite each agency's authoritative landing page.
Block 0's harvesting pass replaces them with deep links to the specific advisory.
Never add an entry whose URL you have not opened.
"""

from __future__ import annotations

from nlp_rag.corpus_loader import Citation

REGISTRY: dict[str, Citation] = {
    "RC_SYNTHETIC_VOICE_DETECTED": Citation(
        playbook_id="cite-deepfake-voice",
        title="Deepfake and cloned-voice fraud advisory",
        category="Voice cloning",
        source_url="https://cybercrime.gov.in/",
        source_agency="Indian Cyber Crime Coordination Centre (I4C), MHA",
    ),
    "RC_SPEAKER_MISMATCH": Citation(
        playbook_id="cite-impersonation",
        title="Impersonation of a known contact",
        category="Impersonation",
        source_url="https://cybercrime.gov.in/",
        source_agency="Indian Cyber Crime Coordination Centre (I4C), MHA",
    ),
    "RC_REPLAY_SUSPECTED": Citation(
        playbook_id="cite-replay",
        title="Recorded-audio replay in voice fraud",
        category="Replay attack",
        source_url="https://cybercrime.gov.in/",
        source_agency="Indian Cyber Crime Coordination Centre (I4C), MHA",
    ),
    "RC_UNKNOWN_CALLER_UNVERIFIED": Citation(
        playbook_id="cite-report-suspicious",
        title="Reporting suspected fraud communication",
        category="Guidance / Reporting",
        source_url="https://sancharsaathi.gov.in/",
        source_agency="Department of Telecommunications, Government of India",
    ),
}


def for_code(code: str) -> Citation | None:
    """Return the citation registered for `code`, or None if there is not one."""
    return REGISTRY.get(code)


if __name__ == "__main__":  # pragma: no cover - CLI smoke test
    for code, citation in REGISTRY.items():
        print(f"  {code:34} {citation.source_agency}")
        print(f"  {'':34} {citation.source_url}")
