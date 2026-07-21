"""HTTP API for orion.board (B-011: AI Board Orchestrator; extended by
G-012 with the read-only ``/roster`` endpoint). Same pattern
orion.governance.routes/orion.intelligence.routes/orion.business.routes
already establish: a separate router, mounted alongside the other
kernel routers in orion.window.app, every endpoint a thin wrapper over
orion.board.services/orion.board.canonical -- never a second, parallel
source of truth.

Namespaced under /api/board -- verified free of collisions before
choosing it, same discipline every prior Sprint's routes.py applied
for its own prefix.

G-012 note: /members below already reads its ``board_seat`` labels
through orion.board.member_registry, which itself now derives those
labels from .ai/board.yaml (orion.board.canonical) -- no route change
was needed there for it to reflect the canonical source. /roster is
the one genuinely new endpoint: it exposes the actual AI Board roster
(who: Luis/ChatGPT/Claude/Jules/Nemotron/AutoClaw), a different
concern from /members' Mission pipeline stages. It never returns
agent prompt file contents (only their path), per this Mission's
"no expongas... prompts internos" constraint.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from orion.board import services as board_services
from orion.board.board_engine import decide_pipeline
from orion.board.canonical import BoardConfigurationError, load_board_config

router = APIRouter(prefix="/api/board", tags=["board"])


@router.get("/roster")
def get_roster() -> list[dict]:
    try:
        config = load_board_config()
    except BoardConfigurationError as exc:
        raise HTTPException(status_code=500, detail=f"BoardConfigurationError: {exc}")
    return [
        {
            "id": m.id,
            "display_name": m.display_name,
            "role": m.role,
            "status": m.status,
            "responsibilities": list(m.responsibilities),
            "restrictions": list(m.restrictions),
            "documentation_path": m.documentation_path,
        }
        for m in config.members
    ]


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
