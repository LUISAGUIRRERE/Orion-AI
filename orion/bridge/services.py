"""Business logic for the Command Bridge.

Ties storage, the queue, and automatic timeline-event generation
together. Every mutation (creation, status change, new message)
produces a recorded Event, so a mission's full history can always be
reconstructed.
"""

from __future__ import annotations

from datetime import datetime, timezone

from orion.bridge import queue as queue_module
from orion.bridge import storage
from orion.bridge.models import (
    Event,
    Message,
    MessageCreate,
    Mission,
    MissionCreate,
    MissionStatus,
)

_TERMINAL_STATUSES = {MissionStatus.DONE, MissionStatus.FAILED}

STATUS_BUCKETS: dict[str, tuple[MissionStatus, ...]] = {
    "pendientes": (MissionStatus.NEW, MissionStatus.READY),
    "en_ejecucion": (MissionStatus.RUNNING, MissionStatus.REVIEW),
    "esperando": (MissionStatus.WAITING,),
    "terminadas": (MissionStatus.DONE,),
    "bloqueadas": (MissionStatus.BLOCKED, MissionStatus.FAILED),
}


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _next_mission_id() -> str:
    """Generate the next sequential MISSION-XXXX identifier."""
    max_n = 0
    for mission_id in storage.list_mission_ids():
        try:
            max_n = max(max_n, int(mission_id.split("-")[-1]))
        except ValueError:
            continue
    return f"MISSION-{max_n + 1:04d}"


def record_event(mission_id: str, event_type: str, message: str, author: str) -> Event:
    """Append a timeline event for a mission and return it.

    Public on purpose: any role (not just this module's own mission
    lifecycle functions) may need to record a custom event type, e.g.
    the Builder Agent's builder_assigned / builder_progress events.
    """
    events = storage.read_events(mission_id)
    event = Event(
        id=len(events) + 1,
        mission_id=mission_id,
        type=event_type,
        message=message,
        author=author,
        timestamp=_now_iso(),
    )
    storage.append_event(mission_id, event.model_dump())
    return event


def create_mission(payload: MissionCreate, author: str = "ORION") -> Mission:
    """Create a new mission, persist it, enqueue it, and record its creation."""
    mission_id = _next_mission_id()
    now = _now_iso()
    mission = Mission(
        id=mission_id,
        title=payload.title,
        description=payload.description,
        business_unit=payload.business_unit,
        assigned_role=payload.assigned_role,
        priority=payload.priority,
        mission_type=payload.mission_type,
        status=MissionStatus.NEW,
        created_at=now,
        updated_at=now,
        owner=payload.owner,
        tags=payload.tags,
        # Sprint 009 (Multi Project Engine): passthrough only. This
        # function does not know or care what a project is — that
        # stays entirely in orion.projects, which resolves these
        # fields before calling here. Left empty, a mission behaves
        # exactly as it did before this Sprint.
        project_id=payload.project_id,
        repository=payload.repository,
        working_branch=payload.working_branch,
        artifact_path=payload.artifact_path,
    )
    storage.write_mission(mission_id, mission.model_dump(mode="json"))
    record_event(mission_id, "created", f"Mission '{mission.title}' creada.", author)
    if payload.owner or payload.assigned_role:
        record_event(
            mission_id,
            "assigned",
            f"Asignada a owner='{payload.owner or '—'}', rol='{payload.assigned_role or '—'}'.",
            author,
        )
    queue_module.enqueue(mission_id)
    return mission


def get_mission(mission_id: str) -> Mission | None:
    """Load a single mission by id, or None if it does not exist."""
    data = storage.read_mission(mission_id)
    return None if data is None else Mission(**data)


def list_missions() -> list[Mission]:
    """Load every persisted mission."""
    return [Mission(**storage.read_mission(mid)) for mid in storage.list_mission_ids()]


def update_status(mission_id: str, new_status: MissionStatus, author: str = "ORION") -> Mission | None:
    """Change a mission's status and record the transition on its timeline."""
    mission = get_mission(mission_id)
    if mission is None:
        return None

    old_status = mission.status
    mission.status = new_status
    mission.updated_at = _now_iso()

    if new_status == MissionStatus.RUNNING and mission.started_at is None:
        mission.started_at = mission.updated_at
        record_event(mission_id, "started", "Mission iniciada.", author)

    if new_status in _TERMINAL_STATUSES and mission.finished_at is None:
        mission.finished_at = mission.updated_at
        record_event(mission_id, "finished", f"Mission finalizada con estado {new_status.value}.", author)

    storage.write_mission(mission_id, mission.model_dump(mode="json"))
    record_event(
        mission_id,
        "status_changed",
        f"Estado cambiado de {old_status.value} a {new_status.value}.",
        author,
    )
    return mission


def add_message(mission_id: str, payload: MessageCreate) -> Message | None:
    """Append a message to a mission's conversation and record the event."""
    if not storage.mission_exists(mission_id):
        return None
    messages = storage.read_messages(mission_id)
    message = Message(
        id=len(messages) + 1,
        mission_id=mission_id,
        sender=payload.sender,
        receiver=payload.receiver,
        message=payload.message,
        created_at=_now_iso(),
        attachments=payload.attachments,
    )
    storage.append_message(mission_id, message.model_dump())
    record_event(mission_id, "message", f"Mensaje de {payload.sender} a {payload.receiver}.", payload.sender)
    return message


def assign_owner(mission_id: str, owner: str, author: str = "ORION") -> Mission | None:
    """Assign a mission to an owner (e.g. a specific Builder) without
    changing its status or executing anything.

    Used by coordinating roles, like the COO, that decide who should
    work on a mission without doing the work themselves.
    """
    mission = get_mission(mission_id)
    if mission is None:
        return None
    mission.owner = owner
    mission.updated_at = _now_iso()
    storage.write_mission(mission_id, mission.model_dump(mode="json"))
    return mission


def get_messages(mission_id: str) -> list[Message]:
    """List every message for a mission, in chronological order."""
    return [Message(**m) for m in storage.read_messages(mission_id)]


def get_events(mission_id: str) -> list[Event]:
    """List every timeline event for a mission, in chronological order."""
    return [Event(**e) for e in storage.read_events(mission_id)]


def get_queue() -> list[str]:
    """Return the current mission queue, front to back."""
    return queue_module.list_queue()


def get_mission_summary() -> dict[str, int]:
    """Count missions per dashboard bucket: pendientes, en_ejecucion,
    esperando, terminadas, bloqueadas.
    """
    counts = {bucket: 0 for bucket in STATUS_BUCKETS}
    for mission in list_missions():
        for bucket, statuses in STATUS_BUCKETS.items():
            if mission.status in statuses:
                counts[bucket] += 1
                break
    return counts
