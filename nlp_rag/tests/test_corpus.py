"""The corpus never emits a citation that does not point at a page someone read.

`RetrievedPlaybook` has no `derived` field, so a variant must resolve to its anchor
before it reaches the contract. See `nlp_rag/PLAN.md` §4.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from nlp_rag.corpus_loader import CorpusError, load_corpus

ANCHOR = """\
id: anch-digital-arrest-001
kind: anchor
scam_family: digital_arrest
lang: en
script: latin
title: Digital Arrest & Fake Police Extortion Advisory
source_url: https://cybercrime.gov.in/Webform/Crime_Advisory.aspx
source_agency: Indian Cyber Crime Coordination Centre (I4C), MHA
category: Extortion / Impersonation
markers: [MK_AUTHORITY_IMPERSONATION, MK_ISOLATION_DEMAND]
severity: 0.9
text: >-
  Callers impersonating police claim a warrant exists and demand immediate payment
  while forbidding the victim from contacting anyone.
"""

VARIANT_HI_LATN = """\
id: var-digital-arrest-001-hi-latn
kind: variant
anchor_id: anch-digital-arrest-001
derived: true
scam_family: digital_arrest
lang: hi_latn
script: latin
title: Cloned son arrested, urgent UPI bail
text: >-
  Papa emergency ho gaya hai, police ne pakad liya hai. Phone kisi ko mat dena,
  turant 50000 bhejo is UPI ID pe.
"""

BENIGN = """\
id: benign-delivery-001
kind: benign
scam_family: none
lang: en
script: latin
title: Routine delivery confirmation
text: Your parcel will be delivered between 4 and 6 PM today.
"""

HELDOUT = """\
id: heldout-real-case-001
kind: heldout
scam_family: digital_arrest
lang: en
script: latin
title: Reported case excerpt
text: The caller said a warrant had been issued and I must not disconnect.
"""


def _write(root: Path, name: str, body: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")


@pytest.fixture
def corpus_dir(tmp_path: Path) -> Path:
    _write(tmp_path, "anchors/digital_arrest.yaml", ANCHOR)
    _write(tmp_path, "variants/digital_arrest_hi.yaml", VARIANT_HI_LATN)
    _write(tmp_path, "benign/delivery.yaml", BENIGN)
    _write(tmp_path, "heldout/real_cases.yaml", HELDOUT)
    return tmp_path


# --- loading -----------------------------------------------------------------

def test_loads_documents_of_every_kind(corpus_dir: Path):
    corpus = load_corpus(corpus_dir)
    assert len(corpus.retrievable) == 2      # anchor + variant
    assert len(corpus.benign) == 1
    assert len(corpus.heldout) == 1


def test_heldout_documents_are_never_retrievable(corpus_dir: Path):
    """Held-out excerpts are the test set. Indexing them makes P@3 meaningless."""
    corpus = load_corpus(corpus_dir)
    assert "heldout-real-case-001" not in {doc.id for doc in corpus.retrievable}


def test_benign_documents_are_never_retrievable_as_scam_playbooks(corpus_dir: Path):
    corpus = load_corpus(corpus_dir)
    assert "benign-delivery-001" not in {doc.id for doc in corpus.retrievable}


# --- citation integrity ------------------------------------------------------

def test_anchor_resolves_to_its_own_citation(corpus_dir: Path):
    corpus = load_corpus(corpus_dir)
    citation = corpus.resolve_citation("anch-digital-arrest-001")
    assert citation.source_url == "https://cybercrime.gov.in/Webform/Crime_Advisory.aspx"
    assert citation.source_agency == "Indian Cyber Crime Coordination Centre (I4C), MHA"


def test_variant_inherits_its_anchors_citation(corpus_dir: Path):
    corpus = load_corpus(corpus_dir)
    citation = corpus.resolve_citation("var-digital-arrest-001-hi-latn")
    assert citation.source_url == "https://cybercrime.gov.in/Webform/Crime_Advisory.aspx"
    assert citation.source_agency == "Indian Cyber Crime Coordination Centre (I4C), MHA"


def test_playbook_built_from_a_variant_carries_the_anchor_title(corpus_dir: Path):
    """The panel cites the advisory that was read, never the authored variant."""
    corpus = load_corpus(corpus_dir)
    playbook = corpus.to_playbook("var-digital-arrest-001-hi-latn", similarity=0.91)

    assert playbook.playbook_id == "anch-digital-arrest-001"
    assert playbook.title == "Digital Arrest & Fake Police Extortion Advisory"
    assert playbook.source_url == "https://cybercrime.gov.in/Webform/Crime_Advisory.aspx"
    assert playbook.similarity_score == 0.91


def test_playbook_excerpt_comes_from_the_matched_document_not_the_anchor(corpus_dir: Path):
    """The citation is the anchor's; the excerpt shown is what actually matched."""
    corpus = load_corpus(corpus_dir)
    playbook = corpus.to_playbook("var-digital-arrest-001-hi-latn", similarity=0.91)
    assert "kisi ko mat dena" in playbook.matched_excerpt


def test_three_scripts_of_one_concept_share_a_single_citation(tmp_path: Path):
    _write(tmp_path, "anchors/a.yaml", ANCHOR)
    _write(tmp_path, "variants/hi_latn.yaml", VARIANT_HI_LATN)
    _write(
        tmp_path,
        "variants/hi_deva.yaml",
        """\
        id: var-digital-arrest-001-hi-deva
        kind: variant
        anchor_id: anch-digital-arrest-001
        derived: true
        scam_family: digital_arrest
        lang: hi
        script: devanagari
        title: क्लोन बेटा, तुरंत यूपीआई
        text: किसी को मत बताओ, तुरंत पैसे भेजो।
        """,
    )
    corpus = load_corpus(tmp_path)
    urls = {
        corpus.resolve_citation(doc.id).source_url for doc in corpus.retrievable
    }
    assert urls == {"https://cybercrime.gov.in/Webform/Crime_Advisory.aspx"}


# --- authoring errors fail loudly at load ------------------------------------

def test_variant_pointing_at_a_missing_anchor_is_rejected(tmp_path: Path):
    _write(tmp_path, "variants/orphan.yaml", VARIANT_HI_LATN)
    with pytest.raises(CorpusError, match="anch-digital-arrest-001"):
        load_corpus(tmp_path)


def test_anchor_without_a_source_url_is_rejected(tmp_path: Path):
    _write(
        tmp_path,
        "anchors/bad.yaml",
        """\
        id: anch-no-url-001
        kind: anchor
        scam_family: kyc_update
        lang: en
        script: latin
        title: Missing citation
        text: Some advisory text.
        """,
    )
    with pytest.raises(CorpusError, match="source_url"):
        load_corpus(tmp_path)


def test_duplicate_document_ids_are_rejected(tmp_path: Path):
    _write(tmp_path, "anchors/a.yaml", ANCHOR)
    _write(tmp_path, "anchors/b.yaml", ANCHOR)
    with pytest.raises(CorpusError, match="duplicate"):
        load_corpus(tmp_path)


# --- the corpus actually shipped in this repo --------------------------------

def test_shipped_corpus_loads_and_every_anchor_has_a_citation():
    corpus = load_corpus(Path(__file__).parent.parent / "corpus")
    assert corpus.retrievable, "seed corpus is empty"
    assert corpus.benign, "benign cohort is empty; scoring cannot normalise"
    for doc in corpus.retrievable:
        citation = corpus.resolve_citation(doc.id)
        assert citation.source_url.startswith("https://")
        assert citation.source_agency
