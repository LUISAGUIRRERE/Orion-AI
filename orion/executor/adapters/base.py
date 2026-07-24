"""The interface every Provider Adapter must implement."""

from __future__ import annotations

from datetime import datetime, timezone

from orion.executor.models import AdapterCapabilities, AdapterHealth, ExecutionResult
from orion.prompt_composer.models import PromptPackage


class ProviderAdapter:
    """Base interface for an Executor adapter.

    An adapter's only job: given a PromptPackage -- its only source of
    context, ever -- produce the ExecutionArtifacts that satisfy the
    mission, wrapped in an ExecutionResult. An adapter must never:

    - know about Mission at all (only PromptPackage);
    - run git itself (see orion.execution.git_manager);
    - discover its own context beyond what the PromptPackage already
      carries;
    - assume or hardcode a specific target technology stack;
    - embed business logic specific to any one project.

    ``name`` is what callers pass to
    ``orion.executor.registry.get_adapter`` -- it must be unique
    across every registered adapter.

    Only ``execute`` is mandatory to override. ``health_check``,
    ``cancel``, and ``capabilities`` ship with safe, honest defaults so
    an adapter that has nothing meaningful to report for them (like
    DeterministicLocalAdapter) never has to fake an answer:

    - the default ``health_check`` reports healthy=True, since a local
      test-double adapter genuinely has nothing that can be
      unhealthy;
    - the default ``cancel`` reports False, since nothing is ever
      actually in flight to cancel unless an adapter says otherwise;
    - the default ``capabilities`` reports supports_cancel=False and
      no timeout ceiling.

    A real adapter (Claude Code, and in the future Codex CLI, Gemini
    CLI, ...) is expected to override every one of these with a real,
    honest answer -- see orion.providers.claude_code.adapter for the
    reference implementation.
    """

    name: str = "base"

    def execute(self, package: PromptPackage) -> ExecutionResult:
        raise NotImplementedError

    def health_check(self) -> AdapterHealth:
        return AdapterHealth(
            healthy=True,
            message=f"Adaptador '{self.name}' no define health_check() propio; asumido saludable por defecto.",
            checked_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )

    def cancel(self, mission_id: str) -> bool:
        return False

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            name=self.name,
            supports_cancel=False,
            max_timeout_seconds=None,
            notes=f"Adaptador '{self.name}' no define capabilities() propio; valores por defecto.",
        )
