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

# Every anchor, including the ones excluded from the index. Citation integrity is an
# obligation of being an anchor, not of being retrievable — an un-indexed anchor still
# owes a deep link and a named agency, because citations.py may still point at it.
ANCHORS = CORPUS.anchors


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


# --- family labels must agree with each other ---------------------------------
# `scam_family` is the key `eval_retrieval` scores family-level P@3 against. A document
# filed by filename rather than by content turns a correct retrieval into a recorded
# miss, and the metric quietly measures the labelling instead of the retrieval.

VARIANTS = [d for d in CORPUS.retrievable if d.derived]


@pytest.mark.parametrize("variant", VARIANTS, ids=lambda d: d.id)
def test_every_variant_shares_its_anchors_family(variant):
    anchor = CORPUS.get(variant.anchor_id)
    assert variant.scam_family == anchor.scam_family, (
        f"{variant.id} is {variant.scam_family!r} but {anchor.id} is "
        f"{anchor.scam_family!r}. Two names for one concept split the family-level "
        f"metric across both."
    )


@pytest.mark.parametrize("doc", CORPUS.heldout, ids=lambda d: d.id)
def test_every_heldout_shares_its_expected_anchors_family(doc):
    anchor = CORPUS.get(doc.expected_anchor)
    assert doc.scam_family == anchor.scam_family, (
        f"{doc.id} is {doc.scam_family!r} but the anchor it expects "
        f"({anchor.id}) is {anchor.scam_family!r}. One of the two is mislabelled, and "
        f"family-level P@3 scores a correct retrieval as a miss."
    )


# --- three-script coverage -----------------------------------------------------
# Whisper's output script is unstable: Devanagari when it detects `hi`, Latin
# transliteration on code-switched audio. A concept present in only one script is
# invisible to half of its own calls.
#
# This is also the language-bias guard. Scoring normalises against the benign cohort,
# which is thoroughly multilingual; when the scam corpus was not, a Devanagari call met
# a well-populated background and a nearly empty foreground and under-scored purely for
# being in Hindi.

SCRIPTS = {"en", "hi_latn", "hi"}

#: `lang` and `script` are two views of one fact and must not disagree. Latin-script
#: Hindi is `hi_latn`, never `hi` with `script: latin` — `_script_mix` and the
#: three-script coverage check both key on `lang`, so a document labelled `hi` while
#: written in Latin counts toward Devanagari coverage it does not provide.
EXPECTED_SCRIPT = {"en": "latin", "hi_latn": "latin", "hi": "devanagari"}


@pytest.mark.parametrize(
    "doc",
    list(CORPUS.retrievable) + list(CORPUS.benign) + list(CORPUS.heldout),
    ids=lambda d: d.id,
)
def test_lang_and_script_agree(doc):
    assert doc.script == EXPECTED_SCRIPT[doc.lang], (
        f"{doc.id} is lang={doc.lang!r} script={doc.script!r}; "
        f"lang {doc.lang!r} implies script {EXPECTED_SCRIPT[doc.lang]!r}"
    )


@pytest.mark.parametrize(
    "anchor", [a for a in ANCHORS if a.indexed], ids=lambda d: d.id
)
def test_every_indexed_anchor_covers_all_three_scripts(anchor):
    covered = {
        v.lang for v in CORPUS.retrievable if v.anchor_id == anchor.id
    }
    missing = sorted(SCRIPTS - covered)
    assert not missing, (
        f"{anchor.id} has no variant in {missing}. A call transcribed in that script "
        f"has nothing to retrieve against and under-scores for its language alone."
    )


# --- citable without being retrievable ----------------------------------------

def test_reporting_advisories_are_not_in_the_scam_index():
    """They describe what a victim should do, never what a caller says.

    No held-out item expects one, so in the index they are pure false-positive surface:
    a benign caller mentioning the 1930 helpline retrieves a scam playbook.
    """
    indexed = {d.id for d in CORPUS.retrievable}
    reporting = {a.id for a in ANCHORS if a.scam_family == "reporting"}
    assert reporting, "expected the reporting advisories to still be in the corpus"
    assert not (indexed & reporting), f"still indexed: {sorted(indexed & reporting)}"


@pytest.mark.parametrize(
    "anchor", [a for a in ANCHORS if not a.indexed], ids=lambda d: d.id
)
def test_an_unindexed_anchor_can_still_be_cited(anchor):
    """Leaving the index must not cost a document its citation."""
    citation = CORPUS.resolve_citation(anchor.id)
    assert citation.source_url == anchor.source_url
    assert citation.source_agency


def test_every_family_label_comes_from_the_closed_set():
    from nlp_rag.corpus_loader import VALID_FAMILIES

    everything = list(CORPUS.retrievable) + list(CORPUS.benign) + list(CORPUS.heldout)
    unknown = sorted({d.scam_family for d in everything} - VALID_FAMILIES)
    assert not unknown, f"family labels outside VALID_FAMILIES: {unknown}"
