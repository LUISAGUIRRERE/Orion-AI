"""The Builder Agent itself.

Finds the next READY mission, takes it, runs it through the correct
handler, records every step as a timeline event on the Mission
Framework, and always leaves the mission in a consistent terminal
state: REVIEW on success, FAILED on any error. Never RUNNING forever.

The Builder's own operational status (BuilderState) is persisted to
``workspace/builder_state.yaml``, not just held in memory. The Builder
is normally invoked as a separate process from the web server (there is
no execution-trigger API route, by design — see executor.py), so an
in-memory-only state would never be visible to The Window's dashboard,
which reads it from the server process. Persisting it, the same way
every other piece of Bridge data is persisted, closes that gap.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from orion.bridge import services as bridge_services
from orion.bridge import storage as bridge_storage
from orion.bridge.models import Mission, MissionStatus
from orion.execution import pipeline as execution_pipeline

AUTHOR = "Builder"
STATE_FILE: Path = bridge_storage.WORKSPACE_DIR / "builder_state.yaml"


@dataclass
class BuilderState:
    """The Builder's current operational status, surfaced to The Window."""

    status: str = "idle"
    current_mission_id: str | None = None
    current_handler: str | None = None
    completed_today: int = 0
    failed_today: int = 0
    last_activity: str | None = None
    day: str = field(default_factory=lambda: datetime.now(timezone.utc).date().isoformat())

    def roll_day(self) -> None:
        """Reset the daily counters when the UTC date changes."""
        today = datetime.now(timezone.utc).date().isoformat()
        if today != self.day:
            self.day = today
            self.completed_today = 0
            self.failed_today = 0

    def touch(self) -> None:
        """Record that the Builder just did something."""
        self.last_activity = datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_state() -> BuilderState:
    """Load the Builder's persisted state, or a fresh idle state if none exists."""
    if not STATE_FILE.exists():
        return BuilderState()
    with STATE_FILE.open("r", encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh) or {}
    state = BuilderState(**{**asdict(BuilderState()), **data})
    state.roll_day()
    return state


def _save_state(state: BuilderState) -> None:
    """Persist the Builder's state so any process can read it."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with STATE_FILE.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(asdict(state), fh)


def get_state() -> BuilderState:
    """Return the Builder's current, persisted state."""
    return _load_state()


def _find_next_ready_mission() -> Mission | None:
    """Find the first READY mission, preferring queue order."""
    for mission_id in bridge_services.get_queue():
        mission = bridge_services.get_mission(mission_id)
        if mission is not None and mission.status == MissionStatus.READY:
            return mission
    # Fall back to a full scan in case a READY mission isn't in the
    # queue (e.g. it was re-opened directly via PATCH .../status).
    for mission in bridge_services.list_missions():
        if mission.status == MissionStatus.READY:
            return mission
    return None


def process_next() -> Mission | None:
    """Process exactly one READY mission end to end.

    Returns the mission in its final state (REVIEW or FAILED), or None
    if no READY mission was found.
    """
    state = _load_state()
    mission = _find_next_ready_mission()
    if mission is None:
        state.status = "idle"
        _save_state(state)
        return None

    state.status = "working"
    state.current_mission_id = mission.id
    state.touch()
    _save_state(state)

    bridge_services.record_event(
        mission.id, "builder_assigned", f"Builder tomo la mission '{mission.title}'.", AUTHOR
    )
    mission = bridge_services.update_status(mission.id, MissionStatus.RUNNING, author=AUTHOR)
    assert mission is not None
    bridge_services.record_event(mission.id, "builder_started", "Builder inicio la ejecucion.", AUTHOR)

    state.current_handler = mission.mission_type
    _save_state(state)

    try:
        pipeline_result = execution_pipeline.run(mission)
    except Exception as exc:  # noqa: BLE001 - the pipeline itself must never crash the agent
        bridge_services.record_event(mission.id, "builder_failed", str(exc), AUTHOR)
        bridge_services.update_status(mission.id, MissionStatus.FAILED, author=AUTHOR)
        state.status = "idle"
        state.failed_today += 1
        state.current_mission_id = None
        state.current_handler = None
        state.touch()
        _save_state(state)
        return bridge_services.get_mission(mission.id)

    if not pipeline_result.success:
        bridge_services.record_event(mission.id, "builder_failed", pipeline_result.message, AUTHOR)
        bridge_services.update_status(mission.id, MissionStatus.FAILED, author=AUTHOR)
        state.status = "idle"
        state.failed_today += 1
        state.current_mission_id = None
        state.current_handler = None
        state.touch()
        _save_state(state)
        return bridge_services.get_mission(mission.id)

    result = pipeline_result.handler_result

    bridge_services.record_event(
        mission.id, "builder_progress", f"Handler '{mission.mission_type}' ejecutado.", AUTHOR
    )
    for artifact_name in result.artifacts:
        bridge_services.record_event(
            mission.id, "artifact_created", f"Artifact generado: {artifact_name}", AUTHOR
        )

    bridge_services.update_status(mission.id, MissionStatus.REVIEW, author=AUTHOR)
    bridge_services.record_event(
        mission.id, "builder_completed", result.summary or "Mission completada y enviada a revision.", AUTHOR
    )

    state.status = "idle"
    state.completed_today += 1
    state.current_mission_id = None
    state.current_handler = None
    state.touch()
    _save_state(state)

    return bridge_services.get_mission(mission.id)
