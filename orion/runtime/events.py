"""Runtime event bus: real-time fan-out for Server-Sent Events,
layered on top of the Mission Framework's own persisted event log
(orion.bridge.services.record_event) as the single source of truth.

emit() always writes to that persisted log first -- this module adds
nothing new to disk, it only distributes what is already being
recorded to any currently-connected SSE subscriber. If nobody is
listening right now, nothing is lost: a client that connects later
still sees full history via GET /missions/{id} or events.yaml
directly, exactly like every mission's timeline always has.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass

from orion.bridge import services as bridge_services


@dataclass
class RuntimeEvent:
    mission_id: str
    type: str
    message: str
    source: str
    timestamp: str


class EventBus:
    """Thread-safe pub/sub. One queue.Queue per subscriber (typically
    one per open SSE connection); publish() never blocks on a slow
    subscriber -- each subscriber's queue is unbounded, matching the
    already-small, already-bounded volume of Mission Framework events
    (nothing here is a firehose)."""

    def __init__(self) -> None:
        self._subscribers: list[queue.Queue] = []
        self._lock = threading.Lock()

    def subscribe(self) -> "queue.Queue[RuntimeEvent]":
        q: "queue.Queue[RuntimeEvent]" = queue.Queue()
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: "queue.Queue[RuntimeEvent]") -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def publish(self, event: RuntimeEvent) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            q.put(event)

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)


BUS = EventBus()


def emit(mission_id: str, event_type: str, message: str, source: str) -> RuntimeEvent:
    """Record + publish, in that order, always. See module docstring
    for why the persisted record always comes first."""
    event = bridge_services.record_event(mission_id, event_type, message, source)
    runtime_event = RuntimeEvent(
        mission_id=mission_id,
        type=event_type,
        message=message,
        source=source,
        timestamp=event.timestamp,
    )
    BUS.publish(runtime_event)
    return runtime_event
