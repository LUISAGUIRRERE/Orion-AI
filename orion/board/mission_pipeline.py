"""Persists, per Mission, the BoardPipeline orion.board.board_engine
already decided for it -- so `orion board progress`/the Window/the API
can read back *what was actually decided* days later, instead of
re-deciding it (which could silently drift if request text or
category data changes upstream). Same file-per-mission pattern
orion.bridge.storage already uses for Missions themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from orion.board import storage
from orion.board.board_engine import BoardPipeline, MissionKind
from orion.governance.change_classifier import ChangeCategory


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class BoardMissionState:
    mission_id: str
    kind: str
    category: str | None
    stages: tuple[str, ...]
    rule: str
    decided_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "mission_id": self.mission_id,
            "kind": self.kind,
            "category": self.category,
            "stages": list(self.stages),
            "rule": self.rule,
            "decided_at": self.decided_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BoardMissionState":
        return cls(
            mission_id=data["mission_id"],
            kind=data["kind"],
            category=data.get("category"),
            stages=tuple(data.get("stages", [])),
            rule=data.get("rule", ""),
            decided_at=data.get("decided_at", _now_iso()),
        )

    def as_pipeline(self) -> BoardPipeline:
        category = ChangeCategory(self.category) if self.category else None
        return BoardPipeline(kind=MissionKind(self.kind), category=category, stages=self.stages, rule=self.rule)


def save_state(mission_id: str, pipeline: BoardPipeline) -> BoardMissionState:
    state = BoardMissionState(
        mission_id=mission_id,
        kind=pipeline.kind.value,
        category=pipeline.category.value if pipeline.category is not None else None,
        stages=pipeline.stages,
        rule=pipeline.rule,
    )
    storage.write_yaml(storage.mission_state_path(mission_id), state.to_dict())
    return state


def load_state(mission_id: str) -> BoardMissionState | None:
    data = storage.read_yaml(storage.mission_state_path(mission_id), None)
    if data is None:
        return None
    return BoardMissionState.from_dict(data)


def list_states() -> list[BoardMissionState]:
    missions_dir = storage.missions_dir()
    if not missions_dir.exists():
        return []
    states = []
    for path in sorted(missions_dir.glob("*.yaml")):
        data = storage.read_yaml(path, None)
        if data is not None:
            states.append(BoardMissionState.from_dict(data))
    return states
