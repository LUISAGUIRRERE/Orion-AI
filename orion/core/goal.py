"""Goal domain entity."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, model_validator


class BusinessGoal(BaseModel):
    """Represents a high-level strategic business goal."""

    id: str = Field(..., description="Unique goal ID, e.g. 'GOAL-001'")
    title: str = Field(..., description="Goal title")
    status: Literal["not_started", "in_progress", "completed", "blocked"] = Field("not_started")
    progress_percentage: float = Field(0.0, description="Current progress (0.0 to 100.0)")
    parent_goal_id: str | None = Field(None, description="Optional parent goal key for hierarchy")

    @model_validator(mode="after")
    def validate_status_from_progress(self) -> BusinessGoal:
        """Enforces that if progress_percentage >= 100.0, status is auto-resolved to 'completed'."""
        if self.progress_percentage >= 100.0:
            self.status = "completed"
        return self
