"""The deterministic local adapter -- a test double, not a real
provider.

Exists solely to validate the Executor's full contract end to end:
ExecutionRequest in, ExecutionResult out, real files written, real
validation, real commit/push/PR. It never calls any external API,
never reads a credential or secret, and never claims to be a real AI
provider's response -- every artifact and every summary it produces
says explicitly, in plain text, that it came from this deterministic
test adapter. Given the same ExecutionRequest, it always returns the
exact same ExecutionResult (module datetime calls aside): no
randomness, no network, no hidden state.
"""

from __future__ import annotations

from datetime import datetime, timezone

from orion.executor.models import ExecutionArtifact, ExecutionRequest, ExecutionResult, ExecutionStatus
from orion.executor.registry import register_adapter


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DeterministicLocalAdapter:
    """See module docstring. Registered under 'deterministic_local'."""

    name = "deterministic_local"

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        started_at = _now_iso()
        package = request.prompt_package

        lines = [
            "# Execution log (adaptador deterministico de prueba)",
            "",
            f"Mision: {package.mission.id} -- {package.mission.title}",
            f"Adaptador: {self.name}",
            "",
            "**Este archivo NO fue generado por un proveedor de IA real.** "
            "El adaptador deterministico existe unicamente para validar el "
            "contrato completo del Executor (ExecutionRequest -> "
            "ExecutionResult -> archivos -> validacion -> commit -> push -> "
            "PR), nunca para simular una respuesta real.",
            "",
            "## Instrucciones recibidas (PromptPackage.execution_prompt)",
            "",
            package.execution_prompt.instructions,
            "",
            "## Restricciones recibidas",
            "",
        ]
        lines.extend(f"- {c}" for c in package.execution_prompt.constraints)
        lines.append("")
        content = "\n".join(lines) + "\n"

        artifact = ExecutionArtifact(
            path=f"execution-log/{package.mission.id}.md",
            content=content,
            description=(
                "Registro deterministico generado por el adaptador de prueba; "
                "confirma que el ExecutionRequest llego completo y que el "
                "contrato del Executor funciona de punta a punta."
            ),
        )

        return ExecutionResult(
            mission_id=package.mission.id,
            adapter=self.name,
            status=ExecutionStatus.SUCCEEDED,
            artifacts=[artifact],
            summary=(
                f"Adaptador deterministico '{self.name}' ejecutado correctamente "
                "(prueba de contrato, no trabajo de producto real)."
            ),
            started_at=started_at,
            finished_at=_now_iso(),
            duration_seconds=0.0,
        )


register_adapter(DeterministicLocalAdapter())
