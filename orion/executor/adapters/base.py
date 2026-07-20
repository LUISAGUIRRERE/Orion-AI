"""The interface every Provider Adapter must implement."""

from __future__ import annotations

from orion.executor.models import ExecutionRequest, ExecutionResult


class ProviderAdapter:
    """Base interface for an Executor adapter.

    An adapter's only job: given an ExecutionRequest (which already
    carries the full PromptPackage -- the adapter's only source of
    context), produce the ExecutionArtifacts that satisfy the mission,
    wrapped in an ExecutionResult. An adapter must never:

    - run git itself (see orion.execution.git_manager);
    - discover its own context beyond what the ExecutionRequest
      already carries;
    - assume or hardcode a specific target technology stack.

    ``name`` is what callers pass to
    ``orion.executor.registry.get_adapter`` -- it must be unique
    across every registered adapter.
    """

    name: str = "base"

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        raise NotImplementedError
