"""JSON API routes for the Command Bridge."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from orion.agents.builder import agent as builder_agent
from orion.agents.coo import agent as coo_agent
from orion.agents.coo import metrics as coo_metrics
from orion.bridge import services
from orion.execution import pipeline as execution_pipeline
from orion.bridge.models import (
    Event,
    Message,
    MessageCreate,
    Mission,
    MissionCreate,
    MissionStatusUpdate,
)

router = APIRouter(prefix="/api")


def _require_mission(mission_id: str) -> Mission:
    """Load a mission or raise 404."""
    mission = services.get_mission(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail=f"Mission '{mission_id}' not found")
    return mission


@router.post("/missions", response_model=Mission)
async def create_mission_endpoint(payload: MissionCreate) -> Mission:
    """Create a new mission and enqueue it."""
    return services.create_mission(payload)


@router.get("/missions", response_model=list[Mission])
async def list_missions_endpoint() -> list[Mission]:
    """List every mission."""
    return services.list_missions()


@router.get("/missions/{mission_id}", response_model=Mission)
async def get_mission_endpoint(mission_id: str) -> Mission:
    """Get a single mission by id."""
    return _require_mission(mission_id)


@router.patch("/missions/{mission_id}/status", response_model=Mission)
async def update_mission_status_endpoint(mission_id: str, payload: MissionStatusUpdate) -> Mission:
    """Change a mission's status."""
    _require_mission(mission_id)
    mission = services.update_status(mission_id, payload.status)
    assert mission is not None
    return mission


@router.post("/missions/{mission_id}/message", response_model=Message)
async def post_message_endpoint(mission_id: str, payload: MessageCreate) -> Message:
    """Append a message to a mission's conversation."""
    _require_mission(mission_id)
    message = services.add_message(mission_id, payload)
    assert message is not None
    return message


@router.get("/missions/{mission_id}/messages", response_model=list[Message])
async def get_messages_endpoint(mission_id: str) -> list[Message]:
    """List every message in a mission's conversation."""
    _require_mission(mission_id)
    return services.get_messages(mission_id)


@router.get("/missions/{mission_id}/events", response_model=list[Event])
async def get_events_endpoint(mission_id: str) -> list[Event]:
    """List every timeline event for a mission."""
    _require_mission(mission_id)
    return services.get_events(mission_id)


@router.get("/builder/status")
async def get_builder_status_endpoint() -> dict[str, str | int | None]:
    """Return the Builder Agent's current operational status.

    Reuses the Command Bridge's existing API router and prefix rather
    than introducing a new one, per Sprint 006's instruction not to
    duplicate infrastructure.
    """
    state = builder_agent.get_state()
    return {
        "status": state.status,
        "current_mission_id": state.current_mission_id,
        "current_handler": state.current_handler,
        # Sprint 009 (Multi Project Engine): minimal, documented
        # addition — surfaces BuilderState.current_project_id.
        "current_project_id": state.current_project_id,
        "completed_today": state.completed_today,
        "failed_today": state.failed_today,
        "last_activity": state.last_activity,
    }


@router.get("/coo/status")
async def get_coo_status_endpoint() -> dict[str, str | int | None]:
    """Return the COO Agent's current operational status."""
    state = coo_agent.get_state()
    return {
        "status": state.status,
        "assignments_today": state.assignments_today,
        "last_assignment": state.last_assignment,
        "last_scan": state.last_scan,
    }


@router.get("/coo/metrics")
async def get_coo_metrics_endpoint() -> dict[str, object]:
    """Return every COO metric, recalculated from current data."""
    return coo_metrics.compute()


@router.get("/coo/assignments")
async def get_coo_assignments_endpoint() -> list[dict[str, str | None]]:
    """Return every assignment the COO has made, derived from the
    Mission Framework's own event log (coo_assignment_created events) —
    no separate assignments store.
    """
    assignments: list[dict[str, str | None]] = []
    for mission in services.list_missions():
        for event in services.get_events(mission.id):
            if event.type == "coo_assignment_created":
                assignments.append(
                    {
                        "mission_id": mission.id,
                        "title": mission.title,
                        "owner": mission.owner,
                        "timestamp": event.timestamp,
                        "message": event.message,
                    }
                )
    assignments.sort(key=lambda a: a["timestamp"] or "")
    return assignments


@router.get("/execution/status")
async def get_execution_status_endpoint() -> dict[str, str | None]:
    """Return the Execution Pipeline's current operational status."""
    state = execution_pipeline.get_state()
    return {
        "workspace": state.workspace,
        "current_branch": state.current_branch,
        "current_commit": state.current_commit,
        "validation_status": state.validation_status,
        "repository_status": state.repository_status,
        "last_push": state.last_push,
        "pull_request": state.pull_request,
    }


@router.get("/execution/history")
async def get_execution_history_endpoint() -> list[dict[str, object]]:
    """Return every recorded execution outcome, oldest first."""
    return execution_pipeline.list_outcomes()


@router.get("/execution/current")
async def get_execution_current_endpoint() -> dict[str, object] | None:
    """Return the most recently recorded execution outcome, if any."""
    outcomes = execution_pipeline.list_outcomes()
    return outcomes[-1] if outcomes else None


@router.get("/queue", response_model=list[str])
async def get_queue_endpoint() -> list[str]:
    """List mission ids currently in the queue, front to back."""
    return services.get_queue()
