"""JSON API routes for the Multi-Project Engine.

A separate router, mounted alongside the Command Bridge's own
``/api`` router in ``orion/window/app.py`` — not added into
``orion/bridge/routes.py``, per this Sprint's restriction against
modifying Command Bridge code directly.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from orion.bridge.models import Mission
from orion.projects import registry, services
from orion.projects.models import Project

router = APIRouter(prefix="/api/projects")


def _require_project(project_id: str) -> Project:
    """Load a project or raise 404."""
    project = registry.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return project


@router.get("", response_model=list[Project])
async def list_projects_endpoint() -> list[Project]:
    """Return every registered project."""
    return registry.list_projects()


@router.get("/{project_id}", response_model=Project)
async def get_project_endpoint(project_id: str) -> Project:
    """Return a single registered project."""
    return _require_project(project_id)


@router.get("/{project_id}/missions", response_model=list[Mission])
async def get_project_missions_endpoint(project_id: str) -> list[Mission]:
    """Return every mission belonging to a project."""
    _require_project(project_id)
    return services.missions_for_project(project_id)


@router.get("/{project_id}/metrics")
async def get_project_metrics_endpoint(project_id: str) -> dict[str, object]:
    """Return a project's computed metrics: load, active Builders,
    average execution time, last activity, last commit.
    """
    project = _require_project(project_id)
    return services.describe_project(project)
