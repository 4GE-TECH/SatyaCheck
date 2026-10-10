"""SatyaCheck — the signed-in account itself.

  DELETE /api/account?confirm=DELETE   erase everything this account stored (DPDP Act
                                       2023 right to erasure): contacts, voiceprints,
                                       consents, calls, results, reports, call audio.

C owns this file.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from server import retention
from server.auth import current_owner

log = logging.getLogger("satyacheck.account")
router = APIRouter(prefix="/api/account", tags=["account"])


@router.delete("", summary="Delete this account's data permanently")
async def delete_account(
    confirm: str = Query("", description="Must be DELETE"),
    owner_id: str = Depends(current_owner),
) -> dict:
    if confirm != "DELETE":
        raise HTTPException(status_code=400, detail="Add ?confirm=DELETE: this cannot be undone.")
    try:
        return {"deleted": True, "removed": retention.delete_account(owner_id)}
    except Exception as e:
        log.error(f"account {owner_id}: erase failed: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail="The account could not be deleted. Please try again.")
