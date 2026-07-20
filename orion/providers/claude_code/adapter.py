"""ClaudeCodeAdapter -- the first real Provider Adapter with a real,
live subprocess invocation (BETA 006: Claude Code Live Invocation).

Implements the full ProviderAdapter contract: health_check(),
execute(PromptPackage), cancel(), capabilities(). It knows nothing
about Mission -- only PromptPackage, exactly like every adapter must
per orion.executor.adapters.base. It never runs git itself
(orion.execution.git_manager owns that exclusively), never decides
architecture, never discovers its own context, and never hardcodes a
target stack or embeds business logic specific to any one project.

Architecture (matches the Sprint brief exactly):

    Executor -> ClaudeCodeAdapter -> subprocess seguro -> Claude Code
    CLI -> workspace aislado -> archivos modificados -> ExecutionResult

Every flag used below (``-p``, ``--output-format json``,
``--permission-mode``, ``--model``, ``auth status --json``) was
verified against the real CLI installed in this environment
(``claude --version`` -> 2.1.209) by running ``claude --help`` and
probing real (unauthenticated) invocations. See
docs/CLAUDE_CODE_ADAPTER.md for the full inspection record, including
the two things this Sprint explicitly asked for and could not be
invented: a native ``--timeout`` flag (doesn't exist -- enforced here
instead, in Python) and a native turn-limit flag (doesn't exist in
this CLI version -- ORION_CLAUDE_CODE_MAX_TURNS is accepted and
stored, never silently dropped, but never translated into a flag that
isn't real).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from orion.executor.models import (
    AdapterCapabilities,
    AdapterHealth,
    ExecutionArtifact,
    ExecutionResult,
    ExecutionStatus,
)
from orion.executor.registry import register_adapter
from orion.prompt_composer.models import PromptPackage
from orion.providers.claude_code.config import ClaudeCodeConfig

# Hard ceilings on what ORION ever stores/persists from a subprocess'
# output -- "Límite máximo de salida" from the Sprint's security
# requirements. MAX_CAPTURE_CHARS bounds what the drain threads retain
# in memory per stream while the process runs (they keep reading past
# this cap so the child never blocks on a full pipe, they just stop
# *keeping* what they read). MAX_EXCERPT_CHARS bounds what actually
# ends up in ExecutionResult (and therefore in execution_result.yaml
# and mission events) -- deliberately much smaller, since that's what
# gets persisted and displayed.
MAX_CAPTURE_CHARS = 200_000
MAX_EXCERPT_CHARS = 4_000

# Paths never treated as adapter output, even if present inside the
# isolated workspace -- our own scratch metadata (prompt_package.json,
# written by _write_package before the baseline snapshot is taken, so
# it's excluded from the diff automatically) plus any tool-internal
# state a real CLI invocation might create in its working directory.
_EXCLUDED_PATH_PARTS = {".git", ".claude"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return text[:limit] + f"\n... (truncado, {omitted} caracteres omitidos)"


def _drain_stream(stream, cap: int, sink: dict, key: str) -> None:
    """Continuously read ``stream`` in a background thread so the
    child process never blocks on a full pipe buffer, while retaining
    at most ``cap`` characters. Runs until EOF or the stream errors."""
    kept: list[str] = []
    kept_len = 0
    total = 0
    try:
        while True:
            chunk = stream.read(4096)
            if not chunk:
                break
            total += len(chunk)
            if kept_len < cap:
                room = cap - kept_len
                kept.append(chunk[:room])
                kept_len += min(len(chunk), room)
    except (ValueError, OSError):
        pass
    finally:
        try:
            stream.close()
        except OSError:
            pass
    sink[key] = "".join(kept)
    sink[f"{key}_total_chars"] = total


@dataclass
class _SubprocessOutcome:
    stdout: str
    stderr: str
    returncode: int | None
    timed_out: bool


class ClaudeCodeNotAvailableError(RuntimeError):
    """Raised only for the narrow race condition where the binary
    disappears between health_check() (which execute() always calls
    first) and the actual subprocess launch. execute() catches this
    and returns a normal, structured FAILED ExecutionResult -- it
    never propagates raw."""


class ClaudeCodeAdapter:
    """See module docstring. Registered under 'claude_code'."""

    name = "claude_code"

    def __init__(self, config: ClaudeCodeConfig | None = None) -> None:
        self._config = config or ClaudeCodeConfig.from_env()
        self._lock = threading.Lock()
        # mission_id -> the live subprocess.Popen currently running
        # for it, only while it's actually running. This is the real
        # "Registrar PID mientras esté activo" requirement -- cancel()
        # looks a mission up here.
        self._active_processes: dict[str, subprocess.Popen] = {}
        # mission_ids that cancel() was called for, so execute() can
        # tell "the process died because the CLI genuinely finished"
        # apart from "the process died because we killed it".
        self._cancel_requested: set[str] = set()

    # ------------------------------------------------------------------
    # health_check
    # ------------------------------------------------------------------

    def health_check(self) -> AdapterHealth:
        """Real, honest health check: is the binary on PATH, and is it
        authenticated? Both checks are read-only and side-effect-free
        (``claude auth status --json`` reads local auth state, it does
        not call the API)."""
        binary = shutil.which(self._config.cli_path)
        if binary is None:
            return AdapterHealth(
                healthy=False,
                message=(
                    f"El binario '{self._config.cli_path}' no se encontro en PATH "
                    "(configurable via ORION_CLAUDE_CODE_BIN)."
                ),
                checked_at=_now_iso(),
            )

        try:
            probe = subprocess.run(
                [self._config.cli_path, "auth", "status", "--json"],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return AdapterHealth(
                healthy=False,
                message=(
                    f"El binario '{self._config.cli_path}' existe en PATH ({binary}), pero "
                    f"'{self._config.cli_path} auth status --json' fallo: {type(exc).__name__}: {exc}."
                ),
                checked_at=_now_iso(),
            )

        try:
            status = json.loads(probe.stdout)
        except (json.JSONDecodeError, TypeError):
            return AdapterHealth(
                healthy=False,
                message=(
                    f"El binario '{self._config.cli_path}' existe en PATH ({binary}), pero "
                    "'auth status --json' no devolvio JSON valido -- no se puede confirmar "
                    "si esta autenticado."
                ),
                checked_at=_now_iso(),
            )

        logged_in = bool(status.get("loggedIn"))
        auth_method = status.get("authMethod", "unknown")
        if not logged_in:
            return AdapterHealth(
                healthy=False,
                message=(
                    f"El binario '{self._config.cli_path}' existe en PATH ({binary}) y responde "
                    f"correctamente, pero no hay sesion activa (authMethod={auth_method!r}). "
                    "Requiere 'claude auth login' interactivo o ANTHROPIC_API_KEY -- ninguno de "
                    "los dos esta disponible en este entorno. execute() fallara de forma "
                    "controlada sin intentar la llamada real."
                ),
                checked_at=_now_iso(),
            )

        return AdapterHealth(
            healthy=True,
            message=f"Binario '{self._config.cli_path}' ({binary}) autenticado via {auth_method!r}.",
            checked_at=_now_iso(),
        )

    # ------------------------------------------------------------------
    # execute
    # ------------------------------------------------------------------

    def execute(self, package: PromptPackage) -> ExecutionResult:
        started_at = _now_iso()
        started_monotonic = time.monotonic()
        mission_id = package.mission.id

        # Step 1 of the Sprint's own list: "Ejecutar health_check()."
        # Never even attempt the subprocess if we already know it will
        # fail -- a clean, immediate, documented FAILED result instead
        # of a doomed subprocess launch.
        health = self.health_check()
        if not health.healthy:
            return ExecutionResult(
                mission_id=mission_id,
                adapter=self.name,
                status=ExecutionStatus.FAILED,
                error=f"health_check() fallo, no se intento invocar Claude Code: {health.message}",
                started_at=started_at,
                finished_at=_now_iso(),
                duration_seconds=round(time.monotonic() - started_monotonic, 3),
            )

        workspace = Path(tempfile.mkdtemp(prefix="orion-claude-code-"))
        try:
            # Step 2: PromptPackage -> neutral text input, plus our
            # own provenance file (excluded from the diff below since
            # baseline is snapshotted right after writing it).
            self._write_package(package, workspace)
            baseline = self._snapshot(workspace)
            prompt_text = self._build_prompt_text(package)
            args = self._build_args()

            # Steps 3-4: launch in the isolated workspace, wait for
            # completion/timeout/cancellation.
            try:
                outcome = self._invoke(args, workspace, prompt_text, mission_id)
            except ClaudeCodeNotAvailableError as exc:
                return ExecutionResult(
                    mission_id=mission_id,
                    adapter=self.name,
                    status=ExecutionStatus.FAILED,
                    error=str(exc),
                    started_at=started_at,
                    finished_at=_now_iso(),
                    duration_seconds=round(time.monotonic() - started_monotonic, 3),
                )

            with self._lock:
                was_cancelled = mission_id in self._cancel_requested
                self._cancel_requested.discard(mission_id)

            stdout_excerpt = _truncate(outcome.stdout, MAX_EXCERPT_CHARS)
            stderr_excerpt = _truncate(outcome.stderr, MAX_EXCERPT_CHARS)
            duration = round(time.monotonic() - started_monotonic, 3)

            if was_cancelled:
                return ExecutionResult(
                    mission_id=mission_id,
                    adapter=self.name,
                    status=ExecutionStatus.CANCELLED,
                    error="Ejecucion cancelada via ClaudeCodeAdapter.cancel().",
                    stdout_excerpt=stdout_excerpt,
                    stderr_excerpt=stderr_excerpt,
                    exit_code=outcome.returncode,
                    started_at=started_at,
                    finished_at=_now_iso(),
                    duration_seconds=duration,
                )

            if outcome.timed_out:
                return ExecutionResult(
                    mission_id=mission_id,
                    adapter=self.name,
                    status=ExecutionStatus.TIMEOUT,
                    error=(
                        f"Claude Code no respondio dentro de {self._config.timeout_seconds}s "
                        "(ORION_CLAUDE_CODE_TIMEOUT)."
                    ),
                    stdout_excerpt=stdout_excerpt,
                    stderr_excerpt=stderr_excerpt,
                    exit_code=outcome.returncode,
                    started_at=started_at,
                    finished_at=_now_iso(),
                    duration_seconds=duration,
                )

            parsed = self._parse_json_result(outcome.stdout)
            provider_failed = (
                parsed is None or bool(parsed.get("is_error")) or (outcome.returncode != 0)
            )

            if provider_failed:
                if parsed is not None:
                    error_detail = str(
                        parsed.get("result") or parsed.get("subtype") or "Claude Code reporto un error."
                    )
                else:
                    error_detail = "No se pudo interpretar la salida de Claude Code como JSON."
                return ExecutionResult(
                    mission_id=mission_id,
                    adapter=self.name,
                    status=ExecutionStatus.FAILED,
                    error=f"{error_detail} (exit_code={outcome.returncode})",
                    stdout_excerpt=stdout_excerpt,
                    stderr_excerpt=stderr_excerpt,
                    exit_code=outcome.returncode,
                    started_at=started_at,
                    finished_at=_now_iso(),
                    duration_seconds=duration,
                )

            # Steps 5-6: real file diff against the isolated workspace,
            # ExecutionArtifact per change.
            after = self._snapshot(workspace)
            created, modified, deleted = self._diff(baseline, after)
            artifacts = self._build_artifacts(workspace, created, modified, deleted)

            summary_parts = [
                f"Claude Code genero {len(artifacts)} cambio(s) "
                f"({len(created)} creado(s), {len(modified)} modificado(s), "
                f"{len(deleted)} eliminado(s))."
            ]
            if parsed.get("result"):
                summary_parts.append(str(parsed["result"]))
            if parsed.get("num_turns") is not None:
                summary_parts.append(f"{parsed['num_turns']} turno(s).")
            if self._config.max_turns is not None:
                summary_parts.append(
                    "(ORION_CLAUDE_CODE_MAX_TURNS configurado pero esta version de la CLI no "
                    "expone un flag equivalente; ignorado -- ver docs/CLAUDE_CODE_ADAPTER.md.)"
                )

            # Step 7: ExecutionResult con status, provider (adapter),
            # duration, stdout/stderr resumido, exit code, artifacts.
            return ExecutionResult(
                mission_id=mission_id,
                adapter=self.name,
                status=ExecutionStatus.SUCCEEDED,
                artifacts=artifacts,
                summary=" ".join(summary_parts),
                stdout_excerpt=stdout_excerpt,
                stderr_excerpt=stderr_excerpt,
                exit_code=outcome.returncode,
                started_at=started_at,
                finished_at=_now_iso(),
                duration_seconds=duration,
            )
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    # ------------------------------------------------------------------
    # execute() helpers
    # ------------------------------------------------------------------

    def _write_package(self, package: PromptPackage, workspace: Path) -> None:
        """Persist the PromptPackage into the temporary workspace as
        provenance. Written before the baseline snapshot, so it's
        never mistaken for a Claude-Code-produced change."""
        (workspace / "prompt_package.json").write_text(
            package.model_dump_json(indent=2), encoding="utf-8"
        )

    def _build_prompt_text(self, package: PromptPackage) -> str:
        """The one and only translation step from the neutral
        PromptPackage into what Claude Code actually accepts: plain
        text on stdin. No roles, no XML tags, no provider-specific
        structure -- exactly the same neutral instructions
        orion.prompt_composer already composed."""
        lines = [package.execution_prompt.instructions.strip()]
        if package.execution_prompt.constraints:
            lines.append("")
            lines.append("Restricciones:")
            lines.extend(f"- {c}" for c in package.execution_prompt.constraints)
        return "\n".join(lines) + "\n"

    def _build_args(self) -> list[str]:
        """Every flag here is real and was verified against the
        installed CLI (see module docstring). ``--permission-mode
        acceptEdits`` is a deliberate security choice: it auto-accepts
        file-edit actions (what a workspace-scoped coding mission
        needs) without granting blanket bypass
        (``--dangerously-skip-permissions``/``bypassPermissions``),
        which the CLI's own help text reserves for "sandboxes with no
        internet access" -- not the guarantee ORION wants to rely on
        for a real, network-connected provider call."""
        args = [
            self._config.cli_path,
            "-p",
            "--output-format",
            "json",
            "--permission-mode",
            "acceptEdits",
        ]
        if self._config.model:
            args += ["--model", self._config.model]
        return args

    def _parse_json_result(self, stdout: str) -> dict | None:
        try:
            parsed = json.loads(stdout)
        except (json.JSONDecodeError, TypeError):
            return None
        return parsed if isinstance(parsed, dict) else None

    def _snapshot(self, workspace: Path) -> dict[str, str]:
        """path (relative, posix-style) -> sha256 of its content, for
        every real file under ``workspace``, excluding our own
        scratch/tooling paths (see _EXCLUDED_PATH_PARTS)."""
        snapshot: dict[str, str] = {}
        for path in workspace.rglob("*"):
            if not path.is_file():
                continue
            rel_parts = path.relative_to(workspace).parts
            if any(part in _EXCLUDED_PATH_PARTS for part in rel_parts):
                continue
            rel_path = path.relative_to(workspace).as_posix()
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                continue
            snapshot[rel_path] = digest
        return snapshot

    def _diff(
        self, before: dict[str, str], after: dict[str, str]
    ) -> tuple[list[str], list[str], list[str]]:
        created = sorted(p for p in after if p not in before)
        deleted = sorted(p for p in before if p not in after)
        modified = sorted(p for p in after if p in before and after[p] != before[p])
        return created, modified, deleted

    def _build_artifacts(
        self, workspace: Path, created: list[str], modified: list[str], deleted: list[str]
    ) -> list[ExecutionArtifact]:
        artifacts: list[ExecutionArtifact] = []
        for rel_path in created + modified:
            target = workspace / rel_path
            try:
                content = target.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                content = f"<no se pudo leer el archivo como UTF-8: {type(exc).__name__}: {exc}>"
            change_type = "created" if rel_path in created else "modified"
            artifacts.append(
                ExecutionArtifact(
                    path=rel_path,
                    content=content,
                    description=f"Archivo {change_type} por Claude Code.",
                    change_type=change_type,
                )
            )
        for rel_path in deleted:
            artifacts.append(
                ExecutionArtifact(
                    path=rel_path,
                    content="",
                    description="Archivo eliminado por Claude Code.",
                    change_type="deleted",
                )
            )
        return artifacts

    # ------------------------------------------------------------------
    # subprocess -- the real, live invocation
    # ------------------------------------------------------------------

    def _invoke(
        self, args: list[str], cwd: Path, prompt_text: str, mission_id: str
    ) -> _SubprocessOutcome:
        """Launch Claude Code as a real subprocess and wait for it.

        Security requirements from the Sprint, all real here (not
        aspirational): the subprocess is launched via Popen with an
        explicit argument list -- never a shell-interpreted string;
        explicit timeout enforced by ORION itself (the CLI has none); stdout/stderr captured continuously by dedicated
        threads so the child never deadlocks on a full pipe, with a
        hard retention cap (MAX_CAPTURE_CHARS); the PID is registered
        in self._active_processes for the exact duration the process
        is alive, so cancel() can find and kill it; ``cwd=workspace``
        is the only directory this call ever touches -- no --add-dir
        is ever passed, so Claude Code's own file tools have no
        ORION-granted reason to look outside it.
        """
        try:
            process = subprocess.Popen(
                args,
                cwd=str(cwd),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise ClaudeCodeNotAvailableError(
                f"El binario '{args[0]}' no se pudo ejecutar: {exc}. Esto no deberia ocurrir "
                "si health_check() ya confirmo el binario -- indica una condicion de carrera "
                "(el binario desaparecio entre health_check() e _invoke())."
            ) from exc

        with self._lock:
            self._active_processes[mission_id] = process

        capture: dict[str, object] = {}
        t_out = threading.Thread(
            target=_drain_stream, args=(process.stdout, MAX_CAPTURE_CHARS, capture, "stdout"), daemon=True
        )
        t_err = threading.Thread(
            target=_drain_stream, args=(process.stderr, MAX_CAPTURE_CHARS, capture, "stderr"), daemon=True
        )
        t_out.start()
        t_err.start()

        try:
            process.stdin.write(prompt_text)
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass

        timed_out = False
        try:
            returncode = process.wait(timeout=self._config.timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._kill_process_group(process)
            try:
                returncode = process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                returncode = None
        finally:
            with self._lock:
                self._active_processes.pop(mission_id, None)

        t_out.join(timeout=10)
        t_err.join(timeout=10)

        return _SubprocessOutcome(
            stdout=str(capture.get("stdout", "")),
            stderr=str(capture.get("stderr", "")),
            returncode=returncode,
            timed_out=timed_out,
        )

    def _kill_process_group(self, process: subprocess.Popen) -> None:
        """SIGTERM the whole process group first (real cancellation,
        including any child processes Claude Code itself spawned --
        start_new_session=True in _invoke is what makes this a
        distinct, killable group), escalating to SIGKILL only if it
        doesn't exit within 5s."""
        try:
            pgid = os.getpgid(process.pid)
        except ProcessLookupError:
            return
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    # ------------------------------------------------------------------
    # cancel / capabilities
    # ------------------------------------------------------------------

    def cancel(self, mission_id: str) -> bool:
        """Real cancellation: if ``mission_id`` has a live subprocess
        tracked, terminate its whole process group and report True.
        Otherwise, honestly False -- nothing to cancel."""
        with self._lock:
            process = self._active_processes.get(mission_id)
            if process is None:
                return False
            self._cancel_requested.add(mission_id)
        self._kill_process_group(process)
        return True

    def capabilities(self) -> AdapterCapabilities:
        notes = (
            "Adaptador real para Claude Code con invocacion en vivo (BETA 006). "
            "health_check() y execute() estan completos, incluida la llamada real al CLI "
            "instalado. Requiere 'claude auth login' interactivo o ANTHROPIC_API_KEY -- "
            "ninguno disponible en este entorno sandbox, por lo que health_check() reportara "
            "healthy=False y execute() fallara de forma controlada hasta que el entorno de "
            "despliegue real provea una sesion autenticada. ORION_CLAUDE_CODE_MAX_TURNS se "
            "acepta pero esta version de la CLI (2.1.209) no expone un flag equivalente."
        )
        return AdapterCapabilities(
            name=self.name,
            supports_cancel=True,
            max_timeout_seconds=self._config.timeout_seconds,
            notes=notes,
        )


register_adapter(ClaudeCodeAdapter())
