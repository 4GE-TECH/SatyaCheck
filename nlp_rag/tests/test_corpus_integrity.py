"""What "Block 0 complete" means, as assertions.

The evidence panel's whole claim (PRD §4.6) is that our explanation is an external
retrieved document with a source URL — a different evidence type from an attribution
map. A citation pointing at `cybercrime.gov.in/` supports that claim no better than no
citation at all: the reader cannot find the advisory being referred to.

The held-out set exists so M4 is a metric rather than a measurement of B's memory of
B's own writing. Without it `eval_retrieval.py` measures nothing.
"""

from __future__ import annotations

from urllib.parse import urlparse

import pytest

from nlp_rag.corpus_loader import load_corpus

CORPUS = load_corpus("nlp_rag/corpus")
ANCHORS = [d for d in CORPUS.retrievable if not d.derived]


def path_of(url: str) -> str:
    return urlparse(url).path.strip("/")


# --- citations must be findable ---------------------------------------------

@pytest.mark.parametrize("anchor", ANCHORS, ids=lambda d: d.id)
def test_every_anchor_cites_a_deep_link(anchor):
    """A bare domain is not a citation. A judge must land on the advisory itself."""
    assert path_of(anchor.source_url), (
        f"{anchor.id} cites the homepage {anchor.source_url!r}. "
        f"Harvest the specific advisory and link that."
    )


@pytest.mark.parametrize("anchor", ANCHORS, ids=lambda d: d.id)
def test_every_anchor_names_its_publishing_agency(anchor):
    assert anchor.source_agency, f"{anchor.id} has no source_agency"


def test_anchors_do_not_share_a_source_url():
    """Two anchors on one URL means at least one is not really sourced from it."""
    seen: dict[str, str] = {}
    collisions = []
    for anchor in ANCHORS:
        if anchor.source_url in seen:
            collisions.append(f"{anchor.id} and {seen[anchor.source_url]} → {anchor.source_url}")
        seen[anchor.source_url] = anchor.id
    assert not collisions, "anchors sharing a URL: " + "; ".join(collisions)


def test_the_corpus_has_enough_anchors_to_cover_the_scenarios():
    assert len(ANCHORS) >= 12, f"only {len(ANCHORS)} anchors"


def test_anchors_span_the_scam_families_the_demo_needs():
    families = {a.scam_family for a in ANCHORS}
    required = {
        "family_emergency",
        "digital_arrest",
        "kyc_update",
        "utility_disconnection",
        "parcel_customs",
    }
    assert required <= families, f"missing: {sorted(required - families)}"


# --- the held-out set ---------------------------------------------------------

def test_heldout_set_is_populated():
    assert len(CORPUS.heldout) >= 12, (
        f"only {len(CORPUS.heldout)} held-out documents; M4 needs a real test set"
    )


def test_heldout_documents_are_never_indexed():
    """Held-out text must not be retrievable, or P@3 is scored against itself."""
    indexed = {d.id for d in CORPUS.retrievable} | {d.id for d in CORPUS.benign}
    assert not (indexed & {d.id for d in CORPUS.heldout})


def test_heldout_text_is_not_copied_from_an_indexed_document():
    indexed_text = {d.text.strip().lower() for d in CORPUS.retrievable}
    overlap = [d.id for d in CORPUS.heldout if d.text.strip().lower() in indexed_text]
    assert not overlap, f"held-out text duplicated from the corpus: {overlap}"


@pytest.mark.parametrize("doc", CORPUS.heldout, ids=lambda d: d.id)
def test_every_heldout_document_declares_its_expected_anchor(doc):
    """The ground-truth label P@3 is scored against."""
    assert doc.expected_anchor, f"{doc.id} has no expected_anchor"


@pytest.mark.parametrize("doc", CORPUS.heldout, ids=lambda d: d.id)
def test_heldout_expected_anchors_exist(doc):
    assert doc.expected_anchor in {a.id for a in ANCHORS}, (
        f"{doc.id} expects unknown anchor {doc.expected_anchor!r}"
    )


def test_heldout_covers_more_than_one_scam_family():
    assert len({d.scam_family for d in CORPUS.heldout}) >= 4


def test_heldout_includes_devanagari_and_latin_script():
    scripts = {d.script for d in CORPUS.heldout}
    assert {"latin", "devanagari"} <= scripts, f"only {scripts}"
