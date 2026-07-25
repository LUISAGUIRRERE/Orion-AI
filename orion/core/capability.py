"""Capability domain entity."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Capability(BaseModel):
    """Represents a specialized black-box business Capability exposed by a Department."""

    id: str = Field(..., description="Unique capability key, e.g. 'technical_seo_audit'")
    goal: str = Field(..., description="The objective or mission this capability solves")
    department_id: str = Field(..., description="The owning Department's identifier")
    required_inputs: list[str] = Field(default_factory=list, description="Inputs required to invoke this capability")
    expected_outputs: list[str] = Field(default_factory=list, description="Outputs produced upon success")
    estimated_cost_dollars: float = Field(0.0, description="Approximate execution cost in API tokens/hosting")
    estimated_duration_seconds: int = Field(0, description="Approximate execution duration in seconds")
