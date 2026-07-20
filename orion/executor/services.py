"""Public entry point for the Executor.

orion.execution.task_runner is the only caller: for a mission of type
'executor', it delegates entirely to ``run_for_mission`` instead of
the legacy handler registry (orion.agents.builder.registry). This is
the whole integration -- no other module needs to know the Executor
exists.
"""

from __future__ import annotations

import concurrent.futures
import importlib
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from orion.bridge import services as bridge_services
from orion.bridge.models import Mission
from orion.executor import adapters as _adapters  # noqa: F401 -- import registers built-in adapters
from orion.executor import storage
from orion.executor.models import ExecutionRequest, ExecutionResult, ExecutionStatus
from orion.executor.registry import get_adapter
from orion.prompt_composer import storage as prompt_storage

if TYPE_CHECKING:
    from orion.executor.adapters.base import ProviderAdapter

AUTHOR = "Executor"
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_ADAPTER = "deterministic_local"

# Cambiar unicamente esta variable de entorno (sin tocar ningun otro
# modulo) es el criterio de exito literal de BETA "Claude Code
# Provider Adapter": ORION_PROVIDER=claude_code hace que toda mision
# sin tag adapter:<nombre> explicito use el nuevo adaptador real.
ORION_PROVIDER_ENV_VAR = "ORION_PROVIDER"


class ExecutorError(RuntimeError):
    """Raised when a mission's execution could not be completed.

    orion.execution.task_runner lets this propagate exactly like a
    GitManagerError already does -- orion.execution.pipeline's
    existing try/except around task_runner.execute() turns it into a
    normal FAILED mission, with no special-casing needed there.
    """


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _default_adapter_name() -> str:
    """The adapter used when a mission has no explicit adapter:<name>
    tag. Configurable via ORION_PROVIDER so switching the whole
    system's default provider never requires touching this module's
    code -- only its configuration."""
    return os.environ.get(ORION_PROVIDER_ENV_VAR, DEFAULT_ADAPTER)


def _resolve_adapter_name(mission: Mission) -> str:
    """Which adapter to use for this mission.

    v1 convention: a tag of the form ``adapter:<name>`` on the mission
    picks the adapter explicitly; absent that, ``_default_adapter_name()``
    decides (deterministic_local unless ORION_PROVIDER says otherwise).
    """
    for tag in mission.tags:
        if tag.startswith("adapter:"):
            return tag.removeprefix("adapter:")
    return _default_adapter_name()


def _get_adapter_with_discovery(name: str) -> "ProviderAdapter":
    """Resolve an adapter by name, falling back to dynamic plugin
    discovery before giving up.

    orion.executor never imports a specific provider package by name
    (that would recreate the exact coupling this Sprint exists to
    remove). Instead: if ``name`` isn't registered yet, it attempts
    ``importlib.import_module(f"orion.providers.{name}")`` -- by
    convention, importing that package is expected to register the
    adapter as a side effect, exactly like
    orion.executor.adapters.deterministic already does for the
    built-in adapter. If that package doesn't exist, or it exists but
    never registers an adapter under ``name``, this raises
    ExecutorError -- an unknown adapter is always a hard failure,
    never a silent no-op.
    """
    try:
        return get_adapter(name)
    except KeyError:
        pass

    try:
        importlib.import_module(f"orion.providers.{name}")
    except ImportError as exc:
        raise ExecutorError(
            f"No hay ningun adaptador registrado con el nombre '{name}', y "
            f"orion.providers.{name} tampoco existe como paquete de descubrimiento "
            "dinamico (ni build-in ni provider real)."
        ) from exc

    try:
        return get_adapter(name)
    except KeyError as exc:
        raise ExecutorError(
            f"orion.providers.{name} se importo correctamente pero nunca registro "
            f"ningun adaptador llamado '{name}' -- revisa su __init__.py."
        ) from exc


def run_for_mission(mission: Mission, repo_root: Path) -> tuple[list[str], str]:
    """Execute a mission through the Executor and write its artifacts
    into ``repo_root``. Returns (repository-relative file paths
    written, summary). Raises ExecutorError on any failure or timeout.
    """
    package = prompt_storage.load(mission.id)
    if package is None:
        raise ExecutorError(
            f"No hay un PromptPackage persistido para {mission.id}. El Executor nunca descubre "
            "contexto por si mismo: depende de que orion.prompt_composer ya haya compuesto uno "
            "antes de que el Builder llegue a esta mision."
        )

    adapter_name = _resolve_adapter_name(mission)
    adapter = _get_adapter_with_discovery(adapter_name)
    bridge_services.record_event(
        mission.id,
        "provider_selected",
        f"Proveedor/adaptador seleccionado: '{adapter_name}'.",
        AUTHOR,
    )

    request = ExecutionRequest(
        mission_id=mission.id,
        adapter=adapter_name,
        prompt_package=package,
        timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
        requested_at=_now_iso(),
    )
    storage.save_request(mission.id, request)
    bridge_services.record_event(
        mission.id,
        "execution_requested",
        f"Solicitud de ejecucion creada para el adaptador '{adapter_name}'.",
        AUTHOR,
    )

    bridge_services.record_event(
        mission.id, "execution_started", f"Adaptador '{adapter_name}' iniciado.", AUTHOR
    )
    bridge_services.record_event(
        mission.id, "provider_started", f"Proveedor '{adapter_name}' iniciado.", AUTHOR
    )
    started_monotonic = time.monotonic()

    result = _run_with_timeout(adapter, request, started_monotonic)
    storage.save_result(mission.id, result)

    if result.status != ExecutionStatus.SUCCEEDED:
        failure_message = result.error or f"El adaptador termino con estado {result.status.value}."
        bridge_services.record_event(mission.id, "execution_failed", failure_message, AUTHOR)
        bridge_services.record_event(
            mission.id,
            "provider_failed",
            f"Proveedor '{adapter_name}' fallo: {failure_message}",
            AUTHOR,
        )
        raise ExecutorError(
            result.error or f"El adaptador '{adapter_name}' termino con estado {result.status.value}."
        )

    bridge_services.record_event(
        mission.id,
        "execution_completed",
        f"Adaptador '{adapter_name}' genero {len(result.artifacts)} artifact(s).",
        AUTHOR,
    )
    bridge_services.record_event(
        mission.id,
        "provider_finished",
        f"Proveedor '{adapter_name}' finalizo correctamente.",
        AUTHOR,
    )

    written: list[str] = []
    for artifact in result.artifacts:
        target = repo_root / artifact.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(artifact.content, encoding="utf-8")
        written.append(artifact.path)

    return written, result.summary


def _run_with_timeout(
    adapter: object, request: ExecutionRequest, started_monotonic: float
) -> ExecutionResult:
    """Call ``adapter.execute(request.prompt_package)`` bounded by
    ``request.timeout_seconds``, always returning a structured
    ExecutionResult -- never letting an adapter's exception or a
    timeout escape as a raw exception.

    Note the single contract change of this Sprint: the adapter
    receives ``request.prompt_package`` directly, never the
    ExecutionRequest wrapper -- an adapter must never know about
    Mission, timeouts, or adapter-selection metadata, only the
    PromptPackage itself. ExecutionRequest still exists and is still
    persisted (it's the Executor's own record of what was asked), it
    is simply no longer what an adapter's execute() receives.

    Runs the adapter in a single worker thread so a genuinely hung
    adapter (e.g. a future subprocess-based one that never returns)
    cannot block the Builder forever; ``future.result(timeout=...)``
    raises TimeoutError from the calling thread even if the worker
    thread itself is still stuck.
    """
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(adapter.execute, request.prompt_package)  # type: ignore[attr-defined]
            return future.result(timeout=request.timeout_seconds)
    except concurrent.futures.TimeoutError:
        return ExecutionResult(
            mission_id=request.mission_id,
            adapter=request.adapter,
            status=ExecutionStatus.TIMEOUT,
            error=f"El adaptador '{request.adapter}' no respondio dentro de {request.timeout_seconds}s.",
            started_at=request.requested_at,
            finished_at=_now_iso(),
            duration_seconds=round(time.monotonic() - started_monotonic, 3),
        )
    except Exception as exc:  # noqa: BLE001 - any adapter failure must be captured structurally, never crash the Builder
        return ExecutionResult(
            mission_id=request.mission_id,
            adapter=request.adapter,
            status=ExecutionStatus.FAILED,
            error=f"{type(exc).__name__}: {exc}",
            started_at=request.requested_at,
            finished_at=_now_iso(),
            duration_seconds=round(time.monotonic() - started_monotonic, 3),
        )
