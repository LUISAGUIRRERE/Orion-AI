"""Pydantic models for the Executor: ExecutionRequest, ExecutionResult,
ExecutionArtifact, ExecutionStatus.

Provider-neutral, the same way orion.prompt_composer.models is: plain
strings, lists, and simple sub-objects. Nothing here encodes any
specific AI provider's request/response shape -- an adapter for a real
provider (Claude Code, Codex CLI, Gemini CLI, Jules, ...) translates
its own request/response into these models, not the other way around.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from orion.prompt_composer.models import PromptPackage


class ExecutionStatus(str, Enum):
    """The only statuses an ExecutionResult may hold."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    # BETA 006 (Claude Code Live Invocation): a real, long-running
    # subprocess-backed adapter can genuinely be cancelled mid-flight
    # (ProviderAdapter.cancel()) -- distinct from TIMEOUT (the
    # Executor/adapter gave up waiting) and FAILED (the provider
    # itself reported an error). orion.executor.services never
    # branches exhaustively on this enum without a default path (see
    # ``if result.status != ExecutionStatus.SUCCEEDED`` in
    # run_for_mission), so adding a member here is additive and safe.
    CANCELLED = "CANCELLED"


class ExecutionArtifact(BaseModel):
    """A single file change an adapter produced.

    ``path`` is repository-relative -- the Executor writes it under
    the mission's target repo_root exactly at this path, the same
    convention orion.execution.task_runner already uses for
    artifact_path/artifact_files.

    ``change_type`` (BETA 006, additive/backward-compatible): a real
    adapter that lets a provider edit a live workspace directly (like
    ClaudeCodeAdapter) can observe files being created, modified, or
    deleted -- not just "produced". Defaults to "modified", which
    keeps every pre-existing artifact producer
    (DeterministicLocalAdapter, every test double in
    tests/test_executor.py) byte-for-byte unchanged:
    orion.executor.services.run_for_mission still just writes
    ``content`` to ``path`` unconditionally for anything that isn't
    explicitly "deleted".
    """

    path: str
    content: str = ""
    description: str = ""
    change_type: Literal["created", "modified", "deleted"] = "modified"


class ExecutionRequest(BaseModel):
    """What the Executor sends to an adapter.

    ``prompt_package`` is the *only* source of context an adapter may
    use -- the Executor never adds anything an adapter could use to
    discover more on its own. This is what makes "the Executor never
    discovers context" an enforceable property, not just a rule
    written in a docstring: an adapter that only ever receives an
    ExecutionRequest has nothing else to discover from.
    """

    mission_id: str
    adapter: str
    prompt_package: PromptPackage
    timeout_seconds: int = 120
    requested_at: str


class ExecutionResult(BaseModel):
    """What an adapter (or the Executor itself, on timeout/error)
    produced for one ExecutionRequest.

    ``stdout_excerpt``/``stderr_excerpt``/``exit_code`` (BETA 006,
    additive/backward-compatible): generic enough for any
    subprocess-backed adapter to populate, not Claude-Code-specific.
    Every pre-existing adapter (DeterministicLocalAdapter, the test
    doubles in tests/test_executor.py) simply leaves them at their
    defaults. The excerpts are deliberately bounded/truncated by
    whichever adapter populates them -- this model itself does not
    enforce a limit, so an adapter's own truncation policy (see
    orion.providers.claude_code.adapter._truncate) is what actually
    keeps ``execution_result.yaml`` and mission events bounded.
    """

    mission_id: str
    adapter: str
    status: ExecutionStatus
    artifacts: list[ExecutionArtifact] = Field(default_factory=list)
    summary: str = ""
    error: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: float | None = None
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""
    exit_code: int | None = None


class AdapterHealth(BaseModel):
    """What ProviderAdapter.health_check() reports.

    A real adapter (Claude Code, Codex CLI, ...) uses this to say
    honestly whether it is currently able to execute -- binary/SDK
    reachable, credentials present, service reachable, etc. -- rather
    than only discovering that mid-execute().
    """

    healthy: bool
    message: str = ""
    checked_at: str


class AdapterCapabilities(BaseModel):
    """What ProviderAdapter.capabilities() reports.

    Deliberately small in v1: just enough for the Executor (or a
    future scheduler) to make a basic decision, without inventing a
    speculative capability-negotiation protocol before a second real
    adapter exists to justify one.
    """

    name: str
    supports_cancel: bool = False
    max_timeout_seconds: int | None = None
    notes: str = ""
