"""Knowledge domain entity."""

from __future__ import annotations

from pydantic import BaseModel, Field


class KnowledgeFact(BaseModel):
    """Represents a generalized fact or learned knowledge in the corporate repository."""

    id: str = Field(..., description="Unique fact key, e.g. 'FACT-SEO-01'")
    category: str = Field(..., description="E.g. 'SEO', 'Compliance', 'Marketing'")
    fact: str = Field(..., description="The plain-text learned fact or guideline")
    confidence_score: float = Field(1.0, description="Confidence in this fact's validity (0-1)")
    source_mission_id: str | None = Field(None, description="The mission ID that generated this fact")
