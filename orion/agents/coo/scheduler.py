"""COO Scheduler — a simple, dependency-free scan-and-assign cycle.

Each call to ``run_cycle()`` performs exactly one cycle:

1. Scan the queue for the next READY mission.
2. Look for an available Builder in the department.
3. Assign the mission, if both exist.
4. Record events.
5. Finish.

No external libraries, no cron, no background thread — the COO is
invoked explicitly, the same way the Builder Agent's executor is.

Events are recorded against the mission the cycle found, using the
existing Mission Framework event log. When a cycle finds no READY
mission at all, there is nothing to attach an event to, so none is
recorded — the COO's own state (see ``agent.py``) still reflects that
the scan happened.
"""

from __future__ import annotations

from orion.agents.coo import dispatcher
from orion.bridge import services as bridge_services
from orion.bridge.models import Mission, MissionStatus

AUTHOR = "COO"


def _find_next_ready_mission() -> Mission | None:
    """Find the first READY mission, preferring queue order."""
    for mission_id in bridge_services.get_queue():
        mission = bridge_services.get_mission(mission_id)
        if mission is not None and mission.status == MissionStatus.READY:
            return mission
    for mission in bridge_services.list_missions():
        if mission.status == MissionStatus.READY:
            return mission
    return None


def run_cycle() -> dict[str, object]:
    """Run exactly one scan-and-assign cycle and report the outcome."""
    mission = _find_next_ready_mission()
    if mission is None:
        return {"assigned": False, "reason": "no_ready_mission"}

    bridge_services.record_event(
        mission.id, "coo_scan_started", "COO escaneo la cola en busca de una mision READY.", AUTHOR
    )

    builder = dispatcher.select_available_builder()
    if builder is None:
        bridge_services.record_event(
            mission.id, "coo_assignment_failed", "No hay Builders disponibles en el departamento.", AUTHOR
        )
        return {"assigned": False, "reason": "no_builder_available", "mission_id": mission.id}

    bridge_services.record_event(
        mission.id, "coo_builder_available", f"Builder disponible: {builder.id}.", AUTHOR
    )

    dispatcher.assign(mission, builder, author=AUTHOR)

    bridge_services.record_event(mission.id, "coo_scan_completed", "Ciclo del COO completado.", AUTHOR)

    return {"assigned": True, "mission_id": mission.id, "builder_id": builder.id}
