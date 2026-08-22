"""Corpus loading and citation resolution.

Documents live in `nlp_rag/corpus/` as YAML. Four kinds:

- `anchor`   a real advisory that was harvested and read. Carries the exact URL.
- `variant`  an authored script. Marked `derived`, inherits its anchor's citation.
- `benign`   an ordinary call transcript. The cohort scoring normalises against.
- `heldout`  a real excerpt reserved for evaluation. Never indexed.

`RetrievedPlaybook` has no `derived` field, so the anchor/variant distinction must
never leak past this module: a retrieved variant resolves to its anchor *before* the
contract object is built. One fabricated URL and `PRD.md` §4.6 stops being true.

Authoring mistakes fail loudly here. `nlp_rag.api` catches and degrades; a corpus with
a dangling anchor is a build-time bug, not a runtime condition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal

import yaml

from contracts import RetrievedPlaybook

DocKind = Literal["anchor", "variant", "benign", "heldout"]
VALID_KINDS: frozenset[str] = frozenset({"anchor", "variant", "benign", "heldout"})
VALID_LANGS: frozenset[str] = frozenset({"en", "hi", "hi_latn"})


class CorpusError(Exception):
    """Raised when the corpus on disk violates its own schema."""


@dataclass(frozen=True)
class Citation:
    """The externally verifiable half of a playbook. Always an anchor's."""

    playbook_id: str
    title: str
    category: str
    source_url: str
    source_agency: str


@dataclass(frozen=True)
class CorpusDoc:
    id: str
    kind: DocKind
    text: str
    title: str = ""
    scam_family: str = "none"
    lang: str = "en"
    script: str = "latin"
    category: str = "Uncategorised"
    source_url: str | None = None
    source_agency: str | None = None
    anchor_id: str | None = None
    derived: bool = False
    markers: list[str] = field(default_factory=list)
    severity: float = 0.5


class Corpus:
    """An immutable view over the loaded documents."""

    def __init__(self, docs: Iterable[CorpusDoc]) -> None:
        self._docs: dict[str, CorpusDoc] = {doc.id: doc for doc in docs}

    @property
    def retrievable(self) -> list[CorpusDoc]:
        """Anchors and variants — the only documents that may be indexed as scam text."""
        return [d for d in self._docs.values() if d.kind in ("anchor", "variant")]

    @property
    def benign(self) -> list[CorpusDoc]:
        return [d for d in self._docs.values() if d.kind == "benign"]

    @property
    def heldout(self) -> list[CorpusDoc]:
        return [d for d in self._docs.values() if d.kind == "heldout"]

    def get(self, doc_id: str) -> CorpusDoc:
        try:
            return self._docs[doc_id]
        except KeyError:
            raise CorpusError(f"unknown document id: {doc_id}") from None

    def resolve_citation(self, doc_id: str) -> Citation:
        """Return the anchor-backed citation for `doc_id`.

        A variant resolves to its anchor. An anchor resolves to itself. Nothing else
        can produce a citation, which is what keeps every `source_url` real.
        """
        doc = self.get(doc_id)
        anchor = self.get(doc.anchor_id) if doc.anchor_id else doc

        if not anchor.source_url:
            raise CorpusError(f"{anchor.id}: anchor has no source_url")

        return Citation(
            playbook_id=anchor.id,
            title=anchor.title,
            category=anchor.category,
            source_url=anchor.source_url,
            source_agency=anchor.source_agency or "",
        )

    def markers_for(self, doc_id: str) -> list[str]:
        """Markers this document exemplifies, falling back to its anchor's.

        Scoring uses this to avoid counting a marker twice — once because it fired on
        the transcript, and again because it is why the playbook retrieved at all.
        """
        doc = self.get(doc_id)
        if doc.markers:
            return list(doc.markers)
        if doc.anchor_id:
            return list(self.get(doc.anchor_id).markers)
        return []

    def to_playbook(self, doc_id: str, similarity: float) -> RetrievedPlaybook:
        """Build the contract object: anchor's citation, matched document's excerpt."""
        citation = self.resolve_citation(doc_id)
        return RetrievedPlaybook(
            playbook_id=citation.playbook_id,
            title=citation.title,
            category=citation.category,
            similarity_score=max(0.0, min(1.0, similarity)),
            matched_excerpt=self.get(doc_id).text,
            source_url=citation.source_url,
            source_agency=citation.source_agency,
        )

    def __len__(self) -> int:
        return len(self._docs)


def _coerce(raw: dict[str, Any], origin: Path) -> CorpusDoc:
    missing = [k for k in ("id", "kind", "text") if not raw.get(k)]
    if missing:
        raise CorpusError(f"{origin.name}: document missing required field(s): {missing}")

    kind = raw["kind"]
    if kind not in VALID_KINDS:
        raise CorpusError(f"{raw['id']}: unknown kind {kind!r}, expected one of {sorted(VALID_KINDS)}")

    lang = raw.get("lang", "en")
    if lang not in VALID_LANGS:
        raise CorpusError(f"{raw['id']}: unknown lang {lang!r}, expected one of {sorted(VALID_LANGS)}")

    if kind == "anchor" and not raw.get("source_url"):
        raise CorpusError(
            f"{raw['id']}: anchor has no source_url. Every anchor must cite a page "
            f"that was actually harvested and read."
        )
    if kind == "variant" and not raw.get("anchor_id"):
        raise CorpusError(f"{raw['id']}: variant has no anchor_id, so it can carry no citation")

    return CorpusDoc(
        id=raw["id"],
        kind=kind,
        text=str(raw["text"]).strip(),
        title=raw.get("title", ""),
        scam_family=raw.get("scam_family", "none"),
        lang=lang,
        script=raw.get("script", "latin"),
        category=raw.get("category", "Uncategorised"),
        source_url=raw.get("source_url"),
        source_agency=raw.get("source_agency"),
        anchor_id=raw.get("anchor_id"),
        derived=bool(raw.get("derived", False)),
        markers=list(raw.get("markers", []) or []),
        severity=float(raw.get("severity", 0.5)),
    )


def load_corpus(root: str | Path) -> Corpus:
    """Load every YAML document under `root`, validating the schema as it goes.

    A file may hold a single document or a list of them.
    """
    root = Path(root)
    if not root.is_dir():
        raise CorpusError(f"corpus directory not found: {root}")

    docs: dict[str, CorpusDoc] = {}
    for path in sorted(root.rglob("*.y*ml")):
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise CorpusError(f"{path.name}: invalid YAML: {exc}") from exc

        if payload is None:
            continue
        entries = payload if isinstance(payload, list) else [payload]

        for raw in entries:
            doc = _coerce(raw, path)
            if doc.id in docs:
                raise CorpusError(f"duplicate document id: {doc.id}")
            docs[doc.id] = doc

    corpus = Corpus(docs.values())

    for doc in corpus.retrievable:
        if doc.anchor_id and doc.anchor_id not in docs:
            raise CorpusError(f"{doc.id}: anchor_id refers to a missing anchor: {doc.anchor_id}")

    return corpus


if __name__ == "__main__":  # pragma: no cover - CLI smoke test
    corpus = load_corpus(Path(__file__).parent / "corpus")
    print(f"{len(corpus)} documents: {len(corpus.retrievable)} retrievable, "
          f"{len(corpus.benign)} benign, {len(corpus.heldout)} held-out")
    for doc in corpus.retrievable[:5]:
        citation = corpus.resolve_citation(doc.id)
        print(f"  {doc.id:44} → {citation.source_agency} · {citation.source_url}")
