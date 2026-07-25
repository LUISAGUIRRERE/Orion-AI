"""Department domain entity."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Department(BaseModel):
    """Represents a corporate department (e.g. SEO, CRM, Engineering)."""

    id: str = Field(..., description="Unique department key, e.g. 'engineering'")
    name: str = Field(..., description="Display name of the department")
    purpose: str = Field(..., description="A clear statement of the department's single responsibility")
    executive_owner_id: str | None = Field(None, description="The ID of the Executive seat who owns this department")
