"""The Project Registry: ORION's single source of truth for which
companies and projects it administers.

Registers, retrieves, lists, and updates projects. Nothing here
hardcodes a specific project's identity into the registry's own logic
— ``_SEED_PROJECTS`` below is bootstrap *data* (mirroring how The
Window seeds its example Business Units in
``orion/window/services.py``), not special-cased behavior: the same
``register_project`` function handles every project, seeded or not.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from orion.projects import storage
from orion.projects.models import Project, ProjectCreate, ProjectUpdate

# Bootstrap data only, seeded once on first run and never overwritten
# afterwards (same "no romper / no eliminar" rule The Window's own
# seed data follows). Each entry's ``business_unit_slug`` links it to
# the matching pre-existing Business Unit from Sprint 004, without
# merging the two systems: a Business Unit is a strategic/narrative
# snapshot for the CEO; a Project is the technical/operational record
# (repository, branch, missions) the Multi-Project Engine works with.
_REPOSITORY = "https://github.com/LUISAGUIRRERE/Orion-AI.git"

_SEED_PROJECTS: dict[str, dict[str, Any]] = {
    "atman": {
        "name": "ATMAN",
        "description": "Negocio principal de ORION.",
        "status": "active",
        "metadata": {"business_unit_slug": "atman"},
    },
    "cgiso": {
        "name": "CGISO",
        "description": "Operaciones y logistica.",
        "status": "active",
        "metadata": {"business_unit_slug": "cgiso"},
    },
    "casino": {
        "name": "CASINO",
        "description": "Unidad bajo revision regulatoria.",
        "status": "paused",
        "metadata": {"business_unit_slug": "casino"},
    },
    "tealife": {
        "name": "TEALIFE",
        "description": "Nueva linea de producto.",
        "status": "active",
        "metadata": {"business_unit_slug": "tealife"},
    },
    "resonance": {
        "name": "RESONANCE",
        "description": "Unidad en fase de planeacion.",
        "status": "planning",
        "metadata": {"business_unit_slug": "resonance"},
    },
    "autismo": {
        "name": "AUTISMO",
        "description": "Programa de cobertura terapeutica.",
        "status": "active",
        "metadata": {"business_unit_slug": "autismo"},
    },
}


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def register_project(payload: ProjectCreate) -> Project:
    """Register a new project. Raises ValueError if the id is already taken."""
    storage.ensure_projects_storage()
    if storage.project_exists(payload.project_id):
        raise ValueError(f"El proyecto '{payload.project_id}' ya esta registrado.")
    now = _now_iso()
    project = Project(
        project_id=payload.project_id,
        name=payload.name,
        description=payload.description,
        repository=payload.repository,
        default_branch=payload.default_branch,
        local_path=payload.local_path,
        status=payload.status,
        created_at=now,
        updated_at=now,
        metadata=payload.metadata,
    )
    storage.write_project(project.project_id, project.model_dump(mode="json"))
    return project


def get_project(project_id: str) -> Project | None:
    """Load a single project by id, or None if it is not registered."""
    data = storage.read_project(project_id)
    return None if data is None else Project(**data)


def list_projects() -> list[Project]:
    """Load every registered project, sorted by id."""
    return [Project(**storage.read_project(pid)) for pid in storage.list_project_ids()]


def update_project(project_id: str, payload: ProjectUpdate) -> Project | None:
    """Update an existing project's configuration. Only provided fields change."""
    project = get_project(project_id)
    if project is None:
        return None
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changes.items():
        setattr(project, field, value)
    project.updated_at = _now_iso()
    storage.write_project(project_id, project.model_dump(mode="json"))
    return project


def ensure_default_projects() -> None:
    """Seed the example companies (ATMAN, CGISO, CASINO, TEALIFE,
    RESONANCE, AUTISMO) on first run. Idempotent: a project that is
    already registered is never touched again, exactly like The
    Window's own Business Unit seeding.
    """
    storage.ensure_projects_storage()
    for project_id, data in _SEED_PROJECTS.items():
        if storage.project_exists(project_id):
            continue
        register_project(
            ProjectCreate(
                project_id=project_id,
                name=data["name"],
                description=data["description"],
                repository=_REPOSITORY,
                default_branch="main",
                status=data["status"],
                metadata=data["metadata"],
            )
        )
