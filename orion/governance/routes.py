"""HTTP API for orion.governance (BETA 010: Autonomous Development
Engine). Same pattern orion.intelligence.routes/orion.business.routes
already establish: a separate router, mounted alongside the other
kernel routers in orion.window.app, every endpoint a thin wrapper over
orion.governance.services -- the only module allowed to hold real
governance logic.

Namespaced under /api/governance -- verified free of collisions
before choosing it (same discipline BETA 009 learned the hard way for
/api/business): no other router in this codebase registers anything
under /governance, and no existing single-segment wildcard route
(e.g. orion.window.routes' GET /api/business/{name}) can match an
/api/governance/* path.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from orion.governance import services as governance_services

router = APIRouter(prefix="/api/governance", tags=["governance"])


class ApproveRequest(BaseModel):
    request_id: str
    approver: str = "ORION"
    notes: str = ""
    reject: bool = False


class ModeRequest(BaseModel):
    mode: str
    author: str = "ORION"
    reason: str = ""


@router.get("/policies")
def get_policies() -> list[dict]:
    return governance_services.describe_policies()


@router.get("/risk")
def get_risk(request: str = Query(..., description="Natural-language request/change description")) -> dict:
    evaluation = governance_services.evaluate_change(request)
    return evaluation.risk.to_dict()


@router.get("/audit")
def get_audit(category: str | None = None, mission_id: str | None = None) -> list[dict]:
    return governance_services.list_audit(category=category, mission_id=mission_id)


@router.get("/mode")
def get_mode() -> dict:
    profile = governance_services.get_mode_profile()
    return {"mode": profile.mode, "description": profile.description}


@router.post("/approve")
def post_approve(payload: ApproveRequest) -> dict:
    if payload.reject:
        result = governance_services.reject_request(payload.request_id, payload.approver, payload.notes)
    else:
        result = governance_services.approve_request(payload.request_id, payload.approver, payload.notes)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Solicitud de aprobacion '{payload.request_id}' no encontrada.")
    return result


@router.post("/mode")
def post_mode(payload: ModeRequest) -> dict:
    try:
        profile = governance_services.set_mode(payload.mode, author=payload.author, reason=payload.reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"mode": profile.mode, "description": profile.description}
