"""Pydantic models for The Window.

These models define the shape of a Business Unit, an Event, and the
aggregated Dashboard summary served by the API and rendered by the
templates.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BusinessUnit(BaseModel):
    """A single business unit tracked by ORION OS.

    Loaded from ``workspace/business/<slug>/business.yaml``.
    """

    slug: str = Field(..., description="Folder-safe identifier, e.g. 'atman'.")
    name: str = Field(..., description="Display name, e.g. 'ATMAN'.")
    status: str = Field(..., description="Current operating status, e.g. 'active', 'paused', 'planning'.")
    health: str = Field(..., description="Health signal used for the status color: 'green', 'yellow', or 'red'.")
    objective: str = Field(default="", description="Current top-level objective for this business unit.")
    missions: list[str] = Field(default_factory=list, description="Active missions for this business unit.")
    business: dict[str, Any] = Field(default_factory=dict, description="Free-form business metrics (stage, revenue status, etc.).")
    events: list[str] = Field(default_factory=list, description="Business-unit-local event notes, distinct from the global Event Service log.")
    decisions: list[str] = Field(default_factory=list, description="Decisions pending from the CEO for this business unit.")
    opportunities: list[str] = Field(default_factory=list, description="Identified opportunities for this business unit.")

    @property
    def next_decision(self) -> str | None:
        """Return the next pending decision, if any."""
        return self.decisions[0] if self.decisions else None


class BusinessUnitCard(BaseModel):
    """Condensed view of a Business Unit for the dashboard cards."""

    slug: str
    name: str
    status: str
    health: str
    active_missions: int
    next_decision: str | None


class Event(BaseModel):
    """A single event recorded by the Event Service."""

    id: int | None = Field(default=None, description="Row id, assigned by SQLite.")
    fecha: str = Field(..., description="ISO 8601 timestamp of the event.")
    tipo: str = Field(..., description="Event type/category, e.g. 'decision', 'alert', 'update'.")
    business_unit: str = Field(..., description="Slug of the related business unit, or 'orion' for system-wide events.")
    mensaje: str = Field(..., description="Human-readable event message.")
    autor: str = Field(..., description="Who or what raised the event.")


class DashboardSummary(BaseModel):
    """Aggregated payload for the main dashboard view."""

    business_unit_count: int
    event_count: int
    business_units: list[BusinessUnitCard]
    recent_events: list[Event]
