"""Derives a Mission's real per-stage progress against a decided
BoardPipeline, purely from that Mission's own already-recorded event
history (orion.bridge.services.get_events). Never a second execution
path, never a guess: a stage is "completed" only when one of its real
event_signatures (see orion.board.member_registry) actually appears on
the Mission's timeline, exactly the way BETA 008/009/010 already
derive every other "did X really happen" answer this codebase gives.
"""

from __future__ import annotations

from dataclasses import dataclass

from orion.bridge import services as bridge_services
from orion.board import member_registry
from orion.board.board_engine import BoardPipeline


@dataclass(frozen=True)
class StageProgress:
    key: str
    display_name: str
    board_seat: str | None
    status: str  # "pending" | "completed"
    matched_events: tuple[str, ...]


def compute_progress(mission_id: str, pipeline: BoardPipeline) -> list[StageProgress]:
    events = bridge_services.get_events(mission_id)
    event_types = {e.type for e in events}

    progress: list[StageProgress] = []
    for key in pipeline.stages:
        member = member_registry.get_member(key)
        matched = tuple(sig for sig in member.event_signatures if sig in event_types)
        status = "completed" if matched else "pending"
        progress.append(
            StageProgress(
                key=key,
                display_name=member.display_name,
                board_seat=member.board_seat,
                status=status,
                matched_events=matched,
            )
        )
    return progress


def next_stage(mission_id: str, pipeline: BoardPipeline) -> str | None:
    """The first stage in pipeline order that has not completed yet,
    or None once every stage has."""
    for stage in compute_progress(mission_id, pipeline):
        if stage.status == "pending":
            return stage.key
    return None


def is_pipeline_complete(mission_id: str, pipeline: BoardPipeline) -> bool:
    return next_stage(mission_id, pipeline) is None
