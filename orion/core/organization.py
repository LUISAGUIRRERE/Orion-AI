"""Organization domain entity."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class Organization(BaseModel):
    """Represents a business organization or company portfolio administered by ORION."""

    id: str = Field(..., description="Unique folder-safe organization identifier, e.g. 'atman'")
    name: str = Field(..., description="Legal or display name of the company")
    industry: str = Field(..., description="Primary vertical of operations, e.g. 'B2B SaaS'")
    vision: str = Field("", description="The company's long-term aspirational goal")
    website: str | None = Field(None, description="Official company URL")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary custom organizational metadata")
