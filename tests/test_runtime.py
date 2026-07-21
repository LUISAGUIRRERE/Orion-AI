"""Tests for orion.runtime (BETA 007).

Standard library unittest only (no pytest, no new dependency), same
convention as every other test module in this repo. Covers exactly
what this Sprint's brief lists: Runtime start, Runtime stop, Queue,
Worker, API, Health, Cancel, Eventos, SSE, Concurrencia, Recovery.

Scope boundary, deliberately: these tests exercise orion.runtime's OWN
orchestration logic (queue bookkeeping, cancellation semantics, worker
concurrency, event fan-out, API routes, health aggregation, state
persistence/recovery). The real, potentially-slow half of a mission --
Prompt Composer -> Executor -> Provider -> Validation -> Git ->
Experience, which orion.agents.builder.agent.run_claimed_mission()
drives -- is faked here (see _fake_run_claimed_mission below), the
same way tests/test_executor.py already fakes ProviderAdapter.execute()
rather than invoking a real git-backed pipeline. The *claiming* half
(orion.agents.builder.agent.claim_next_ready_mission(), the exact
function this Sprint's concurrency fix lives in) is deliberately left
real and unpatched in every test below: that is the one piece of logic
this Sprint's own concurrency bug lived in, so faking it away would
hide the very thing these tests exist to prove.

Run with:

    python3 -m unittest tests.test_runtime -v
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from orion.bridge import services as bridge_services
from orion.bridge import storage as bridge_storage
from orion.bridge.models import MissionStatus
from orion.executor.adapters.base import ProviderAdapter
from orion.executor.models import AdapterHealth
from orion.executor.registry import register_adapter
from orion.runtime import api as runtime_api
from orion.runtime import events as runtime_events
from orion.runtime import queue as runtime_queue
from orion.runtime import services as runtime_services
from orion.runtime import storage as runtime_storage
from orion.runtime import worker as runtime_worker
from orion.runtime.models import MissionAskRequest, QueueItemStatus
from orion.runtime.scheduler import Scheduler
from orion.runtime.worker import Worker


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Test-double ProviderAdapters, registered once at import time -- same
# permissive-registry convention tests/test_executor.py already uses.
# ---------------------------------------------------------------------------


class _AlwaysHealthyAdapter(ProviderAdapter):
    name = "runtime_test_healthy"

    def execute(self, package):  # pragma: no cover - not exercised here
        raise NotImplementedError

    def health_check(self) -> AdapterHealth:
        return AdapterHealth(healthy=True, message="ok", checked_at=_now())

    def cancel(self, mission_id: str) -> bool:
        return True


class _AlwaysUnhealthyAdapter(ProviderAdapter):
    name = "runtime_test_unhealthy"

    def execute(self, package):  # pragma: no cover - not exercised here
        raise NotImplementedError

    def health_check(self) -> AdapterHealth:
        return AdapterHealth(healthy=False, message="deliberately unhealthy", checked_at=_now())

    def cancel(self, mission_id: str) -> bool:
        return False


register_adapter(_AlwaysHealthyAdapter())
register_adapter(_AlwaysUnhealthyAdapter())


def _fake_run_claimed_mission(delay: float = 0.0, final_status: MissionStatus = MissionStatus.REVIEW):
    """Stand-in for orion.agents.builder.agent.run_claimed_mission():
    given an already-claimed (already RUNNING) Mission, optionally
    sleeps to simulate real work, then transitions it to
    ``final_status`` and returns the updated Mission. The claim itself
    (finding the mission, transitioning it to RUNNING) is never faked
    anywhere in this file -- see module docstring."""

    def _run(mission):
        if delay:
            time.sleep(delay)
        return bridge_services.update_status(mission.id, final_status, author="FakeBuilder")

    return _run


def _hard_stop(scheduler: Scheduler, timeout: float = 25.0) -> None:
    """scheduler.stop()'s own thread.join(timeout=...) does not raise
    or even report if a Worker thread fails to finish within the
    timeout -- it just returns, silently. Under real CPU contention
    (observed running this whole suite back to back many times) a
    single stop(timeout=2.0) inside a test's own cleanup occasionally
    was not quite enough, leaving one Worker thread alive just long
    enough to steal the *next* test's freshly-created mission before
    that next test's own run_once() call ever got to it -- a genuine,
    reproduced flake, not a corruption bug (the earlier atomic-write
    fixes in orion.runtime.storage/orion.bridge.storage/
    orion.agents.builder.agent already closed the corruption class of
    bug this same investigation surfaced). Rather than just hoping a
    longer fixed timeout is always enough, this retries stop() in a
    loop and fails loudly with a clear message if a Worker thread
    truly never terminates, instead of letting it silently corrupt
    some unrelated, later test.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        scheduler.stop(timeout=1.0)
        if not scheduler.is_running():
            return
    if scheduler.is_running():
        raise AssertionError(
            f"Scheduler still has live Worker thread(s) after {timeout}s -- "
            "a real thread-shutdown bug, not the flaky-timing issue this "
            "helper exists to absorb."
        )


class IsolatedRuntimeTestCase(unittest.TestCase):
    """Redirects the Mission Framework's storage and orion.runtime's
    own storage at a temporary directory for the duration of each
    test, restoring the real paths in tearDown. Never touches
    Orion-AI's real workspace/. Also resets orion.runtime.services'
    module-level Scheduler singleton so no test leaks a running
    thread pool into the next one, and restores
    orion.agents.builder.agent.run_claimed_mission whenever a test
    patches it.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(self._tmp.name)

        self._orig_missions_dir = bridge_storage.MISSIONS_DIR
        self._orig_queue_file = bridge_storage.QUEUE_FILE
        bridge_storage.MISSIONS_DIR = tmp_path / "missions"
        bridge_storage.QUEUE_FILE = bridge_storage.MISSIONS_DIR / "_queue.yaml"
        bridge_storage.ensure_bridge_storage()

        self._orig_runtime_dir = runtime_storage.RUNTIME_DIR
        self._orig_runtime_queue_file = runtime_storage.QUEUE_FILE
        self._orig_runtime_state_file = runtime_storage.STATE_FILE
        runtime_storage.RUNTIME_DIR = tmp_path / "runtime"
        runtime_storage.QUEUE_FILE = runtime_storage.RUNTIME_DIR / "queue.yaml"
        runtime_storage.STATE_FILE = runtime_storage.RUNTIME_DIR / "runtime_state.yaml"
        runtime_storage.ensure_runtime_storage()

        runtime_services._scheduler = None

        self._orig_run_claimed_mission = runtime_worker.builder_agent.run_claimed_mission

    def tearDown(self) -> None:
        if runtime_services._scheduler is not None:
            _hard_stop(runtime_services._scheduler)
            runtime_services._scheduler = None

        runtime_worker.builder_agent.run_claimed_mission = self._orig_run_claimed_mission

        bridge_storage.MISSIONS_DIR = self._orig_missions_dir
        bridge_storage.QUEUE_FILE = self._orig_queue_file
        runtime_storage.RUNTIME_DIR = self._orig_runtime_dir
        runtime_storage.QUEUE_FILE = self._orig_runtime_queue_file
        runtime_storage.STATE_FILE = self._orig_runtime_state_file
        self._tmp.cleanup()

    def _make_ready_mission(self, title: str = "Runtime test mission") -> str:
        response = runtime_services.ask(MissionAskRequest(title=title))
        return response.mission_id


# ---------------------------------------------------------------------------
# Queue / storage
# ---------------------------------------------------------------------------


class QueueTests(IsolatedRuntimeTestCase):
    def test_enqueue_is_idempotent(self) -> None:
        item1 = runtime_queue.enqueue("MISSION-A")
        runtime_queue.mark_running("MISSION-A", "worker-1")
        item2 = runtime_queue.enqueue("MISSION-A")
        self.assertEqual(item2.status, QueueItemStatus.RUNNING)
        self.assertEqual(item2.worker_id, "worker-1")
        self.assertEqual(item1.mission_id, item2.mission_id)

    def test_mark_transitions_persist(self) -> None:
        runtime_queue.enqueue("MISSION-B")
        runtime_queue.mark_running("MISSION-B", "worker-2")
        loaded = runtime_queue.get_item("MISSION-B")
        self.assertEqual(loaded.status, QueueItemStatus.RUNNING)
        self.assertEqual(loaded.worker_id, "worker-2")

        runtime_queue.mark_completed("MISSION-B")
        self.assertEqual(runtime_queue.get_item("MISSION-B").status, QueueItemStatus.COMPLETED)
        self.assertIsNotNone(runtime_queue.get_item("MISSION-B").finished_at)

    def test_mark_failed_records_error(self) -> None:
        runtime_queue.enqueue("MISSION-C")
        runtime_queue.mark_failed("MISSION-C", "boom")
        item = runtime_queue.get_item("MISSION-C")
        self.assertEqual(item.status, QueueItemStatus.FAILED)
        self.assertEqual(item.error, "boom")

    def test_request_cancel_sets_flag_without_changing_status(self) -> None:
        runtime_queue.enqueue("MISSION-D")
        runtime_queue.request_cancel("MISSION-D")
        item = runtime_queue.get_item("MISSION-D")
        self.assertTrue(item.cancel_requested)
        self.assertEqual(item.status, QueueItemStatus.QUEUED)

    def test_operations_on_unknown_mission_return_none(self) -> None:
        self.assertIsNone(runtime_queue.mark_running("MISSING", "w"))
        self.assertIsNone(runtime_queue.mark_completed("MISSING"))
        self.assertIsNone(runtime_queue.mark_failed("MISSING", "x"))
        self.assertIsNone(runtime_queue.mark_cancelled("MISSING"))
        self.assertIsNone(runtime_queue.request_cancel("MISSING"))

    def test_depth_by_status(self) -> None:
        runtime_queue.enqueue("MISSION-E")
        runtime_queue.enqueue("MISSION-F")
        runtime_queue.mark_completed("MISSION-F")
        depth = runtime_queue.depth_by_status()
        self.assertEqual(depth["QUEUED"], 1)
        self.assertEqual(depth["COMPLETED"], 1)
        self.assertEqual(sum(depth.values()), 2)

    def test_queue_survives_a_fresh_read_simulating_restart(self) -> None:
        runtime_queue.enqueue("MISSION-G")
        runtime_queue.mark_running("MISSION-G", "worker-1")

        reloaded = runtime_queue.get_item("MISSION-G")
        self.assertEqual(reloaded.status, QueueItemStatus.RUNNING)
        self.assertEqual(reloaded.worker_id, "worker-1")


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


class WorkerTests(IsolatedRuntimeTestCase):
    def test_run_once_returns_false_when_nothing_ready(self) -> None:
        w = Worker(worker_id="worker-1")
        self.assertFalse(w.run_once())

    def test_run_once_completes_a_ready_mission(self) -> None:
        mission_id = self._make_ready_mission()
        runtime_worker.builder_agent.run_claimed_mission = _fake_run_claimed_mission(final_status=MissionStatus.REVIEW)

        w = Worker(worker_id="worker-1")
        processed = w.run_once()

        self.assertTrue(processed)
        self.assertEqual(w.processed_count, 1)
        self.assertEqual(w.failed_count, 0)
        item = runtime_queue.get_item(mission_id)
        self.assertEqual(item.status, QueueItemStatus.COMPLETED)
        event_types = [e.type for e in bridge_services.get_events(mission_id)]
        self.assertIn("worker_claimed", event_types)
        self.assertIn("worker_completed", event_types)

    def test_run_once_marks_failed_mission_as_failed(self) -> None:
        mission_id = self._make_ready_mission()
        runtime_worker.builder_agent.run_claimed_mission = _fake_run_claimed_mission(final_status=MissionStatus.FAILED)

        w = Worker(worker_id="worker-1")
        w.run_once()

        self.assertEqual(w.failed_count, 1)
        item = runtime_queue.get_item(mission_id)
        self.assertEqual(item.status, QueueItemStatus.FAILED)
        self.assertIn("worker_failed", [e.type for e in bridge_services.get_events(mission_id)])

    def test_run_once_skips_mission_cancelled_before_claim(self) -> None:
        mission_id = self._make_ready_mission()
        # Pre-mark cancellation intent before any Worker ever claims it.
        # claim_next_ready_mission() is real here: the mission really
        # does get transitioned to RUNNING, exactly like a genuine
        # Worker claim would -- run_once() must still bring it to a
        # clean terminal state instead of running it.
        runtime_queue.request_cancel(mission_id)

        w = Worker(worker_id="worker-1")
        processed = w.run_once()

        self.assertTrue(processed)
        item = runtime_queue.get_item(mission_id)
        self.assertEqual(item.status, QueueItemStatus.CANCELLED)
        mission = bridge_services.get_mission(mission_id)
        self.assertEqual(mission.status, MissionStatus.FAILED)
        self.assertIn("worker_cancelled", [e.type for e in bridge_services.get_events(mission_id)])

    def test_run_once_marks_cancelled_when_cancelled_during_run(self) -> None:
        mission_id = self._make_ready_mission()

        def _run_claimed_mission_that_gets_cancelled_midflight(mission):
            runtime_queue.request_cancel(mission.id)
            return bridge_services.update_status(mission.id, MissionStatus.REVIEW, author="FakeBuilder")

        runtime_worker.builder_agent.run_claimed_mission = _run_claimed_mission_that_gets_cancelled_midflight

        w = Worker(worker_id="worker-1")
        w.run_once()

        item = runtime_queue.get_item(mission_id)
        self.assertEqual(item.status, QueueItemStatus.CANCELLED)
        self.assertIn("worker_cancelled", [e.type for e in bridge_services.get_events(mission_id)])


# ---------------------------------------------------------------------------
# Scheduler / concurrency
# ---------------------------------------------------------------------------


class SchedulerTests(IsolatedRuntimeTestCase):
    def test_start_is_idempotent_and_stop_joins_threads(self) -> None:
        scheduler = Scheduler(worker_count=2, poll_interval_seconds=0.05)
        scheduler.start()
        first_threads = list(scheduler._threads)
        scheduler.start()  # no-op, must not double the pool
        self.assertEqual(scheduler._threads, first_threads)
        self.assertTrue(scheduler.is_running())

        _hard_stop(scheduler)
        self.assertFalse(scheduler.is_running())
        self.assertEqual(scheduler.workers, [])

    def test_worker_statuses_reports_each_worker(self) -> None:
        scheduler = Scheduler(worker_count=3, poll_interval_seconds=0.05)
        scheduler.start()
        try:
            statuses = scheduler.worker_statuses()
            self.assertEqual(len(statuses), 3)
            self.assertEqual({s.worker_id for s in statuses}, {"worker-1", "worker-2", "worker-3"})
        finally:
            _hard_stop(scheduler)

    def test_concurrent_workers_each_process_a_distinct_mission_exactly_once(self) -> None:
        """The direct regression test for this Sprint's concurrency
        race: claim_next_ready_mission() runs real and unpatched here
        -- only the slow half (run_claimed_mission) is faked -- so this
        proves the actual fix in orion.agents.builder.agent /
        orion.runtime.worker, not a simplified stand-in for it."""
        mission_ids = [self._make_ready_mission(f"Concurrent mission {i}") for i in range(4)]
        runtime_worker.builder_agent.run_claimed_mission = _fake_run_claimed_mission(
            delay=0.05, final_status=MissionStatus.REVIEW
        )

        scheduler = Scheduler(worker_count=3, poll_interval_seconds=0.02)
        scheduler.start()
        try:
            # Generous deadline: this only needs to be "clearly bounded,
            # never truly infinite", not tight. Sandbox CPU scheduling
            # can occasionally stall a thread for multiple seconds even
            # for tiny critical sections (observed directly while
            # hardening this test) -- 4 missions x a 0.05s fake delay
            # across 3 workers should finish in well under a second on
            # an unloaded machine, so 20s is slack for contention, not
            # a tolerance for a real hang.
            deadline = time.monotonic() + 20.0
            while time.monotonic() < deadline:
                depth = runtime_queue.depth_by_status()
                if depth.get("COMPLETED", 0) >= len(mission_ids):
                    break
                time.sleep(0.05)
            # Snapshot each Worker's processed_count *before* stop(),
            # which clears scheduler.workers -- reading it afterwards
            # would always see an empty list regardless of how many
            # missions were actually processed.
            total_processed = sum(w.processed_count for w in scheduler.workers)
        finally:
            _hard_stop(scheduler)

        depth = runtime_queue.depth_by_status()
        self.assertEqual(depth.get("COMPLETED", 0), len(mission_ids))
        self.assertEqual(depth.get("QUEUED", 0), 0)
        self.assertEqual(depth.get("RUNNING", 0), 0)
        for mission_id in mission_ids:
            self.assertEqual(runtime_queue.get_item(mission_id).status, QueueItemStatus.COMPLETED)
            # Exactly one worker_claimed event per mission -- the
            # symptom of the original bug was a duplicate here.
            claimed_events = [
                e for e in bridge_services.get_events(mission_id) if e.type == "worker_claimed"
            ]
            self.assertEqual(len(claimed_events), 1)
        self.assertEqual(total_processed, len(mission_ids))


# ---------------------------------------------------------------------------
# Events / SSE
# ---------------------------------------------------------------------------


class EventBusTests(IsolatedRuntimeTestCase):
    def test_subscribe_publish_unsubscribe(self) -> None:
        bus = runtime_events.EventBus()
        q = bus.subscribe()
        self.assertEqual(bus.subscriber_count(), 1)

        event = runtime_events.RuntimeEvent(
            mission_id="MISSION-X", type="t", message="m", source="s", timestamp=_now()
        )
        bus.publish(event)
        received = q.get_nowait()
        self.assertEqual(received.mission_id, "MISSION-X")

        bus.unsubscribe(q)
        self.assertEqual(bus.subscriber_count(), 0)

    def test_emit_records_and_publishes(self) -> None:
        mission_id = self._make_ready_mission()
        q = runtime_events.BUS.subscribe()
        try:
            runtime_events.emit(mission_id, "custom_event", "hola", "Test")
            persisted_types = [e.type for e in bridge_services.get_events(mission_id)]
            self.assertIn("custom_event", persisted_types)

            received = q.get(timeout=2.0)
            self.assertEqual(received.mission_id, mission_id)
            self.assertEqual(received.type, "custom_event")
        finally:
            runtime_events.BUS.unsubscribe(q)


class SSEEndpointTests(IsolatedRuntimeTestCase):
    def test_sse_stream_delivers_a_live_event(self) -> None:
        mission_id = self._make_ready_mission()

        async def scenario():
            response = await runtime_api.sse_events_endpoint()
            agen = response.body_iterator
            task = asyncio.ensure_future(agen.__anext__())
            await asyncio.sleep(0.1)  # let event_stream() reach the blocking subscriber.get()
            runtime_events.emit(mission_id, "sse_test_event", "hola SSE", "Test")
            chunk = await asyncio.wait_for(task, timeout=5.0)
            await agen.aclose()
            return chunk

        chunk = asyncio.run(scenario())
        self.assertIn("sse_test_event", chunk)
        payload = json.loads(chunk[len("data: "):].strip())
        self.assertEqual(payload["mission_id"], mission_id)
        self.assertEqual(payload["type"], "sse_test_event")


# ---------------------------------------------------------------------------
# Services: start/stop, ask, cancel, health, recovery
# ---------------------------------------------------------------------------


class RuntimeStartStopTests(IsolatedRuntimeTestCase):
    def test_start_runtime_persists_state_and_is_idempotent(self) -> None:
        from orion.runtime.config import RuntimeConfig

        config = RuntimeConfig(provider="runtime_test_healthy", workers=2, port=8099)

        state1 = runtime_services.start_runtime(config)
        self.assertTrue(state1.running)
        self.assertEqual(state1.workers, 2)
        scheduler_after_first_start = runtime_services.get_scheduler()

        state2 = runtime_services.start_runtime(config)
        self.assertIs(runtime_services.get_scheduler(), scheduler_after_first_start)
        self.assertTrue(state2.running)

        loaded = runtime_storage.load_state()
        self.assertTrue(loaded.running)
        self.assertEqual(loaded.workers, 2)

    def test_stop_runtime_marks_state_not_running(self) -> None:
        from orion.runtime.config import RuntimeConfig

        runtime_services.start_runtime(RuntimeConfig(provider="runtime_test_healthy", workers=1))
        state = runtime_services.stop_runtime()
        self.assertFalse(state.running)
        self.assertFalse(runtime_storage.load_state().running)
        self.assertFalse(runtime_services.get_scheduler().is_running())

    def test_recovery_state_survives_simulated_restart(self) -> None:
        """No new process is actually spawned here (the test harness
        cannot do that), but the persisted RuntimeState file is the
        exact mechanism a real `orion runtime start` reads/writes, so
        proving a fresh read sees a previous write is the faithful
        in-process equivalent of 'sobrevive reinicios'."""
        from orion.runtime.config import RuntimeConfig

        runtime_services.start_runtime(RuntimeConfig(provider="runtime_test_healthy", workers=1, port=8123))

        # Simulate the old process disappearing without a clean
        # shutdown (e.g. a crash) -- only the in-memory singleton is
        # dropped, the persisted file is untouched.
        runtime_services._scheduler = None

        recovered_state = runtime_services.get_runtime_state()
        self.assertTrue(recovered_state.running)
        self.assertEqual(recovered_state.port, 8123)


class AskAndCancelTests(IsolatedRuntimeTestCase):
    def test_ask_creates_a_ready_mission_and_enqueues_it(self) -> None:
        response = runtime_services.ask(MissionAskRequest(title="Crear hello-orion.txt", project_id="p1"))
        self.assertEqual(response.status, MissionStatus.READY.value)
        self.assertEqual(response.queue_status, QueueItemStatus.QUEUED)

        mission = bridge_services.get_mission(response.mission_id)
        self.assertEqual(mission.status, MissionStatus.READY)
        self.assertEqual(mission.mission_type, "executor")

        item = runtime_queue.get_item(response.mission_id)
        self.assertIsNotNone(item)
        self.assertEqual(item.status, QueueItemStatus.QUEUED)

        event_types = [e.type for e in bridge_services.get_events(response.mission_id)]
        self.assertIn("mission_enqueued", event_types)

    def test_cancel_mission_marks_intent_and_calls_adapter_cancel(self) -> None:
        import os

        mission_id = self._make_ready_mission()
        old_provider = os.environ.get("ORION_PROVIDER")
        os.environ["ORION_PROVIDER"] = "runtime_test_healthy"
        try:
            accepted = runtime_services.cancel_mission(mission_id)
        finally:
            if old_provider is None:
                os.environ.pop("ORION_PROVIDER", None)
            else:
                os.environ["ORION_PROVIDER"] = old_provider

        self.assertTrue(accepted)
        item = runtime_queue.get_item(mission_id)
        self.assertTrue(item.cancel_requested)
        event_types = [e.type for e in bridge_services.get_events(mission_id)]
        self.assertIn("mission_cancel_requested", event_types)
        self.assertIn("provider_cancel_sent", event_types)

    def test_cancel_mission_on_unknown_id_still_attempts_adapter_cancel(self) -> None:
        import os

        old_provider = os.environ.get("ORION_PROVIDER")
        os.environ["ORION_PROVIDER"] = "runtime_test_unhealthy"
        try:
            accepted = runtime_services.cancel_mission("MISSION-DOES-NOT-EXIST")
        finally:
            if old_provider is None:
                os.environ.pop("ORION_PROVIDER", None)
            else:
                os.environ["ORION_PROVIDER"] = old_provider

        self.assertFalse(accepted)


class HealthReportTests(IsolatedRuntimeTestCase):
    def test_health_report_true_when_every_subsystem_is_healthy(self) -> None:
        import os

        old_provider = os.environ.get("ORION_PROVIDER")
        os.environ["ORION_PROVIDER"] = "runtime_test_healthy"
        try:
            report = runtime_services.health_report()
        finally:
            if old_provider is None:
                os.environ.pop("ORION_PROVIDER", None)
            else:
                os.environ["ORION_PROVIDER"] = old_provider

        self.assertTrue(report.healthy)
        for key in ("runtime_test_healthy", "git", "workspace", "queue", "workers", "storage"):
            self.assertIn(key, report.checks)
            self.assertTrue(report.checks[key]["healthy"])

    def test_health_report_false_when_provider_is_unhealthy(self) -> None:
        import os

        old_provider = os.environ.get("ORION_PROVIDER")
        os.environ["ORION_PROVIDER"] = "runtime_test_unhealthy"
        try:
            report = runtime_services.health_report()
        finally:
            if old_provider is None:
                os.environ.pop("ORION_PROVIDER", None)
            else:
                os.environ["ORION_PROVIDER"] = old_provider

        self.assertFalse(report.healthy)
        self.assertFalse(report.checks["runtime_test_unhealthy"]["healthy"])

    def test_health_report_false_when_provider_name_is_unregistered(self) -> None:
        import os

        old_provider = os.environ.get("ORION_PROVIDER")
        os.environ["ORION_PROVIDER"] = "nonexistent_provider_xyz"
        try:
            report = runtime_services.health_report()
        finally:
            if old_provider is None:
                os.environ.pop("ORION_PROVIDER", None)
            else:
                os.environ["ORION_PROVIDER"] = old_provider

        self.assertFalse(report.healthy)
        self.assertFalse(report.checks["nonexistent_provider_xyz"]["healthy"])

    def test_health_report_regression_deterministic_local_has_health_check(self) -> None:
        """BETA 007 regression guard: DeterministicLocalAdapter used to
        not inherit ProviderAdapter at all, so calling .health_check()
        on it raised AttributeError the first time any generic caller
        (this function) invoked it. Proves the fix holds."""
        import os

        old_provider = os.environ.get("ORION_PROVIDER")
        os.environ["ORION_PROVIDER"] = "deterministic_local"
        try:
            report = runtime_services.health_report()
        finally:
            if old_provider is None:
                os.environ.pop("ORION_PROVIDER", None)
            else:
                os.environ["ORION_PROVIDER"] = old_provider

        self.assertIn("deterministic_local", report.checks)
        self.assertTrue(report.checks["deterministic_local"]["healthy"])


# ---------------------------------------------------------------------------
# API routes (functional, no TestClient -- httpx2 is not an installed
# dependency, so route coroutines are awaited directly via asyncio.run,
# same technique used to validate this Sprint's live smoke test).
# ---------------------------------------------------------------------------


class APIRouteTests(IsolatedRuntimeTestCase):
    def test_create_and_get_mission_roundtrip(self) -> None:
        async def scenario():
            created = await runtime_api.create_mission(MissionAskRequest(title="API test mission"))
            fetched = await runtime_api.get_mission_endpoint(created.mission_id)
            return created, fetched

        created, fetched = asyncio.run(scenario())
        self.assertEqual(fetched["mission"]["id"], created.mission_id)
        self.assertEqual(fetched["mission"]["status"], "READY")
        self.assertEqual(fetched["queue_item"]["status"], "QUEUED")

    def test_get_mission_endpoint_404_for_unknown_mission(self) -> None:
        from fastapi import HTTPException

        async def scenario():
            await runtime_api.get_mission_endpoint("MISSION-NOPE")

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(scenario())
        self.assertEqual(ctx.exception.status_code, 404)

    def test_list_missions_endpoint(self) -> None:
        async def scenario():
            await runtime_api.create_mission(MissionAskRequest(title="Mission one"))
            await runtime_api.create_mission(MissionAskRequest(title="Mission two"))
            return await runtime_api.list_missions_endpoint()

        missions = asyncio.run(scenario())
        self.assertEqual(len(missions), 2)

    def test_cancel_mission_endpoint(self) -> None:
        import os

        async def scenario():
            created = await runtime_api.create_mission(MissionAskRequest(title="Cancel me"))
            return created, await runtime_api.cancel_mission_endpoint(created.mission_id)

        old_provider = os.environ.get("ORION_PROVIDER")
        os.environ["ORION_PROVIDER"] = "runtime_test_healthy"
        try:
            created, result = asyncio.run(scenario())
        finally:
            if old_provider is None:
                os.environ.pop("ORION_PROVIDER", None)
            else:
                os.environ["ORION_PROVIDER"] = old_provider

        self.assertEqual(result["mission_id"], created.mission_id)
        self.assertTrue(result["cancel_requested"])

    def test_cancel_mission_endpoint_404_for_unknown_mission(self) -> None:
        from fastapi import HTTPException

        async def scenario():
            await runtime_api.cancel_mission_endpoint("MISSION-NOPE")

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(scenario())
        self.assertEqual(ctx.exception.status_code, 404)

    def test_health_endpoint(self) -> None:
        import os

        old_provider = os.environ.get("ORION_PROVIDER")
        os.environ["ORION_PROVIDER"] = "runtime_test_healthy"
        try:
            report = asyncio.run(runtime_api.health_endpoint())
        finally:
            if old_provider is None:
                os.environ.pop("ORION_PROVIDER", None)
            else:
                os.environ["ORION_PROVIDER"] = old_provider

        self.assertTrue(report["healthy"])
        self.assertIn("checks", report)

    def test_queue_endpoint(self) -> None:
        async def scenario():
            created = await runtime_api.create_mission(MissionAskRequest(title="Queue endpoint test"))
            return created, await runtime_api.queue_endpoint()

        created, snapshot = asyncio.run(scenario())
        ids = [i["mission_id"] for i in snapshot["items"]]
        self.assertIn(created.mission_id, ids)
        self.assertEqual(snapshot["depth_by_status"]["QUEUED"], 1)


if __name__ == "__main__":
    unittest.main()
