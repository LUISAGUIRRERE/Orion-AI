"""HTTP API for orion.board (B-011: AI Board Orchestrator). Same
pattern orion.governance.routes/orion.intelligence.routes/orion.
business.routes already establish: a separate router, mounted
alongside the other kernel routers in orion.window.app, every endpoint
a thin wrapper over orion.board.services -- the only module allowed to
hold real Board logic.

Namespaced under /api/board -- verified free of collisions before
choosing it, same discipline every prior Sprint's routes.py applied
for its own prefix.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from orion.board import services as board_services
from orion.board.board_engine import decide_pipeline

router = APIRouter(prefix="/api/board", tags=["board"])


@router.get("/members")
def get_members() -> list[dict]:
    return [
        {
            "key": m.key,
            "display_name": m.display_name,
            "board_seat": m.board_seat,
            "implemented_by": m.implemented_by,
            "description": m.description,
        }
        for m in board_services.describe_members()
    ]


@router.get("/pipeline")
def get_pipeline_dry_run(request: str = Query(..., description="Natural-language request (dry-run, not persisted)")) -> dict:
    pipeline = decide_pipeline(request)
    return {
        "kind": pipeline.kind.value,
        "category": pipeline.category.value if pipeline.category is not None else None,
        "stages": list(pipeline.stages),
        "rule": pipeline.rule,
        "summary": pipeline.summary_text(),
    }


@router.get("/pipeline/{mission_id}")
def get_pipeline_for_mission(mission_id: str) -> dict:
    decision = board_services.get_decision(mission_id)
    if decision is None:
        raise HTTPException(status_code=404, detail=f"No hay un pipeline decidido para la mission '{mission_id}'.")
    pipeline = decision.pipeline
    return {
        "mission_id": mission_id,
        "kind": pipeline.kind.value,
        "category": pipeline.category.value if pipeline.category is not None else None,
        "stages": list(pipeline.stages),
        "rule": pipeline.rule,
        "summary": pipeline.summary_text(),
    }


@router.get("/progress/{mission_id}")
def get_progress_for_mission(mission_id: str) -> list[dict]:
    progress = board_services.get_progress(mission_id)
    if progress is None:
        raise HTTPException(status_code=404, detail=f"No hay un pipeline decidido para la mission '{mission_id}'.")
    return [
        {
            "key": stage.key,
            "display_name": stage.display_name,
            "board_seat": stage.board_seat,
            "status": stage.status,
            "matched_events": list(stage.matched_events),
        }
        for stage in progress
    ]
