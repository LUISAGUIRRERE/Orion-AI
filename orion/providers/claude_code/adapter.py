"""ClaudeCodeAdapter -- the first real (non-deterministic-test)
Provider Adapter for the Executor.

Implements the full ProviderAdapter contract: health_check(),
execute(PromptPackage), cancel(), capabilities(). It knows nothing
about Mission -- only PromptPackage, exactly like every adapter must
per orion.executor.adapters.base. It never runs git itself
(orion.execution.git_manager owns that exclusively), never decides
architecture, never discovers its own context, and never hardcodes a
target stack or embeds business logic specific to any one project --
it only ever forwards PromptPackage.execution_prompt to Claude Code
and collects whatever files come back.

Honest limitation of this Sprint (documented here, not hidden):
this sandboxed environment has no real Claude Code SDK/CLI reachable,
and no credentials are being connected regardless -- both explicitly
out of scope per this Sprint's brief. Every method below is fully
implemented and exercised end-to-end by
tests/test_claude_code_adapter.py EXCEPT the single point where a
real subprocess/SDK call would happen -- ``_invoke()`` -- which raises
ClaudeCodeNotAvailableError with a message explaining exactly what is
missing and what a real implementation looks like. execute() catches
that exception and returns a normal, structured
ExecutionResult(status=FAILED, error=...): it never crashes the
Executor, never pretends to succeed, and never fabricates a fake
successful response.
"""

from __future__ import annotations

import shutil
import tempfile
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ClaudeCodeNotAvailableError(RuntimeError):
    """Raised by _invoke() -- the one deliberately unimplemented
    boundary of this Sprint. See module docstring and _invoke()'s own
    docstring for exactly what is missing and why."""


class ClaudeCodeAdapter:
    """See module docstring. Registered under 'claude_code'."""

    name = "claude_code"

    def __init__(self, config: ClaudeCodeConfig | None = None) -> None:
        self._config = config or ClaudeCodeConfig.from_env()

    def health_check(self) -> AdapterHealth:
        """Honestly reports whether execute() can currently do real
        work.

        Checks whether the configured CLI binary is even reachable on
        PATH -- but even when it is, this Sprint's execute() still
        cannot use it (see _invoke()), so this always reports
        healthy=False, with a message that distinguishes 'binary not
        found on PATH' from 'binary found, but this adapter cannot
        call it yet'. Reporting healthy=True here would be a lie: a
        caller trusting it would expect execute() to be able to
        succeed, and it cannot.
        """
        binary = shutil.which(self._config.cli_path)
        if binary is None:
            return AdapterHealth(
                healthy=False,
                message=(
                    f"El binario '{self._config.cli_path}' no se encontro en PATH "
                    "(configurable via ORION_CLAUDE_CODE_CLI)."
                ),
                checked_at=_now_iso(),
            )
        return AdapterHealth(
            healthy=False,
            message=(
                f"El binario '{self._config.cli_path}' existe en PATH ({binary}), pero este "
                "adaptador todavia no invoca al SDK/CLI real -- ver ClaudeCodeAdapter._invoke() "
                "y docs/CLAUDE_CODE_ADAPTER.md. healthy=False es la respuesta honesta: execute() "
                "fallara de forma controlada, no simulara exito."
            ),
            checked_at=_now_iso(),
        )

    def execute(self, package: PromptPackage) -> ExecutionResult:
        """Create a temporary workspace, hand the PromptPackage to
        Claude Code, wait for completion, collect modified files,
        return an ExecutionResult -- exactly the flow the Sprint
        specifies. Everything up to and including the call boundary is
        real; only the call itself (_invoke) is not implemented in
        this environment.
        """
        started_at = _now_iso()
        workspace = Path(tempfile.mkdtemp(prefix="orion-claude-code-"))
        try:
            self._write_package(package, workspace)
            try:
                modified_paths = self._invoke(package, workspace)
            except ClaudeCodeNotAvailableError as exc:
                return ExecutionResult(
                    mission_id=package.mission.id,
                    adapter=self.name,
                    status=ExecutionStatus.FAILED,
                    error=str(exc),
                    started_at=started_at,
                    finished_at=_now_iso(),
                    duration_seconds=0.0,
                )
            artifacts = self._collect_modified_files(workspace, modified_paths)
            return ExecutionResult(
                mission_id=package.mission.id,
                adapter=self.name,
                status=ExecutionStatus.SUCCEEDED,
                artifacts=artifacts,
                summary=f"Claude Code genero {len(artifacts)} archivo(s).",
                started_at=started_at,
                finished_at=_now_iso(),
                duration_seconds=0.0,
            )
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    def _write_package(self, package: PromptPackage, workspace: Path) -> None:
        """Persist the PromptPackage into the temporary workspace so a
        real _invoke() implementation has something concrete on disk
        to hand to a CLI-based provider (most CLI tools expect a
        working directory, not an in-memory Python object). Real,
        working code -- exercised directly by
        tests/test_claude_code_adapter.py, not a stub."""
        (workspace / "prompt_package.json").write_text(
            package.model_dump_json(indent=2), encoding="utf-8"
        )

    def _invoke(self, package: PromptPackage, workspace: Path) -> list[str]:
        """THE deliberately unimplemented boundary of this Sprint.

        A real implementation would look approximately like:

            result = subprocess.run(
                [
                    self._config.cli_path,
                    "--print", package.execution_prompt.instructions,
                    "--cwd", str(workspace),
                    "--output-format", "json",
                ],
                capture_output=True,
                text=True,
                timeout=self._config.timeout_seconds,
            )
            if result.returncode != 0:
                raise ClaudeCodeNotAvailableError(result.stderr)
            return _parse_modified_files_from(result.stdout)

        This sandbox has no real Claude Code SDK/CLI reachable, and no
        credentials are connected regardless -- explicitly out of
        scope for this Sprint ("No conectar todavia claves
        privadas"). Every other part of this adapter -- workspace
        lifecycle, PromptPackage hand-off, structured error capture,
        file collection -- is real and already exercised by
        tests/test_claude_code_adapter.py. Only this one call is
        missing.
        """
        raise ClaudeCodeNotAvailableError(
            "ClaudeCodeAdapter._invoke() no esta implementado en este entorno: no hay SDK/CLI de "
            "Claude Code disponible ni credenciales conectadas (fuera de alcance de este Sprint). "
            "Toda la logica alrededor de este punto (workspace temporal, entrega del "
            "PromptPackage, captura estructurada de errores, recoleccion de archivos) es real y "
            "esta probada. Ver docs/CLAUDE_CODE_ADAPTER.md para el detalle exacto de este limite."
        )

    @staticmethod
    def _collect_modified_files(workspace: Path, relative_paths: list[str]) -> list[ExecutionArtifact]:
        """Real, working logic for turning a list of repo-relative
        paths a real _invoke() would report as modified into
        ExecutionArtifacts. Unreachable in this Sprint (_invoke()
        always raises before returning any paths) but ready and
        tested for when _invoke() becomes real -- see
        tests/test_claude_code_adapter.py, which calls this method
        directly."""
        artifacts: list[ExecutionArtifact] = []
        for rel_path in relative_paths:
            target = workspace / rel_path
            if not target.is_file():
                continue
            artifacts.append(
                ExecutionArtifact(
                    path=rel_path,
                    content=target.read_text(encoding="utf-8"),
                    description="Generado por Claude Code.",
                )
            )
        return artifacts

    def cancel(self, mission_id: str) -> bool:
        """Nothing is ever actually in flight to cancel in v1 --
        execute() runs synchronously end to end and _invoke() never
        even starts a real subprocess yet. Honest False, never a fake
        True."""
        return False

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            name=self.name,
            supports_cancel=False,
            max_timeout_seconds=self._config.timeout_seconds,
            notes=(
                "Adaptador real para Claude Code. health_check() y execute() estan completos "
                "excepto por la llamada final al SDK/CLI real (ClaudeCodeAdapter._invoke()), "
                "deliberadamente no implementada en este Sprint: sin SDK/CLI disponible en este "
                "entorno y sin credenciales conectadas todavia. Ver docs/CLAUDE_CODE_ADAPTER.md."
            ),
        )


register_adapter(ClaudeCodeAdapter())
