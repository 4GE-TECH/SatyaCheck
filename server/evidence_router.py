"""SatyaCheck — evidence log endpoints (item 17).

  GET /api/evidence/root               current tree size and root hash
  GET /api/evidence/{alert_id}/proof   inclusion proof for one alert (EvidenceAnchor)
  GET /api/evidence/verify             recompute every leaf and recorded root

C owns this file.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from contracts import EvidenceAnchor
from server import evidence

router = APIRouter(prefix="/api/evidence", tags=["evidence"])


@router.get("/root", summary="Current evidence-log root")
async def get_root() -> dict:
    root = evidence.get_log().root()
    return {"tree_size": root.tree_size, "root_hash": root.root_hash}


@router.get("/verify", summary="Recompute the whole log; false means it was edited")
async def verify() -> dict:
    return {"ok": evidence.get_log().verify_all()}


@router.get("/{alert_id}/proof", response_model=EvidenceAnchor, summary="Inclusion proof for an alert")
async def get_proof(alert_id: str) -> EvidenceAnchor:
    anchor = evidence.get_log().proof(alert_id)
    if anchor is None:
        raise HTTPException(status_code=404, detail=f"No logged alert '{alert_id}'.")
    return anchor
