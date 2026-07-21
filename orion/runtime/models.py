"""Pydantic models for orion.runtime.

Provider/subsystem-neutral, the same way every other *.models module
in this codebase is: plain strings, lists, enums, and simple
sub-objects. Nothing here duplicates orion.bridge.models.Mission --
the Runtime never invents its own notion of a mission, it only adds a
thin scheduling layer (QueueItem) on top of the real one.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class QueueItemStatus(str, Enum):
    """The Runtime's own scheduling status for a mission.

    Deliberately separate from orion.bridge.models.MissionStatus
    (NEW/READY/RUNNING/WAITING/BLOCKED/REVIEW/DONE/FAILED), which the
    Mission Framework already owns and which
    orion.agents.builder.agent.process_next() still drives, completely
    unchanged, underneath every Worker call. QueueItemStatus only
    answers "where is this mission in the Runtime's own queue/worker
    lifecycle" -- exactly the six values this Sprint's brief lists,
    none invented beyond that.
    """

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class QueueItem(BaseModel):
    """One mission's entry in the Runtime's persistent queue ledger."""

    mission_id: str
    status: QueueItemStatus = QueueItemStatus.QUEUED
    enqueued_at: str
    started_at: str | None = None
    finished_at: str | None = None
    worker_id: str | None = None
    error: str = ""
    cancel_requested: bool = False


class WorkerStatus(BaseModel):
    """A single Worker's current, live status (in-memory, not
    persisted -- see orion.runtime.scheduler.Scheduler.worker_statuses)."""

    worker_id: str
    busy: bool = False
    current_mission_id: str | None = None
    processed_count: int = 0
    failed_count: int = 0


class RuntimeState(BaseModel):
    """The Runtime process' own operational status, persisted so
    `orion runtime start` can report/recover after a restart, and so
    GET /health and The Window can read it without an RPC into a
    possibly-different process."""

    running: bool = False
    pid: int | None = None
    started_at: str | None = None
    workers: int = 1
    provider: str = ""
    port: int = 8090


class MissionAskRequest(BaseModel):
    """What POST /missions and `orion ask` both send.

    Deliberately smaller than orion.bridge.models.MissionCreate: the
    Runtime always creates 'executor' missions (the only mission_type
    the Executor/ProviderAdapter chain understands), so mission_type
    is never a caller-supplied field here -- CEO/`orion ask` provide
    intent, not implementation.
    """

    title: str
    description: str = ""
    project_id: str = ""
    tags: list[str] = Field(default_factory=list)


class MissionAskResponse(BaseModel):
    mission_id: str
    status: str
    queue_status: QueueItemStatus


class HealthReport(BaseModel):
    """What GET /health reports -- real, per-subsystem checks, never
    a hardcoded 'ok'."""

    healthy: bool
    checks: dict[str, Any] = Field(default_factory=dict)
