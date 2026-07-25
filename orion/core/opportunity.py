"""Opportunity domain entity."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Opportunity(BaseModel):
    """Represents a discovered business opportunity or market gap."""

    id: str = Field(..., description="Unique opportunity ID, e.g. 'OPP-001'")
    title: str = Field(..., description="Short descriptive title of the opportunity")
    business_value: float = Field(0.0, description="Estimated monthly revenue or leverage score (1-10)")
    risk: float = Field(0.0, description="Estimated risk score (1-10)")
    cost: float = Field(0.0, description="Estimated setup/running token cost")
    urgency: float = Field(1.0, description="Time-sensitivity factor")
    confidence: float = Field(1.0, description="Probability of execution success")

    def strategic_score(self) -> float:
        """Calculates the strategic prioritize score using the Strategic Ranking Framework.

        Score = (Value * ROI * Confidence - Risk) / (Cost * Urgency)
        """
        roi = self.business_value / max(0.01, self.cost)
        numerator = (self.business_value * roi * self.confidence) - self.risk
        denominator = max(0.01, self.cost * self.urgency)
        return round(numerator / denominator, 3)
