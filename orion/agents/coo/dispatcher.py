"""Dispatcher — pairs a READY mission with an available Builder.

The Dispatcher never executes a mission; it only decides the pairing,
persists the assignment (``mission.owner``), and records the event.

The COO never talks to a specific Builder by name — it always queries
the Builder Department. Today the department has exactly one Builder
(the Sprint 006 Builder Agent), wrapped as a single ``BuilderHandle``.
Adding a second Builder later means adding a second entry to
``list_department()`` — nothing in the COO, the scheduler, or the
dispatcher's own dispatch logic needs to change.
"""

from __future__ import annotations

from dataclasses import dataclass

from orion.agents.builder import agent as builder_agent
from orion.bridge import services as bridge_services
from orion.bridge.models import Mission

AUTHOR = "COO"


@dataclass
class BuilderHandle:
    """A single Builder as seen by the Builder Department."""

    id: str
    available: bool
    current_mission_id: str | None


def list_department() -> list[BuilderHandle]:
    """Return every Builder in the department, available or not."""
    state = builder_agent.get_state()
    return [
        BuilderHandle(
            id="builder-1",
            available=(state.status == "idle"),
            current_mission_id=state.current_mission_id,
        )
    ]


def select_available_builder() -> BuilderHandle | None:
    """Pick the first available Builder in the department, if any."""
    for handle in list_department():
        if handle.available:
            return handle
    return None


def assign(mission: Mission, builder: BuilderHandle, author: str = AUTHOR) -> Mission:
    """Assign a READY mission to a Builder.

    Never changes the mission's status and never touches its
    artifacts — only records who it was handed to.
    """
    updated = bridge_services.assign_owner(mission.id, owner=builder.id, author=author)
    assert updated is not None
    bridge_services.record_event(
        mission.id, "coo_assignment_created", f"Mission asignada a {builder.id}.", author
    )
    return updated
