"""Business Memory domain entity."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class MemoryLedger(BaseModel):
    """Represents the long-term transactional business memory ledger for a portfolio organization."""

    organization_id: str = Field(..., description="The ID of the organization this ledger belongs to")
    competitor_profiles: dict[str, Any] = Field(default_factory=dict, description="Competitor intelligence store")
    brand_guidelines_path: str | None = Field(None, description="Path to active brand voice and styles")
    successful_campaigns: list[str] = Field(default_factory=list, description="IDs of historically successful campaigns")
    failed_campaigns: list[str] = Field(default_factory=list, description="IDs of historically failed campaigns")
    business_rules: list[str] = Field(default_factory=list, description="Explicit rules guiding operations")
