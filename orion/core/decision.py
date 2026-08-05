"""Decision domain entity."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, model_validator


class BusinessDecision(BaseModel):
    """Represents a formal business or architecture decision made by ORION."""

    id: str = Field(..., description="Unique decision key, e.g. 'DEC-0001'")
    title: str = Field(..., description="Decision title")
    status: Literal["proposed", "accepted", "superseded", "rejected"] = Field("proposed")
    author_role_id: str = Field(..., description="Role ID of the deciding authority")
    risk_level: str = Field("low", description="Evaluated risk level (low, medium, high, critical)")
    estimated_roi: float = Field(0.0, description="Estimated ROI score")
    rationale: str = Field(..., description="Deep architectural or strategic reasoning")
    consequences: str = Field("", description="Expected impact and trade-offs of this decision")
    superseded_by_id: str | None = Field(None, description="The Decision ID of the newer decision that supersedes this one")

    @model_validator(mode="after")
    def validate_superseded_state(self) -> BusinessDecision:
        """Enforces that a superseded decision must specify the newer Decision ID that replaces it."""
        if self.status == "superseded" and not self.superseded_by_id:
            raise ValueError("A superseded decision must specify 'superseded_by_id' pointing to the newer decision.")
        return self
