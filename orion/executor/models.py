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

from pydantic import BaseModel, Field

from orion.prompt_composer.models import PromptPackage


class ExecutionStatus(str, Enum):
    """The only statuses an ExecutionResult may hold."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


class ExecutionArtifact(BaseModel):
    """A single file an adapter produced.

    ``path`` is repository-relative -- the Executor writes it under
    the mission's target repo_root exactly at this path, the same
    convention orion.execution.task_runner already uses for
    artifact_path/artifact_files.
    """

    path: str
    content: str
    description: str = ""


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
    produced for one ExecutionRequest."""

    mission_id: str
    adapter: str
    status: ExecutionStatus
    artifacts: list[ExecutionArtifact] = Field(default_factory=list)
    summary: str = ""
    error: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: float | None = None
