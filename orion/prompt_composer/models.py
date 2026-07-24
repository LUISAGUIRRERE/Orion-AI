"""Pydantic models for the Prompt Composer's output: PromptPackage.

Every field here is deliberately provider-neutral: plain strings,
lists, and simple sub-objects. Nothing in this module encodes a
prompt format, a message-role structure, or any other convention that
belongs to a specific AI provider or CLI tool. Translating a
PromptPackage into something like a Claude Code system prompt, a
Codex CLI task file, or a Gemini CLI context bundle is explicitly the
job of a future, separate adapter -- not this module.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from orion.bridge.models import Mission
from orion.projects.models import Project


class MissionSummary(BaseModel):
    """The parts of a Mission relevant to building its context -- not
    the full Mission object, so a PromptPackage never accidentally
    carries Bridge-internal bookkeeping (timestamps, owner, etc.) that
    an execution adapter has no use for.
    """

    id: str
    title: str
    description: str
    mission_type: str
    priority: str
    status: str
    tags: list[str] = Field(default_factory=list)

    @classmethod
    def from_mission(cls, mission: Mission) -> "MissionSummary":
        return cls(
            id=mission.id,
            title=mission.title,
            description=mission.description,
            mission_type=mission.mission_type,
            priority=mission.priority,
            status=mission.status.value,
            tags=list(mission.tags),
        )


class ProjectSummary(BaseModel):
    """The parts of a Project relevant to building context. ``None`` at
    the PromptPackage level means the mission has no project_id --
    this is normal (e.g. Orion-AI's own kernel work), not an error.
    """

    project_id: str
    name: str
    description: str
    repository: str
    default_branch: str

    @classmethod
    def from_project(cls, project: Project) -> "ProjectSummary":
        return cls(
            project_id=project.project_id,
            name=project.name,
            description=project.description,
            repository=project.repository,
            default_branch=project.default_branch,
        )


class BusinessContext(BaseModel):
    """Who this is for and why -- the project's own identity, never
    inferred from the mission itself."""

    project_name: str
    project_description: str = ""
    business_unit: str = ""


class TechnicalContext(BaseModel):
    """Summaries of whatever technical documentation the target
    repository already has. Every field is an excerpt of a real,
    discovered file (see discovery.py) -- never invented."""

    architecture_summary: str = ""
    design_system_summary: str = ""
    design_tokens_summary: str = ""
    content_guide_summary: str = ""
    project_status: dict[str, Any] = Field(default_factory=dict)


class FileReference(BaseModel):
    """A single file the Composer found relevant, and why."""

    path: str
    reason: str


class CodingStandards(BaseModel):
    """Where an implementation's style/conventions rules come from,
    plus any notes the Composer itself needs to add (e.g. "none
    found")."""

    sources: list[FileReference] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ArchitectureRules(BaseModel):
    """Where an implementation's structural constraints come from."""

    sources: list[FileReference] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class RelatedMissionReference(BaseModel):
    """Another mission the Composer judged relevant, and why (shared
    project, shared tags, ...)."""

    mission_id: str
    title: str
    status: str
    relation: str


class CommitReference(BaseModel):
    """One recent commit on the target repository."""

    hash: str
    author: str
    date: str
    message: str


class PullRequestReference(BaseModel):
    """A related, in-flight branch, inferred locally.

    ``status`` is always qualified as inferred rather than confirmed:
    ORION has no GitHub API access in this environment (see
    orion.execution.git_manager.pull_request_url), so this can only
    ever be a best-effort read of local remote-tracking branches, not
    a real query against GitHub's Pull Request state.
    """

    branch: str
    url: str
    status: str


class SuggestedPlan(BaseModel):
    """A neutral, ordered list of steps. Deliberately simple in v1 --
    template-based, not the product of any model call (Prompt Composer
    itself never calls an AI provider; see the package docstring)."""

    steps: list[str] = Field(default_factory=list)


class ExecutionPrompt(BaseModel):
    """The final, neutral instructions block plus general constraints.

    This is the text a future provider-specific adapter (Claude Code,
    Codex CLI, Gemini CLI, Jules, ...) translates into its own format
    -- system prompt, task file, whatever that provider expects. It
    intentionally contains no provider-specific structure itself.
    """

    instructions: str
    constraints: list[str] = Field(default_factory=list)


class PromptPackage(BaseModel):
    """Everything an implementation needs to execute a Mission,
    structured as a single, provider-neutral object.

    This is the Prompt Composer's only output and the contract the
    rest of ORION (today: the Builder Agent, for logging/evidence;
    tomorrow: a real Executor) depends on.
    """

    mission: MissionSummary
    project: ProjectSummary | None = None
    business_context: BusinessContext
    technical_context: TechnicalContext
    coding_standards: CodingStandards
    architecture_rules: ArchitectureRules
    related_files: list[FileReference] = Field(default_factory=list)
    related_missions: list[RelatedMissionReference] = Field(default_factory=list)
    recent_commits: list[CommitReference] = Field(default_factory=list)
    related_pull_requests: list[PullRequestReference] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    suggested_plan: SuggestedPlan
    execution_prompt: ExecutionPrompt
    generated_at: str
