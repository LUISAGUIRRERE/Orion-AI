"""Runtime Worker: claims the next READY mission and runs it end to
end by delegating entirely to orion.agents.builder.agent -- the exact
same Mission -> Prompt Composer -> Executor -> Provider -> Validation
-> Git -> Experience -> Status Update chain BETA 001 through BETA 006
already built and tested. This module adds nothing new to that chain;
it only wraps it with orion.runtime's own QueueItem bookkeeping,
cooperative cancellation, and live event emission so the Runtime's
API/SSE layer can observe it.
"""

from __future__ import annotations

import threading

from orion.agents.builder import agent as builder_agent
from orion.bridge import services as bridge_services
from orion.bridge.models import MissionStatus
from orion.runtime import events as runtime_events
from orion.runtime import queue as runtime_queue

AUTHOR = "RuntimeWorker"


class Worker:
    """One polling loop, meant to run in its own thread (see
    scheduler.py). Multiple Workers are safe to run concurrently:
    claiming (finding the next READY mission and transitioning it to
    RUNNING) happens entirely inside
    orion.agents.builder.agent.claim_next_ready_mission(), which is
    the single, lock-protected scan-and-claim implementation --
    Worker.run_once() below never re-implements that scan itself.

    BETA 007 correctness note, found and fixed via
    tests/test_runtime.py::SchedulerTests::
    test_concurrent_workers_each_process_a_distinct_mission_exactly_once:
    an earlier version of this class had its own separate
    "_next_ready_mission_id()" scan, guarded by a *different* lock
    than orion.agents.builder.agent's own claim lock. Two locks that
    don't exclude each other meant two Worker threads could still both
    decide "I'm claiming mission X" before either had actually
    transitioned it away from READY, corrupting that mission's
    events.yaml (concurrent unlocked writes to the same file). Calling
    claim_next_ready_mission() directly -- rather than scanning here
    and calling process_next() separately -- removes the second scan
    entirely, so there is exactly one place a mission can be claimed.
    """

    def __init__(self, worker_id: str, poll_interval_seconds: float = 1.0) -> None:
        self.worker_id = worker_id
        self.poll_interval_seconds = poll_interval_seconds
        self.busy = False
        self.current_mission_id: str | None = None
        self.processed_count = 0
        self.failed_count = 0
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run_forever(self) -> None:
        while not self._stop_event.is_set():
            processed = self.run_once()
            if not processed:
                self._stop_event.wait(self.poll_interval_seconds)

    def run_once(self) -> bool:
        """Process at most one READY mission. Returns True if one was
        found this cycle (processed or skipped-as-cancelled), False if
        nothing was READY."""
        mission = builder_agent.claim_next_ready_mission()
        if mission is None:
            return False

        mission_id = mission.id
        item = runtime_queue.enqueue(mission_id)
        runtime_queue.mark_running(mission_id, self.worker_id)
        self.busy = True
        self.current_mission_id = mission_id
        runtime_events.emit(
            mission_id, "worker_claimed", f"Worker '{self.worker_id}' tomo la mision.", AUTHOR
        )

        if item.cancel_requested:
            # Cancelled while still QUEUED, before this Worker's claim
            # above actually ran -- the Mission is already RUNNING for
            # real at this point (claim_next_ready_mission() always
            # transitions it), so bring it to a clean terminal state
            # here instead of running work nobody wants anymore.
            bridge_services.update_status(mission_id, MissionStatus.FAILED, author=AUTHOR)
            runtime_queue.mark_cancelled(mission_id)
            runtime_events.emit(
                mission_id, "worker_cancelled", "Mision cancelada antes de ser tomada por un Worker.", AUTHOR
            )
            self.busy = False
            self.current_mission_id = None
            return True

        try:
            result_mission = builder_agent.run_claimed_mission(mission)
        finally:
            self.busy = False
            self.current_mission_id = None

        if result_mission is None:  # pragma: no cover - defensive only
            return True

        current_item = runtime_queue.get_item(mission_id)
        cancel_was_requested = bool(current_item and current_item.cancel_requested)

        if cancel_was_requested:
            runtime_queue.mark_cancelled(mission_id)
            runtime_events.emit(mission_id, "worker_cancelled", "Mision cancelada durante su ejecucion.", AUTHOR)
        elif result_mission.status in (MissionStatus.REVIEW, MissionStatus.DONE):
            # RELEASE 0.9.0-beta FASE 2 root-cause fix: processed_count
            # must be incremented BEFORE the queue item's on-disk status
            # becomes COMPLETED, never after. A caller (see
            # tests/test_runtime.py::SchedulerTests::
            # test_concurrent_workers_each_process_a_distinct_mission_exactly_once)
            # legitimately treats "every mission's on-disk status is
            # COMPLETED" as the signal that it is now safe to read
            # processed_count -- but this method runs entirely on this
            # Worker's own thread with no lock or barrier between the
            # two statements, so incrementing the counter *after*
            # persisting COMPLETED left a real, provable window (a
            # thread can be preempted for arbitrarily long between the
            # two lines, and mark_completed() itself does real file
            # I/O, widening it further) in which an external reader
            # could observe the disk already showing COMPLETED while
            # processed_count had not been incremented yet -- an
            # undercount, not a flaky assertion. Swapping the order
            # establishes a true happens-before within this thread's
            # own program order: by the time any reader can observe
            # COMPLETED on disk, processed_count is already correct.
            self.processed_count += 1
            runtime_queue.mark_completed(mission_id)
            runtime_events.emit(mission_id, "worker_completed", "Worker completo la mision.", AUTHOR)
        elif result_mission.status == MissionStatus.WAITING:
            # BETA 010 (Governance): orion.agents.builder.agent's
            # Governance hook parks a mission here -- a real, deliberate
            # pause for a hard_stop Decision (Architecture / Breaking
            # Change / CRITICAL risk), never a failure. QueueItemStatus.WAITING
            # already existed (orion.runtime.queue.mark_waiting), reserved
            # for exactly this and never used until now -- this is not a
            # new queue state, just its first real caller.
            runtime_queue.mark_waiting(mission_id)
            runtime_events.emit(
                mission_id, "worker_waiting_for_governance",
                "Worker dejo la mision en espera: Governance requiere una decision humana o aprobacion real.",
                AUTHOR,
            )
        else:
            # Same root-cause fix as processed_count above, mirrored
            # for the failure path: increment failed_count before the
            # on-disk status becomes FAILED, not after.
            self.failed_count += 1
            runtime_queue.mark_failed(
                mission_id, f"Mision termino con estado {result_mission.status.value}."
            )
            runtime_events.emit(
                mission_id, "worker_failed", f"Mision termino en estado {result_mission.status.value}.", AUTHOR
            )

        return True
