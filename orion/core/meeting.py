"""Meeting domain entity."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Meeting(BaseModel):
    """Represents a structured board meeting held by ORION C-Suite agents."""

    id: str = Field(..., description="Unique meeting ID, e.g. 'MEET-2026-01'")
    title: str = Field(..., description="Title of the meeting session")
    participants: list[str] = Field(default_factory=list, description="List of participating Role IDs")
    agenda: list[str] = Field(default_factory=list, description="Meeting agenda points")
    date_iso: str = Field(..., description="Date of meeting in ISO format")
    minutes: str = Field("", description="Formally recorded meeting minutes or action items")
