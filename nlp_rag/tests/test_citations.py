"""Citations for reason codes that do not come from retrieval.

`RetrievedPlaybook.source_url` is the only *retrieved* citation, but the identity and
authenticity branches produce reason codes too — and `build_reason_codes` is B's, so
every citation in the product is B's. See `nlp_rag/PLAN.md` §9.
"""

from __future__ import annotations

from nlp_rag.citations import REGISTRY, for_code


def test_synthetic_voice_code_has_a_citation():
    citation = for_code("RC_SYNTHETIC_VOICE_DETECTED")
    assert citation is not None
    assert citation.source_url.startswith("https://")


def test_unknown_code_has_no_citation():
    assert for_code("RC_NOT_A_REAL_CODE") is None


def test_every_registered_citation_is_complete():
    """A half-filled citation renders as a broken link in the evidence panel."""
    assert REGISTRY, "registry is empty"
    for code, citation in REGISTRY.items():
        assert citation.source_url.startswith("https://"), code
        assert citation.title, code
        assert citation.source_agency, code
