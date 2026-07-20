"""Pydantic models for the Command Bridge: Mission, Message, Event."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class MissionStatus(str, Enum):
    """The only statuses a Mission may hold. No others are permitted."""

    NEW = "NEW"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    BLOCKED = "BLOCKED"
    REVIEW = "REVIEW"
    DONE = "DONE"
    FAILED = "FAILED"


class Mission(BaseModel):
    """A unit of work that travels from The Window to an agent and back,
    carrying its full history with it.
    """

    id: str = Field(..., description="Sequential identifier, e.g. 'MISSION-0001'.")
    title: str
    description: str = ""
    business_unit: str = ""
    assigned_role: str = ""
    priority: str = "normal"
    status: MissionStatus = MissionStatus.NEW
    mission_type: str = Field(
        default="documentation",
        description="Which Builder handler executes this mission: documentation, research, scaffold, or code_generation.",
    )
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None
    owner: str = ""
    tags: list[str] = Field(default_factory=list)


class MissionCreate(BaseModel):
    """Payload to create a new Mission."""

    title: str
    description: str = ""
    business_unit: str = ""
    assigned_role: str = ""
    priority: str = "normal"
    mission_type: str = "documentation"
    owner: str = ""
    tags: list[str] = Field(default_factory=list)


class MissionStatusUpdate(BaseModel):
    """Payload to change a Mission's status."""

    status: MissionStatus


class Message(BaseModel):
    """A single message in a Mission's conversation. Never deleted."""

    id: int
    mission_id: str
    sender: str
    receiver: str
    message: str
    created_at: str
    attachments: list[str] = Field(default_factory=list)


class MessageCreate(BaseModel):
    """Payload to post a new Message to a Mission."""

    sender: str
    receiver: str
    message: str
    attachments: list[str] = Field(default_factory=list)


class Event(BaseModel):
    """A single timeline event for a Mission, generated automatically."""

    id: int
    mission_id: str
    type: str
    message: str
    author: str
    timestamp: str
