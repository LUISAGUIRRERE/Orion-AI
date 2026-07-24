"""Goals: a company's real objectives -- every Mission that works
towards one is linked here, so "what did we actually move forward
this quarter" has a real, computed answer instead of a guess.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from orion.business import storage

GOAL_STATUSES = ("active", "done", "abandoned")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Goal:
    id: str
    company_id: str
    title: str
    description: str = ""
    status: str = "active"
    # Real, manually-set progress (0-100) -- never computed/fabricated
    # from unrelated signals. Missions contributing to this goal are
    # evidence of movement, not a formula for a percentage.
    progress: float = 0.0
    target_date: str = ""
    mission_ids: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "company_id": self.company_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "progress": self.progress,
            "target_date": self.target_date,
            "mission_ids": self.mission_ids,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Goal":
        return cls(
            id=data["id"],
            company_id=data["company_id"],
            title=data["title"],
            description=data.get("description", ""),
            status=data.get("status", "active"),
            progress=float(data.get("progress", 0.0)),
            target_date=data.get("target_date", ""),
            mission_ids=list(data.get("mission_ids", [])),
            created_at=data.get("created_at", _now_iso()),
            updated_at=data.get("updated_at", _now_iso()),
        )


def load_goals(company_id: str) -> list[Goal]:
    raw = storage.read_yaml(storage.goals_path(company_id), default=[])
    return [Goal.from_dict(item) for item in raw]


def save_goals(company_id: str, goals: list[Goal]) -> None:
    storage.write_yaml(storage.goals_path(company_id), [g.to_dict() for g in goals])


def add_goal(company_id: str, title: str, description: str = "", target_date: str = "") -> Goal:
    goal = Goal(id=uuid.uuid4().hex[:12], company_id=company_id, title=title, description=description, target_date=target_date)
    goals = load_goals(company_id)
    goals.append(goal)
    save_goals(company_id, goals)
    return goal


def link_mission(company_id: str, goal_id: str, mission_id: str) -> Goal | None:
    goals = load_goals(company_id)
    for goal in goals:
        if goal.id == goal_id:
            if mission_id not in goal.mission_ids:
                goal.mission_ids.append(mission_id)
            goal.updated_at = _now_iso()
            save_goals(company_id, goals)
            return goal
    return None


def list_active(company_id: str) -> list[Goal]:
    return [g for g in load_goals(company_id) if g.status == "active"]
