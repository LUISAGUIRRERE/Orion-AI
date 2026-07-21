"""Public entry point for orion.board -- the only module other Sprints
(orion.agents.builder.agent, bin/orion, orion.window.routes) should
ever import from directly. Mirrors orion.governance.services' own
single-entry-point shape.
"""

from __future__ import annotations

from dataclasses import dataclass

from orion.board import member_registry, mission_pipeline
from orion.board.board_engine import BoardPipeline, MissionKind, decide_pipeline
from orion.board.board_router import StageProgress, compute_progress
from orion.board.member_registry import BoardMember
from orion.bridge import services as bridge_services
from orion.governance.change_classifier import ChangeCategory

AUTHOR = "BoardOrchestrator"


@dataclass(frozen=True)
class BoardDecision:
    mission_id: str
    pipeline: BoardPipeline

    def summary_text(self) -> str:
        return self.pipeline.summary_text()


def decide_and_record(
    mission_id: str,
    request_text: str,
    category: ChangeCategory | None = None,
) -> BoardDecision | None:
    """Decides the pipeline for one Mission, persists it, and records
    one real "board_pipeline_decided" event on that Mission's own
    timeline. Wrapped in try/except by design (same as every other
    BETA 009/010 hook orion.agents.builder.agent already runs): a
    Board decision must never crash or block a Mission whose actual
    work has not started yet. Returns None -- disclosed, never a fake
    success -- if the decision could not be made or persisted; the
    caller (the Runtime hook) records a real "board_failed" event in
    that case instead of pretending a pipeline exists."""
    try:
        pipeline = decide_pipeline(request_text, category=category)
        mission_pipeline.save_state(mission_id, pipeline)
        bridge_services.record_event(mission_id, "board_pipeline_decided", pipeline.summary_text(), AUTHOR)
        return BoardDecision(mission_id=mission_id, pipeline=pipeline)
    except Exception:  # noqa: BLE001 - deciding must never crash the caller
        return None


def get_decision(mission_id: str) -> BoardDecision | None:
    state = mission_pipeline.load_state(mission_id)
    if state is None:
        return None
    return BoardDecision(mission_id=mission_id, pipeline=state.as_pipeline())


def get_progress(mission_id: str) -> list[StageProgress] | None:
    decision = get_decision(mission_id)
    if decision is None:
        return None
    return compute_progress(mission_id, decision.pipeline)


def describe_members() -> list[BoardMember]:
    return member_registry.list_members()


def list_decisions() -> list[BoardDecision]:
    return [
        BoardDecision(mission_id=state.mission_id, pipeline=state.as_pipeline())
        for state in mission_pipeline.list_states()
    ]
