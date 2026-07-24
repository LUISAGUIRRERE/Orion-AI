"""Roadmap: one company's real work items -- idea/backlog/in_progress/
done/blocked -- automatically linked to real Missions once one starts
working on them (see services.learn_from_mission).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from orion.business import storage

ROADMAP_STATUSES = ("idea", "backlog", "in_progress", "done", "blocked")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class RoadmapItem:
    id: str
    company_id: str
    title: str
    description: str = ""
    status: str = "idea"
    project_id: str | None = None  # BusinessProject.id this item belongs to, if any
    goal_id: str | None = None
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
            "project_id": self.project_id,
            "goal_id": self.goal_id,
            "mission_ids": self.mission_ids,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RoadmapItem":
        return cls(
            id=data["id"],
            company_id=data["company_id"],
            title=data["title"],
            description=data.get("description", ""),
            status=data.get("status", "idea"),
            project_id=data.get("project_id"),
            goal_id=data.get("goal_id"),
            mission_ids=list(data.get("mission_ids", [])),
            created_at=data.get("created_at", _now_iso()),
            updated_at=data.get("updated_at", _now_iso()),
        )


def load_roadmap(company_id: str) -> list[RoadmapItem]:
    raw = storage.read_yaml(storage.roadmap_path(company_id), default=[])
    return [RoadmapItem.from_dict(item) for item in raw]


def save_roadmap(company_id: str, items: list[RoadmapItem]) -> None:
    storage.write_yaml(storage.roadmap_path(company_id), [item.to_dict() for item in items])


def add_item(
    company_id: str, title: str, description: str = "", status: str = "idea",
    project_id: str | None = None, goal_id: str | None = None,
) -> RoadmapItem:
    status = status if status in ROADMAP_STATUSES else "idea"
    item = RoadmapItem(
        id=uuid.uuid4().hex[:12], company_id=company_id, title=title, description=description,
        status=status, project_id=project_id, goal_id=goal_id,
    )
    items = load_roadmap(company_id)
    items.append(item)
    save_roadmap(company_id, items)
    return item


def update_status(company_id: str, item_id: str, status: str) -> RoadmapItem | None:
    if status not in ROADMAP_STATUSES:
        raise ValueError(f"Estado de roadmap invalido: '{status}'. Debe ser uno de {ROADMAP_STATUSES}.")
    items = load_roadmap(company_id)
    for item in items:
        if item.id == item_id:
            item.status = status
            item.updated_at = _now_iso()
            save_roadmap(company_id, items)
            return item
    return None


def link_mission(company_id: str, item_id: str, mission_id: str) -> RoadmapItem | None:
    items = load_roadmap(company_id)
    for item in items:
        if item.id == item_id:
            if mission_id not in item.mission_ids:
                item.mission_ids.append(mission_id)
            item.updated_at = _now_iso()
            save_roadmap(company_id, items)
            return item
    return None


def list_by_status(company_id: str, status: str | None = None) -> list[RoadmapItem]:
    items = load_roadmap(company_id)
    if status is None:
        return items
    return [item for item in items if item.status == status]
