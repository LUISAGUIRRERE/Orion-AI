"""orion.runtime's own persistent Mission Queue: a durable ledger of
where each mission is in the Runtime's scheduling lifecycle
(QueueItemStatus), layered on top of -- never replacing -- the Mission
Framework's own queue (orion.bridge.storage's queue file /
orion.bridge.services.get_queue()), which
orion.agents.builder.agent.process_next() still drives completely
unchanged (see worker.py). This queue survives restarts because it is
plain YAML on disk, read fresh on every call, exactly like every other
*.yaml file in this codebase.
"""

from __future__ import annotations

from datetime import datetime, timezone

from orion.runtime import storage
from orion.runtime.models import QueueItem, QueueItemStatus


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def enqueue(mission_id: str) -> QueueItem:
    """Idempotent: enqueueing a mission_id that already has an entry
    returns the existing entry unchanged, rather than resetting its
    status/timestamps -- a Worker that calls this defensively (see
    worker.py) must never accidentally un-cancel or un-complete a
    mission."""
    item = storage.load_item(mission_id)
    if item is not None:
        return item
    item = QueueItem(mission_id=mission_id, status=QueueItemStatus.QUEUED, enqueued_at=_now_iso())
    storage.save_item(item)
    return item


def mark_running(mission_id: str, worker_id: str) -> QueueItem | None:
    item = storage.load_item(mission_id)
    if item is None:
        return None
    item.status = QueueItemStatus.RUNNING
    item.worker_id = worker_id
    item.started_at = _now_iso()
    storage.save_item(item)
    return item


def mark_waiting(mission_id: str) -> QueueItem | None:
    item = storage.load_item(mission_id)
    if item is None:
        return None
    item.status = QueueItemStatus.WAITING
    storage.save_item(item)
    return item


def mark_completed(mission_id: str) -> QueueItem | None:
    item = storage.load_item(mission_id)
    if item is None:
        return None
    item.status = QueueItemStatus.COMPLETED
    item.finished_at = _now_iso()
    storage.save_item(item)
    return item


def mark_failed(mission_id: str, error: str) -> QueueItem | None:
    item = storage.load_item(mission_id)
    if item is None:
        return None
    item.status = QueueItemStatus.FAILED
    item.finished_at = _now_iso()
    item.error = error
    storage.save_item(item)
    return item


def mark_cancelled(mission_id: str) -> QueueItem | None:
    item = storage.load_item(mission_id)
    if item is None:
        return None
    item.status = QueueItemStatus.CANCELLED
    item.finished_at = _now_iso()
    storage.save_item(item)
    return item


def request_cancel(mission_id: str) -> QueueItem | None:
    """Marks intent only. A QUEUED mission is skipped by the next
    Worker that would have claimed it (see worker.py); a RUNNING
    mission's real cancellation still requires calling the live
    ProviderAdapter's own cancel() -- see orion.runtime.services.cancel_mission,
    which does both."""
    item = storage.load_item(mission_id)
    if item is None:
        return None
    item.cancel_requested = True
    storage.save_item(item)
    return item


def get_item(mission_id: str) -> QueueItem | None:
    return storage.load_item(mission_id)


def list_items() -> list[QueueItem]:
    return storage.list_items()


def depth_by_status() -> dict[str, int]:
    counts: dict[str, int] = {status.value: 0 for status in QueueItemStatus}
    for item in list_items():
        counts[item.status.value] = counts.get(item.status.value, 0) + 1
    return counts
