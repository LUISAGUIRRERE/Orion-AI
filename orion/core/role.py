"""Role and Person domain entity."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class ProfessionalRole(BaseModel):
    """Represents an executive seat, agent, or professional role within ORION Core."""

    id: str = Field(..., description="Unique role identifier, e.g. 'cmo'")
    title: str = Field(..., description="Corporate title, e.g. 'Chief Marketing Officer'")
    status: Literal["active", "inactive", "proposed"] = Field("active", description="Role seat status")
    responsibilities: list[str] = Field(default_factory=list, description="Explicit responsibilities assigned to this role")
    restrictions: list[str] = Field(default_factory=list, description="Explicit restrictions or boundaries of authority")
    department_id: str | None = Field(None, description="Department this role is associated with or owns")
