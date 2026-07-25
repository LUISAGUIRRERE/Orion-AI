"""Goal domain entity."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class BusinessGoal(BaseModel):
    """Represents a high-level strategic business goal."""

    id: str = Field(..., description="Unique goal ID, e.g. 'GOAL-001'")
    title: str = Field(..., description="Goal title")
    status: Literal["not_started", "in_progress", "completed", "blocked"] = Field("not_started")
    progress_percentage: float = Field(0.0, description="Current progress (0.0 to 100.0)")
    parent_goal_id: str | None = Field(None, description="Optional parent goal key for hierarchy")
