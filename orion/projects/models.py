"""Pydantic models for ORION's Multi-Project Engine: Project."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Project(BaseModel):
    """A company or project ORION administers.

    Loaded from ``workspace/companies/<project_id>/project.yaml``.
    """

    project_id: str = Field(..., description="Folder-safe identifier, e.g. 'atman'.")
    name: str = Field(..., description="Display name, e.g. 'ATMAN'.")
    description: str = Field(default="", description="What this project/company is.")
    repository: str = Field(default="", description="Git repository URL this project's work lives in.")
    default_branch: str = Field(default="main", description="Base branch the Execution Pipeline branches missions from.")
    # ORION ALPHA 001: optional, backward-compatible addition. Where
    # this project's repository is actually cloned in this
    # environment, so the Execution Pipeline can branch/commit/push
    # against it directly instead of always operating on Orion-AI's
    # own checkout. Empty means "no separate clone yet" — the Pipeline
    # falls back to Orion-AI's own repo_root exactly as it did before
    # this field existed.
    local_path: str = Field(default="", description="Local filesystem path to this project's own git clone, if any.")
    status: str = Field(default="active", description="Operating status, e.g. 'active', 'paused', 'planning'.")
    created_at: str
    updated_at: str
    metadata: dict[str, Any] = Field(default_factory=dict, description="Free-form extra data (e.g. related business-unit slug).")


class ProjectCreate(BaseModel):
    """Payload to register a new Project."""

    project_id: str
    name: str
    description: str = ""
    repository: str = ""
    default_branch: str = "main"
    local_path: str = ""
    status: str = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    """Payload to update an existing Project's configuration.

    Every field is optional: only the ones provided are changed.
    """

    name: str | None = None
    description: str | None = None
    repository: str | None = None
    default_branch: str | None = None
    local_path: str | None = None
    status: str | None = None
    metadata: dict[str, Any] | None = None
