"""Business Knowledge: real, discrete facts about a company -- never a
document dump. "ATMAN vende cursos" is knowledge; the PDF that says so
is a Document (see documents.py), which knowledge items may cite via
``source``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from orion.business import storage


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class KnowledgeItem:
    id: str
    company_id: str
    fact: str
    category: str = "general"  # e.g. "tech_stack", "business_model", "objective", "market"
    tags: list[str] = field(default_factory=list)
    source: str = ""
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "company_id": self.company_id,
            "fact": self.fact,
            "category": self.category,
            "tags": self.tags,
            "source": self.source,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeItem":
        return cls(
            id=data["id"],
            company_id=data["company_id"],
            fact=data["fact"],
            category=data.get("category", "general"),
            tags=list(data.get("tags", [])),
            source=data.get("source", ""),
            created_at=data.get("created_at", _now_iso()),
        )


def load_knowledge(company_id: str) -> list[KnowledgeItem]:
    raw = storage.read_yaml(storage.knowledge_path(company_id), default=[])
    return [KnowledgeItem.from_dict(item) for item in raw]


def save_knowledge(company_id: str, items: list[KnowledgeItem]) -> None:
    storage.write_yaml(storage.knowledge_path(company_id), [item.to_dict() for item in items])


def add_fact(
    company_id: str, fact: str, category: str = "general", tags: list[str] | None = None, source: str = ""
) -> KnowledgeItem:
    """Real dedup by exact fact text (case-insensitive): "no volver a
    preguntarlo" also means never recording the same real fact twice.
    Returns the existing item unchanged if this exact fact is already
    known."""
    items = load_knowledge(company_id)
    normalized = fact.strip().lower()
    for existing in items:
        if existing.fact.strip().lower() == normalized:
            return existing
    item = KnowledgeItem(
        id=uuid.uuid4().hex[:12], company_id=company_id, fact=fact.strip(), category=category,
        tags=list(tags or []), source=source,
    )
    items.append(item)
    save_knowledge(company_id, items)
    return item


def list_knowledge(company_id: str, category: str | None = None) -> list[KnowledgeItem]:
    items = load_knowledge(company_id)
    if category is None:
        return items
    return [item for item in items if item.category == category]
