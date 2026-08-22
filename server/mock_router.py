"""SatyaCheck — Mock API Router

Block 0 deliverable: returns frozen contract fixtures so D can render the UI
before any real ML branches are wired up.

REMOVE or DEPRECATE after GATE C2 (Block 2 integration).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from contracts import ScreeningResponse, create_mock_fixture

router = APIRouter(prefix="/api/mock", tags=["mock"])

ScenarioType = Literal["green", "caution", "suspicious", "red", "unverified", "insufficient"]


@router.get(
    "/screen/{scenario}",
    response_model=ScreeningResponse,
    summary="[MOCK] Return a frozen screening fixture",
    description=(
        "Returns a hardcoded ScreeningResponse for the given scenario. "
        "Used by D during Block 0/1 before real branches are integrated. "
        "Deprecated after GATE C2."
    ),
)
async def get_mock_screening(scenario: ScenarioType) -> ScreeningResponse:
    return create_mock_fixture(scenario)


@router.get(
    "/screen",
    summary="[MOCK] List available fixture scenarios",
)
async def list_mock_scenarios() -> JSONResponse:
    return JSONResponse(content={
        "scenarios": ["green", "caution", "suspicious", "red", "unverified", "insufficient"],
        "note": "Hit /api/mock/screen/{scenario} for a full ScreeningResponse fixture.",
        "bands_covered": ["verified", "caution", "suspicious", "high_risk", "unverified", "insufficient"],
        "deprecated_after": "GATE C2 (Block 2 integration)",
    })
