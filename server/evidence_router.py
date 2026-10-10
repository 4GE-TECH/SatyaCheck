"""SatyaCheck — evidence log endpoints (item 17).

  GET /api/evidence/root               current tree size and root hash
  GET /api/evidence/{alert_id}/proof   inclusion proof for one alert (EvidenceAnchor)
  GET /api/evidence/verify             recompute every leaf and recorded root

Every route needs a signed-in account. The log is one tree across all accounts and the
API serves only hashes; a proof is served only to the owner of the alert's session.

C owns this file.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from contracts import EvidenceAnchor
from server import evidence
from server.auth import current_owner
from server.database import ScreeningSession, get_owner_db

router = APIRouter(prefix="/api/evidence", tags=["evidence"], dependencies=[Depends(current_owner)])


@router.get("/root", summary="Current evidence-log root")
async def get_root() -> dict:
    root = evidence.get_log().root()
    return {"tree_size": root.tree_size, "root_hash": root.root_hash}


@router.get("/verify", summary="Recompute the whole log; false means it was edited")
async def verify() -> dict:
    return {"ok": evidence.get_log().verify_all()}


@router.get("/{alert_id}/proof", response_model=EvidenceAnchor, summary="Inclusion proof for an alert")
async def get_proof(alert_id: str, owner_id: str = Depends(current_owner),
                    db: Session = Depends(get_owner_db)) -> EvidenceAnchor:
    anchor = evidence.get_log().proof(alert_id)
    session_id = evidence.get_log().session_of(alert_id) if anchor is not None else None
    owned = session_id is not None and db.query(ScreeningSession.session_id).filter(
        ScreeningSession.session_id == session_id, ScreeningSession.owner_id == owner_id).first()
    if not owned:   # another account's alert is indistinguishable from none
        raise HTTPException(status_code=404, detail=f"No logged alert '{alert_id}'.")
    return anchor
