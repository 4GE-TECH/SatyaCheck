"""SatyaCheck — tamper-evident evidence log (item 17).

Every guardian alert becomes a leaf in an append-only Merkle tree, built the way
Certificate Transparency builds its logs (RFC 6962 §2.1, RFC 9162 §2.1):

    leaf hash = SHA-256(0x00 || canonical alert JSON)
    node hash = SHA-256(0x01 || left || right)
    MTH(D[n]) splits at the largest power of two below n — no leaf is ever duplicated

The 0x00 / 0x01 prefixes are domain separation: without them an interior node can be
presented as a leaf (a second-preimage forgery). Every root the log has ever had is
recorded, so rewriting a past alert — even together with its leaf hash — no longer
reproduces the roots already printed on earlier PDF reports.

What is hashed is the alert's canonical JSON: ids, timestamp, score, band, summary, key
reasons and the audio's SHA-256. **No audio and no transcript are stored**, and the
caller's name or number is left out too — the log proves what SatyaCheck said, it is not
a second copy of who called. Persisted in SQLite (server/database.py), never in memory.

Single-process: appends are serialised with an in-process lock. Run one uvicorn worker,
or move appends behind a real writer before scaling out.

C owns this file.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import dataclass
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.engine import Engine

from contracts import EvidenceAnchor, GuardianAlert

log = logging.getLogger("satyacheck.evidence")


# --- RFC 6962 hashing ------------------------------------------------------------------

def leaf_hash(data: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + data).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def _split(n: int) -> int:
    """Largest power of two strictly less than n (n >= 2)."""
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def merkle_root(leaves: Sequence[bytes]) -> bytes:
    """MTH over already-hashed leaves."""
    n = len(leaves)
    if n == 0:
        return hashlib.sha256(b"").digest()
    if n == 1:
        return leaves[0]
    k = _split(n)
    return node_hash(merkle_root(leaves[:k]), merkle_root(leaves[k:]))


def audit_path(index: int, leaves: Sequence[bytes]) -> list[bytes]:
    """PATH(m, D[n]): the sibling hashes from leaf `index` up to the root."""
    n = len(leaves)
    if n <= 1:
        return []
    k = _split(n)
    if index < k:
        return audit_path(index, leaves[:k]) + [merkle_root(leaves[k:])]
    return audit_path(index - k, leaves[k:]) + [merkle_root(leaves[:k])]


def verify_inclusion(leaf: bytes, index: int, tree_size: int, path: Sequence[bytes], root: bytes) -> bool:
    """RFC 9162 §2.1.3.2 inclusion-proof verification."""
    if index >= tree_size or index < 0:
        return False
    fn, sn, r = index, tree_size - 1, leaf
    for p in path:
        if sn == 0:
            return False
        if fn & 1 or fn == sn:
            r = node_hash(p, r)
            if not fn & 1:
                while not fn & 1 and fn != 0:
                    fn >>= 1
                    sn >>= 1
        else:
            r = node_hash(r, p)
        fn >>= 1
        sn >>= 1
    return sn == 0 and r == root


# --- what is hashed --------------------------------------------------------------------------

#: Left out of the hashed record: who called is not what SatyaCheck said.
_EXCLUDED = {"caller_name_or_number"}


def canonical_alert(alert: GuardianAlert) -> bytes:
    body = {k: v for k, v in alert.model_dump(mode="json").items() if k not in _EXCLUDED}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


# --- the persisted log -----------------------------------------------------------------------------

@dataclass(frozen=True)
class Root:
    tree_size: int
    root_hash: str


class EvidenceLog:
    """Append-only alert log over the evidence tables in `engine`'s database."""

    def __init__(self, engine: Engine) -> None:
        from server.database import Base, EvidenceLeaf, EvidenceRoot

        self.engine = engine
        self._leaf_t = EvidenceLeaf.__table__
        self._root_t = EvidenceRoot.__table__
        Base.metadata.create_all(engine, tables=[self._leaf_t, self._root_t])
        self._lock = threading.Lock()

    # reads ------------------------------------------------------------------------------

    def _leaves(self, conn) -> list[tuple]:
        return conn.execute(
            select(self._leaf_t.c.leaf_index, self._leaf_t.c.alert_id, self._leaf_t.c.session_id,
                   self._leaf_t.c.leaf_hash, self._leaf_t.c.canonical_json)
            .order_by(self._leaf_t.c.leaf_index)
        ).all()

    def root(self) -> Root:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(self._root_t.c.tree_size, self._root_t.c.root_hash)
                .order_by(self._root_t.c.tree_size.desc()).limit(1)
            ).first()
        return Root(row[0], row[1]) if row else Root(0, merkle_root([]).hex())

    def _anchor(self, leaves: list[tuple], position: int) -> EvidenceAnchor:
        hashes = [bytes.fromhex(r[3]) for r in leaves]
        return EvidenceAnchor(
            alert_id=leaves[position][1],
            leaf_index=position,
            leaf_hash=hashes[position].hex(),
            tree_size=len(hashes),
            root_hash=merkle_root(hashes).hex(),
            audit_path=[h.hex() for h in audit_path(position, hashes)],
        )

    def proof(self, alert_id: str) -> Optional[EvidenceAnchor]:
        """Inclusion proof for `alert_id` against the current root, or None."""
        with self.engine.connect() as conn:
            leaves = self._leaves(conn)
        for position, row in enumerate(leaves):
            if row[1] == alert_id:
                return self._anchor(leaves, position)
        return None

    def session_of(self, alert_id: str) -> Optional[str]:
        """The session a logged alert belongs to (for ownership checks), or None."""
        with self.engine.connect() as conn:
            row = conn.execute(select(self._leaf_t.c.session_id)
                               .where(self._leaf_t.c.alert_id == alert_id)).first()
        return row[0] if row else None

    def latest_for_session(self, session_id: str) -> Optional[EvidenceAnchor]:
        with self.engine.connect() as conn:
            leaves = self._leaves(conn)
        positions = [i for i, row in enumerate(leaves) if row[2] == session_id]
        return self._anchor(leaves, positions[-1]) if positions else None

    def verify_all(self) -> bool:
        """Recompute every leaf from its stored JSON and every recorded root from the
        leaves. False on any mismatch — the log has been edited."""
        with self.engine.connect() as conn:
            leaves = self._leaves(conn)
            roots = conn.execute(select(self._root_t.c.tree_size, self._root_t.c.root_hash)).all()
        recomputed = [leaf_hash(row[4].encode("utf-8")) for row in leaves]
        for row, h in zip(leaves, recomputed):
            if row[3] != h.hex():
                log.error(f"evidence leaf {row[0]} ({row[1]}) does not match its stored JSON")
                return False
        for size, stored in roots:
            if size > len(recomputed) or merkle_root(recomputed[:size]).hex() != stored:
                log.error(f"evidence root at tree size {size} no longer reproduces")
                return False
        return True

    # writes -----------------------------------------------------------------------------

    def append(self, alert: GuardianAlert) -> EvidenceAnchor:
        """Add `alert` (once — a repeat returns its existing anchor) and record the new root."""
        data = canonical_alert(alert)
        with self._lock, self.engine.begin() as conn:
            leaves = self._leaves(conn)
            for position, row in enumerate(leaves):
                if row[1] == alert.alert_id:
                    return self._anchor(leaves, position)
            index = len(leaves)
            h = leaf_hash(data).hex()
            conn.execute(self._leaf_t.insert().values(
                leaf_index=index, alert_id=alert.alert_id, session_id=alert.session_id,
                leaf_hash=h, canonical_json=data.decode("utf-8"),
            ))
            leaves.append((index, alert.alert_id, alert.session_id, h, data.decode("utf-8")))
            anchor = self._anchor(leaves, index)
            conn.execute(self._root_t.insert().values(tree_size=anchor.tree_size, root_hash=anchor.root_hash))
        log.info(f"evidence: {alert.alert_id} -> leaf {index}, root {anchor.root_hash[:16]}… (size {anchor.tree_size})")
        return anchor


_default_log: Optional[EvidenceLog] = None


def get_log() -> EvidenceLog:
    """The log over the application database (server.database.engine)."""
    global _default_log
    if _default_log is None:
        from server.database import engine

        _default_log = EvidenceLog(engine)
    return _default_log
