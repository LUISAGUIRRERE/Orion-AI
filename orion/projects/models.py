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
    status: str | None = None
    metadata: dict[str, Any] | None = None
