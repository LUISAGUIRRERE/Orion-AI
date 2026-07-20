"""COO Metrics — recalculated from the Mission Framework and the Builder
Department on every call. Nothing here is cached or persisted
separately; recomputing on demand is what keeps a single source of
truth for mission and builder state.
"""

from __future__ import annotations

from datetime import datetime, timezone

from orion.agents.coo import dispatcher
from orion.bridge import services as bridge_services
from orion.bridge.models import MissionStatus


def _parse(timestamp: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp, or return None if absent."""
    return datetime.fromisoformat(timestamp) if timestamp else None


def compute() -> dict[str, object]:
    """Compute every COO metric fresh from current data."""
    missions = bridge_services.list_missions()
    department = dispatcher.list_department()
    queue = bridge_services.get_queue()

    counts = {status.value: 0 for status in MissionStatus}
    for mission in missions:
        counts[mission.status.value] += 1

    today = datetime.now(timezone.utc).date().isoformat()
    done_today = sum(
        1 for m in missions if m.status == MissionStatus.DONE and (m.finished_at or "").startswith(today)
    )
    failed_today = sum(
        1 for m in missions if m.status == MissionStatus.FAILED and (m.updated_at or "").startswith(today)
    )

    available = sum(1 for b in department if b.available)
    busy = len(department) - available

    exec_durations: list[float] = []
    wait_durations: list[float] = []
    for m in missions:
        created, started, finished = _parse(m.created_at), _parse(m.started_at), _parse(m.finished_at)
        if created and started:
            wait_durations.append((started - created).total_seconds())
        if started and finished:
            exec_durations.append((finished - started).total_seconds())

    avg_exec = round(sum(exec_durations) / len(exec_durations), 2) if exec_durations else 0.0
    avg_wait = round(sum(wait_durations) / len(wait_durations), 2) if wait_durations else 0.0

    return {
        "builders_available": available,
        "builders_busy": busy,
        "missions_total": len(missions),
        "missions_ready": counts[MissionStatus.READY.value],
        "missions_running": counts[MissionStatus.RUNNING.value],
        "missions_waiting": counts[MissionStatus.WAITING.value],
        "missions_blocked": counts[MissionStatus.BLOCKED.value],
        "missions_review": counts[MissionStatus.REVIEW.value],
        "missions_done": counts[MissionStatus.DONE.value],
        "missions_done_today": done_today,
        "missions_failed_today": failed_today,
        "average_execution_seconds": avg_exec,
        "average_wait_seconds": avg_wait,
        "queue_size": len(queue),
    }
