"""High-level operations for the Multi-Project Engine.

This is the only module that ties the Project Registry to the Command
Bridge, the Builder Agent, and the Execution Pipeline. None of those
are modified beyond this Sprint's documented minimal additions —
everything here works by reading their existing, already-public data
(``bridge_services.list_missions()``, ``builder_agent.get_state()``,
``execution_pipeline.get_outcome()``), never by reaching into their
internals.
"""

from __future__ import annotations

from orion.agents.builder import agent as builder_agent
from orion.bridge import services as bridge_services
from orion.bridge.models import Mission, MissionCreate, MissionStatus
from orion.projects import registry
from orion.projects.models import Project

AUTHOR = "ORION"

_ACTIVE_STATUSES = (
    MissionStatus.NEW,
    MissionStatus.READY,
    MissionStatus.RUNNING,
    MissionStatus.WAITING,
    MissionStatus.REVIEW,
)


def create_project_mission(project_id: str, payload: MissionCreate, author: str = AUTHOR) -> Mission:
    """Create a mission explicitly attached to a registered project.

    Resolves ``repository`` and ``working_branch`` from the Project's
    own configuration (never trusting the caller to know them), then
    creates the mission through the Command Bridge's existing,
    unmodified ``create_mission`` — and records ``project_selected``
    the same way the Builder records its own events: as a normal,
    public caller of ``record_event``.
    """
    project = registry.get_project(project_id)
    if project is None:
        raise ValueError(f"El proyecto '{project_id}' no esta registrado.")

    payload.project_id = project.project_id
    payload.repository = project.repository
    payload.working_branch = project.default_branch

    mission = bridge_services.create_mission(payload, author=author)
    bridge_services.record_event(
        mission.id,
        "project_selected",
        f"Mision asociada al proyecto '{project.name}' (repositorio: {project.repository or '-'}).",
        author,
    )
    return mission


def missions_for_project(project_id: str) -> list[Mission]:
    """Every mission belonging to a project, filtered from the Command
    Bridge's own full mission list.
    """
    return [m for m in bridge_services.list_missions() if m.project_id == project_id]


def project_mission_load(project_id: str) -> dict[str, int]:
    """Mission counts by status for a single project."""
    counts = {status.value: 0 for status in MissionStatus}
    for mission in missions_for_project(project_id):
        counts[mission.status.value] += 1
    return counts


def project_active_builders(project_id: str) -> int:
    """How many Builders are currently working a mission of this project.

    With exactly one Builder in the department (Sprint 006/007), this
    is always 0 or 1. The check is generic — it looks at whichever
    mission the Builder currently has, not a hardcoded Builder count —
    so it keeps working unchanged if the department grows.
    """
    state = builder_agent.get_state()
    if state.current_mission_id is None:
        return 0
    mission = bridge_services.get_mission(state.current_mission_id)
    return 1 if mission is not None and mission.project_id == project_id else 0


def project_last_activity(project_id: str) -> str | None:
    """The most recent event timestamp across every mission of this project."""
    latest: str | None = None
    for mission in missions_for_project(project_id):
        for event in bridge_services.get_events(mission.id):
            if latest is None or event.timestamp > latest:
                latest = event.timestamp
    return latest


def _last_execution_outcome(project_id: str) -> dict[str, object] | None:
    """The most recently finished Execution Pipeline outcome for this
    project, if any. Imported locally to avoid a module-load-time
    dependency between orion.projects and orion.execution.
    """
    from orion.execution import pipeline as execution_pipeline

    latest: dict[str, object] | None = None
    for mission in missions_for_project(project_id):
        outcome = execution_pipeline.get_outcome(mission.id)
        if outcome is None:
            continue
        if latest is None or (outcome.get("finished_at") or "") > (latest.get("finished_at") or ""):
            latest = outcome
    return latest


def _average_execution_seconds(project_id: str) -> float:
    from orion.execution import pipeline as execution_pipeline

    values = [
        outcome["execution_seconds"]
        for mission in missions_for_project(project_id)
        if (outcome := execution_pipeline.get_outcome(mission.id)) is not None
        and outcome.get("execution_seconds") is not None
    ]
    return round(sum(values) / len(values), 3) if values else 0.0


def describe_project(project: Project) -> dict[str, object]:
    """A single, reusable summary of a project: everything both the
    Projects view and the Business Overview section need. Computed
    once here so the two never drift out of sync with each other.
    """
    load = project_mission_load(project.project_id)
    last_outcome = _last_execution_outcome(project.project_id)
    return {
        "project_id": project.project_id,
        "name": project.name,
        "status": project.status,
        "repository": project.repository,
        "default_branch": project.default_branch,
        "missions_total": sum(load.values()),
        "missions_active": sum(load[s.value] for s in _ACTIVE_STATUSES),
        "load": load,
        "active_builders": project_active_builders(project.project_id),
        "last_activity": project_last_activity(project.project_id),
        "last_commit": last_outcome["commit_hash"] if last_outcome else None,
        "average_execution_seconds": _average_execution_seconds(project.project_id),
    }


def business_overview() -> dict[str, object]:
    """Aggregated payload for the dashboard's 'Business Overview' section."""
    projects = registry.list_projects()
    summaries = [describe_project(p) for p in projects]
    active_repositories = {s["repository"] for s in summaries if s["repository"]}
    last_activity: str | None = None
    for summary in summaries:
        activity = summary["last_activity"]
        if activity and (last_activity is None or activity > last_activity):
            last_activity = activity
    return {
        "active_projects": sum(1 for p in projects if p.status == "active"),
        "active_repositories": len(active_repositories),
        "last_activity": last_activity,
        "companies": summaries,
    }
