"""Public entry points for orion.runtime's API/CLI layer.

This is the only module orion.runtime.api and bin/orion are allowed to
call directly -- the same "one entry point per subsystem" convention
orion.executor.services and orion.experience.services already
establish. Nothing here duplicates business logic that already lives
elsewhere: it only wires together orion.bridge, orion.executor's
registry, and this package's own queue/scheduler/storage.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from orion.bridge import services as bridge_services
from orion.bridge.models import Mission, MissionCreate, MissionStatus
from orion.executor.registry import get_adapter
from orion.runtime import events as runtime_events
from orion.runtime import queue as runtime_queue
from orion.runtime import storage as runtime_storage
from orion.runtime.config import RuntimeConfig
from orion.runtime.models import HealthReport, MissionAskRequest, MissionAskResponse, QueueItem, RuntimeState
from orion.runtime.scheduler import Scheduler

AUTHOR = "Runtime"

_scheduler: Scheduler | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def start_runtime(config: RuntimeConfig | None = None) -> RuntimeState:
    """Idempotent: calling this twice in the same process leaves the
    existing Scheduler running rather than starting a second pool."""
    global _scheduler
    config = config or RuntimeConfig.from_env()
    if _scheduler is None:
        _scheduler = Scheduler(worker_count=config.workers, poll_interval_seconds=config.poll_interval_seconds)
    _scheduler.start()

    state = RuntimeState(
        running=True,
        pid=os.getpid(),
        started_at=_now_iso(),
        workers=config.workers,
        provider=config.provider,
        port=config.port,
    )
    runtime_storage.save_state(state)
    return state


def stop_runtime() -> RuntimeState:
    global _scheduler
    if _scheduler is not None:
        _scheduler.stop()
    state = runtime_storage.load_state()
    state.running = False
    runtime_storage.save_state(state)
    return state


def get_runtime_state() -> RuntimeState:
    return runtime_storage.load_state()


def get_scheduler() -> Scheduler | None:
    """Exposed mainly for tests and GET /health -- orion.runtime.api
    never manipulates the Scheduler directly, it only reads its
    status through here."""
    return _scheduler


def ask(request: MissionAskRequest) -> MissionAskResponse:
    """Mission -> Prompt Composer -> Executor -> Provider -> ...:
    creates a real Mission (mission_type='executor', the only type the
    Executor/ProviderAdapter chain understands), marks it READY, and
    enqueues it on the Runtime's own queue ledger. ask() itself never
    runs the mission synchronously -- a running Worker (started
    separately via `orion runtime start`) picks it up on its next
    poll, exactly like a real queue.
    """
    mission = bridge_services.create_mission(
        MissionCreate(
            title=request.title,
            description=request.description or request.title,
            mission_type="executor",
            project_id=request.project_id,
            tags=request.tags,
        ),
        author=AUTHOR,
    )
    # Fixed in BETA 007: bridge_services.update_status() returns the
    # *updated* Mission rather than mutating the one already held in
    # ``mission`` -- discarding its return value left this function
    # reporting the pre-update status ("NEW") in MissionAskResponse
    # even though the mission was already READY in storage (every
    # other reader, e.g. GET /missions/{id}, was always correct, since
    # it re-fetches fresh -- only this function's own return value was
    # stale). See tests/test_runtime.py::AskAndCancelTests::
    # test_ask_creates_a_ready_mission_and_enqueues_it.
    updated_mission = bridge_services.update_status(mission.id, MissionStatus.READY, author=AUTHOR)
    assert updated_mission is not None
    item = runtime_queue.enqueue(mission.id)
    runtime_events.emit(mission.id, "mission_enqueued", "Mision encolada en el Runtime.", AUTHOR)
    return MissionAskResponse(mission_id=mission.id, status=updated_mission.status.value, queue_status=item.status)


def get_mission(mission_id: str) -> Mission | None:
    return bridge_services.get_mission(mission_id)


def list_missions() -> list[Mission]:
    return bridge_services.list_missions()


def queue_item(mission_id: str) -> QueueItem | None:
    return runtime_queue.get_item(mission_id)


def queue_snapshot() -> list[QueueItem]:
    return runtime_queue.list_items()


def queue_depth() -> dict[str, int]:
    return runtime_queue.depth_by_status()


def cancel_mission(mission_id: str) -> bool:
    """Real cancellation, in two parts:

    1. Mark intent on the Runtime queue, so a Worker that has not
       claimed this mission yet skips it instead of running it (see
       orion.runtime.worker.Worker.run_once).
    2. Reach into the live ClaudeCodeAdapter singleton registered in
       orion.executor.registry and call its real .cancel(mission_id)
       -- the exact mechanism BETA 006 built (os.killpg on the real
       subprocess), not a new one. If this exact mission_id is
       mid-execution in some Worker's thread right now, this actually
       kills the running Claude Code process.

    Returns True if either action had any effect (an entry existed to
    mark, or a live process was actually signalled).
    """
    item = runtime_queue.request_cancel(mission_id)
    runtime_events.emit(mission_id, "mission_cancel_requested", "Cancelacion solicitada.", AUTHOR)

    process_cancelled = False
    try:
        adapter = _resolve_provider_adapter(RuntimeConfig.from_env().provider)
        process_cancelled = adapter.cancel(mission_id)
    except KeyError:
        pass

    if process_cancelled:
        runtime_events.emit(
            mission_id, "provider_cancel_sent", "Señal de cancelacion enviada al proceso real.", AUTHOR
        )

    return item is not None or process_cancelled


def _resolve_provider_adapter(name: str):
    """Same convention orion.executor.services._get_adapter_with_discovery
    already established: if ``name`` is not registered yet, try
    importing orion.providers.<name> (expected to self-register as an
    import-time side effect, like every provider package does) before
    giving up. Duplicated here (a few lines of orchestration, not
    business logic) rather than importing that module's private
    helper directly across a package boundary.
    """
    # orion.executor.services imports orion.executor.adapters as a
    # module-level side effect, which registers every built-in
    # adapter (deterministic_local). That import is normally triggered
    # lazily, deep inside orion.execution.task_runner.execute(), only
    # once a mission actually runs -- too late for a health check
    # taken right after startup, before any mission ever has. Ensure
    # it here first, unconditionally and cheaply (Python caches
    # imports), before falling back to the orion.providers.<name>
    # convention for real, external providers.
    import orion.executor.services  # noqa: F401

    try:
        return get_adapter(name)
    except KeyError:
        pass
    import importlib

    try:
        importlib.import_module(f"orion.providers.{name}")
    except ImportError as exc:
        raise KeyError(f"Adaptador '{name}' no registrado y orion.providers.{name} no existe.") from exc
    return get_adapter(name)


def health_report() -> HealthReport:
    """GET /health -- real, per-subsystem checks, never a hardcoded
    'ok'. Covers exactly the six things this Sprint's spec lists:
    Claude Code, Git, Workspace, Queue, Workers, Storage."""
    checks: dict[str, object] = {}

    provider_name = RuntimeConfig.from_env().provider
    try:
        adapter = _resolve_provider_adapter(provider_name)
        health = adapter.health_check()
        checks[provider_name] = {"healthy": health.healthy, "message": health.message}
    except KeyError as exc:
        checks[provider_name] = {"healthy": False, "message": str(exc)}

    from orion.execution import git_manager

    try:
        branch = git_manager.current_branch()
        checks["git"] = {"healthy": True, "branch": branch}
    except Exception as exc:  # noqa: BLE001 - health check must never raise
        checks["git"] = {"healthy": False, "message": str(exc)}

    from orion.bridge import storage as bridge_storage

    checks["workspace"] = {
        "healthy": bridge_storage.WORKSPACE_DIR.exists(),
        "path": str(bridge_storage.WORKSPACE_DIR),
    }

    checks["queue"] = {"healthy": True, "depth": queue_depth()}

    scheduler = get_scheduler()
    worker_statuses = scheduler.worker_statuses() if scheduler else []
    checks["workers"] = {
        "healthy": True,
        "count": len(worker_statuses),
        "busy": sum(1 for w in worker_statuses if w.busy),
    }

    try:
        runtime_storage.ensure_runtime_storage()
        checks["storage"] = {"healthy": True, "path": str(runtime_storage.RUNTIME_DIR)}
    except OSError as exc:
        checks["storage"] = {"healthy": False, "message": str(exc)}

    overall_healthy = all(bool(c.get("healthy")) for c in checks.values() if isinstance(c, dict))
    return HealthReport(healthy=overall_healthy, checks=checks)
